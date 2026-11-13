"""Reaggregate the finished G-E2E path CSV independently of the filter."""
import csv
import json
import math
from pathlib import Path
import sys

import numpy as np
from scipy.stats import beta

base = Path(sys.argv[1])
with (base / "S1P_G_E2E_PATHS.csv").open(newline="", encoding="utf-8") as file:
    rows = list(csv.DictReader(file))
with (base / "S1P_G_E2E.json").open(encoding="utf-8") as file:
    result = json.load(file)
rng = np.random.default_rng(2026111340)
checked = {}
all_flags = set()
for model in ("independent", "markov"):
    group = [row for row in rows if row["model"] == model]
    assert [int(r["path_id"]) for r in group] == list(range(250))
    keys = ("covered", "covered_at_17", "g1_mse", "mean_nees", "rejected", "eligible")
    def numeric(value):
        return float(value == "True") if value in {"True", "False"} else float(value)
    def columns(prefix):
        return np.array([[numeric(row[f"{prefix}_{key}"]) for key in keys] for row in group])
    a, b = columns("snap"), columns("continuous")
    dr = np.array([float(row["dr_mse"]) for row in group])
    sel = rng.integers(250, size=(10000, 250))
    def estimates(x, d):
        avg = np.mean(x, axis=-2)
        rmse = np.sqrt(avg[..., 2])
        return np.stack((avg[..., 0]/17, avg[..., 1], rmse/np.sqrt(np.mean(d, axis=-1)),
                         avg[..., 3], rmse, avg[..., 4]/avg[..., 5]), axis=-1)
    ax, bx = estimates(a, dr), estimates(b, dr)
    interval = np.percentile(estimates(a[sel], dr[sel]) - estimates(b[sel], dr[sel]), [2.5,97.5], axis=0)
    plus = int(np.count_nonzero(a[:, 1] > b[:, 1]))
    minus = int(np.count_nonzero(a[:, 1] < b[:, 1]))
    def upper(k, p):
        return 1. if k == 250 else beta.ppf(p, k+1, 250-k)
    def lower(k, p):
        return 0. if k == 0 else beta.ppf(p, k, 251-k)
    interval[:, 1] = [lower(plus, .0125)-upper(minus, .9875),
                      upper(plus, .9875)-lower(minus, .0125)]
    disc = np.count_nonzero(a[:, 0] != b[:, 0])
    if disc < 5:
        u = upper(disc, .95)
        interval[:, 0] = [-u, u]
    disc = np.count_nonzero(np.any(a[:, 4:] != b[:, 4:], axis=1))
    if disc < 5:
        denom = a[:, 5].mean()/17 - math.sqrt(math.log(40)/500)
        u = min(1., upper(disc, .975) / denom)
        interval[:, 5] = [-u, u]
    checked[model] = {}
    for i, (key, threshold) in enumerate(zip(
            ("coverage_1_to_17", "coverage_at_17", "rmse_ratio_1_to_17",
             "mean_nees_1_to_17", "g1_rmse_1_to_17_deg", "gate_rejection_1_to_17"),
            (.02, .04, .05, .25, .15, .03))):
        got = result["models"][model]["metrics"][key]
        np.testing.assert_allclose([got["snap"], got["continuous"]], [ax[i], bx[i]], rtol=0, atol=1e-12)
        np.testing.assert_allclose(got["difference"], ax[i]-bx[i], rtol=0, atol=1e-12)
        lo, hi = interval[:, i]
        expected = "INCONCLUSIVE"
        if np.isfinite([lo,hi]).all() and (lo != hi or i == 1):
            np.testing.assert_allclose(got["ci95"], [lo, hi], rtol=0, atol=1e-12)
            if -threshold <= lo <= hi <= threshold:
                expected = "PASS"
            elif hi < -threshold or lo > threshold:
                expected = "FAIL"
        else:
            assert got["ci95"] is None
        assert got["status"] == expected
        checked[model][key] = expected
        all_flags.add(expected)
overall = "FAIL" if "FAIL" in all_flags else ("PASS" if all_flags == {"PASS"} else "INCONCLUSIVE")
assert result["status"] == overall
print(json.dumps(dict(result="PASS_REAGGREGATION", pairs=len(rows), gate=overall, metrics=checked), indent=2))
