#!/usr/bin/env python3
"""Offline tests van de parseerlogica met nagemaakte antwoorden."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_data as fd

rows = [{"from": "2026-11-10T23:00:00.000Z", "till": "2026-11-11T00:00:00.000Z", "marketPrice": 0.10, "marketPriceTax": 0.021,
         "sourcingMarkupPrice": 0.02, "energyTaxPrice": 0.11}]
r = fd.parse_frank(rows)
assert abs(r[0]["all_in"] - 0.251) < 1e-9, r
# kwartierdata middelen naar uur (00:00-01:00 lokale tijd = 23:00Z)
q = [dict(r[0], **{"from": "2026-11-10T23:%02d:00.000Z" % m, "all_in": v, "market": v}) for m, v in ((0, .1), (15, .2), (30, .3), (45, .4))]
h = fd.hourly(q)
assert len(h) == 1 and h[0]["t"] == "2026-11-11T00:00" and abs(h[0]["all_in"] - .25) < 1e-9 and h[0]["n"] == 4, h
assert fd.to_local("2026-07-01T10:00:00Z").hour == 12   # zomertijd
w = fd.parse_weather({"hourly": {"time": ["2026-11-10T00:00"], "temperature_2m": [5.1], "shortwave_radiation": [0],
                                 "cloud_cover": [80], "wind_speed_10m": [12]}})
assert w[0]["temp"] == 5.1 and w[0]["wind100"] is None
import calibrate as cal
c = cal.ols([[1, 0], [1, 1], [1, 2], [1, 3]], [1, 3, 5, 7])
assert abs(c[0] - 1) < 1e-9 and abs(c[1] - 2) < 1e-9, c
c, idx = cal.trimmed([[1, x] for x in range(10)], [2 * x + 1 + (20 if x == 4 else 0) for x in range(10)])
assert 4 not in idx and abs(c[1] - 2) < 1e-6, (c, idx)
print("alle tests ok")
