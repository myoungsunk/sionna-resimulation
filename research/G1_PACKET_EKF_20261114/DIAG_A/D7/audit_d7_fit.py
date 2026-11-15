"""Audit D7.1's alternative upper-bound criterion on frozen D4 fit bins."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from scipy.optimize import nnls

fit_path, historical_manifest, output = map(Path, sys.argv[1:])
d4_sha = hashlib.sha256(fit_path.read_bytes()).hexdigest()
assert d4_sha == "6208455eada004ead57b9db4ae14dae037e530e82888596f8700fe977eb8b4e8"
d4 = json.loads(fit_path.read_text(encoding="utf-8"))
record = {"d4_sha256": d4_sha, "case": {}, "pass": True}
for case, value in d4["case_cohort"].items():
    row = {}
    for name in ("distance_variogram", "range_residual_variogram", "rotation_yaw_correlation"):
        source = value[name]
        fit = source["exponential_fit"]
        yaw = name == "rotation_yaw_correlation"
        unit, obs = ("deg", "pearson") if yaw else ("m", "semivariance")
        bins = [b for b in source["bins"] if b["n_pairs"] >= source["fit_bin_min_pairs"]
                and b.get(obs) is not None and b.get(f"mean_lag_{unit}", 0) > 0]
        assert len(bins) == source["n_fit_bins"], (case, name, len(bins), source["n_fit_bins"])
        lag = np.array([b[f"mean_lag_{unit}"] for b in bins])
        y = np.array([b[obs] for b in bins])
        lo, hi = fit[f"length_fit_bounds_{unit}"]
        grid = np.geomspace(lo, hi, 2049)
        candidate = fit[f"fit_candidate_length_{unit}"]
        grid = np.sort(np.append(grid, candidate))
        obj = []
        for length in grid:
            if yaw:
                q = np.exp(-lag/length)
                a = np.clip(q@y/(q@q), 0, 1)
                residual = a*q-y
            else:
                h = np.c_[np.ones(len(lag)), -np.expm1(-lag/length)]
                coeff, _ = nnls(h, y)
                residual = h@coeff-y
            obj.append(np.mean(residual**2))
        obj = np.array(obj)
        bound_flag = np.isclose(candidate, hi, atol=0, rtol=1e-8)
        monotone = np.all(np.diff(obj) <= 1e-12)
        # A strict increase from an interior candidate to the upper endpoint also
        # disproves a monotonic decrease irrespective of the chosen grid density.
        gap = float(obj[-1]-obj[np.argmin(np.abs(grid-candidate))])
        assert bound_flag or (gap > 1e-10 and not monotone), (case, name, gap)
        row[name] = {"candidate": candidate, "upper": hi, "at_upper": bool(bound_flag),
                     "objective_monotone_toward_upper_1e-12": bool(monotone),
                     "objective_at_upper_minus_at_candidate": gap,
                     "grid_points": len(grid), "D7_arm_assignment_needs_change": False}
        if yaw:
            max_mean_turn_pair_lag = max(b["mean_lag_deg"] for b in source["bins"] if b["mean_lag_deg"] is not None)
            row[name]["max_mean_observed_turn_pair_separation_deg"] = max_mean_turn_pair_lag
            row[name]["shorter_than_half_turn_span_proven_for_some_turn"] = bool(
                2*fit["length_deg"] < max_mean_turn_pair_lag)
    record["case"][case] = row
    print(case, [(n, x["at_upper"], x["objective_at_upper_minus_at_candidate"]) for n,x in row.items()])

baseline = json.loads(historical_manifest.read_text(encoding="utf-8"))
hashes = {key: value for key,value in baseline["outputs_sha256"].items()
          if key.endswith(("D5_CHECKPOINT.npz","D6_CHECKPOINT.npz"))}
assert len(hashes) == 56
record["prior_manifest_sha256"] = hashlib.sha256(historical_manifest.read_bytes()).hexdigest()
record["prior_D5_D6_checkpoint_sha256"] = hashes
output.write_text(json.dumps(record, indent=2)+"\n", encoding="utf-8")
print("PASS: no additional upper fit under the monotone alternative; 56 baseline hashes recorded")
