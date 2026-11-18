"""Three checks on the yaw estimate.

A. Does a denser yaw sweep help?  Sweep matching: the whole measured |s|(yaw) curve (known relative yaw steps, unknown absolute offset,
   within +-45 deg) is matched to the angle-model template.  Evaluated with sample spacings of 10 deg (all 19 points) up to 90 deg to see the
   trend and where it saturates (the measured sweeps are 10 deg apart, so finer than that cannot be tested).
B. Flat regions (curve near |s| = 1): is the weaker port the one that reflections contaminate most?
C. 0 deg versus 90 deg: with ideal ports a 90 deg turn swaps the ports, so |s|(0) = |s|(90).  How far is the real antenna from that?

  python scripts/corridor_flat_region_check.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import corridor_reflection_fit as crf  # noqa: E402
import corridor_shift_fit as sf  # noqa: E402
import corridor_template_compare as tc  # noqa: E402
import corridor_tx_angle_sweep as ta  # noqa: E402
from qclean_uwb.features.reflection_attribution import GROUPS  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402
from rt_cp_uwb_py.features import extract_first_path  # noqa: E402
from rt_cp_uwb_py.rf_channel_closure import contribution_cir  # noqa: E402

YAWS = sf.YAWS
WIDE = np.arange(-120, 481) / 2.0          # -60 .. 240 deg, 0.5 deg
FINE_DELTA = np.arange(-450, 451) / 10.0   # offset search +-45 deg


def wide_model(banks, setup, x, y, tn):
    theta, phi, rng = tc.angles_for(setup, x, y)
    ta.LINK_M = rng
    return np.array(ta.one(banks, np.radians(theta), np.radians(phi), rx_actual=True, tx_actual=True, yaws=WIDE)[tn]["s"])


def sweep_match(r_meas, yaws, s_model_wide):
    """Offset estimate: argmin over delta of sum (r_meas - |s_model(yaw + delta)|)^2."""
    sse = np.array([np.sum((r_meas - np.abs(np.interp(yaws + d, WIDE, s_model_wide))) ** 2) for d in FINE_DELTA])
    return float(FINE_DELTA[np.argmin(sse)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "CORRIDOR_SCAN_20261006" / "FLAT_REGION_CHECK.json")
    args = ap.parse_args()
    setup, banks = CorridorSetup(), sf.Banks()
    shift = json.loads((ROOT / "results/CORRIDOR_SCAN_20261006/SHIFT_FIT.json").read_text())
    positions = sorted(shift["positions"], key=lambda q: (q["x"], q["y"]))
    # ---------------- A. sweep matching with sparser and sparser samples
    steps = [10, 20, 30, 40, 60, 90]
    errA = {st: [] for st in steps}
    per_curve = []
    for p in positions:
        if p["off_boresight_deg"] < 1:
            continue
        for tn in sf.TX:
            r = np.abs(np.array(p["tx"][tn]["s_full"]))
            sm = wide_model(banks, setup, p["x"], p["y"], tn)
            row = dict(x=p["x"], y=p["y"], tx=tn)
            for st in steps:
                sub_err = []
                for phase in range(0, st, 10):
                    sel = np.where((YAWS - phase) % st == 0)[0] if st > 10 else np.arange(len(YAWS))
                    sel = sel[YAWS[sel] >= phase] if st > 10 else sel
                    if len(sel) < 3:
                        continue
                    sub_err.append(sweep_match(r[sel], YAWS[sel], sm))
                errA[st].extend(sub_err)
                row[f"err_step{st}"] = float(np.sqrt(np.mean(np.square(sub_err)))) if sub_err else None
            per_curve.append(row)
    A = {str(st): dict(rmse=float(np.sqrt(np.mean(np.square(v)))), median_abs=float(np.median(np.abs(v))), max_abs=float(np.max(np.abs(v))), n_estimates=len(v), mean_points=float(np.mean([len(np.where((YAWS - ph) % st == 0)[0]) if st > 10 else 19 for ph in range(0, st, 10)]))) for st, v in errA.items()}
    # ---------------- B. contamination of the weaker port in flat versus steep regions
    flat_yaws, steep_yaws = [0, 10, 80, 90, 100, 170, 180], [30, 40, 50, 60, 120, 130, 140, 150]
    kb = {"flat": dict(weak=[], strong=[], gap_db=[]), "steep": dict(weak=[], strong=[], gap_db=[])}
    for p in positions:
        if p["off_boresight_deg"] < 1:
            continue
        z = np.load(ROOT / p["file"])
        Hg, *_ = crf.group_channels(z, setup)
        Hf = Hg.sum(0)
        idx = []
        for k in range(len(YAWS)):
            cir, t = contribution_cir(Hf[k], sf.FREQ)
            pk = np.abs(cir).max(0)
            rx, tx = np.unravel_index(pk.argmax(), pk.shape)
            idx.append(extract_first_path(cir[:, rx, tx], t)[0])
        C = np.zeros((len(GROUPS), len(YAWS), 2, 2), complex)
        for g in range(len(GROUPS)):
            for k in range(len(YAWS)):
                C[g, k] = contribution_cir(Hg[g, k], sf.FREQ)[0][idx[k]]
        refl = C[1:].sum(0)
        for t in (0, 1):
            for k, yaw in enumerate(YAWS):
                grp = "flat" if yaw in flat_yaws else ("steep" if yaw in steep_yaws else None)
                if grp is None:
                    continue
                a = np.abs(C[0, k, :, t])
                weak, strong = int(np.argmin(a)), int(np.argmax(a))
                kb[grp]["weak"].append(float(abs(refl[k, weak, t]) / a[weak]))
                kb[grp]["strong"].append(float(abs(refl[k, strong, t]) / a[strong]))
                kb[grp]["gap_db"].append(float(20 * np.log10(a[strong] / a[weak])))
    B = {g: dict(n=len(v["weak"]), median_gap_db=float(np.median(v["gap_db"])), median_contamination_weak_port=float(np.median(v["weak"])), median_contamination_strong_port=float(np.median(v["strong"])),
                 share_weak_port_contamination_above_0p2=float(np.mean(np.array(v["weak"]) > 0.2))) for g, v in kb.items()}
    # ---------------- C. 0 versus 90 degrees (swap symmetry), angle model, LoS only
    rows = []
    for th in (0, 20, 40, 60, 80):
        ta.LINK_M = 3.0
        r = ta.one(banks, np.radians(th), 0.0, rx_actual=True, tx_actual=True, yaws=np.array([0.0, 90.0, 180.0]))
        for tn in sf.TX:
            v = r[tn]
            s0, s90, s180 = v["s"]
            rows.append(dict(theta=th, tx=tn, s0=s0, s90=s90, s180=s180, abs0=abs(s0), abs90=abs(s90), abs180=abs(s180), swap_asymmetry=s0 + s90,
                             d_port1_90_vs_port2_0_db=v["p1_db"][1] - v["p2_db"][0], d_port2_90_vs_port1_0_db=v["p2_db"][1] - v["p1_db"][0]))
    # the same three yaws at the real coordinates (simulated, all paths) for the x scan
    real = [dict(x=p["x"], y=p["y"], tx=tn, off=p["off_boresight_deg"], abs0_los=abs(p["tx"][tn]["s_los"][0]), abs90_los=abs(p["tx"][tn]["s_los"][9]), abs180_los=abs(p["tx"][tn]["s_los"][18]),
                 abs0_full=abs(p["tx"][tn]["s_full"][0]), abs90_full=abs(p["tx"][tn]["s_full"][9]), abs180_full=abs(p["tx"][tn]["s_full"][18])) for p in positions for tn in sf.TX]
    args.out.write_text(json.dumps(dict(A=A, A_per_curve=per_curve, B=B, C=rows, C_real=real, single_sample_oracle_rmse=4.82), indent=1))
    print("A. sweep matching, offset RMSE by sample spacing:", {k: (round(v["rmse"], 2), round(v["mean_points"], 1)) for k, v in A.items()})
    print("B.", json.dumps({g: {k: round(v, 3) for k, v in d.items()} for g, d in B.items()}))
    for r in rows:
        print(f"C. theta {r['theta']:2d} {r['tx'][3:]}: |s|(0) {r['abs0']:.3f} |s|(90) {r['abs90']:.3f} |s|(180) {r['abs180']:.3f} | s(0)+s(90) {r['swap_asymmetry']:+.3f} | P1(90)-P2(0) {r['d_port1_90_vs_port2_0_db']:+.1f} dB, P2(90)-P1(0) {r['d_port2_90_vs_port1_0_db']:+.1f} dB")


if __name__ == "__main__":
    main()
