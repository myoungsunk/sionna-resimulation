"""Evaluate frozen G-OBS gates and extract the preregistered spatial inputs."""
from argparse import ArgumentParser
from concurrent.futures import ProcessPoolExecutor
import math
from pathlib import Path
import time

import numpy as np
from run_step1 import dump, verify, get_groups
from run_step2 import CASES
from s1_analysis import _spatial_rows
from v32_observation import ObservationCase, extended_sigma_axis

def run_case(args):
    root, banks, name = args
    start = time.monotonic()
    case = ObservationCase(root, name, banks)
    result = case.parity()
    sigma = [case.projected_sigma(group, k) for group in case.groups for k in (0, 50)]
    spatial = spatial_inputs(case)
    detail, rho = _spatial_rows({name: spatial})
    detail = {key: value for key, value in detail[0].items()
              if not isinstance(value, float) or math.isfinite(value)}
    print(name, result, rho[name], "seconds", round(time.monotonic()-start, 1), flush=True)
    return name, result, min(sigma), max(sigma), detail, rho[name], len(case.groups)

def spatial_inputs(case):
    from run_step1 import BLOCK, LUT
    from qclean_uwb.drivesim import hs_lut, observation
    import json
    source = case.inputs.root / BLOCK / "BLOCK_C"
    samples = json.loads((source / case.name / "SAMPLES.json").read_bytes())
    x, y, yaw = (np.asarray([r[key] for r in samples]) for key in ("x", "y", "yaw_body_deg"))
    cases = json.loads((source / "CASES.json").read_bytes())
    row = next(c for c in cases if c["case"] == case.name)
    freqs = np.load(case.inputs.root / BLOCK / "freqs_hz.npy", allow_pickle=False)
    arrays = [source / "FULL_RF" / f"H_{case.name}.npy", source / f"H_LoS_{case.name}.npy"]
    full, los = [observation.observe(np.load(p, allow_pickle=False), freqs, None, None, tx=0)["s"]
                 for p in arrays]
    lut = hs_lut.HsLut(dict(theta_deg=np.arange(0., 91., 2.), phi_deg=np.arange(-180., 180., 2.),
                           s=np.load(case.inputs.root / LUT / "INPUTS/hs_lut_2deg.npy", allow_pickle=False)))
    _, jac = hs_lut.s_model(lut, row["anchor_xyz"], row["robot_z"], x, y, np.radians(yaw),
                            row["mount_deg"], with_jac=True)
    return dict(x=x, y=y, yaw_deg=yaw, s_full=full, s_los=los, jac_yaw=jac[:, 2],
                sweep_indices=get_groups(samples))

def main():
    p = ArgumentParser()
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--banks", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--workers", type=int, default=1)
    a = p.parse_args()
    verify(a.inputs, Path(__file__).resolve().parent / "INPUTS_CHECK_1ce68f3.json")
    by_case = {}
    names = (*CASES, "R2_aA_m45")
    with ProcessPoolExecutor(max_workers=a.workers) as executor:
        for name, gates, low, high, spatial, rho, n in executor.map(
                run_case, ((a.inputs, a.banks, name) for name in names)):
            by_case[name] = dict(gates=gates, sigma_min=low, sigma_max=high,
                                 n90=n, spatial=spatial, rho=rho)
            dump(a.out / "S1P_OBS_PREFLIGHT_PARTIAL.json", by_case)
    primary = [c for c in CASES if all(by_case[c]["gates"][g]["passed"]
                                      for g in ("G-OBS-1", "G-OBS-2"))]
    sigma_max = max(by_case[c]["sigma_max"] for c in CASES)
    dump(a.out / "S1P_OBS_PREFLIGHT.json", dict(by_case=by_case, primary=primary,
         sigma_min=min(by_case[c]["sigma_min"] for c in CASES),
         sigma_max=sigma_max, sigma_axis=extended_sigma_axis(sigma_max).tolist()))

if __name__ == "__main__":
    main()
