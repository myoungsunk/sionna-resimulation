"""First-path ranging error at the office positions: detected first-path delay x c0 minus the true anchor-tag range, per yaw, from the stored H only.
The detector is the one used for the FP-power ratio (strongest of the 2x2 branches per yaw, first tap above 30% of that branch peak, Hann CIR).
That detector has a constant leading-edge offset even on a free LoS link, so the error is also reported relative to the median offset of the LoS-clear
positions (bias-calibrated), which isolates what blockage/multipath add.   python scripts/office_ranging_error.py
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]
import corridor_shift_fit as sf  # noqa: E402
import office_analysis as oa  # noqa: E402
from rt_cp_uwb_py.features import extract_first_path  # noqa: E402
from rt_cp_uwb_py.rf_channel_closure import contribution_cir  # noqa: E402

C0 = 299792458.0
OUT = ROOT / "results" / "OFFICE_RANGING_20261008"


def fp_delays(H):
    """Per yaw: first-path delay of the strongest branch (all 4), and for each TX port of the strongest RX branch of that TX only."""
    full, single = [], {tn: [] for tn in sf.TX}
    for k in range(H.shape[0]):
        cir, t = contribution_cir(H[k], sf.FREQ)
        pk = np.abs(cir).max(0)
        rx, tx = np.unravel_index(pk.argmax(), pk.shape)
        full.append(t[extract_first_path(cir[:, rx, tx], t)[0]])
        for ti, tn in enumerate(sf.TX):
            r = int(pk[:, ti].argmax())
            single[tn].append(t[extract_first_path(cir[:, r, ti], t)[0]])
    return np.array(full), {k: np.array(v) for k, v in single.items()}


def stats(e):
    return dict(mean=float(e.mean()), std=float(e.std()), rms=float(np.sqrt(np.mean(e ** 2))), min=float(e.min()), max=float(e.max()), pp=float(np.ptp(e)))


def main():
    plan = json.loads((ROOT / "results/OFFICE_RUN_PLAN_20261008/RUN_PLAN.json").read_text())["positions"]
    rows = []
    for p in sorted(plan, key=lambda r: (r["theta_deg"], r["x"], r["y"])):
        tag = f"office_x{p['x']}_y{p['y']}"
        H = np.load(oa.RUN / tag / f"{tag}_H.npy")
        full, single = fp_delays(H)
        err = full * C0 - p["range_m"]
        rows.append(dict(x=p["x"], y=p["y"], los_clear=p["los_clear"], blockers=p["blockers"], theta_deg=p["theta_deg"], range_m=p["range_m"], err_m=[round(float(v), 3) for v in err],
                         err_single={tn: [round(float(v), 3) for v in single[tn] * C0 - p["range_m"]] for tn in sf.TX}, **stats(err)))
    bias = float(np.median([r["mean"] for r in rows if r["los_clear"]]))
    for r in rows:
        r["err_cal_m"] = [round(v - bias, 3) for v in r["err_m"]]
        r["mean_cal"] = r["mean"] - bias
    summ = {}
    for flag, name in ((True, "los_clear"), (False, "blocked")):
        sel = [r for r in rows if r["los_clear"] is flag]
        e = np.concatenate([r["err_cal_m"] for r in sel])
        summ[name] = dict(n=len(sel), rms_cal=float(np.sqrt(np.mean(e ** 2))), mean_cal=float(e.mean()), p95_abs=float(np.percentile(np.abs(e), 95)), max_abs=float(np.abs(e).max()),
                          n_gt_0p3m=int(np.sum([np.any(np.abs(r["err_cal_m"]) > 0.3) for r in sel])))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "OFFICE_RANGING.json").write_text(json.dumps(dict(c0=C0, tap_spacing_m=float(4.9885263893046e-10 * C0), los_clear_median_offset_m=bias, summary=summ, positions=rows), indent=1))
    print(f"detector offset on LoS-clear (median of means) {bias:+.3f} m, tap {4.9885e-10*C0:.3f} m")
    for k, v in summ.items():
        print(k, {a: (round(b, 3) if isinstance(b, float) else b) for a, b in v.items()})
    print("blocked positions (calibrated):")
    for r in rows:
        if not r["los_clear"]:
            print(f"({r['x']},{r['y']}) th={r['theta_deg']:.0f} R={r['range_m']:.2f} bl={r['blockers']} mean={r['mean_cal']:+.2f} std={r['std']:.2f} min={min(r['err_cal_m']):+.2f} max={max(r['err_cal_m']):+.2f}")
    print("clear worst:")
    for r in sorted([r for r in rows if r["los_clear"]], key=lambda r: -np.abs(r["err_cal_m"]).max())[:4]:
        print(f"({r['x']},{r['y']}) th={r['theta_deg']:.0f} mean={r['mean_cal']:+.2f} min={min(r['err_cal_m']):+.2f} max={max(r['err_cal_m']):+.2f}")


if __name__ == "__main__":
    main()
