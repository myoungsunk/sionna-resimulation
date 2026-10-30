"""P2_RFRES (AMENDMENT-009 option C): EXPLORATORY transfer check of the synthetic residual model against existing ray-traced
channels (DRIVE_SIM BLOCK_C, 7 corridor cases, Full and LoS-only RT channels). Previously used data: not confirmatory.

  c_rfres.py run --out D       (REFLECT_ROOT with rf/H_<c>.npy, rf/H_LoS_<c>.npy, rf/SAMPLES_<c>.json, traces/)

Per case, on the time-ordered drive-trace packets (truth pose of the trace, noise-free first-path observation):
  e_tot = obs(Full RT) - FFD_LoS(truth)      residual the filter sees
  e_mp  = obs(Full RT) - obs(LoS RT)         multipath-induced part (what the synthetic GP stands for)
  e_los = obs(LoS RT)  - FFD_LoS(truth)      LoS model / chain mismatch
Statistics: mean, sd, MAD-sd, skewness, excess kurtosis, fraction of first-path index switches (Full vs LoS), jumps at switches,
empirical spatial correlogram of e_mp vs the synthetic pose kernel (ell_p 0.5 m, ell_psi 20 deg), lag autocorrelation.
Pre-declared descriptive flags (no gate): BIAS |mean| > 0.5 sigma_synth; SCALE sd/sigma_synth outside [0.5, 2];
NON_GAUSSIAN |excess kurtosis| > 1 or |skew| > 0.5; FP_SWITCH switch fraction > 0.05; CORR_MISMATCH any distance bin with
>= 200 pairs where |corr_emp - 0.7 k| > 0.3 (0.7 = POSE_HIGH alpha_pose).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import info_core as IC  # noqa: E402
import manifest as MF  # noqa: E402
import world as Wd  # noqa: E402

C = Wd.C
CASES = tuple(C.CASES)
D_BINS = (0.0, 0.1, 0.25, 0.5, 1.0, 2.0)
SYN = Wd.PARAMS["synthetic_s1"]; SIG = dict(r=SYN["sigma_r_m"], s=SYN["sigma_s"])
ELL_P = SYN["pose_corr_length_m"]; ELL_PSI = math.radians(SYN["pose_corr_yaw_deg"]); ALPHA_POSE = SYN["high_spatial"]["alpha_pose"]


def _obs_mod():
    sys.path.insert(0, str(Path(os.environ["REFLECT_ROOT"]) / "repo/results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src"))
    from qclean_uwb.drivesim import observation as OBS
    return OBS


def moments(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]; m = x.mean(); sd = x.std(ddof=1); c = x - m
    return dict(n=len(x), mean=float(m), sd=float(sd), mad_sd=float(1.4826 * np.median(np.abs(x - np.median(x)))),
                skew=float(np.mean(c ** 3) / sd ** 3), exkurt=float(np.mean(c ** 4) / sd ** 4 - 3), frac_gt_3mad=float(np.mean(np.abs(c) > 3 * 1.4826 * np.median(np.abs(c)))))


def correlogram(xy, yaw, e):
    e = (e - e.mean()) / e.std(); n = len(e)
    D = np.hypot(xy[:, None, 0] - xy[None, :, 0], xy[:, None, 1] - xy[None, :, 1]); K = IC.k_pose(xy, yaw, ELL_P, ELL_PSI)
    iu = np.triu_indices(n, 1); d = D[iu]; k = K[iu]; p = (e[:, None] * e[None, :])[iu]; out = []
    for lo, hi in zip(D_BINS[:-1], D_BINS[1:]):
        m = (d >= lo) & (d < hi)
        out.append(dict(d_lo=lo, d_hi=hi, n_pairs=int(m.sum()), corr_emp=float(p[m].mean()) if m.any() else float("nan"),
                        kernel_mean=float(k[m].mean()) if m.any() else float("nan"),
                        synth_pose_high=float(ALPHA_POSE * k[m].mean()) if m.any() else float("nan")))
    return out


def case_rows(case, OBS, freqs):
    ref = C.load_control(case, "B0"); spec = C.CASES[case]; gt = ref["truth_scoring_only"]; pid = ref["pose_id"].astype(int); t = ref["t_s"]
    Hf, Hl, samples = C.load_rf(case); idx = {int(p["pose_id"]): i for i, p in enumerate(samples)}
    rows = np.array([idx.get(p, -1) for p in pid]); ok = rows >= 0
    oF = OBS.observe(np.asarray(Hf[rows[ok]]), freqs, None, None); oL = OBS.observe(np.asarray(Hl[rows[ok]]), freqs, None, None)
    h, _ = Wd.model().batch(np.c_[gt[ok, :3], np.zeros(ok.sum())], spec); h = np.asarray(h)
    d = pd.DataFrame(dict(case=case, t=t[ok], pose_id=pid[ok], x=gt[ok, 0], y=gt[ok, 1], yaw=gt[ok, 2],
                          rF=oF["range_m"], sF=oF["s"], rL=oL["range_m"], sL=oL["s"], h_r=h[:, 0], h_s=h[:, 1],
                          idxF=oF["index"], idxL=oL["index"]))
    d["fp_switch"] = d.idxF != d.idxL
    for ch, a, b in (("r", "rF", "h_r"), ("s", "sF", "h_s")):
        d[f"etot_{ch}"] = d[a] - d[b]
    d["emp_r"] = d.rF - d.rL; d["emp_s"] = d.sF - d.sL; d["elos_r"] = d.rL - d.h_r; d["elos_s"] = d.sL - d.h_s
    return d, int(len(pid)), int(ok.sum())


def flags(st, ch, sw, cg):
    f = []
    if abs(st["mean"]) > 0.5 * SIG[ch]:
        f.append("BIAS")
    if not 0.5 <= st["sd"] / SIG[ch] <= 2.0:
        f.append("SCALE")
    if abs(st["exkurt"]) > 1 or abs(st["skew"]) > 0.5:
        f.append("NON_GAUSSIAN")
    if sw > 0.05:
        f.append("FP_SWITCH")
    if cg is not None and any(b["n_pairs"] >= 200 and abs(b["corr_emp"] - b["synth_pose_high"]) > 0.3 for b in cg):
        f.append("CORR_MISMATCH")
    return f


def cmd_run(out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    OBS = _obs_mod(); freqs = np.asarray(Wd.model().freqs); allrows = []; stats = []; cgs = []; acs = []; summ = {}
    for case in CASES:
        d, npk, nmatch = case_rows(case, OBS, freqs); allrows.append(d)
        sw = float(d.fp_switch.mean()); summ[case] = dict(packets=npk, matched=nmatch, fp_switch_frac=sw, flags={})
        for kind in ("etot", "emp", "elos"):
            for ch in ("r", "s"):
                st = moments(d[f"{kind}_{ch}"]); stats.append(dict(case=case, residual=kind, channel=ch, sd_over_sigma_synth=st["sd"] / SIG[ch], **st))
        for ch in ("r", "s"):
            e = d[f"emp_{ch}"].to_numpy(); m = np.isfinite(e)
            cg = correlogram(d[["x", "y"]].to_numpy()[m], d.yaw.to_numpy()[m], e[m]) if m.sum() > 10 and np.std(e[m]) > 0 else None
            for b in cg or []:
                cgs.append(dict(case=case, channel=ch, **b))
            ee = (e[m] - e[m].mean()) / (e[m].std() or 1)
            for lag in (1, 2, 5, 10, 25):
                acs.append(dict(case=case, channel=ch, lag=lag, acf=float(np.mean(ee[lag:] * ee[:-lag])) if len(ee) > lag else float("nan")))
            jump = np.abs(np.diff(d[f"etot_{ch}"].to_numpy())); tog = np.diff(d.fp_switch.to_numpy().astype(int)) != 0
            st_tot = [s for s in stats if s["case"] == case and s["residual"] == "etot" and s["channel"] == ch][0]
            summ[case]["flags"][ch] = flags(st_tot, ch, sw, cg)
            summ[case][f"median_jump_at_switch_{ch}"] = float(np.median(jump[tog])) if tog.any() else None
            summ[case][f"median_jump_no_switch_{ch}"] = float(np.median(jump[~tog])) if (~tog).any() else None
    R = pd.concat(allrows, ignore_index=True)
    R.to_csv(out / "RFRES_ROWS.csv", index=False, float_format="%.12g")
    pd.DataFrame(stats).to_csv(out / "RFRES_MOMENTS.csv", index=False, float_format="%.6g")
    pd.DataFrame(cgs).to_csv(out / "RFRES_CORRELOGRAM.csv", index=False, float_format="%.6g")
    pd.DataFrame(acs).to_csv(out / "RFRES_ACF.csv", index=False, float_format="%.6g")
    anyflag = sorted({fl for c in summ.values() for ch in c["flags"].values() for fl in ch})
    res = dict(label="EXPLORATORY_TRANSFER_CHECK (previously used corridor RT data; not confirmatory; no gate)",
               cases=summ, flags_any_case=anyflag, sigma_synth=SIG, kernel=dict(ell_p_m=ELL_P, ell_psi_deg=SYN["pose_corr_yaw_deg"], alpha_pose_high=ALPHA_POSE),
               use="informs the pre-P3 amendment (G7): which synthetic assumptions the physical RT stage must not take for granted")
    (out / "RFRES_SUMMARY.json").write_text(json.dumps(res, indent=1, default=float))
    print("RFRES flags", anyflag, flush=True)
    return 0


def cmd_aggregate(shards, out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    src = next(Path(shards).rglob("RFRES_SUMMARY.json"), None)
    if src is not None:
        for f in src.parent.glob("RFRES_*"):
            (out / f.name).write_bytes(f.read_bytes())
    status = "PASS" if src is not None else "FAIL"
    MF.write_manifest(out, phase="P2_S1", status=status, contract_sha=MF.sha256_file(MF.CONTRACT),
                      config_files=[Wd.EXP / "config/PLAN_PARAMETERS.json", Wd.EXP / "contracts/AMENDMENT-009.md"],
                      input_lock=Path(os.environ.get("REFLECT_ROOT", ".")) / "out" / "INPUT_LOCK.sha256", outputs=sorted(out.glob("RFRES_*")),
                      seed_ledger=None, verdict="NOT_EVALUATED", unit="mathematical_deterministic",
                      limitations=["EXPLORATORY: previously used corridor RT data", "noise-free first-path observation", "SELF_REVIEW_ONLY"],
                      extra=dict(sub_phase="P2_RFRES", amendment="AMENDMENT-009"))
    return 0 if status == "PASS" else 1


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("cmd"); ap.add_argument("--out", required=True); ap.add_argument("--shards")
    a = ap.parse_args()
    return cmd_run(a.out) if a.cmd == "run" else cmd_aggregate(a.shards, a.out)


if __name__ == "__main__":
    raise SystemExit(main())
