"""Yaw curves versus the anchor's emission angle, with an ideal receiver at boresight.

Only the transmit direction (theta from boresight, phi azimuth in the anchor frame) changes. The robot's ports are read
at boresight and rotated by yaw, so any shift of the curve comes from the TX antenna alone.  Per (theta, phi, TX port):
  * |s|(yaw) curve and its (yaw0, B, A) fit, through the project's CIR/first-path chain at a 3 m link;
  * the TX field seen by the receiver (Ex, Ey of the radiated field, centre bin): degree of linear polarisation, ellipticity,
    and the shift predicted from its Stokes tilt:  s(yaw) = (S2 cos 2yaw - S1 sin 2yaw) / S0;
  * the antenna's own cross-polar discrimination against the ideal (x +- y)/sqrt2 polarisation projected on the wavefront.

  python scripts/corridor_tx_angle_sweep.py
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
import corridor_shift_fit as sf  # noqa: E402
from qclean_uwb.scenarios.corridor import ANCHOR_ROTATION, PORT_LOCAL_E, rot_z  # noqa: E402
from rt_cp_uwb_py.features import extract_first_path  # noqa: E402
from rt_cp_uwb_py.rf_channel_closure import contribution_cir  # noqa: E402

LINK_M = 3.0
CENTER_BIN = 128


def one(banks, theta, phi):
    dl = np.array([np.sin(theta) * np.cos(phi), np.sin(theta) * np.sin(phi), np.cos(theta)])
    k = ANCHOR_ROTATION @ dl
    vt = banks.vectors(ANCHOR_ROTATION, k)  # (257, 2 ports, 3) world Cartesian
    amp = sf.C0 / sf.FREQ / (4 * np.pi * LINK_M) * np.exp(-2j * np.pi * sf.FREQ * LINK_M / sf.C0)
    Hs = np.stack([np.einsum("fic,fjc->fij", banks.vectors(rot_z(y), -k, force_boresight=True), vt) * amp[:, None, None] for y in sf.YAWS])
    cir, t = contribution_cir(Hs[0], sf.FREQ)
    pk = np.abs(cir).max(0)
    rx, tx = np.unravel_index(pk.argmax(), pk.shape)
    idx = extract_first_path(cir[:, rx, tx], t)[0]
    C = sf.fp_field_from_H(Hs, [idx] * len(sf.YAWS))
    out = {}
    for t_i, tn in enumerate(sf.TX):
        sg = sf.SIGMA[tn]
        s = sf.signed(C, t_i)
        fit = sf.fit_shift(s, sg)
        Ex, Ey = vt[CENTER_BIN, t_i, 0], vt[CENTER_BIN, t_i, 1]
        S0 = abs(Ex) ** 2 + abs(Ey) ** 2
        S1, S2, S3 = abs(Ex) ** 2 - abs(Ey) ** 2, 2 * np.real(Ex * np.conj(Ey)), -2 * np.imag(Ex * np.conj(Ey))
        yaw0_th = float(np.degrees(0.5 * np.arctan2(sg * (-S1 / S0), sg * (S2 / S0))))
        # Intrinsic purity: field in the anchor frame against the ideal polarisation projected on the wavefront.
        e = banks.field(t_i, theta, phi)[CENTER_BIN]
        eth = np.array([np.cos(theta) * np.cos(phi), np.cos(theta) * np.sin(phi), -np.sin(theta)])
        eph = np.array([-np.sin(phi), np.cos(phi), 0.0])
        E = e[0] * eth + e[1] * eph
        u = PORT_LOCAL_E[sf.TX[t_i]]
        p = u - dl * (dl @ u)
        p = p / np.linalg.norm(p)
        q = np.cross(dl, p)
        co, cx = abs(p @ E) ** 2, abs(q @ E) ** 2
        out[tn] = dict(ratio=np.abs(s).tolist(), yaw0=fit["yaw0_deg"], B=fit["B"], A=fit["A"], captured=fit["captured"], dolp=float(np.hypot(S1, S2) / S0),
                       ellipticity=float(S3 / S0), yaw0_pred=yaw0_th, xpd_db=float(10 * np.log10(co / cx)), gain_rel_db=float(10 * np.log10((co + cx))))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "CORRIDOR_SCAN_20261006" / "TX_ANGLE_SWEEP.json")
    args = ap.parse_args()
    banks = sf.Banks()
    thetas, phis = list(range(0, 86, 5)), list(range(0, 360, 45))
    data = {f"{th}_{ph}": one(banks, np.radians(th), np.radians(ph)) for th in thetas for ph in phis}
    ref = max(v[sf.TX[0]]["gain_rel_db"] for v in data.values())
    for v in data.values():
        for tn in sf.TX:
            v[tn]["gain_rel_db"] -= ref
    args.out.write_text(json.dumps(dict(yaw_deg=sf.YAWS.tolist(), theta_deg=thetas, phi_deg=phis, link_m=LINK_M, center_bin=CENTER_BIN, data=data)))
    for th in (0, 40, 60, 80):
        r = data[f"{th}_0"][sf.TX[0]]
        print(f"theta {th:2d} phi 0 TX+45: yaw0 {r['yaw0']:+6.1f} (pred {r['yaw0_pred']:+6.1f}) B {r['B']:+.3f} A {r['A']:.3f} DoLP {r['dolp']:.3f} XPD {r['xpd_db']:5.1f} dB")


if __name__ == "__main__":
    main()
