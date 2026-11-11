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


# ---------------- prijsmodel (uurlijkse kale marktprijs voor de komende dagen) ----------------
PRICE_FEATURES = ["uur0..uur23 (intercept per uur)", "L7 (gem. marktprijs laatste 7 bekende dagen)", "L30 (idem 30 dagen)",
                  "wind100 daggemiddelde (km/u)", "temperatuur daggemiddelde (C)", "weekend (0/1)", "straling dit uur (kW/m2)"]
NH = 14          # aantal uren in de planner-backtest (ca. 40 kWh bij 3 kW)
KS = (1, 2, 3, 4, 5)


def price_model(bt):
    try:
        import numpy as np
    except ImportError:
        bt["prijsmodel"] = {"overgeslagen": "numpy niet beschikbaar"}
        return None
    try:
        H = json.load(open(os.path.join(DATA, "historie.json")))["days"]
    except Exception as e:
        bt["prijsmodel"] = {"overgeslagen": "geen historie.json: %r" % (e,)}
        return None
    dates = sorted(H)
    n = len(dates)
    if n < 120:
        bt["prijsmodel"] = {"overgeslagen": "te weinig historie (%d dagen, minimaal 120)" % n}
        return None
    M = np.array([H[d]["m"] for d in dates]); Wd = np.array([H[d]["w"] for d in dates])
    R = np.array([H[d]["r"] for d in dates]) / 1000.0; Tt = np.array([H[d]["t"] for d in dates])
    dm = M.mean(1); wm = Wd.mean(1); tm = Tt.mean(1)
    wk = np.array([1.0 if dt.date.fromisoformat(d).weekday() >= 5 else 0.0 for d in dates])
    cs = np.concatenate([[0.0], np.cumsum(dm)])

    def lvl(i, k, w):
        j = i - k
        return (cs[j + 1] - cs[j + 1 - w]) / w

    def feat(i, k):
        L7, L30 = lvl(i, k, 7), lvl(i, k, 30)
        F = np.zeros((24, 30))
        for h in range(24):
            F[h, h] = 1.0
            F[h, 24:30] = [L7, L30, wm[i], tm[i], wk[i], R[i, h]]
        return F

    def fit(last_target, k):
        rows = [i for i in range(k + 29, last_target + 1)]
        X = np.vstack([feat(i, k) for i in rows]); y = np.concatenate([M[i] for i in rows])
        return np.linalg.solve(X.T @ X + 1e-4 * np.eye(30), X.T @ y)

    ntest = min(150, n - 80)
    start = n - ntest
    res = {k: [] for k in KS}; base_prof = {k: [] for k in KS}; base_l7 = {k: [] for k in KS}
    for k in KS:
        c = None
        for ti, i in enumerate(range(start, n)):
            if ti % 25 == 0:
                c = fit(i - k, k)
            pred = feat(i, k) @ c
            res[k].append(pred - M[i])
            prof = M[max(0, i - k - 59):i - k + 1].mean(0)
            base_prof[k].append(prof * (lvl(i, k, 7) / prof.mean()) - M[i] if prof.mean() > 0.01 else prof - M[i])
            base_l7[k].append(np.full(24, lvl(i, k, 7)) - M[i])
    per_k = {}
    for k in KS:
        e = np.array(res[k])
        per_k[str(k)] = {"mae_ct": round(float(np.abs(e).mean()) * 100, 2), "rmse_ct": round(float(np.sqrt((e ** 2).mean())) * 100, 2),
                         "mae_ct_profiel_x_L7": round(float(np.abs(np.array(base_prof[k])).mean()) * 100, 2),
                         "mae_ct_alleen_L7": round(float(np.abs(np.array(base_l7[k])).mean()) * 100, 2)}
    # planner-backtest: kies NH goedkoopste uren in de komende 5 dagen op basis van voorspelling
    plan = []
    cache = {}
    for C in range(start, n - 5, 2):
        pred, act = [], []
        for j in range(1, 6):
            key = (j, C // 25)
            if key not in cache:
                cache[key] = fit(C, j)
            pred.append(feat(C + j, j) @ cache[key]); act.append(M[C + j])
        pred = np.concatenate(pred); act = np.concatenate(act)
        ch = np.argsort(pred)[:NH]
        prof = M[max(0, C - 59):C + 1].mean(0)
        chb = np.argsort(np.tile(prof, 5))[:NH]
        plan.append((act[ch].mean(), np.sort(act)[:NH].mean(), act.mean(), act[chb].mean(), act[:NH].mean()))
    p = (np.mean(plan, axis=0) * 100).tolist()
    planner = {"uren": NH, "venster_dagen": 5, "n_vensters": len(plan), "eenheid": "ct/kWh kale marktprijs, gemiddelde van de gekozen uren",
               "model": round(p[0], 2), "optimum_achteraf": round(p[1], 2), "gemiddeld_uur": round(p[2], 2),
               "alleen_uurprofiel": round(p[3], 2), "meteen_beginnen": round(p[4], 2)}
    coefs = {str(k): {"coef": [round(float(x), 6) for x in fit(n - 1, k)], "sd": round(float(np.sqrt((np.array(res[k]) ** 2).mean())), 5)} for k in KS}
    bt["prijsmodel"] = {"historie_dagen": n, "eerste_dag": dates[0], "laatste_dag": dates[-1], "testperiode_dagen": ntest,
                        "methode": "rolling origin, elke 25 dagen opnieuw gefit, per horizon k (dagen vooruit)", "per_horizon": per_k, "planner": planner}
    return {"versie": 1, "features": PRICE_FEATURES, "k": coefs, "historie_dagen": n, "laatste_historiedag": dates[-1]}


def conversion():
    """Omrekening van kale marktprijs naar all-in prijs, uit het meest recente Frank-uur."""
    try:
        hs = [h for h in json.load(open(os.path.join(DATA, "prijzen.json")))["hours"] if h.get("market_tax") is not None and h["market"] > 0.01]
        h = hs[-1]
        return {"btw": round(h["market_tax"] / h["market"], 4), "toeslag": round((h["markup"] or 0) + (h["energy_tax"] or 0), 5), "bron_uur": h["t"]}
    except Exception:
        return {"btw": 0.21, "toeslag": 0.129, "bron_uur": None}


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
    pm = price_model(bt)
    if pm:
        pm["omrekening"] = conversion()
        pm["kwaliteit"] = {"per_horizon": bt["prijsmodel"]["per_horizon"], "planner": bt["prijsmodel"]["planner"], "testperiode_dagen": bt["prijsmodel"]["testperiode_dagen"]}
        model["prijsmodel"] = pm
    json.dump(model, open(os.path.join(DATA, "model.json"), "w"), indent=1)
    json.dump(bt, open(os.path.join(DATA, "backtest.json"), "w"), indent=1)
    print(json.dumps({"model": {k: model[k] for k in ("afname", "terug", "kosten")}, "uitbijters": outl,
                      "backtest_kosten_zonder_uitbijters": bt["kosten_keten_zonder_uitbijters"],
                      "backtest_kosten_alle": bt["kosten_keten_alle_dagen"],
                      "backtest_kosten_werkelijk_verbruik": bt["kosten_bij_werkelijk_verbruik"],
                      "afname": bt["afname_kwh"], "terug": bt["teruglevering_kwh"]}, indent=1))


if __name__ == "__main__":
    main()
