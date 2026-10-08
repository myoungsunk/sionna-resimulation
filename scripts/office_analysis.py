"""First analysis of the office sweep (35 tag positions): FP-power ratio |P1-P2|/|P1+P2| versus yaw for both anchor TX ports, compared with the ideal
curve |cos 2 yaw| and, for the geometric LoS positions, with the antenna-pattern angle model (LoS only).  Works on the stored H only (no path files).
    python scripts/office_analysis.py
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import corridor_case_check as cc  # noqa: E402
import corridor_shift_fit as sf  # noqa: E402
import corridor_template_compare as tc  # noqa: E402
from rt_cp_uwb_py.features import extract_first_path  # noqa: E402
from rt_cp_uwb_py.rf_channel_closure import contribution_cir  # noqa: E402
from qclean_uwb.scenarios.office import OfficeSetup  # noqa: E402

RUN = ROOT / "results" / "OFFICE_SNOWBALL_20261008_819fa93" / "full35_stride1"
OUT = ROOT / "results" / "OFFICE_ANALYSIS_20261008"
BINS = [(0, 30), (30, 50), (50, 65), (65, 75), (75, 90)]


def fp_fields(H):
    """First-path tap detected per yaw on the full 2x2 channel (strongest branch, 30% leading edge), field at that tap: (yaw, rx, tx), tap index."""
    c, idx = [], []
    for k in range(H.shape[0]):
        cir, t = contribution_cir(H[k], sf.FREQ)
        pk = np.abs(cir).max(0)
        rx, tx = np.unravel_index(pk.argmax(), pk.shape)
        i = extract_first_path(cir[:, rx, tx], t)[0]
        idx.append(int(i))
        c.append(cir[i])
    return np.array(c), np.array(idx), t


def main():
    setup, banks = OfficeSetup(), sf.Banks()
    plan = {(r["x"], r["y"]): r for r in json.loads((ROOT / "results/OFFICE_RUN_PLAN_20261008/RUN_PLAN.json").read_text())["positions"]}
    rows = []
    for (x, y), pl in sorted(plan.items(), key=lambda kv: (kv[1]["theta_deg"], kv[0])):
        tag = f"office_x{x}_y{y}"
        H = np.load(RUN / tag / f"{tag}_H.npy")
        c, idx, t = fp_fields(H)
        g = setup.link_geometry(x, y)
        rec = dict(x=x, y=y, los_clear=pl["los_clear"], blockers=pl["blockers"], theta_deg=pl["theta_deg"], phi_deg=round(g["anchor_phi_deg"], 1), range_m=pl["range_m"],
                   first_path_tap=[int(idx.min()), int(idx.max())], tx={})
        for t_i, tn in enumerate(sf.TX):
            s = sf.signed(c, t_i)
            dense, _ = tc.model_curve(banks, setup, x, y, tn)
            model = np.interp(sf.YAWS, cc.GRID, dense)
            ideal_abs = np.abs(np.cos(2 * np.radians(cc.GRID)))
            e_model = tc.err_from_curve(s, np.abs(dense))
            e_ideal = tc.err_from_curve(s, ideal_abs)
            rec["tx"][tn] = dict(s=[round(float(v), 4) for v in s], model=[round(float(v), 4) for v in model], model_dense_abs=[round(float(v), 4) for v in np.abs(dense)[::10]],
                                 rms_dev_model=float(np.sqrt(np.mean((np.abs(s) - np.abs(model)) ** 2))), rms_dev_ideal=float(np.sqrt(np.mean((np.abs(s) - np.abs(np.cos(2 * np.radians(sf.YAWS)))) ** 2))),
                                 yaw_rmse_model=float(np.sqrt(np.mean(e_model ** 2))), yaw_rmse_ideal=float(np.sqrt(np.mean(e_ideal ** 2))),
                                 yaw_err_model=e_model.tolist(), yaw_err_ideal=e_ideal.tolist())
        rows.append(rec)
    summ = {}
    for flag, name in ((True, "los"), (False, "nlos")):
        sel = [r for r in rows if r["los_clear"] is flag]
        e = {k: np.concatenate([r["tx"][tn][f"yaw_err_{k}"] for r in sel for tn in sf.TX]) for k in ("model", "ideal")}
        summ[name] = dict(n_positions=len(sel), median_rms_dev_model=float(np.median([r["tx"][tn]["rms_dev_model"] for r in sel for tn in sf.TX])),
                          median_rms_dev_ideal=float(np.median([r["tx"][tn]["rms_dev_ideal"] for r in sel for tn in sf.TX])),
                          yaw_rmse_model=float(np.sqrt(np.mean(e["model"] ** 2))), within5_model=float(np.mean(np.abs(e["model"]) <= 5)),
                          yaw_rmse_ideal=float(np.sqrt(np.mean(e["ideal"] ** 2))), within5_ideal=float(np.mean(np.abs(e["ideal"]) <= 5)))
    by_theta = []
    for lo, hi in BINS:
        sel = [r for r in rows if r["los_clear"] and lo <= r["theta_deg"] < hi]
        if sel:
            e = np.concatenate([r["tx"][tn]["yaw_err_model"] for r in sel for tn in sf.TX])
            by_theta.append(dict(theta_lo=lo, theta_hi=hi, n_positions=len(sel), median_rms_dev_model=float(np.median([r["tx"][tn]["rms_dev_model"] for r in sel for tn in sf.TX])),
                                 yaw_rmse_model=float(np.sqrt(np.mean(e ** 2))), within5=float(np.mean(np.abs(e) <= 5))))
    (OUT / "OFFICE_ANALYSIS.json").write_text(json.dumps(dict(yaw_deg=sf.YAWS.tolist(), model_yaw_deg=np.arange(0, 181, 1.0).tolist(), summary=summ, los_by_theta=by_theta, positions=rows), separators=(",", ":")))
    for k, v in summ.items():
        print(k, {a: (round(b, 3) if isinstance(b, float) else b) for a, b in v.items()})
    for b in by_theta:
        print(f"LoS theta {b['theta_lo']:2d}-{b['theta_hi']:2d}: n={b['n_positions']:2d} median rms dev (angle model) {b['median_rms_dev_model']:.3f} yaw RMSE {b['yaw_rmse_model']:.2f} within5 {b['within5']*100:.0f}%")


if __name__ == "__main__":
    main()
