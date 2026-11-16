"""Trace-only audit of KS/KI follow-up results (no replay).

Usage: python audit_traces.py --release DIR_WITH_{R2,R4,R5}_B0_Full_10__evaluator.npz
Reads saved traces under INTEGRITY_DIAG_001 (Git LFS) and prints, per route/arm:
heading95, RMSE, sign-weighted heading-update contributions (s, r, prediction),
cross-track error/SD before each anchor pass and mirror-side flips.
"""
import argparse
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares

ROOT = Path(__file__).resolve().parent.parent
WRAP = lambda v: np.angle(np.exp(1j * v))
ARMS = {
    "LORO": "attempt_02/d5/B_B0_{r}.npz",
    "E0": "attempt_02/d0/B_B0_{r}.npz",
    "C5_distance": "continuation_checks_c1_c8/run_01/C5_{r}_distance.npz",
    "C5_conservative": "continuation_checks_c1_c8/run_01/C5_{r}_conservative.npz",
    "C4_norm_full": "continuation_checks_c1_c8/run_c4_retry_03/C4_{r}_norm_full.npz",
}
R4_ONLY = {f"V3_{a}": f"continuation_ks/run_03/V3_{a}.npz" for a in ("a", "b", "c", "a_prime")}
R4_ONLY["C1_KI"] = "continuation_checks_c1_c8/run_01/C1_R4_KI.npz"


def anchor(d):
    return least_squares(lambda a: np.hypot(*(d["x"][:-1, :2] - a).T) - d["rho_before"][1:], [10., 0.]).x


def analyze(route, label, d, truth):
    a = anchor(d)
    eh = WRAP(d["x"][:, 2] - truth[:, 2])
    zh = eh / np.sqrt(d["P"][:, 2, 2])
    sgn = np.sign(WRAP(d["prior"][:, 2] - truth[:, 2]))
    pred = np.r_[0., WRAP((d["prior"][1:, 2] - d["x"][:-1, 2]) - (truth[1:, 2] - truth[:-1, 2]))]
    us, ur = d["K"][:, 2, 1] * d["nu"][:, 1], d["K"][:, 2, 0] * d["nu"][:, 0]
    ex = d["x"][:, :2] - truth[:, :2]
    x = truth[:, 0]
    passes = [i for i in range(1, len(x)) if (x[i - 1] - a[0]) * (x[i] - a[0]) <= 0]
    before = [max(0, i - 25) for i in passes]
    pre = [(round(100 * ex[i, 1]), round(100 * np.sqrt(d["P"][i, 1, 1]))) for i in before]
    flips = [bool(np.sign(d["x"][min(i + 10, len(x) - 1), 1] - a[1]) != np.sign(truth[min(i + 10, len(x) - 1), 1] - a[1]))
             for i in passes]
    print(f"{route} {label:16s} h95={np.mean(np.abs(zh) < 1.96):.3f} "
          f"hRMSE={np.rad2deg(np.sqrt(np.mean(eh**2))):.2f}deg xyRMSE={100*np.sqrt(np.mean(np.sum(ex**2, 1))):.1f}cm | "
          f"error-ward heading: s {np.rad2deg(np.sum(-sgn*us)):+.1f} r {np.rad2deg(np.sum(-sgn*ur)):+.1f} "
          f"pred {np.rad2deg(np.sum(sgn*pred)):+.1f}deg | y_err/sd_y 5s before passes [cm] {pre} flips {flips}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    args = parser.parse_args()
    for route in ("R2", "R4", "R5"):
        truth = np.load(Path(args.release) / f"{route}_B0_Full_10__evaluator.npz")["truth"]
        arms = dict(ARMS, **(R4_ONLY if route == "R4" else {}))
        for label, pattern in arms.items():
            path = ROOT / pattern.format(r=route)
            if not path.exists() or path.stat().st_size < 1000:
                print(route, label, "MISSING (fetch with git lfs pull)")
                continue
            analyze(route, label, np.load(path), truth)


if __name__ == "__main__":
    main()
