#!/usr/bin/env python3
"""Haalt weer en Frank-uurprijzen op en schrijft JSON naar data/.

Draait in een GitHub Action. Alleen standaardbibliotheek. Elke bron probeert
meerdere endpoints/varianten; alles wat gebeurt komt in data/status.json,
zodat zonder internet of Actions-toegang te zien is wat werkte.
"""
import json, os, sys, time, datetime as dt, urllib.request, urllib.error, urllib.parse
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Amsterdam")
LAT, LON = 52.70, 6.19            # Meppel
START = dt.date(2026, 10, 1)      # historie vanaf hier
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DATA = os.path.join(ROOT, "data")
RAW = os.path.join(DATA, "raw")

# Alleen gebruikt als Frank zelf onbereikbaar is: benadering vanuit de kale marktprijs.
# NIET geverifieerd, aanpassen als de echte waarden bekend zijn (excl. btw, EUR/kWh).
APPROX = {"markup_excl": 0.0150, "energy_tax_excl": 0.0916, "btw": 1.21}

STATUS = {"started": None, "finished": None, "sources": {}}


def now():
    return dt.datetime.now(TZ)


def http(method, url, body=None, headers=None, timeout=30, retries=2):
    last = None
    for i in range(retries + 1):
        try:
            h = {"User-Agent": "energie-calc/1.0 (+https://github.com/gerdjan/energie)"}
            h.update(headers or {})
            req = urllib.request.Request(url, data=body, method=method, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            txt = e.read().decode("utf-8", "replace")
            if e.code >= 500 and i < retries:
                time.sleep(4 * (i + 1)); continue
            return e.code, txt
        except Exception as e:  # DNS, timeout, SSL
            last = e
            time.sleep(5 * (i + 1))
    return 0, "%s: %s" % (type(last).__name__, last)


def log(src, **kw):
    kw["body"] = (kw.get("body") or "")[:400]
    STATUS["sources"].setdefault(src, {"attempts": []})["attempts"].append(kw)


def save_raw(name, text):
    os.makedirs(RAW, exist_ok=True)
    with open(os.path.join(RAW, name), "w", encoding="utf-8") as f:
        f.write(text[:3000])


def to_local(iso):
    s = iso.replace("Z", "+00:00")
    d = dt.datetime.fromisoformat(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(TZ)


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


# ---------- prijzen: Frank ----------
FRANK_ENDPOINTS = ["https://graphql.frankenergie.nl/", "https://frank-graphql-prod.graphcdn.app/"]
FRANK_HEADERS = {"Content-Type": "application/json", "Accept": "application/json",
                 "x-country": "NL", "x-graphql-client-name": "frank-app", "x-graphql-client-version": "1"}
FIELDS = "from till marketPrice marketPriceTax sourcingMarkupPrice energyTaxPrice"
Q_RANGE = "query MarketPrices($startDate: Date!, $endDate: Date!) { marketPricesElectricity(startDate: $startDate, endDate: $endDate) { %s } }" % FIELDS
Q_DAY_DATE = "query MarketPrices($date: Date!) { marketPrices(date: $date) { electricityPrices { %s } } }" % FIELDS
Q_DAY_STR = "query MarketPrices($date: String!) { marketPrices(date: $date) { electricityPrices { %s } } }" % FIELDS


def parse_frank(rows):
    out = []
    for r in rows or []:
        if not r or "from" not in r:
            continue
        m, mt, mk, et = f(r.get("marketPrice")), f(r.get("marketPriceTax")), f(r.get("sourcingMarkupPrice")), f(r.get("energyTaxPrice"))
        out.append({"from": r["from"], "market": m, "market_tax": mt, "markup": mk, "energy_tax": et,
                    "all_in": m + mt + mk + et, "src": "frank", "approx": False})
    return out


def frank_fetch(start, end, state):
    """Probeer combinaties van endpoint en query. state onthoudt wat werkte."""
    combos = []
    if state.get("ok"):
        combos.append(state["ok"])
    for ep in FRANK_ENDPOINTS:
        for v in ("day_str", "range", "day_date"):
            if (ep, v) not in combos:
                combos.append((ep, v))
    for ep, v in combos:
        if v == "range":
            body = {"query": Q_RANGE, "variables": {"startDate": start.isoformat(), "endDate": end.isoformat()}}
            code, txt = http("POST", ep, json.dumps(body).encode(), FRANK_HEADERS)
            rows = None
            try:
                rows = json.loads(txt)["data"]["marketPricesElectricity"]
            except Exception:
                pass
            recs = parse_frank(rows)
            log("frank", endpoint=ep, variant=v, start=start.isoformat(), end=end.isoformat(), http=code, records=len(recs), body=txt if not recs else "")
            if recs:
                state["ok"] = (ep, v); save_raw("frank_sample.json", txt); return recs
        else:
            q = Q_DAY_DATE if v == "day_date" else Q_DAY_STR
            recs, last = [], ""
            d = start
            while d < end:
                code, txt = http("POST", ep, json.dumps({"query": q, "variables": {"date": d.isoformat()}}).encode(), FRANK_HEADERS)
                last = txt
                try:
                    recs += parse_frank(json.loads(txt)["data"]["marketPrices"]["electricityPrices"])
                except Exception:
                    pass
                d += dt.timedelta(days=1)
            log("frank", endpoint=ep, variant=v, start=start.isoformat(), end=end.isoformat(), http=code, records=len(recs), body=last if not recs else "")
            if recs:
                state["ok"] = (ep, v); save_raw("frank_sample.json", last); return recs
    return []


def frank_all():
    state, recs = {}, []
    today = now().date()
    d = START
    while d <= today:
        chunk_end = min(d + dt.timedelta(days=10), today + dt.timedelta(days=1))
        recs += frank_fetch(d, chunk_end, state)
        d = chunk_end
    # vandaag en morgen apart (einddatum kan exclusief of inclusief zijn; probeer meerdere)
    for end in (today + dt.timedelta(days=2), today + dt.timedelta(days=1)):
        r = frank_fetch(today, end, state)
        if r:
            recs += r
            if any(to_local(x["from"]).date() == today + dt.timedelta(days=1) for x in r):
                break
    return recs


# ---------- prijzen: terugval op marktprijs ----------
def approx_all_in(market_eur_kwh):
    return (market_eur_kwh + APPROX["markup_excl"] + APPROX["energy_tax_excl"]) * APPROX["btw"]


def fallback_energy_charts():
    today = now().date()
    url = "https://api.energy-charts.info/price?bzn=NL&start=%s&end=%s" % (START.isoformat(), (today + dt.timedelta(days=2)).isoformat())
    code, txt = http("GET", url)
    recs = []
    try:
        j = json.loads(txt)
        for ts, p in zip(j["unix_seconds"], j["price"]):
            if p is None:
                continue
            m = p / 1000.0
            iso = dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat()
            recs.append({"from": iso, "market": m, "market_tax": None, "markup": None, "energy_tax": None,
                         "all_in": approx_all_in(m), "src": "energy-charts", "approx": True})
    except Exception:
        pass
    log("prijzen_fallback", endpoint=url, http=code, records=len(recs), body=txt if not recs else "")
    if recs:
        save_raw("energycharts_sample.json", txt)
    return recs


def fallback_energyzero():
    today = now().date()
    a = dt.datetime.combine(START, dt.time(0), TZ).astimezone(dt.timezone.utc)
    b = dt.datetime.combine(today + dt.timedelta(days=2), dt.time(0), TZ).astimezone(dt.timezone.utc)
    url = "https://api.energyzero.nl/v1/energyprices?" + urllib.parse.urlencode({
        "fromDate": a.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "tillDate": b.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "interval": 4, "usageType": 1, "inclBtw": "false"})
    code, txt = http("GET", url)
    recs = []
    try:
        for p in json.loads(txt)["Prices"]:
            m = float(p["price"])
            recs.append({"from": p["readingDate"], "market": m, "market_tax": None, "markup": None, "energy_tax": None,
                         "all_in": approx_all_in(m), "src": "energyzero", "approx": True})
    except Exception:
        pass
    log("prijzen_fallback", endpoint=url, http=code, records=len(recs), body=txt if not recs else "")
    if recs:
        save_raw("energyzero_sample.json", txt)
    return recs


def hourly(recs):
    """Gemiddelde per lokaal uur. Werkt voor uur- en kwartierdata."""
    buckets = {}
    for r in recs:
        t = to_local(r["from"]).replace(minute=0, second=0, microsecond=0)
        buckets.setdefault(t.strftime("%Y-%m-%dT%H:00"), []).append(r)
    out = []
    for t in sorted(buckets):
        rs = buckets[t]
        n = len(rs)
        avg = lambda k: (sum(x[k] for x in rs) / n) if all(x[k] is not None for x in rs) else None
        out.append({"t": t, "all_in": round(avg("all_in"), 5), "market": round(avg("market"), 5),
                    "market_tax": avg("market_tax"), "markup": avg("markup"), "energy_tax": avg("energy_tax"),
                    "n": n, "src": rs[0]["src"], "approx": rs[0]["approx"]})
    return out


def run_prices():
    recs = []
    try:
        recs = frank_all()
    except Exception as e:
        log("frank", error=repr(e))
    if not recs:
        for fn in (fallback_energy_charts, fallback_energyzero):
            try:
                recs = fn()
            except Exception as e:
                log("prijzen_fallback", error=repr(e))
            if recs:
                break
    if not recs:
        STATUS["sources"]["prijzen"] = {"ok": False, "note": "geen enkele bron werkte, oude data blijft staan", **STATUS["sources"].get("prijzen", {})}
        return
    new = {h["t"]: h for h in hourly(recs)}
    path = os.path.join(DATA, "prijzen.json")
    old = {}
    try:
        old = {h["t"]: h for h in json.load(open(path))["hours"]}
    except Exception:
        pass
    old.update(new)
    hours = [old[k] for k in sorted(old)]
    tomorrow = (now().date() + dt.timedelta(days=1)).isoformat()
    json.dump({"fetched_at": now().isoformat(timespec="seconds"), "unit": "EUR/kWh", "tz": "Europe/Amsterdam", "hours": hours},
              open(path, "w"), indent=1)
    n_tom = sum(1 for h in hours if h["t"].startswith(tomorrow))
    STATUS["sources"]["prijzen"] = {**STATUS["sources"].get("prijzen", {}), "ok": True, "hours_total": len(hours),
        "src_used": sorted({h["src"] for h in new.values()}), "approx": any(h["approx"] for h in new.values()),
        "tomorrow_hours": n_tom, "tomorrow_available": n_tom >= 20}


# ---------- weer ----------
HOURLY = "temperature_2m,shortwave_radiation,cloud_cover,wind_speed_10m,wind_speed_100m"


def parse_weather(j):
    h = j["hourly"]
    out = []
    for i, t in enumerate(h["time"]):
        w100 = h.get("wind_speed_100m")
        out.append({"t": t, "temp": h["temperature_2m"][i], "radiation": h["shortwave_radiation"][i],
                    "cloud": h["cloud_cover"][i], "wind": h["wind_speed_10m"][i],
                    "wind100": w100[i] if w100 else None})
    return out


def weather_call(model, params):
    p = dict(params)
    if model:
        p["models"] = model
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(p)
    code, txt = http("GET", url, timeout=25, retries=3)
    rows = []
    try:
        rows = parse_weather(json.loads(txt))
    except Exception:
        pass
    valid = [r for r in rows if r["temp"] is not None]
    log("weer", endpoint=url, model=model or "standaard", http=code, records=len(rows), valid=len(valid), body=txt if not valid else "")
    return rows, valid, txt


def run_weather():
    params = {"latitude": LAT, "longitude": LON, "hourly": HOURLY, "timezone": "Europe/Amsterdam",
              "past_days": 60, "forecast_days": 7}
    rows, used = None, None
    for model in ("knmi_seamless", None):
        r, valid, txt = weather_call(model, params)
        if r and len(valid) > 0.5 * len(r):
            rows, used = r, model
            save_raw("weer_sample.json", txt)
            break
    if rows is None:
        STATUS["sources"]["weer"] = {**STATUS["sources"].get("weer", {}), "ok": False, "note": "geen model werkte, oude data blijft staan"}
        return
    # ontbrekende waarden (bv. buiten de horizon van het KNMI-model) aanvullen met het standaardmodel
    keys = ("temp", "radiation", "cloud", "wind", "wind100")
    missing = sum(1 for r in rows if any(r[k] is None for k in keys))
    filled = 0
    if missing and used:
        r2, valid2, _ = weather_call(None, params)
        by = {x["t"]: x for x in r2}
        for r in rows:
            o = by.get(r["t"])
            if o and any(r[k] is None for k in keys):
                for k in keys:
                    if r[k] is None and o[k] is not None:
                        r[k] = o[k]
                filled += 1
    json.dump({"fetched_at": now().isoformat(timespec="seconds"), "model": used or "open-meteo standaard",
               "tz": "Europe/Amsterdam", "location": [LAT, LON], "hourly": rows},
              open(os.path.join(DATA, "weer.json"), "w"), indent=1)
    last_ok = max((r["t"] for r in rows if all(r[k] is not None for k in keys)), default=None)
    STATUS["sources"]["weer"] = {**STATUS["sources"]["weer"], "ok": True, "model_used": used or "standaard", "hours": len(rows),
                                 "hours_with_gaps_before_fill": missing, "hours_filled_from_default": filled, "last_complete_hour": last_ok}


# ---------- historie voor het prijsmodel ----------
HIST_START = dt.date(2025, 10, 1)


def ec_hourly(start, end):
    """Kale marktprijs (EUR/kWh) per lokaal uur uit Energy-Charts, voor de periode start..end."""
    url = "https://api.energy-charts.info/price?bzn=NL&start=%s&end=%s" % (start.isoformat(), end.isoformat())
    code, txt = http("GET", url, timeout=60)
    recs = []
    try:
        j = json.loads(txt)
        for ts, p in zip(j["unix_seconds"], j["price"]):
            if p is None:
                continue
            m = p / 1000.0
            recs.append({"from": dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat(), "market": m, "market_tax": None,
                         "markup": None, "energy_tax": None, "all_in": m, "src": "energy-charts", "approx": True})
    except Exception:
        pass
    log("historie_prijzen", endpoint=url, http=code, records=len(recs), body=txt if not recs else "")
    if recs:
        save_raw("energycharts_hist_sample.json", txt)
    return {h["t"]: h["market"] for h in hourly(recs)}


def archive_weather(start, end):
    out = {}
    d = start
    while d <= end:
        e = min(end, d + dt.timedelta(days=150))
        url = "https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode(
            {"latitude": LAT, "longitude": LON, "start_date": d.isoformat(), "end_date": e.isoformat(),
             "hourly": HOURLY, "timezone": "Europe/Amsterdam"})
        code, txt = http("GET", url, timeout=90)
        rows = []
        try:
            rows = parse_weather(json.loads(txt))
        except Exception:
            pass
        log("historie_weer", endpoint=url, http=code, records=len(rows), body=txt if not rows else "")
        for r in rows:
            out[r["t"]] = r
        d = e + dt.timedelta(days=1)
    return out


def run_history():
    """Bouwt data/historie.json: per dag 24 uurwaarden van kale marktprijs, wind (100 m), straling en temperatuur.
    Incrementeel: bestaande dagen blijven staan, alleen ontbrekende dagen en de laatste 8 dagen worden (opnieuw) gedaan."""
    path = os.path.join(DATA, "historie.json")
    old = {}
    try:
        old = json.load(open(path))["days"]
    except Exception:
        pass
    today = now().date()
    need = []
    d = HIST_START
    while d < today:
        if d.isoformat() not in old or d >= today - dt.timedelta(days=8):
            need.append(d)
        d += dt.timedelta(days=1)
    if not need:
        STATUS["sources"]["historie"] = {"ok": True, "days": len(old), "new": 0}
        return
    lo, hi = need[0], need[-1]
    market = ec_hourly(lo, hi + dt.timedelta(days=1))
    # Frank heeft voorrang waar die er is; vergelijk beide op de overlap
    frank_m, diffs = {}, []
    try:
        for h in json.load(open(os.path.join(DATA, "prijzen.json")))["hours"]:
            if h["src"] == "frank":
                frank_m[h["t"]] = h["market"]
    except Exception:
        pass
    for t, m in frank_m.items():
        if t in market:
            diffs.append(m - market[t])
    for t, m in frank_m.items():
        market[t] = m
    wx = {}
    cut = today - dt.timedelta(days=7)
    older = [x for x in need if x < cut]
    if older:
        wx.update(archive_weather(older[0], older[-1]))
    try:
        for r in json.load(open(os.path.join(DATA, "weer.json")))["hourly"]:
            if r["t"][:10] >= cut.isoformat() or r["t"] not in wx:
                wx[r["t"]] = r
    except Exception:
        pass
    days = dict(old)
    added, skipped = 0, 0
    for d in need:
        ds = d.isoformat()
        hs = ["%sT%02d:00" % (ds, h) for h in range(24)]
        rows = [wx.get(h) for h in hs]
        if not all(h in market for h in hs) or not all(r and all(r[k] is not None for k in ("temp", "radiation", "wind100")) for r in rows):
            skipped += 1
            continue
        days[ds] = {"m": [round(market[h], 5) for h in hs], "w": [round(r["wind100"], 1) for r in rows],
                    "r": [round(r["radiation"]) for r in rows], "t": [round(r["temp"], 1) for r in rows]}
        added += 1
    json.dump({"updated": now().isoformat(timespec="seconds"), "unit": "EUR/kWh (kale marktprijs, excl. btw)", "start": HIST_START.isoformat(),
               "days": {k: days[k] for k in sorted(days)}}, open(path, "w"), separators=(",", ":"))
    STATUS["sources"]["historie"] = {"ok": len(days) > 30, "days": len(days), "new_or_refreshed": added, "skipped_incomplete": skipped,
        "first_day": min(days) if days else None, "last_day": max(days) if days else None,
        "frank_minus_energycharts_mean_eur_kwh": (round(sum(diffs) / len(diffs), 5) if diffs else None), "overlap_hours": len(diffs),
        "frank_minus_energycharts_max_abs": (round(max(abs(x) for x in diffs), 5) if diffs else None)}


def fresh(path, key, max_hours):
    try:
        t = dt.datetime.fromisoformat(json.load(open(os.path.join(DATA, path)))[key])
        return (now() - t).total_seconds() / 3600.0 < max_hours
    except Exception:
        return False


def main():
    os.makedirs(RAW, exist_ok=True)
    STATUS["started"] = now().isoformat(timespec="seconds")
    for fn in (run_prices, run_weather, run_history):
        try:
            fn()
        except Exception as e:
            STATUS["sources"].setdefault(fn.__name__, {})["fatal"] = repr(e)
    STATUS["finished"] = now().isoformat(timespec="seconds")
    json.dump(STATUS, open(os.path.join(DATA, "status.json"), "w"), indent=1)
    ok = True
    for name, path, key in (("prijzen", "prijzen.json", "fetched_at"), ("weer", "weer.json", "fetched_at"), ("historie", "historie.json", "updated")):
        src = STATUS["sources"].setdefault(name, {})
        if not src.get("ok"):
            # een kortdurende storing is geen mislukking zolang de oude data nog vers is (minder dan 20 uur)
            if fresh(path, key, 20):
                src["stale_ok"] = True
            else:
                ok = False
    json.dump(STATUS, open(os.path.join(DATA, "status.json"), "w"), indent=1)
    print(json.dumps({k: v.get("ok") for k, v in STATUS["sources"].items()}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
