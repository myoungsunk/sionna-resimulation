"""First-order multipath model: LoS + analytic specular reflections, evaluated at the first-path tap like the simulator.

For every coordinate and yaw the model builds H_model(f) = H_LoS + sum over the six surfaces of the analytic reflected channel and
passes it through the same CIR / first-path chain.  It is compared with the Sionna tap fields of the same reflection groups.

  python scripts/corridor_multipath_model.py
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
from qclean_uwb.features.specular_model import SURFACES, reflected_field  # noqa: E402
from qclean_uwb.scenarios.corridor import ANCHOR_ROTATION, CorridorSetup, rot_z  # noqa: E402
from rt_cp_uwb_py.features import extract_first_path  # noqa: E402
from rt_cp_uwb_py.rf_channel_closure import contribution_cir  # noqa: E402

YAWS = sf.YAWS
GROUP_OF = {n: v[2] for n, v in SURFACES.items()}


def channels(banks, setup, a_pos, r_pos, yaws, surfaces=tuple(SURFACES), material_scale=1.0, wall_offset_m=0.0):
    """Model channels (n_yaw, 257, 2, 2) per group: 'los' and each reflection group (floor, ceiling, side_walls, end_walls)."""
    freq = sf.FREQ
    out = {}
    k = r_pos - a_pos
    dist = float(np.linalg.norm(k))
    k = k / dist
    vt = banks.vectors(ANCHOR_ROTATION, k)
    amp = sf.C0 / freq / (4 * np.pi * dist) * np.exp(-2j * np.pi * freq * dist / sf.C0)
    out["los"] = np.stack([np.einsum("fic,fjc->fij", banks.vectors(rot_z(y), -k), vt) * amp[:, None, None] for y in yaws])
    for name in surfaces:
        e_r, k_r, L = reflected_field(banks, a_pos, r_pos, ANCHOR_ROTATION, name, freq, setup.length_m, setup.y_half + wall_offset_m, setup.height_m, material_scale)
        amp_r = sf.C0 / freq / (4 * np.pi * L) * np.exp(-2j * np.pi * freq * L / sf.C0)
        H = np.stack([np.einsum("fic,fjc->fij", banks.vectors(rot_z(y), -k_r), e_r) * amp_r[:, None, None] for y in yaws])
        g = GROUP_OF[name]
        out[g] = out.get(g, 0) + H
    return out


def tap_fields(H_by_group, idx):
    """First-path-tap field per group at the given taps (n_yaw)."""
    return {g: np.array([contribution_cir(H[k], sf.FREQ)[0][idx[k]] for k in range(H.shape[0])]) for g, H in H_by_group.items()}


def detect_idx(H_total):
    idx = []
    for k in range(H_total.shape[0]):
        cir, t = contribution_cir(H_total[k], sf.FREQ)
        pk = np.abs(cir).max(0)
        rx, tx = np.unravel_index(pk.argmax(), pk.shape)
        idx.append(extract_first_path(cir[:, rx, tx], t)[0])
    return np.array(idx)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "CORRIDOR_SCAN_20261006" / "MULTIPATH_MODEL.json")
    args = ap.parse_args()
    setup, banks = CorridorSetup(), sf.Banks()
    shift = json.loads((ROOT / "results/CORRIDOR_SCAN_20261006/SHIFT_FIT.json").read_text())
    rows = []
    for p in sorted(shift["positions"], key=lambda q: (q["x"], q["y"])):
        z = np.load(ROOT / p["file"])
        a_pos, r_pos = z["anchor_m"], z["robot_antenna_m"]
        # Sionna reference: group tap fields at the simulator's own first-path taps.
        Hg, *_ = crf.group_channels(z, setup)
        idx = detect_idx(Hg.sum(0))
        ref = {g: np.array([contribution_cir(Hg[crf.GROUPS.index(g), k], sf.FREQ)[0][idx[k]] for k in range(len(YAWS))]) for g in crf.GROUPS}
        mod = tap_fields(channels(banks, setup, a_pos, r_pos, YAWS), idx)
        row = dict(x=p["x"], y=p["y"], group_error={}, tx={})
        for g in ("floor", "ceiling", "side_walls", "end_walls"):
            err = np.linalg.norm(mod[g] - ref[g]) / max(np.linalg.norm(ref[g]), 1e-30)
            row["group_error"][g] = dict(relative_error=float(err), ref_to_los=float(np.linalg.norm(ref[g]) / np.linalg.norm(ref["los"])), model_to_los=float(np.linalg.norm(mod[g]) / np.linalg.norm(ref["los"])))
        c_ref = ref["los"] + sum(ref[g] for g in ref if g != "los")
        c_mod = mod["los"] + sum(mod[g] for g in ("floor", "ceiling", "side_walls", "end_walls"))
        for t, tn in enumerate(sf.TX):
            s_ref, s_mod, s_los = sf.signed(c_ref, t), sf.signed(c_mod, t), sf.signed(ref["los"], t)
            ideal = np.abs(np.cos(2 * np.radians(YAWS)))
            row["tx"][tn] = dict(ratio_sim=np.abs(s_ref).tolist(), ratio_model=np.abs(s_mod).tolist(), ratio_los=np.abs(s_los).tolist(), ratio_ideal=ideal.tolist(),
                                 rmse_model_vs_sim=float(np.sqrt(np.mean((np.abs(s_mod) - np.abs(s_ref)) ** 2))), rmse_los_vs_sim=float(np.sqrt(np.mean((np.abs(s_los) - np.abs(s_ref)) ** 2))),
                                 mp_effect_sim=float(np.sqrt(np.mean((np.abs(s_ref) - np.abs(s_los)) ** 2))), mp_effect_model=float(np.sqrt(np.mean((np.abs(s_mod) - np.abs(s_los)) ** 2))),
                                 s_model=s_mod.tolist(), s_sim=s_ref.tolist())
        rows.append(row)
    args.out.write_text(json.dumps(dict(yaw_deg=YAWS.tolist(), positions=rows), indent=1))
    for r in rows:
        ge = r["group_error"]
        print(f"({r['x']:5.1f},{r['y']:5.2f}) group tap-field relative error: " + " ".join(f"{g[:5]} {v['relative_error']:.2f}(ref/LoS {v['ref_to_los']:.3f})" for g, v in ge.items())
              + " | RMSE vs sim: LoS-only " + "/".join(f"{t['rmse_los_vs_sim']:.3f}" for t in r['tx'].values()) + " -> +MP model " + "/".join(f"{t['rmse_model_vs_sim']:.3f}" for t in r['tx'].values()))


if __name__ == "__main__":
    main()
