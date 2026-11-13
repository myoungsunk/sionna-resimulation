"""Diagnose frozen LoS/LUT residuals using the authenticated antenna banks."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from scipy.interpolate import RegularGridInterpolator

BLOCK = "results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449"
LUT = "results/DRIVE_SIM_20261007/CAUSE_CHECK_A23_EXECUTION_20261010"
BANKS = {
    "LP_plus45_bank.npz": "b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b",
    "LP_minus45_bank.npz": "39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9",
}


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def summary(x):
    return dict(mean=float(np.mean(x)), median_abs=float(np.median(np.abs(x))),
                p90_abs=float(np.quantile(np.abs(x), .9)), p95_abs=float(np.quantile(np.abs(x), .95)),
                max_abs=float(np.max(np.abs(x))), over_020=int(np.sum(np.abs(x) > .02)),
                rmse=float(np.sqrt(np.mean(x**2))))


def phase_adjust(h, f, d0, d1, c0):
    scale = d0 / d1
    phase = np.exp(-2j * np.pi * f * (d1 - d0) / c0)
    return h * (scale * phase)[:, None, None]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--banks", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.input / LUT / "retrieved/source/src"))
    from qclean_uwb.drivesim import hs_lut as L, observation as O, pattern_apply as P

    banks = []
    for name, expected in BANKS.items():
        path = args.banks / name
        if sha(path) != expected:
            raise ValueError(f"Wrong bank hash: {path}")
        with np.load(path, allow_pickle=False) as z:
            banks.append(P.Bank(dict(z)))
    b = args.input / BLOCK / "BLOCK_C"
    freqs = np.load(args.input / BLOCK / "freqs_hz.npy", allow_pickle=False)
    if not all(np.array_equal(f, freqs) for f in (banks[0].freqs_hz, banks[1].freqs_hz,
                                                 np.load(b / "freqs_hz.npy", allow_pickle=False))):
        raise ValueError("Frequency bins differ")
    values = np.load(args.input / LUT / "INPUTS/hs_lut_2deg.npy", allow_pickle=False)
    th, ph = np.arange(0., 91., 2.), np.arange(-180., 180., 2.)
    lut = L.HsLut(dict(theta_deg=th, phi_deg=ph, s=values))
    periodic = np.concatenate((values, values[:, :, :1]), axis=2)
    periodic = np.concatenate((periodic, periodic[:, :1, :]), axis=1)
    interp = RegularGridInterpolator((th, np.r_[ph, 180.], np.r_[ph, 180.]), periodic)
    provenance = {"spec_commit": "1ce68f358aee003116be5e077ac5bbb4a5f2b7d9",
                  "block_commit": "047cce2acb244ec2d7badc563345ccdd1f48613f",
                  "lut_commit": "f9a7691c14a0c1750790a998de7a91c5d9eb918b",
                  "python": sys.version, "numpy": np.__version__, "command": sys.argv,
                  "bank_sha256": BANKS, "cases": {}}
    node_rng = np.random.default_rng(20261113)
    i, j, k = [node_rng.integers(0, n, 160) for n in (len(th), len(ph), len(ph))]
    node_direct = np.array([L.los_s_direct(banks, th[ii], ph[jj], ph[kk]) for ii, jj, kk in zip(i, j, k)])
    provenance["160_grid_node_consistency"] = summary(node_direct - values[i, j, k])
    for case in json.loads((b / "CASES.json").read_bytes()):
        name = case["case"]
        if name not in {"R2_aB_m0", "R2_aA_m0"}:
            continue
        fp = b / "FULL_RF" / f"H_{name}.npy"
        lp = b / f"H_LoS_{name}.npy"
        sp = b / name / "SAMPLES.json"
        actual_hashes = {"input_H_sha256": sha(fp), "H_sha256": sha(lp), "samples_sha256": sha(sp)}
        if any(actual_hashes[k] != case[k] for k in actual_hashes):
            raise ValueError(f"Input identity differs: {name}")
        if actual_hashes["samples_sha256"] != case["input_rf_poses_sha256"]:
            raise ValueError(f"Full RF pose identity differs: {name}")
        samples = json.loads(sp.read_bytes())
        if [p["pose_id"] for p in samples] != list(range(len(samples))):
            raise ValueError("Pose order differs")
        x, y, yaw = (np.array([p[k] for p in samples]) for k in ("x", "y", "yaw_body_deg"))
        xyz = np.column_stack((x, y, np.full_like(x, case["robot_z"])))
        anchor = case["anchor_xyz"]
        mount = case["mount_deg"]
        v = xyz - anchor
        d = np.linalg.norm(v, axis=1)
        unit = v / d[:, None]
        angles = L.geometry_angles(anchor, xyz, yaw + mount)
        reference = L.s_model(lut, anchor, case["robot_z"], x, y, np.radians(yaw), mount)
        independent_interp = interp(np.column_stack(angles))
        np.testing.assert_allclose(reference, independent_interp, atol=5e-14, rtol=0.)
        direct_actual = np.stack([L.los_h(banks, u, a, r) for u, a, r in zip(unit, yaw + mount, d)])
        direct_ref10 = np.stack([L.los_h(banks, u, a, L.D_REF_M) for u, a in zip(unit, yaw + mount)])
        recorded = np.load(lp, allow_pickle=False)
        recorded_ref10 = np.stack([phase_adjust(h, freqs, r, L.D_REF_M, L.C0) for h, r in zip(recorded, d)])
        measure = lambda h: O.observe(h, freqs, None, None, tx=0)
        rec, rec10 = measure(recorded), measure(recorded_ref10)
        da, d10 = measure(direct_actual), measure(direct_ref10)
        chain = {"recorded_actual_minus_lut": rec["s"] - reference,
                 "recorded_actual_minus_direct_actual": rec["s"] - da["s"],
                 "direct_actual_minus_direct_10m": da["s"] - d10["s"],
                 "direct_10m_minus_lut": d10["s"] - reference,
                 "recorded_10m_minus_lut": rec10["s"] - reference,
                 "recorded_10m_minus_direct_10m": rec10["s"] - d10["s"],
                 "recorded_actual_minus_recorded_10m": rec["s"] - rec10["s"],
                 "direct_actual_minus_lut": da["s"] - reference}
        np.testing.assert_allclose(chain["recorded_actual_minus_lut"],
                                   chain["recorded_actual_minus_direct_actual"]
                                   + chain["direct_actual_minus_direct_10m"]
                                   + chain["direct_10m_minus_lut"], atol=5e-15, rtol=0.)
        high = np.abs(chain["recorded_actual_minus_lut"]) > .02
        keys = tuple(chain)
        provenance["cases"][name] = {"input_sha256": actual_hashes, "poses": len(samples),
                "interpolation_max_abs_vs_scipy": float(np.max(np.abs(reference - independent_interp))),
                "all_poses": {k: summary(a) for k, a in chain.items()},
                "above_gate_pose_subset": {k: summary(a[high]) for k, a in chain.items()} if high.any() else {},
                "above_gate_pose_subset_count": int(high.sum()),
                "signed_dot_with_total_on_above_gate_subset": {
                    k: float(a[high] @ chain["recorded_actual_minus_lut"][high] /
                             (chain["recorded_actual_minus_lut"][high] @ chain["recorded_actual_minus_lut"][high]))
                    for k, a in chain.items()} if high.any() else {},
                "row_fields": list(keys)}
        with (args.out / f"PARITY_ROWS_{name}.csv").open("x", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["pose_id", "x", "y", "yaw_deg", "distance_m", "theta_deg", "phi_tx_deg", "phi_rx_deg",
                             "s_recorded", "s_lut", "s_direct_actual", "s_direct_10m", "s_recorded_10m", *keys])
            writer.writerows(zip(range(len(x)), x, y, yaw, d, *angles, rec["s"], reference,
                                 da["s"], d10["s"], rec10["s"], *chain.values()))
        print(name, {k: round(summary(a)["p90_abs"], 7) for k, a in chain.items()}, flush=True)
    for name in ("INPUTS/hs_lut_2deg.npy", "INPUTS/hs_lut_meta.json",
                 "retrieved/source/src/qclean_uwb/drivesim/hs_lut.py",
                 "retrieved/source/src/qclean_uwb/drivesim/observation.py",
                 "retrieved/source/src/qclean_uwb/drivesim/pattern_apply.py",
                 "retrieved/source/src/qclean_uwb/scenarios/corridor.py"):
        provenance.setdefault("lut_sha256", {})[name] = sha(args.input / LUT / name)
    provenance["frequencies_sha256"] = sha(args.input / BLOCK / "freqs_hz.npy")
    provenance["script_sha256"] = sha(Path(__file__))
    (args.out / "PARITY_DIAG.json").write_text(json.dumps(provenance, indent=2, allow_nan=False) + "\n",
                                                encoding="utf-8")


if __name__ == "__main__":
    main()

