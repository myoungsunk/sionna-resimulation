"""Fit reflection-distorted yaw-sweep curves and attribute the distortion to actual reflection paths.

For every simulated robot position (the original four plus the x/y scans):
  1. classify each simulated path by delay (image method) into LoS / floor / ceiling / side walls / end walls / multi-bounce;
  2. rebuild the channel per group; at the first-path tap used by the project chain, c = c_los + sum_g c_g;
  3. FP-power ratio r(yaw) for the full channel, LoS only, and LoS + one group at a time;
  4. fit r = m |cos 2(yaw - yaw0)| (LoS only and full) and regress the full distortion on the single-group distortions.

  python scripts/corridor_reflection_fit.py
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from rt_cp_uwb_py.features import extract_first_path  # noqa: E402
from rt_cp_uwb_py.rf_channel_closure import contribution_cir  # noqa: E402
from qclean_uwb.features.port_ratio import port_difference_ratio  # noqa: E402
from qclean_uwb.features.reflection_attribution import C0, GROUPS, classify_paths, fit_abs_cos  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

TX = ("LP_plus45", "LP_minus45")
FREQ = 6250400000.0 + 1950000.0 * np.arange(257)
REFL = GROUPS[1:]


def find_inputs():
    paths = sorted(glob.glob(str(ROOT / "results/CORRIDOR_SWEEP_20261006/pos*/position_*_sweep.npz")))
    paths += sorted(glob.glob(str(ROOT / "results/CORRIDOR_SCAN_20261006/*/*_sweep.npz")))
    return [Path(p) for p in paths]


def group_channels(z, setup):
    """H per group, shape (n_group, yaw, bin, 2, 2), and the label array."""
    n_yaw, n_bin = len(z["yaw_deg"]), len(z["bin_index"])
    off, tau, a = z["offsets"], z["tau_cat"], z["a_cat"]
    counts = np.diff(off)
    call = np.repeat(np.arange(n_yaw * n_bin), counts)
    label, order, table = classify_paths(tau, z["anchor_m"], z["robot_antenna_m"], setup.length_m, setup.y_half, setup.height_m)
    assert (label >= 0).all(), "UNMATCHED_PATHS"
    yi, bi = call % n_yaw, call // n_yaw
    phasor = np.moveaxis(a, -1, 0) * np.exp(-2j * np.pi * z["freqs_hz"][bi] * tau)[:, None, None]
    out = np.zeros((len(GROUPS), n_yaw, n_bin, 2, 2), complex)
    for g in range(len(GROUPS)):
        m = label == g
        np.add.at(out[g], (yi[m], bi[m]), phasor[m])
    return out, label, order, call, table


def ratios(c, t):
    """FP-power ratio of port-pair for TX port ``t`` from c[..., rx, tx]."""
    return port_difference_ratio(np.abs(c[..., 0, t]) ** 2, np.abs(c[..., 1, t]) ** 2)


def analyse(npz: Path, setup: CorridorSetup) -> dict:
    z = np.load(npz)
    yaws = z["yaw_deg"]
    Hg, label, order, call, table = group_channels(z, setup)
    Hfull = Hg.sum(0)
    # The stored H used a float32 phase (about 3e-5 relative); the group sums here use a float64 phase.
    assert np.abs(Hfull - z["H"]).max() <= 1e-3 * np.abs(z["H"]).max(), "GROUP_SUM_MISMATCH"
    idx = []
    for k in range(len(yaws)):
        cir, t = contribution_cir(Hfull[k], FREQ)
        peak = np.abs(cir).max(0)
        rx, tx = np.unravel_index(peak.argmax(), peak.shape)
        idx.append(extract_first_path(cir[:, rx, tx], t)[0])
    idx = np.array(idx)
    C = np.zeros((len(GROUPS), len(yaws), 2, 2), complex)  # first-path-tap field per group
    for g in range(len(GROUPS)):
        for k in range(len(yaws)):
            C[g, k] = contribution_cir(Hg[g, k], FREQ)[0][idx[k]]
    c_los, c_full = C[0], C.sum(0)
    x, y = (float(v) for v in z["robot_xy_m"])
    tau_los = table[()]
    # Excess delay of the first path in each reflection group (ns): from the image-method table, which the simulation matched exactly.
    excess = {}
    for name, members in {"floor": ("floor",), "ceiling": ("ceiling",), "side_walls": ("wall_y_neg", "wall_y_pos"), "end_walls": ("end_x_min", "end_x_max")}.items():
        excess[name] = min(table[(m,)] for m in members) / 1e0 - tau_los
    excess["multi_bounce"] = min(v for s, v in table.items() if len(s) >= 2) - tau_los
    excess = {k: v * 1e9 for k, v in excess.items()}
    eps = {GROUPS[g]: float(np.sqrt((np.abs(C[g]) ** 2).sum() / (np.abs(c_los) ** 2).sum())) for g in range(1, len(GROUPS))}
    eps["all_reflections"] = float(np.sqrt((np.abs(c_full - c_los) ** 2).sum() / (np.abs(c_los) ** 2).sum()))
    res = dict(file=str(npz.relative_to(ROOT)), x=x, y=y, n_paths_per_call=float(np.diff(z["offsets"]).mean()), first_path_index=[int(idx.min()), int(idx.max())],
               path_count_by_group={GROUPS[g]: int((label == g).sum()) for g in range(len(GROUPS))}, excess_delay_ns=excess, tap_leakage_ratio=eps, tx={})
    for t, tname in enumerate(TX):
        r_los, r_full = ratios(c_los, t), ratios(c_full, t)
        partial = {GROUPS[g]: ratios(c_los + C[g], t) for g in range(1, len(GROUPS))}
        d_full = r_full - r_los
        D = np.stack([partial[g] - r_los for g in REFL], axis=1)
        w, *_ = np.linalg.lstsq(D, d_full, rcond=None)
        resid = d_full - D @ w
        ss = float(np.sum(d_full ** 2))
        m_los, y0_los, e_los = fit_abs_cos(yaws, r_los)
        m_full, y0_full, e_full = fit_abs_cos(yaws, r_full)
        res["tx"][tname] = dict(
            ratio_los=r_los.tolist(), ratio_full=r_full.tolist(), ratio_partial={g: v.tolist() for g, v in partial.items()},
            distortion_rms=float(np.sqrt(np.mean(d_full ** 2))), distortion_max=float(np.abs(d_full).max()),
            distortion_rms_by_group={g: float(np.sqrt(np.mean((partial[g] - r_los) ** 2))) for g in REFL},
            fit_los=dict(m=m_los, yaw0_deg=y0_los, rmse=e_los), fit_full=dict(m=m_full, yaw0_deg=y0_full, rmse=e_full),
            delta_m=m_full - m_los, delta_yaw0_deg=float((y0_full - y0_los + 45) % 90 - 45),
            attribution=dict(weights=dict(zip(REFL, w.tolist())), r2=float(1 - np.sum(resid ** 2) / ss) if ss > 0 else None))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "CORRIDOR_SCAN_20261006" / "REFLECTION_FIT.json")
    args = ap.parse_args()
    setup = CorridorSetup()
    rows = [analyse(p, setup) for p in find_inputs()]
    rows.sort(key=lambda r: (r["y"] != 0.0, r["x"] != 7.0, r["x"], r["y"]))
    # Across-position association between distortion and the reflection-path metrics.
    assoc = {}
    for name in ("distortion_rms", "delta_m"):
        v = np.array([np.mean([r["tx"][t][name] for t in TX]) for r in rows])
        assoc[name] = {k: float(spearmanr(v, [r["tap_leakage_ratio"][k] for r in rows]).statistic) for k in rows[0]["tap_leakage_ratio"]}
        assoc[name].update({f"excess_delay_{k}": float(spearmanr(v, [r["excess_delay_ns"][k] for r in rows]).statistic) for k in rows[0]["excess_delay_ns"]})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(dict(groups=list(GROUPS), positions=rows, spearman_across_positions=assoc, n_positions=len(rows)), indent=1))
    for r in rows:
        a = r["tx"][TX[0]]; b = r["tx"][TX[1]]
        print(f"({r['x']:5.2f},{r['y']:5.2f}) dist_rms {a['distortion_rms']:.3f}/{b['distortion_rms']:.3f}  m_los {a['fit_los']['m']:.2f}->{a['fit_full']['m']:.2f} y0 {a['fit_los']['yaw0_deg']:+5.1f}->{a['fit_full']['yaw0_deg']:+5.1f}  "
              f"eps all {r['tap_leakage_ratio']['all_reflections']:.2f} floor {r['tap_leakage_ratio']['floor']:.2f} ceil {r['tap_leakage_ratio']['ceiling']:.2f} wall {r['tap_leakage_ratio']['side_walls']:.2f} end {r['tap_leakage_ratio']['end_walls']:.2f} multi {r['tap_leakage_ratio']['multi_bounce']:.2f}  "
              f"dt floor {r['excess_delay_ns']['floor']:.2f} wall {r['excess_delay_ns']['side_walls']:.2f}  attr R2 {a['attribution']['r2']:.2f}/{b['attribution']['r2']:.2f}")


if __name__ == "__main__":
    main()
