"""A15: how often did the pre-fix GSF split (shrink P[2,2] only) give an indefinite component covariance on real RF data (audit F08)?

  python scripts/drive_sim/gsf_psd_incidence.py --s1 S1 --h-dir S2 --lut-dir S4 --out DEV_RESULTS/GSF_PSD_INCIDENCE.json --seeds 5
Runs the production GSF (the fixed rule) on the R1 development H stores and evaluates, at every reseed, the legacy rule on the same collapsed
Gaussian.  Reports counts only; it does not rerun or change any evaluation result.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.drivesim import experiment as E  # noqa: E402
from qclean_uwb.drivesim import filters as F  # noqa: E402
from qclean_uwb.drivesim import sensors as S  # noqa: E402
from qclean_uwb.drivesim.hs_lut import HsLut  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

_G: dict = {}
_LOG: list = []


def legacy_min_eig(cov, k):
    z = np.linspace(-1.5, 1.5, k)
    w = np.exp(-0.5 * z ** 2)
    w /= w.sum()
    vb = float((w * z ** 2).sum())
    P = cov.copy()
    P[2, 2] = cov[2, 2] * max(1.0 - vb, 0.05)
    return float(np.linalg.eigvalsh(0.5 * (P + P.T)).min())


_orig = F.DriveFilter.reseed


def reseed_logged(self, std_theta=None):
    mean, cov = self.mean_cov()
    if std_theta is not None:
        cov = cov.copy()
        cov[2, 2] = max(cov[2, 2], std_theta ** 2)
    _LOG.append(legacy_min_eig(cov, self.cfg.gsf_components))
    _orig(self, std_theta)


F.DriveFilter.reseed = reseed_logged


def work(args):
    seed, drift = args
    g = _G
    del _LOG[:]
    rows, _ = E.run_unit(g["worlds"], g["lut"], sensor=S.SensorNoise(), mismatch_sigma=0.18, anchor_xyz=g["anchor"], robot_z=g["robot_z"], range_offset=g["range_offset"],
                         snr_db=30.0, snr_idx=0, drift_idx=drift, seed=seed, compare_filters=True)
    return list(_LOG), sum(1 for r in rows if r["filter"] == "gsf"), sum(1 for r in rows if r["filter"] == "gsf" and r.get("error"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--s1", type=Path, required=True)
    ap.add_argument("--h-dir", type=Path, required=True)
    ap.add_argument("--lut-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--nproc", type=int, default=3)
    args = ap.parse_args()
    setup = CorridorSetup()
    doc = json.loads((args.lut_dir / "hs_lut_meta.json").read_text())
    lut = HsLut(dict(theta_deg=np.array(doc["meta"]["theta_deg"]), phi_deg=np.arange(-180.0, 180.0, doc["meta"]["phi_deg"][2]), s=np.load(args.lut_dir / "hs_lut_2deg.npy")))
    with np.load(ROOT / "LP_plus45_bank.npz") as z:
        freqs = z["freqs_hz"]
    E.POS_PROCESS_STD = 0.01
    _G.update(lut=lut, anchor=tuple(setup.anchor_position), robot_z=setup.robot_antenna_z_m, range_offset=doc["range_bias"]["mean_m"])
    tag = lambda v: "none" if v is None else f"{v:g}"  # noqa: E731
    mins, gsf_runs, gsf_err = [], 0, 0
    for lat, mount in ((0.35, 0.0), (0.35, 45.0)):
        h = np.load(args.h_dir / f"H_y{lat:g}_m{mount:g}.npy", mmap_mode="r")
        _G["worlds"] = {p: E.make_world(args.s1 / f"timeline_y{lat:g}_T{tag(p)}.csv", h, freqs, lat, mount, p) for p in (None, 20.0)}
        with mp.get_context("fork").Pool(args.nproc) as pool:
            for log, n, ne in pool.imap(work, [(s, d) for d in (0, 1, 2) for s in range(args.seeds)], chunksize=1):
                mins += log
                gsf_runs += n
                gsf_err += ne
        print("done", lat, mount, len(mins), flush=True)
    a = np.array(mins)
    out = dict(reseed_calls=int(a.size), gsf_runs=gsf_runs, gsf_runs_with_error=gsf_err, legacy_indefinite_calls=int((a < -1e-12).sum()),
               legacy_min_eig_min=float(a.min()) if a.size else None, note="legacy rule evaluated on the collapsed Gaussian at each reseed; fixed rule is PSD by construction (tests)")
    args.out.write_text(json.dumps(out, indent=1))
    print(json.dumps(out))


if __name__ == "__main__":
    main()
