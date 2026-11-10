#!/usr/bin/env python3
"""Kalibreert het verwachtingsmodel op data/dagen.csv + data/weer.json + data/prijzen.json.
Alleen standaardbibliotheek. Schrijft data/model.json en data/backtest.json.

Model (per dag):
  afname    = c0 + c1 * gemiddelde temperatuur            (robuust, uitbijters = auto laden eruit)
  terug     = max(0, d0 + d1 * zonnestraling + d2 * afname)
  kosten    = k_p * afname * p_dag - k_e * terug * p_zon - k_c * afname
              p_dag = gemiddelde all-in prijs van de dag, p_zon = met zonnestraling gewogen all-in prijs
"""
import csv, json, math, os, sys, datetime as dt

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DATA = os.path.join(ROOT, "data")
EXCLUDE = {"2026-11-10"}   # onvolledige dag ("vandaag tot nu") bij het invoeren


def solve(A, b):
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(M[r][i]))
        M[i], M[p] = M[p], M[i]
        if abs(M[i][i]) < 1e-12:
            raise ValueError("singulier stelsel")
        for r in range(n):
            if r != i:
                fct = M[r][i] / M[i][i]
                M[r] = [x - fct * y for x, y in zip(M[r], M[i])]
    return [M[i][n] / M[i][i] for i in range(n)]


def ols(X, y):
    k = len(X[0])
    A = [[sum(r[i] * r[j] for r in X) for j in range(k)] for i in range(k)]
    b = [sum(r[i] * yy for r, yy in zip(X, y)) for i in range(k)]
    return solve(A, b)


def dot(c, x):
    return sum(a * b for a, b in zip(c, x))


def median(v):
    s = sorted(v); n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def trimmed(X, y, k=2.5, floor=3.0):
    """OLS waarbij dagen met een te HOGE waarde (auto laden) herhaaldelijk worden weggelaten."""
    idx = list(range(len(y)))
    for _ in range(20):
        c = ols([X[i] for i in idx], [y[i] for i in idx])
        res = [y[i] - dot(c, X[i]) for i in range(len(y))]
        r_in = [res[i] for i in idx]
        m = median(r_in)
        s = 1.4826 * median([abs(r - m) for r in r_in])
        new = [i for i in range(len(y)) if res[i] <= max(k * s, floor)]
        if new == idx:
            break
        idx = new
    return c, idx


def load():
    prices = {h["t"]: h for h in json.load(open(os.path.join(DATA, "prijzen.json")))["hours"]}
    wx = {h["t"]: h for h in json.load(open(os.path.join(DATA, "weer.json")))["hourly"]}
    days = []
    for r in csv.DictReader(open(os.path.join(DATA, "dagen.csv"))):
        d = r["datum"]
        if d in EXCLUDE:
            continue
        hs = ["%sT%02d:00" % (d, h) for h in range(24)]
        if not all(h in prices and h in wx and wx[h]["temp"] is not None for h in hs):
            continue
        p = [prices[h]["all_in"] for h in hs]
        rad = [wx[h]["radiation"] or 0 for h in hs]
        days.append({
            "d": d, "a": float(r["afname_kwh"]), "e": float(r["teruglevering_kwh"]),
            "hw": float(r["hw_eur"]), "f": float(r["frank_eur"]) if r["frank_eur"] else None,
            "T": sum(wx[h]["temp"] for h in hs) / 24, "S": sum(rad) / 1000.0,
            "pd": sum(p) / 24, "pz": sum(a * b for a, b in zip(p, rad)) / sum(rad) if sum(rad) > 0 else sum(p) / 24})
    return days


def fit_all(days):
    """Fit alle drie de deelmodellen op de gegeven dagen. Geeft parameters + uitbijters."""
    X = [[1.0, x["T"]] for x in days]
    c_a, idx = trimmed(X, [x["a"] for x in days])
    outl = [days[i]["d"] for i in range(len(days)) if i not in idx]
    inl = [days[i] for i in idx]
    # teruglevering: op alle dagen (de auto beïnvloedt de teruglevering nauwelijks)
    c_e = ols([[x["S"], x["a"], 1.0] for x in days], [x["e"] for x in days])
    d_e = {"d0": c_e[2], "d1": c_e[0], "d2": c_e[1]}
    # kosten: alleen dagen met een echt Frank-bedrag
    fd = [x for x in days if x["f"] is not None]
    c_f = ols([[x["a"] * x["pd"], -x["e"] * x["pz"], -x["a"]] for x in fd], [x["f"] for x in fd])
    return {"afname": {"c0": c_a[0], "c1": c_a[1]}, "terug": d_e,
            "kosten": {"k_p": c_f[0], "k_e": c_f[1], "k_c": c_f[2]}}, outl, idx


def predict(m, T, S, pd, pz):
    a = max(0.0, m["afname"]["c0"] + m["afname"]["c1"] * T)
    e = max(0.0, m["terug"]["d0"] + m["terug"]["d1"] * S + m["terug"]["d2"] * a)
    k = m["kosten"]
    return a, e, k["k_p"] * a * pd - k["k_e"] * e * pz - k["k_c"] * a


def stats(errs):
    if not errs:
        return {"n": 0}
    return {"n": len(errs), "mae": sum(abs(x) for x in errs) / len(errs),
            "rmse": math.sqrt(sum(x * x for x in errs) / len(errs)), "max_abs": max(abs(x) for x in errs)}


def main():
    days = load()
    model, outl, _ = fit_all(days)
    # leave-one-out backtest van de hele keten (verbruik voorspeld, kosten uit voorspeld verbruik)
    rows, e_cost, e_cost_inl, e_a, e_e = [], [], [], [], []
    for i, x in enumerate(days):
        if x["f"] is None:
            continue
        m, _, _ = fit_all(days[:i] + days[i + 1:])
        a, e, c = predict(m, x["T"], x["S"], x["pd"], x["pz"])
        # kosten met werkelijk verbruik, om kostenmodel en verbruiksmodel te scheiden
        _, _, c_true = (x["a"], x["e"], m["kosten"]["k_p"] * x["a"] * x["pd"] - m["kosten"]["k_e"] * x["e"] * x["pz"] - m["kosten"]["k_c"] * x["a"])
        car = x["d"] in outl
        rows.append({"d": x["d"], "frank": x["f"], "voorspeld": round(c, 2), "fout": round(c - x["f"], 2),
                     "voorspeld_met_werkelijk_verbruik": round(c_true, 2), "afname_werkelijk": x["a"], "afname_voorspeld": round(a, 1),
                     "terug_werkelijk": x["e"], "terug_voorspeld": round(e, 1), "uitbijter_afname": car})
        e_cost.append(c - x["f"]); e_a.append(a - x["a"]); e_e.append(e - x["e"])
        if not car:
            e_cost_inl.append(c - x["f"])
    e_true = [r["voorspeld_met_werkelijk_verbruik"] - r["frank"] for r in rows]
    bt = {"methode": "leave-one-out op dagen met echt Frank-bedrag; model wordt telkens zonder die dag opnieuw gefit",
          "kosten_keten_alle_dagen": stats(e_cost), "kosten_keten_zonder_uitbijters": stats(e_cost_inl),
          "kosten_bij_werkelijk_verbruik": stats(e_true), "afname_kwh": stats(e_a), "teruglevering_kwh": stats(e_e), "dagen": rows}
    model.update({
        "versie": 1, "gekalibreerd_op": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "dagen_in_fit": len(days), "dagen_met_frank": sum(1 for x in days if x["f"] is not None),
        "uitbijters_afname": outl,
        "onzekerheid": {"kosten_rmse_zonder_uitbijters": bt["kosten_keten_zonder_uitbijters"].get("rmse"),
                         "kosten_rmse_alle_dagen": bt["kosten_keten_alle_dagen"]["rmse"]},
        # AANNAMEN, niet uit de data gehaald: verdeling van de dag voor het deel van de dag dat al voorbij is
        "dagprofiel_afname": [0.025, 0.02, 0.018, 0.018, 0.02, 0.03, 0.05, 0.065, 0.055, 0.045, 0.04, 0.04,
                              0.04, 0.04, 0.04, 0.045, 0.055, 0.075, 0.085, 0.08, 0.065, 0.05, 0.035, 0.03],
        "toelichting": "kosten = k_p*afname*p_dag - k_e*terug*p_zon - k_c*afname; p_dag = daggemiddelde all-in prijs (EUR/kWh), p_zon = zon-gewogen all-in prijs"})
    json.dump(model, open(os.path.join(DATA, "model.json"), "w"), indent=1)
    json.dump(bt, open(os.path.join(DATA, "backtest.json"), "w"), indent=1)
    print(json.dumps({"model": {k: model[k] for k in ("afname", "terug", "kosten")}, "uitbijters": outl,
                      "backtest_kosten_zonder_uitbijters": bt["kosten_keten_zonder_uitbijters"],
                      "backtest_kosten_alle": bt["kosten_keten_alle_dagen"],
                      "backtest_kosten_werkelijk_verbruik": bt["kosten_bij_werkelijk_verbruik"],
                      "afname": bt["afname_kwh"], "terug": bt["teruglevering_kwh"]}, indent=1))


if __name__ == "__main__":
    main()
