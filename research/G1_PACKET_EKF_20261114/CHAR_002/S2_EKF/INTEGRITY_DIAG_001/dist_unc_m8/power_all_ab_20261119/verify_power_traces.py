"""Self-check all-POWER mean, frozen variance rules, and original baseline traces."""
import argparse
import json
from pathlib import Path
import numpy as np
import run_power_all_ab as P


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--previous", type=Path, required=True)
    args = ap.parse_args()
    R = P.R
    B, table, _ = R.load_frozen()
    env = R.C.env()
    checks, exposure = [], []
    finite_files = 0
    for condition in P.A.CONDITIONS:
        for seed in range(30, 50):
            for route in R.ROUTES:
                root = args.out / condition / f"seed{seed}/traces"
                previous = args.previous / condition / f"seed{seed}/traces"
                for arm in ("H2", "H2S", R.BASE):
                    with np.load(previous / f"{route}_{arm}.npz") as old, np.load(root / f"{route}_{arm}.npz") as new:
                        for key in ("x", "P", "mask", "t", "pose_id", "Reff", "prior", "Pprior"):
                            assert np.array_equal(old[key], new[key]), (condition, seed, route, arm, key)
                            checks.append(dict(condition=condition, seed=seed, route=route,
                                               arm=arm, field=key, bit_exact=True))
                packet = R.C.packet(condition, seed, route)
                for arm in R.ARMS:
                    with np.load(root / f"{route}_{arm}.npz") as tr:
                        assert np.array_equal(packet["t"], tr["t"])
                        assert np.array_equal(packet["pose_id"], tr["pose_id"])
                        for key in tr.files:
                            if np.issubdtype(tr[key].dtype, np.number):
                                assert np.isfinite(tr[key]).all(), (condition, seed, route, arm, key)
                        finite_files += 1
                with np.load(root / f"{route}_{R.BASE}.npz") as old, np.load(root / f"{route}_{R.FAR}.npz") as tr:
                    # Reconstruct used means from the innovation, without using the callback.
                    h, _ = env["model"].batch(tr["prior"], env["spec"])
                    eta_prior = tr["alpha"] * np.r_[0., tr["eta"][:-1]]
                    prediction = h.copy()
                    prediction[:, 1] += tr["a"] * tr["gm_load"] * eta_prior
                    implied_mu = packet["z"] - prediction - tr["nu"]
                    expected_mu = np.c_[B[f"{route}/mu_r"], B[f"{route}/mu_s"]]
                    max_gap = float(np.max(np.abs(implied_mu - expected_mu)))
                    assert max_gap <= 1e-12, (condition, seed, route, max_gap)
                    bins = np.clip(np.searchsorted(table["edges"], tr["distance"], side="right") - 1,
                                   0, len(table["c1"]) - 1)
                    for key in ("c1", "c0"):
                        assert np.array_equal(tr[key], np.asarray(table[key])[bins])
                    for key in ("R_ref", "gyro_Q_rad2", "dt", "threshold"):
                        assert np.array_equal(old[key], tr[key]), (condition, seed, route, key)
                    exposure.append(dict(condition=condition, seed=seed, route=route,
                        packets=len(tr["t"]), power_mean_max_abs=max_gap,
                        candidate_lt3m=int((tr["distance"] < 3.).sum()),
                        candidate_3_to_6m=int(((tr["distance"] >= 3.) & (tr["distance"] < 6.)).sum()),
                        candidate_ge6m=int((tr["distance"] >= 6.).sum())))
    assert finite_files == 480 and len(checks) == 2880 and len(exposure) == 120
    data = dict(kind="IMPLEMENTER_SELF_CHECK", independent_audit=False,
        baseline_reference="Previous authorized far-Kriging baseline; historical original traces unavailable",
        baseline_bit_exact_checks=checks, finite_input_aligned_trace_files=finite_files,
        all_power_mean_and_frozen_variance_checks=exposure,
        power_mean_tolerance=1e-12, power_mean_max_abs=max(r["power_mean_max_abs"] for r in exposure),
        scientific_adoption_pass=False)
    P.write(args.out / "summary/TRACE_SELF_CHECK.json", data)
    print("PASS: 2880 bit-exact baseline arrays; 480 finite/input-aligned traces; 120 all-POWER mean and frozen-variance checks", flush=True)


if __name__ == "__main__":
    main()
