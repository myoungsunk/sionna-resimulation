"""Information boundary of actual P3 preparation, synthetic residuals only."""
import argparse
import copy
from pathlib import Path
import numpy as np
import covariance_core_v2 as C
from p0_inputs_v2 import put, sha
from p1_design_v2 import components
from run_covariance import prepare_donors


def run(out):
    n = 40; t = np.arange(n)*.2; arc = t*.2
    a = np.where(np.arange(n)%2, -.7, .7); yaw = np.zeros(n)
    geometry = dict(t=t, arc_m=arc, yaw_arc_rad=yaw, a_truth=a, rho_m=np.ones(n)*7)
    ds = {r: dict(geometry, e_rf=np.sin(t+k)*.05) for k, r in enumerate(["R2", "R4", "R5"])}
    cmp = components(geometry, np.ones(n, bool))
    split = dict(donor_routes=["R2", "R5"], donor_valid_indices={r: list(range(n)) for r in ["R2", "R5"]},
                 components_donor={r: cmp for r in ["R2", "R5"]})
    before = prepare_donors(ds, split, "R4")
    perturbed = copy.deepcopy(ds); perturbed["R4"]["e_rf"] += np.arange(n)*1000
    after = prepare_donors(perturbed, split, "R4")
    assert before[0] == after[0] and before[1] == after[1] and before[3] == after[3]
    for x, y in zip(before[2], after[2], strict=True):
        for key in ["K", "a", "e", "arc", "yaw"]: assert np.array_equal(x[key], y[key])
    assert C.fit_models(before[2]) == C.fit_models(after[2])
    try: prepare_donors(ds, dict(split, donor_routes=["R4"]), "R4")
    except ValueError as e: assert str(e) == "HOLDOUT_IN_DONORS"
    else: raise AssertionError("holdout entered training")
    out.mkdir(parents=True, exist_ok=False)
    put(out/"RUNNER_INFORMATION_BARRIER.json", dict(passed=True, synthetic_only=True,
        actual_prepare_donors_unchanged_under_holdout_future_perturbation=True,
        holdout_in_donors_rejected=True, same_donor_fit=True,
        sources={p.name: sha(p) for p in [Path(__file__), Path(__file__).with_name("run_covariance.py"), Path(__file__).with_name("covariance_core_v2.py")]}))
    print("Actual runner donor boundary PASS (synthetic)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--out", type=Path, required=True); run(ap.parse_args().out)
