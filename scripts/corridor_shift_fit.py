"""Fit each yaw-sweep curve as the ideal curve with an x-shift and a y-shift, and find what causes each shift.

Signed port ratio  s(yaw) = (P1 - P2) / (P1 + P2)  of the first-path powers; the plotted metric is |s|.
Ideal on-axis curve: s = sigma * cos(2 yaw) with sigma = -1 (anchor TX +45) or +1 (TX -45).
Fit:  s(yaw) = B + sigma * A * cos(2 (yaw - yaw0))      -> yaw0 = x-shift (deg), B = y-shift, A = amplitude.
(Linear least squares on 1, cos 2yaw, sin 2yaw.)

Causes, by sequential substitution on the first-path tap field c = c_los + sum_g c_g:
  * LoS-level: ideal -> LoS only.  Counterfactual LoS channels built from the FFD banks with the validated Cartesian
    contraction (anchor pattern at boresight / robot pattern at boresight / equal RX port gain) tell which part of
    the antenna-direction dependence moves the curve.
  * Multipath-level: LoS-only -> full, split into floor / ceiling / side walls / end walls / multi-bounce
    (groups identified by image-method delay).

  python scripts/corridor_shift_fit.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import corridor_reflection_fit as crf  # noqa: E402
from rt_cp_uwb_py.features import extract_first_path  # noqa: E402
from rt_cp_uwb_py.rf_channel_closure import contribution_cir  # noqa: E402
from qclean_uwb.features.reflection_attribution import GROUPS  # noqa: E402
from qclean_uwb.scenarios.corridor import ANCHOR_ROTATION, CorridorSetup, rot_z  # noqa: E402

C0 = 299792458.0
TX = ("LP_plus45", "LP_minus45")
SIGMA = {"LP_plus45": -1.0, "LP_minus45": 1.0}
FREQ = crf.FREQ
YAWS = np.arange(0.0, 181.0, 10.0)
PSI = np.radians(YAWS)
REFL = GROUPS[1:]
K_FIELD = np.sqrt(2 * np.pi / 376.730313668)


def signed(c, t):
    p1, p2 = np.abs(c[..., 0, t]) ** 2, np.abs(c[..., 1, t]) ** 2
    return (p1 - p2) / (p1 + p2)


def fit_shift(s, sigma):
    """s = B + sigma*A*cos(2(yaw - yaw0)); returns dict with yaw0 (deg, (-90, 90]), B, A, residuals, and the fitted curve."""
    X = np.stack([np.ones_like(PSI), np.cos(2 * PSI), np.sin(2 * PSI)], 1)
    (B, a, b), *_ = np.linalg.lstsq(X, s, rcond=None)
    A = float(np.hypot(a, b))
    yaw0 = float(np.degrees(0.5 * np.arctan2(sigma * b, sigma * a)))
    fit = X @ np.array([B, a, b])
    r, rf = np.abs(s), np.abs(fit)
    ideal = np.abs(np.cos(2 * PSI))
    dev = float(np.sum((r - ideal) ** 2))
    return dict(yaw0_deg=yaw0, B=float(B), A=A, rmse_signed=float(np.sqrt(np.mean((fit - s) ** 2))), rmse_abs=float(np.sqrt(np.mean((rf - r) ** 2))),
                captured=None if dev < 1e-12 else float(1 - np.sum((rf - r) ** 2) / dev), fit_abs=rf.tolist())


class Banks:
    def __init__(self):
        man = json.loads((ROOT / "results/SIONNA_G2_FFD_NOFLIP_20260924_01a0d30b/bank/BANK_MANIFEST.json").read_text())["npz_sha256"]
        self.b = []
        for n in ("LP_plus45", "LP_minus45"):
            p = ROOT / f"{n}_bank.npz"
            assert hashlib.sha256(p.read_bytes()).hexdigest() == man[p.name], f"BANK_SHA_MISMATCH {n}"
            z = np.load(p)
            self.b.append(dict(et=z["e_theta"], ep=z["e_phi"], th=z["theta_deg"], ph=z["phi_deg"]))

    def field(self, port, theta, phi):
        """E_theta, E_phi at (theta, phi) [rad] for all 257 bins (bilinear on the 1 deg grid)."""
        b = self.b[port]
        t = np.clip(np.degrees(theta), 0, 180) / 1.0
        p = (np.degrees(phi) + 180.0) % 360.0 / 1.0
        i, j = min(int(t), 179), min(int(p), 359)
        wt, wp = t - i, p - j
        out = []
        for arr in (b["et"], b["ep"]):
            out.append((1 - wt) * ((1 - wp) * arr[:, i, j] + wp * arr[:, i, j + 1]) + wt * ((1 - wp) * arr[:, i + 1, j] + wp * arr[:, i + 1, j + 1]))
        return np.stack(out, -1)  # (257, 2)

    def vectors(self, rot, d_world, force_boresight=False):
        """Cartesian field vectors (257, 2 ports, 3) of both ports for propagation direction d_world seen from an antenna with rotation rot."""
        d = np.asarray(rot).T @ d_world
        theta, phi = (0.0, 0.0) if force_boresight else (np.arccos(np.clip(d[2], -1, 1)), np.arctan2(d[1], d[0]))
        et = np.array([np.cos(theta) * np.cos(phi), np.cos(theta) * np.sin(phi), -np.sin(theta)])
        ep = np.array([-np.sin(phi), np.cos(phi), 0.0])
        out = []
        for port in (0, 1):
            e = self.field(port, theta, phi)
            out.append((e[:, :1] * et[None, :] + e[:, 1:] * ep[None, :]) @ np.asarray(rot).T * K_FIELD)
        return np.stack(out, 1)


def los_variant(banks, a_pos, r_pos, yaw, variant):
    """LoS-only H (257, rx, tx) built from the banks with the stated counterfactual."""
    k = r_pos - a_pos
    dist = float(np.linalg.norm(k))
    k = k / dist
    r_tx, r_rx = ANCHOR_ROTATION, rot_z(yaw)
    vt = banks.vectors(r_tx, k, force_boresight=variant in ("anchor_boresight", "both_boresight"))
    vr = banks.vectors(r_rx, -k, force_boresight=variant in ("robot_boresight", "both_boresight"))
    if variant == "robot_equal_gain":
        vr = vr / np.linalg.norm(vr, axis=-1, keepdims=True)
    if variant == "anchor_equal_gain":
        vt = vt / np.linalg.norm(vt, axis=-1, keepdims=True)
    amp = C0 / FREQ / (4 * np.pi * dist) * np.exp(-2j * np.pi * FREQ * dist / C0)
    return np.einsum("fic,fjc->fij", vr, vt) * amp[:, None, None]


VARIANTS = ("base", "anchor_boresight", "robot_boresight", "both_boresight", "robot_equal_gain", "anchor_equal_gain")


def fp_field_from_H(Hs, idx):
    """CIR field at the given first-path tap (the one detected on the full channel) for each yaw of a (yaw, 257, 2, 2) channel."""
    return np.array([contribution_cir(Hs[k], FREQ)[0][idx[k]] for k in range(Hs.shape[0])])


def analyse(npz, setup, banks):
    z = np.load(npz)
    Hg, label, order, call, table = crf.group_channels(z, setup)
    Hf = Hg.sum(0)
    idx = []
    for k in range(len(YAWS)):
        cir, t = contribution_cir(Hf[k], FREQ)
        pk = np.abs(cir).max(0)
        rx, tx = np.unravel_index(pk.argmax(), pk.shape)
        idx.append(extract_first_path(cir[:, rx, tx], t)[0])
    C = np.zeros((len(GROUPS), len(YAWS), 2, 2), complex)
    for g in range(len(GROUPS)):
        for k in range(len(YAWS)):
            C[g, k] = contribution_cir(Hg[g, k], FREQ)[0][idx[k]]
    x, y = (float(v) for v in z["robot_xy_m"])
    a_pos, r_pos = z["anchor_m"], z["robot_antenna_m"]
    geo = setup.link_geometry(x, y, 0.0)
    bearing = float(np.degrees(np.arctan2(a_pos[1] - r_pos[1], a_pos[0] - r_pos[0])))  # world azimuth of the anchor as seen from the robot
    variant_C = {}
    for v in VARIANTS:
        Hs = np.stack([los_variant(banks, a_pos, r_pos, yaw, v) for yaw in YAWS])
        variant_C[v] = fp_field_from_H(Hs, idx)
    res = dict(file=str(Path(npz).relative_to(ROOT)), x=x, y=y, range_m=geo["range_m"], off_boresight_deg=geo["anchor_off_boresight_deg"], anchor_bearing_deg=bearing,
               excess_delay_ns={k: v for k, v in zip(("floor", "ceiling", "side_walls", "end_walls", "multi_bounce"), [None] * 5)}, tx={})
    tau_los = table[()]
    ex = {"floor": ("floor",), "ceiling": ("ceiling",), "side_walls": ("wall_y_neg", "wall_y_pos"), "end_walls": ("end_x_min", "end_x_max")}
    res["excess_delay_ns"] = {k: (min(table[(m,)] for m in v) - tau_los) * 1e9 for k, v in ex.items()}
    res["excess_delay_ns"]["multi_bounce"] = (min(v for s_, v in table.items() if len(s_) >= 2) - tau_los) * 1e9
    c_los, c_full = C[0], C.sum(0)
    res["tap_leakage_ratio"] = {GROUPS[g]: float(np.sqrt((np.abs(C[g]) ** 2).sum() / (np.abs(c_los) ** 2).sum())) for g in range(1, len(GROUPS))}
    res["tap_leakage_ratio"]["all_reflections"] = float(np.sqrt((np.abs(c_full - c_los) ** 2).sum() / (np.abs(c_los) ** 2).sum()))
    for t, tn in enumerate(TX):
        sg = SIGMA[tn]
        s_ideal = sg * np.cos(2 * PSI)
        s_los, s_full = signed(c_los, t), signed(c_full, t)
        d = dict(s_ideal=s_ideal.tolist(), s_los=s_los.tolist(), s_full=s_full.tolist(), ratio_ideal=np.abs(s_ideal).tolist(), ratio_los=np.abs(s_los).tolist(), ratio_full=np.abs(s_full).tolist())
        d["fit_los"], d["fit_full"] = fit_shift(s_los, sg), fit_shift(s_full, sg)
        d["fit_partial"] = {g: fit_shift(signed(c_los + C[GROUPS.index(g)], t), sg) for g in REFL}
        d["fit_variants"] = {v: fit_shift(signed(variant_C[v], t), sg) for v in VARIANTS}
        d["variant_base_check_max_abs"] = float(np.abs(signed(variant_C["base"], t) - s_los).max())
        wrap = lambda a: float((a + 90.0) % 180.0 - 90.0)
        fl, ff = d["fit_los"], d["fit_full"]
        d["shift"] = dict(
            x_total=ff["yaw0_deg"], y_total=ff["B"],
            x_antenna_geometry=fl["yaw0_deg"], y_antenna_geometry=fl["B"],
            x_multipath=wrap(ff["yaw0_deg"] - fl["yaw0_deg"]), y_multipath=ff["B"] - fl["B"],
            x_by_group={g: wrap(d["fit_partial"][g]["yaw0_deg"] - fl["yaw0_deg"]) for g in REFL},
            y_by_group={g: d["fit_partial"][g]["B"] - fl["B"] for g in REFL})
        d["shift"]["x_group_sum"] = float(sum(d["shift"]["x_by_group"].values()))
        d["shift"]["y_group_sum"] = float(sum(d["shift"]["y_by_group"].values()))
        res["tx"][tn] = d
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "CORRIDOR_SCAN_20261006" / "SHIFT_FIT.json")
    args = ap.parse_args()
    setup, banks = CorridorSetup(), Banks()
    rows = [analyse(p, setup, banks) for p in crf.find_inputs()]
    rows.sort(key=lambda r: (r["y"] != 0.0, r["x"] != 7.0, r["x"], r["y"]))
    args.out.write_text(json.dumps(dict(yaw_deg=YAWS.tolist(), variants=list(VARIANTS), groups=list(REFL), positions=rows), indent=1))
    for r in rows:
        for tn in TX:
            d = r["tx"][tn]; s = d["shift"]
            print(f"({r['x']:5.2f},{r['y']:5.2f}) {tn[3:]} x-shift los {s['x_antenna_geometry']:+6.1f} +mp {s['x_multipath']:+5.1f} = {s['x_total']:+6.1f} | y-shift los {s['y_antenna_geometry']:+.3f} +mp {s['y_multipath']:+.3f} = {s['y_total']:+.3f} | "
                  f"captured |s| los/full {d['fit_los']['captured']} {d['fit_full']['captured']} | base-check {d['variant_base_check_max_abs']:.1e}")


if __name__ == "__main__":
    main()
