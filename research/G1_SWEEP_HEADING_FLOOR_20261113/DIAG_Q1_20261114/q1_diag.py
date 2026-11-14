"""Q1 diagnostics for G1-MODEL-001 v3.4: per-sweep aligned error vs E1 variance, site bias, station correlation.
Re-runs the frozen LORO training routine (_train_group, TRAIN_SEED XY stream) for all six mount-0 cases.
"""
import json, sys, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
CODE = sys.argv[1]; ROOT = sys.argv[2]; LORO = sys.argv[3]; OUT = sys.argv[4]; W = int(sys.argv[5])
sys.path.insert(0, CODE)
import v33_observation as V
from v32_observation import ObservationInputs, ObservationCase, SEEDS
from v32_filter import training_features
from scipy.stats import spearmanr, pearsonr
names = ["R2_aA_m0", "R2_aB_m0", "R4_aA_m0", "R4_aB_m0", "R5_aA_m0", "R5_aB_m0"]
cal = {k: v["calibration"] for k, v in json.load(open(LORO)).items()}
inputs = ObservationInputs(ROOT, ROOT)
rng = np.random.Generator(np.random.PCG64(V.TRAIN_SEED))
tasks = []
for name in sorted(names):
    case = ObservationCase(inputs, name)
    groups = sorted(case.group_ids)
    offsets = rng.normal(0., V.SIGMA_XY, (len(groups), SEEDS, 2))
    evaluated, _, _ = V.snap_xy(offsets)
    tasks += [(case, g, c) for g, c in zip(groups, evaluated)]
t0 = time.time()
with ThreadPoolExecutor(max_workers=W) as pool:
    feats = list(pool.map(V._train_group, tasks))
print("train_group done", round(time.time() - t0, 1), "s", flush=True)
rows = []
for (case, g, ev), f in zip(tasks, feats):
    seeds = [s for s in range(SEEDS) if case.n_valid(g, s) >= 3]
    assert len(seeds) == len(f.winner_error)
    c = cal[case.route]
    raw = np.where(np.isfinite(f.winner_raw), f.winner_raw, c["cap_raw"])
    sw = case.groups[g]
    hd = float(np.hypot(sw.x - case.anchor[0], sw.y - case.anchor[1]))
    for s, e, r, fl in zip(seeds, f.winner_error, raw, ~np.isfinite(f.winner_raw)):
        rows.append(dict(case=case.name, route=case.route, group=int(g) if np.isscalar(g) else str(g), seed=s,
                         x=float(sw.x), y=float(sw.y), hdist=hd, elev_deg=float(np.degrees(np.arctan2(case.anchor[2] - case.z, hd))),
                         err=float(e), r_e1=float(c["c_l"] * r), flat=bool(fl), dx=float(ev[s][0]), dy=float(ev[s][1])))
json.dump(rows, open(OUT, "w"))
print("rows", len(rows))
