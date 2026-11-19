"""Self-check preserved baseline traces and paired trace integrity; no EKF replay."""
import argparse
import json
from pathlib import Path
import numpy as np


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--prior-baseline", type=Path, required=True)
    args = ap.parse_args()
    checks, exposure = [], []
    for route in ("R2", "R4", "R5"):
        for arm in ("H2", "H2S", "F2SKRWV"):
            oldpath = args.prior_baseline / f"{route}_{arm}.npz"
            newpath = args.out / "B0/seed30/traces" / oldpath.name
            with np.load(oldpath) as old, np.load(newpath) as new:
                for key in ("x", "P", "mask", "t", "pose_id", "Reff", "prior", "Pprior"):
                    if key in old and key in new:
                        assert np.array_equal(old[key], new[key]), (route, arm, key)
                        checks.append(dict(route=route, arm=arm, field=key, bit_exact=True))
    finite_files = 0
    for condition in ("B0", "L2_GYRO_ARW"):
        for seed in range(30, 50):
            for route in ("R2", "R4", "R5"):
                root = args.out / condition / f"seed{seed}/traces"
                with np.load(f"/home/claude/m8/inputs_ext/{condition}/seed{seed}/{route}_online.npz") as packet:
                    for arm in ("H2", "H2S", "F2SKRWV", "F2SKRWV_FAR_K"):
                        with np.load(root / f"{route}_{arm}.npz") as trace:
                            assert np.array_equal(packet["t"], trace["t"])
                            assert np.array_equal(packet["pose_id"], trace["pose_id"])
                            for key in trace.files:
                                if np.issubdtype(trace[key].dtype, np.number):
                                    assert np.isfinite(trace[key]).all(), (condition, seed, route, arm, key)
                            finite_files += 1
                with np.load(root / f"{route}_F2SKRWV.npz") as old, np.load(root / f"{route}_F2SKRWV_FAR_K.npz") as new:
                    eligible = (old["distance"] >= 6.) & (old["distance"] < 10.)
                    idx = np.flatnonzero(eligible)
                    first = int(idx[0]) if len(idx) else len(eligible)
                    # Before the intervention, both recursive filters must coincide exactly.
                    for key in ("x", "P", "mask", "Reff", "prior", "Pprior"):
                        if key in old:
                            assert np.array_equal(old[key][:first], new[key][:first]), (condition, seed, route, key)
                    exposure.append(dict(condition=condition, seed=seed, route=route,
                        packets=len(eligible), baseline_6_to_10m_packets=int(eligible.sum()),
                        candidate_6_to_10m_packets=int(((new["distance"] >= 6.) & (new["distance"] < 10.)).sum()),
                        identical_prefix_packets=first))
    assert finite_files == 480 and len(exposure) == 120
    path = args.out / "summary/TRACE_SELF_CHECK.json"
    assert not path.exists()
    path.write_text(json.dumps(dict(independent_audit=False, kind="IMPLEMENTER_SELF_CHECK",
        baseline_reference="Previous base246 B0 seed30, historical frozen trace unavailable",
        baseline_bit_exact_checks=checks, all_numeric_finite_trace_files=finite_files,
        input_time_pose_id_equal_files=finite_files, intervention_exposure=exposure,
        scientific_adoption_pass=False), indent=2), encoding="utf-8")
    print("PASS: previous baseline traces bit exact; 480 finite and input-aligned traces; 120 paired prefixes")


if __name__ == "__main__":
    main()
