"""S3: realised SNR, s-noise and detection rate versus the placeholder SNR definition ("X dB at 10 m LoS, unit-gain free space").

Used once, before the first filter run, to fix the two SNR levels of the experiment matrix (PREREG deferred item).

  python scripts/drive_sim/snr_calibration.py --s1 S1 --h-dir S2 --out S3/SNR_CALIBRATION.json --snr-db 60 50 40 30 20 10
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.drivesim import experiment as E  # noqa: E402
from qclean_uwb.drivesim import observation as O  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--s1", type=Path, required=True)
    ap.add_argument("--h-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--snr-db", type=float, nargs="+", required=True)
    ap.add_argument("--lateral", type=float, default=0.0)
    ap.add_argument("--mount", type=float, default=0.0)
    ap.add_argument("--draws", type=int, default=20)
    ap.add_argument("--stride", type=int, default=5)
    args = ap.parse_args()
    with np.load(ROOT / "LP_plus45_bank.npz") as z:
        freqs = z["freqs_hz"]
    h = np.load(args.h_dir / f"H_y{args.lateral:g}_m{args.mount:g}.npy", mmap_mode="r")
    w = E.make_world(args.s1 / f"timeline_y{args.lateral:g}_Tnone.csv", h, freqs, args.lateral, args.mount, None)
    sel = np.arange(0, len(w.rows), args.stride)
    hc = w.h[sel]
    clean = O.observe(hc, freqs, None, None)
    x = np.array([w.rows[i]["x"] for i in sel])
    out = {}
    for snr in args.snr_db:
        nv = O.noise_var_from_snr(snr)
        s_all, r_all, det = [], [], []
        for d in range(args.draws):
            o = O.observe(hc, freqs, nv, np.random.default_rng([d, int(snr) + 1000]))
            s_all.append(o["s"] - clean["s"])
            r_all.append(o["range_m"] - clean["range_m"])
            det.append(o["detected"])
        s_all, r_all, det = np.array(s_all), np.array(r_all), np.array(det)
        real = O.realised_snr_db(hc, nv)
        near, far = x < 10.0, x >= 10.0
        out[f"{snr:g}"] = dict(noise_var=nv, detect_rate=float(det.mean()), detect_rate_far=float(det[:, far].mean()) if far.any() else None,
                               realised_snr_db_median=float(np.median(real)), realised_snr_db_p10=float(np.percentile(real, 10)),
                               s_noise_std=float(np.nanstd(s_all)), s_noise_std_far=float(np.nanstd(s_all[:, far])) if far.any() else None,
                               range_noise_std_m=float(np.nanstd(r_all)), first_path_index_flip_rate=float(np.mean((o["index"] != clean["index"]))))
        print(snr, {k: (round(v, 4) if isinstance(v, float) else v) for k, v in out[f"{snr:g}"].items()}, flush=True)
    args.out.write_text(json.dumps(dict(definition="noise_var = free-space |H|^2 of a unit-gain 10 m link at 6.5 GHz / 10^(SNR/10)", lateral=args.lateral,
                                        mount=args.mount, samples=len(sel), draws=args.draws, levels=out), indent=1))


if __name__ == "__main__":
    main()
