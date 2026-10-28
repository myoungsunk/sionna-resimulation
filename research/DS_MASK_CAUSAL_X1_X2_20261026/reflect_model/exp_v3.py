"""V3: robustness of the reflection observer to scene-description errors (observables only, no filter).

  python exp_v3.py [--cases primary|all]

Each perturbation changes only the model's scene description; the measured channel stays the stored one.
Reported per perturbation: far-field (rho >= 3 m) s residual RMS, slow RMS, tap agreement, and the fraction of the
LOS-model residual that is still removed ("retained reduction").
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

import common as C
from refl_model import ReflectiveFFD, corridor_planes

PERTURB = [
    ("nominal", {}),
    ("eps_x0.8", dict(eps_scale=0.8)), ("eps_x1.2", dict(eps_scale=1.2)),
    ("sigma_x0.5", dict(sigma_scale=0.5)), ("sigma_x2", dict(sigma_scale=2.0)),
    ("floor_+5cm", dict(planes=corridor_planes(offsets={"floor": 0.05}))),
    ("walls_+5cm", dict(planes=corridor_planes(offsets={"wall_y_neg": 0.05, "wall_y_pos": 0.05}))),
    ("walls_-5cm", dict(planes=corridor_planes(offsets={"wall_y_neg": -0.05, "wall_y_pos": -0.05}))),
    ("no_ceiling", dict(plane_subset=("floor", "wall_y_neg", "wall_y_pos", "end_x_min", "end_x_max"))),
    ("no_end_walls", dict(plane_subset=("floor", "ceiling", "wall_y_neg", "wall_y_pos"))),
    ("floor_walls_only", dict(plane_subset=("floor", "wall_y_neg", "wall_y_pos"))),
    ("depth1", dict(max_depth=1)),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="primary", choices=["all", "primary"])
    a = ap.parse_args()
    from qclean_uwb.drivesim import observation as O
    v1 = json.loads((C.OUT / "V1_DECISION.json").read_text())
    if not v1.get("chosen_variant"):
        raise SystemExit("V1 chose no variant: V3 not run")
    depth, mode = int(v1["chosen_variant"][1]), v1["chosen_variant"].split("_", 1)[1]
    base = C.base_model()
    cases = list(C.CASES) if a.cases == "all" else list(C.PRIMARY)
    rows = []
    for case in cases:
        z = C.load_control(case, "B0"); pid = z["pose_id"]; gt = z["truth_scoring_only"]; acc = z["acc"][:, z["jb"]].astype(bool)
        Hf, _, _ = C.load_rf(case)
        los = ReflectiveFFD(base, max_depth=0)
        of = O.observe(np.asarray(Hf[pid]), los.freqs, None, None, tx=0)
        a2 = np.array(C.CASES[case]["anchor"][:2]); rg = np.hypot(gt[:, 0] - a2[0], gt[:, 1] - a2[1])
        far = acc & (rg >= 3)
        st = np.column_stack([gt[:, :3], np.zeros(len(gt))])
        ob0, _ = los.observe(los.channel(st, C.CASES[case]))
        los_rms = float(np.sqrt(np.mean((of["s"] - ob0["s"])[far] ** 2)))
        for name, kw in PERTURB:
            kw = dict(kw); kw.setdefault("max_depth", depth)
            m = ReflectiveFFD(base, material_mode=mode, **kw)
            ob, _ = m.observe(m.channel(st, C.CASES[case]))
            res = of["s"] - ob["s"]; sl = C.smooth(res)
            rms = float(np.sqrt(np.mean(res[far] ** 2)))
            rows.append(dict(case=case, perturbation=name, far_rms=rms, far_slow_rms=float(np.sqrt(np.mean(sl[far] ** 2))),
                             tap_agree=float(np.mean(ob["index"][far] == of["index"][far])), los_far_rms=los_rms,
                             retained_reduction=1 - rms / los_rms))
            print(rows[-1], flush=True)
        pd.DataFrame(rows).to_csv(C.OUT / "V3_ROBUSTNESS.csv", index=False)
    C.write_manifest("V3", dict(cases=cases, variant=v1["chosen_variant"], perturbations=[p[0] for p in PERTURB]), ["V3_ROBUSTNESS.csv"])


if __name__ == "__main__":
    main()
