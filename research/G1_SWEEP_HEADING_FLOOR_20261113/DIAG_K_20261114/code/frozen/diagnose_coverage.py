"""Describe the Markov coverage miss from paired, saved nominal trajectories."""
import json
from pathlib import Path
import sys

import numpy as np

base = Path(sys.argv[1])
with np.load(base / "S2P_NOMINAL.npz", allow_pickle=False) as z:
    cases, assigned = z["cases"], z["case_index"]
    result = {"comparison": "paired descriptive analysis", "case": {}}
    for i, case in enumerate(cases):
        row = {}
        for model in ("independent", "markov"):
            hit = z[model + "_covered"][assigned == i, :17]
            err = z[model + "_err"][assigned == i, :17]
            p = z[model + "_p_ee"][assigned == i, :17]
            row[model] = {
                "paths": len(hit), "coverage": float(hit.mean()),
                "misses": int((~hit).sum()), "rmse_deg": float(np.sqrt(np.mean(err**2))),
                "mean_interval_halfwidth_deg": float((1.96 * np.sqrt(p)).mean()),
                "mean_error_deg": float(err.mean()),
            }
        result["case"][str(case)] = row
    result["station_coverage"] = {m:z[m + "_covered"][:, :17].mean(axis=0).tolist()
                                  for m in ("independent", "markov")}
    hit_ind, hit_m = [z[m + "_covered"][:, :17] for m in ("independent", "markov")]
    result["paired_discordant_station_visits"] = {
        "independent_hit_markov_miss": int((hit_ind & ~hit_m).sum()),
        "markov_hit_independent_miss": int((hit_m & ~hit_ind).sum()),
    }
    result["markov_misses"] = int((~hit_m).sum())
    result["markov_minimum_extra_hits_to_pass"] = int(np.ceil(.88 * hit_m.size) - hit_m.sum())
    result["markov_window_miss"] = int(z["markov_miss"][:, :17].sum())
    result["markov_gate_reject"] = int(z["markov_reject"][:, :17].sum())
with (base / "MARKOV_COVERAGE_DIAGNOSTIC.json").open("x", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
    f.write("\n")
print(json.dumps({c: {m:round(r["coverage"], 4) for m,r in d.items()} for c,d in result["case"].items()}))
print(json.dumps({k:v for k,v in result.items() if k.startswith("markov_") or k.startswith("paired_")}))

