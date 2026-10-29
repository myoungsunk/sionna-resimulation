"""Aggregate shards and apply the pre-registered decision rules (PROTOCOL_CONTROLS_KO.md, amendments A1-A8).

  CTL_OUT=<dir with shard files> python3 aggregate_ctl.py
Writes JUDGE_*.csv, DECISIONS.json and RESULTS_SUMMARY.md into CTL_OUT.  Rules are applied mechanically; NA when inputs
are missing, kept distinct from failure.
"""
from __future__ import annotations

import glob
import json
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(os.environ.get("CTL_OUT", Path(__file__).resolve().parent / "out"))
MAIN = ("R5_aA_m0", "R4_aB_m0"); PROTECT = "R5_aB_m0"


def cat(pattern):
    fs = sorted(glob.glob(str(OUT / pattern)))
    return pd.concat([pd.read_csv(f) for f in fs], ignore_index=True) if fs else pd.DataFrame()


def spearman(x, y):
    x = pd.Series(x).rank(); y = pd.Series(y).rank()
    return float(np.corrcoef(x, y)[0, 1]) if x.std() > 0 and y.std() > 0 else np.nan


def med3(s):
    s = pd.Series(s).dropna()
    return (float(s.median()), float(s.min()), float(s.max())) if len(s) else (np.nan, np.nan, np.nan)


def main():
    dec = {}
    md = ["# MB_VAR 대조조건 정정 실행 결과 (자동 생성)", "",
          "판정은 PROTOCOL_CONTROLS_KO.md 본문과 '실행 전 수정' A1–A8의 규칙을 기계적으로 적용한 것이다. 해석 문장은 포함하지 않는다.", ""]

    # ---------------------------------------------------------------- shard status
    st = [json.loads(Path(f).read_text()) for f in sorted(glob.glob(str(OUT / "SHARD_*.json")))]
    S = pd.DataFrame([dict(stage=s["stage"], case=s["case"], part=s["part"], status=s["status"], sec=s["sec"],
                           **{k: v for k, v in s.get("checks", {}).items()}) for s in st])
    S.to_csv(OUT / "SHARD_STATUS.csv", index=False)
    nfail = int((S.status != "ok").sum()) if len(S) else -1
    dec["shards"] = dict(n=len(S), failed=nfail)
    md += [f"## 실행 상태", f"- shard {len(S)}개, 실패 {nfail}개", ""]
    if len(S):
        par = [c for c in S.columns if c.startswith("parity_")]
        mx = float(np.nanmax(S[par].to_numpy(float))) if par else np.nan
        dec["parity_max_state_diff"] = mx
        md += [f"- seed 0 parity(exp_pb.run 대비 상태 최대차): {mx:.3g}", ""]

    # ---------------------------------------------------------------- C0
    A = cat("A_SCORES_*.csv"); AS = cat("A_SUMMARY_*.csv")
    if len(AS):
        k = AS[(AS.window == "all")]
        g = k.groupby(["case", "arm", "set", "comp"])[["mr_eps2_R", "rm_eps2_R", "mr_dh2_HPH", "rm_dh2_HPH", "cross_share", "ell_share"]].median()
        g.to_csv(OUT / "JUDGE_C0_SAMPLESET.csv")
        w = AS[(AS.set == "S_base") & (AS.comp == "s")].groupby(["case", "arm", "window"])[
            ["rms_eps", "E_R", "E_HPH", "E_dh2", "cross_share", "ell_share", "mr_dh2_HPH", "mr_He2_HPH"]].median()
        w.to_csv(OUT / "JUDGE_C0_WINDOWS.csv")
        md += ["## C0 표본 집합·정의 차이 (seed 중앙값, s 성분, all window)", "",
               "| case | arm | 집합 | mean ε²/mean R | mean(ε²/R) | mean δh²/mean HPH | mean(δh²/HPH) | 교차항 몫 | ℓ 몫 |", "|---|---|---|---|---|---|---|---|---|"]
        for (c, a, s_, comp), r in g.iterrows():
            if comp == "s" and a in ("MB_ORIG", "MB_VAR"):
                md.append(f"| {c} | {a} | {s_} | {r.mr_eps2_R:.3f} | {r.rm_eps2_R:.3f} | {r.mr_dh2_HPH:.2f} | {r.rm_dh2_HPH:.2f} | {r.cross_share:+.3f} | {r.ell_share:.3f} |")
        md.append("")
    if len(A):
        A.groupby(["case", "arm"])[["head_rmse", "xy_rmse_cm", "head_z_rms", "nees3", "nees4"]].agg(["median", "min", "max"]).to_csv(OUT / "JUDGE_C0_SEED_SPREAD.csv")
        md += ["## seed 반복 기준점 (10 seed, 고정 BASE mask)", "", "| case | arm | Heading RMSE 중앙값 [min, max] | XY RMSE [min, max] |", "|---|---|---|---|"]
        for (c, a), r in A.groupby(["case", "arm"]):
            h = med3(r.head_rmse); x = med3(r.xy_rmse_cm)
            md.append(f"| {c} | {a} | {h[0]:.3f} [{h[1]:.3f}, {h[2]:.3f}] | {x[0]:.2f} [{x[1]:.2f}, {x[2]:.2f}] |")
        md.append("")

    # ---------------------------------------------------------------- E1
    E1 = cat("E1_*_s0.csv"); E1x = cat("E1_*_sx.csv")
    rows = []
    for (c, arm), g in E1.groupby(["case", "arm"]) if len(E1) else []:
        base = g[g.treat == "BASE"].iloc[0]
        for m in sorted(g[g.treat == "DEC"].m.unique()):
            dec_ = g[(g.treat == "DEC") & (g.m == m)]; rnd = g[(g.treat == "RAND") & (g.m == m)]
            ts = g[(g.treat == "THIN_S") & (g.m == m)]; tr = g[(g.treat == "THIN_R") & (g.m == m)]
            rt = g[(g.treat == "RSC_TOTAL") & (g.m == m)].iloc[0]; rs = g[(g.treat == "RSC_S") & (g.m == m)].iloc[0]
            var_ratio = float(dec_.head_rmse.var() / rnd.head_rmse.var()) if rnd.head_rmse.var() > 0 else np.nan
            def inside(v, col):
                lo, hi = np.quantile(rnd[col], [0.025, 0.975]); return bool(lo <= v <= hi)
            G = base.head_rmse - dec_.head_rmse.mean()
            fs = (base.head_rmse - ts.head_rmse.mean()) / G if G > 0.02 else np.nan
            fr = (base.head_rmse - tr.head_rmse.mean()) / G if (G > 0.02 and len(tr)) else np.nan
            chan = "NA" if not np.isfinite(fs) else ("s" if (fs >= .7 and np.isfinite(fr) and fr <= .3) else ("r" if (np.isfinite(fr) and fr >= .7 and fs <= .3) else "unattributed"))
            rows.append(dict(case=c, arm=arm, m=m, base_head=base.head_rmse, dec_head_mean=dec_.head_rmse.mean(), dec_head_min=dec_.head_rmse.min(),
                             dec_head_max=dec_.head_rmse.max(), rand_head_mean=rnd.head_rmse.mean(), rand_head_q025=rnd.head_rmse.quantile(.025),
                             rand_head_q975=rnd.head_rmse.quantile(.975), phase_over_rand_var=var_ratio, selection_dependent=bool(var_ratio > 1) if np.isfinite(var_ratio) else None,
                             rsc_total_head=rt.head_rmse, rsc_total_xy=rt.xy_rmse_cm, rsc_total_inside_rand=inside(rt.head_rmse, "head_rmse") and inside(rt.xy_rmse_cm, "xy_rmse_cm"),
                             rsc_s_head=rs.head_rmse, thin_s_head_mean=ts.head_rmse.mean(), thin_r_head_mean=tr.head_rmse.mean() if len(tr) else np.nan,
                             recovery_G=G, thin_s_recovery=fs, thin_r_recovery=fr, channel=chan,
                             dec_zpsi_mean=dec_.head_z_rms.mean(), rsc_total_zpsi=rt.head_z_rms, rand_zpsi_mean=rnd.head_z_rms.mean(),
                             dec_cross_s=dec_.s_cross_share.mean(), rand_cross_s=rnd.s_cross_share.mean(), rsc_total_cross_s=rt.s_cross_share))
    J1 = pd.DataFrame(rows); J1.to_csv(OUT / "JUDGE_E1.csv", index=False, float_format="%.6g")
    if len(J1):
        md += ["## E1 선택·빈도·채널·가중치 (seed 0)", "", "| case | arm | m | base | DEC 위상 [min, max] | RAND 2.5–97.5% | 위상분산/RAND분산 | RSC_TOTAL | RSC_TOTAL∈RAND | THIN_S 회복 | THIN_R 회복 | 귀속 |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for _, r in J1.iterrows():
            md.append(f"| {r.case} | {r.arm} | {r.m} | {r.base_head:.3f} | [{r.dec_head_min:.3f}, {r.dec_head_max:.3f}] | [{r.rand_head_q025:.3f}, {r.rand_head_q975:.3f}] | {r.phase_over_rand_var:.2f} | {r.rsc_total_head:.3f} | {r.rsc_total_inside_rand} | {r.thin_s_recovery:.2f} | {r.thin_r_recovery:.2f} | {r.channel} |")
        md.append("")
    if len(E1x):
        sx = E1x.merge(E1x[E1x.treat == "BASE"][["case", "arm", "seed", "head_rmse", "xy_rmse_cm"]].rename(columns={"head_rmse": "b_h", "xy_rmse_cm": "b_x"}), on=["case", "arm", "seed"])
        sx["d_head"] = sx.head_rmse - sx.b_h; sx["d_xy"] = sx.xy_rmse_cm - sx.b_x
        agg = sx[sx.treat != "BASE"].groupby(["case", "arm", "treat", "m", "seed"])[["d_head", "d_xy"]].mean().reset_index()
        q = agg.groupby(["case", "arm", "treat", "m"]).agg(d_head_med=("d_head", "median"), d_head_min=("d_head", "min"), d_head_max=("d_head", "max"),
                                                          n_improve=("d_head", lambda v: int((v < 0).sum())), n_seed=("d_head", "size")).reset_index()
        q.to_csv(OUT / "JUDGE_E1_SEEDS.csv", index=False, float_format="%.6g")

    # ---------------------------------------------------------------- E4
    E4 = pd.concat([cat("E4_*_s0.csv"), cat("E4_*_sx.csv")], ignore_index=True)
    e4dec = {}
    if len(E4):
        E4["manip_ok"] = True
        pm = E4.treat == "PERM"
        E4.loc[pm, "manip_ok"] = E4.loc[pm, "chk_lag1_s_dm"] < 0.10          # A5: stratum-demeaned lag-1 < 0.1
        e4dec["perm_reps_failing_manipulation"] = int((~E4.loc[pm, "manip_ok"]).sum())
        e4dec["perm_reps_total"] = int(pm.sum())
        E4 = E4[E4.manip_ok]
        E4f = E4[E4["mask"] == "fixed"]
        chk_fail = E4f[(E4f.treat.isin(["PERM", "BLOCK"])) & (~E4f.chk_pairs_preserved.astype(bool))]
        e4dec["manipulation_pairs_not_preserved"] = int(len(chk_fail))
        idd = E4f[E4f.treat == "ID"]
        e4dec["id_state_diff_max"] = float(idd.id_state_diff.max()) if "id_state_diff" in idd else np.nan
        med = E4f.groupby(["case", "arm", "seed", "treat", "L_s"])[["head_rmse", "xy_rmse_cm", "head_z_rms", "s_cross_share", "s_mr_dh2_HPH", "chk_lag1_s", "chk_lag1_s_dm", "r_cross_share"]].median().reset_index()
        med.to_csv(OUT / "JUDGE_E4_MEDIANS.csv", index=False, float_format="%.6g")
        crit = []
        for (c, arm, seed), g in med.groupby(["case", "arm", "seed"]):
            i = g[g.treat == "ID"].iloc[0]; p = g[g.treat == "PERM"]
            if not len(p):
                continue
            p = p.iloc[0]
            c1 = abs(p.s_cross_share) <= 0.10
            c2 = (abs(math.log(p.head_z_rms)) < abs(math.log(i.head_z_rms))) and (abs(math.log(p.s_mr_dh2_HPH)) < abs(math.log(i.s_mr_dh2_HPH)))
            c3 = (p.head_rmse < i.head_rmse) and (p.xy_rmse_cm < i.xy_rmse_cm)
            crit.append(dict(case=c, arm=arm, seed=seed, c1=c1, c2=c2, c3=c3, all123=c1 and c2 and c3,
                             id_cross=i.s_cross_share, perm_cross=p.s_cross_share, id_head=i.head_rmse, perm_head=p.head_rmse,
                             id_xy=i.xy_rmse_cm, perm_xy=p.xy_rmse_cm, id_z=i.head_z_rms, perm_z=p.head_z_rms,
                             id_dh2=i.s_mr_dh2_HPH, perm_dh2=p.s_mr_dh2_HPH, id_lag1=i.chk_lag1_s, perm_lag1=p.chk_lag1_s))
        CR = pd.DataFrame(crit); CR.to_csv(OUT / "JUDGE_E4_CRITERIA.csv", index=False, float_format="%.6g")
        # criterion 4 (seed 0 dose-response)
        c4 = {}
        for (c, arm), g in med[med.seed == 0].groupby(["case", "arm"]):
            order = [("PERM", 0.2), ("BLOCK", 1.0), ("BLOCK", 2.0), ("BLOCK", 4.0), ("BLOCK", 8.0), ("ID", 0.0)]
            seq = [g[(g.treat == t_) & (np.isclose(g.L_s, l_))] for t_, l_ in order]
            if any(len(s_) == 0 for s_ in seq):
                continue
            cs = [abs(float(s_.s_cross_share.iloc[0])) for s_ in seq]; hs = [float(s_.head_rmse.iloc[0]) for s_ in seq]
            lag = [float(s_.chk_lag1_s.iloc[0]) for s_ in seq]
            c4[(c, arm)] = dict(rho_cross=spearman(range(6), cs), rho_head=spearman(range(6), hs), rho_lag1=spearman(range(6), lag),
                                seq_cross=cs, seq_head=hs, seq_lag1=lag)
        pd.DataFrame([dict(case=k[0], arm=k[1], **{kk: (json.dumps(v) if isinstance(v, list) else v) for kk, v in d.items()}) for k, d in c4.items()]).to_csv(OUT / "JUDGE_E4_DOSE.csv", index=False)
        for arm in ("MB_ORIG", "MB_VAR"):
            r = {}
            for c in MAIN:
                g = CR[(CR.case == c) & (CR.arm == arm)]
                r[c] = dict(n_seed=int(len(g)), n_c1=int(g.c1.sum()), n_c2=int(g.c2.sum()), n_c3=int(g.c3.sum()), n_all123=int(g.all123.sum()),
                            c4=bool(c4.get((c, arm), {}).get("rho_cross", -1) >= 0.8 and c4.get((c, arm), {}).get("rho_head", -1) >= 0.8))
            pg = med[(med.case == PROTECT) & (med.arm == arm)]
            pr = pg[pg.treat == "PERM"].head_rmse.median() / pg[pg.treat == "ID"].head_rmse.median() if len(pg) else np.nan
            c5 = bool(pr <= 1.10) if np.isfinite(pr) else None
            ok123 = all(r[c]["n_all123"] >= 8 for c in MAIN); ok1 = all(r[c]["n_c1"] >= 8 for c in MAIN); ok3 = all(r[c]["n_c3"] >= 8 for c in MAIN)
            ok4 = all(r[c]["c4"] for c in MAIN)
            verdict = "SUPPORT" if (ok123 and ok4 and c5) else ("PARTIAL" if (ok1 and not ok3) else ("REJECT" if not ok1 else "NOT_SUPPORTED"))
            e4dec[arm] = dict(per_case=r, protect_ratio=pr, c5=c5, verdict=verdict)
        md += ["## E4 시간상관 semi-synthetic replay (H_TC 판정)", "",
               f"- 조작 점검: 쌍 보존 실패 {e4dec['manipulation_pairs_not_preserved']}건, ID 상태차 최대 {e4dec['id_state_diff_max']:.3g}, PERM 반복 중 층-편차 lag-1 ≥ 0.1로 제외 {e4dec['perm_reps_failing_manipulation']}/{e4dec['perm_reps_total']}", ""]
        for arm in ("MB_ORIG", "MB_VAR"):
            d = e4dec[arm]
            md.append(f"- **{arm}: {d['verdict']}** — R5_aB 보호비 PERM/ID = {d['protect_ratio']:.3f} (기준 5: {d['c5']})")
            for c in MAIN:
                pc = d["per_case"][c]
                md.append(f"  - {c}: seed {pc['n_seed']} 중 기준1 {pc['n_c1']}, 기준2 {pc['n_c2']}, 기준3 {pc['n_c3']}, 1–3 동시 {pc['n_all123']}; 기준4 {pc['c4']}")
        md += ["", "| case | arm | ID 교차항 | PERM 교차항 | ID Heading | PERM Heading | ID XY | PERM XY | ID z_ψ | PERM z_ψ | lag-1 ID→PERM |", "|---|---|---|---|---|---|---|---|---|---|---|"]
        for (c, arm), g in CR.groupby(["case", "arm"]):
            f = lambda col: g[col].median()
            md.append(f"| {c} | {arm} | {f('id_cross'):+.3f} | {f('perm_cross'):+.3f} | {f('id_head'):.3f} | {f('perm_head'):.3f} | {f('id_xy'):.2f} | {f('perm_xy'):.2f} | {f('id_z'):.2f} | {f('perm_z'):.2f} | {f('id_lag1'):.2f}→{f('perm_lag1'):.2f} |")
        md += ["", "용량–반응(seed 0, 순서 PERM,B1,B2,B4,B8,ID):", ""]
        for (c, arm), d in c4.items():
            md.append(f"- {c} {arm}: Spearman |교차항| {d['rho_cross']:.2f}, Heading {d['rho_head']:.2f}, lag-1 {d['rho_lag1']:.2f}; Heading 열 {[round(v, 3) for v in d['seq_head']]}")
        rg = E4[E4["mask"] == "regen"]
        if len(rg):
            rq = rg.groupby(["case", "arm", "treat", "L_s"])[["head_rmse", "xy_rmse_cm", "n_upd"]].median().reset_index()
            rq.to_csv(OUT / "JUDGE_E4_REGEN.csv", index=False, float_format="%.6g")
        md.append("")
    dec["E4"] = e4dec

    # ---------------------------------------------------------------- E2 / E3
    E23 = cat("E23_*.csv"); ACF = cat("E2_ACF_*.csv")
    if len(E23):
        b = E23[E23.family == "BASE"][["case", "arm", "seed", "head_rmse", "xy_rmse_cm", "head_z_rms"]].rename(columns=lambda x: x if x in ("case", "arm", "seed") else "b_" + x)
        E = E23[E23.family != "BASE"].merge(b, on=["case", "arm", "seed"])
        E["d_head"] = E.head_rmse - E.b_head_rmse; E["d_xy"] = E.xy_rmse_cm - E.b_xy_rmse_cm; E["d_z"] = E.head_z_rms - E.b_head_z_rms
        q = E.groupby(["case", "arm", "family", "treat", "est"]).agg(d_head_med=("d_head", "median"), d_head_min=("d_head", "min"), d_head_max=("d_head", "max"),
                                                                     d_xy_med=("d_xy", "median"), d_z_med=("d_z", "median"),
                                                                     n_head_improve=("d_head", lambda v: int((v < 0).sum())), n=("d_head", "size")).reset_index()
        q.to_csv(OUT / "JUDGE_E23.csv", index=False, float_format="%.6g")
        inter = []
        for (c, est), g in q[(q.family == "E3") & (q.arm == "MB_ORIG")].groupby(["case", "est"]):
            d = g.set_index("treat").d_head_med
            if all(k in d for k in ("COV_RR", "COV_SS", "COV_RS", "COV_ALL")):
                inter.append(dict(case=c, est=est, d_rr=d["COV_RR"], d_ss=d["COV_SS"], d_rs=d["COV_RS"], d_all=d["COV_ALL"],
                                  interaction=d["COV_ALL"] - d["COV_RR"] - d["COV_SS"] - d["COV_RS"]))
        I = pd.DataFrame(inter); I.to_csv(OUT / "JUDGE_E3_INTERACTION.csv", index=False, float_format="%.6g")
        md += ["## E2 평균만 변경 / E3 공분산 항별 변경 (Heading RMSE 쌍대 차이, 10 seed 중앙값 [min, max], 음수=개선)", "",
               "| case | arm | 처치 | 추정표본 | ΔHeading | ΔXY | Δz_ψ | 개선 seed |", "|---|---|---|---|---|---|---|---|"]
        for _, r in q.iterrows():
            md.append(f"| {r.case} | {r.arm} | {r.treat} | {r.est if isinstance(r.est, str) else ''} | {r.d_head_med:+.3f} [{r.d_head_min:+.3f}, {r.d_head_max:+.3f}] | {r.d_xy_med:+.2f} | {r.d_z_med:+.2f} | {r.n_head_improve}/{r.n} |")
        md.append("")
        if len(I):
            md += ["E3 상호작용(MB_ORIG, ΔALL − ΣΔ단일):", ""] + [f"- {r.case} {r.est}: RR {r.d_rr:+.3f}, SS {r.d_ss:+.3f}, RS {r.d_rs:+.3f}, ALL {r.d_all:+.3f}, 상호작용 {r.interaction:+.3f}" for _, r in I.iterrows()] + [""]
    if len(ACF):
        ACF.to_csv(OUT / "JUDGE_E2_ACF.csv", index=False)
        md += ["E2 조건부 평균 제거 전후 ε 자기상관(평가 route, seed 0, S_all, t≥30):", "", "| case | comp | 모델 | RMS | lag-1 | 1/e lag (s) | 절반 이하 감소 |", "|---|---|---|---|---|---|---|"]
        for (c, comp), g in ACF.groupby(["case", "comp"]):
            base = g[g.model == "NONE"].l1e_s.iloc[0]
            for _, r in g.iterrows():
                halved = (r.l1e_s <= 0.5 * base) if (r.model != "NONE" and np.isfinite(base) and np.isfinite(r.l1e_s)) else ""
                md.append(f"| {c} | {comp} | {r.model} | {r.rms:.4f} | {r.lag1:.3f} | {r.l1e_s} | {halved} |")
        md.append("")

    # ---------------------------------------------------------------- E5
    INFO = cat("E5_INFO_*.csv"); ONE = cat("E5_ONESTEP_*.csv")
    if len(AS):
        lin = AS[(AS.set == "S_base") & (AS.seed == 0) & (AS.arm.isin(["MB_ORIG", "MB_VAR"]))]
        flag = lin[lin.ell_share > 0.3][["case", "arm", "window", "comp", "ell_share", "mr_dh2_HPH", "mr_He2_HPH"]]
        flag.to_csv(OUT / "JUDGE_E5_LINEARIZATION_FLAGS.csv", index=False, float_format="%.6g")
        md += ["## E5 기하·선형화", "", f"- ℓ 몫 > 0.3로 표시된 (case, arm, window, comp): {len(flag)}개 (JUDGE_E5_LINEARIZATION_FLAGS.csv)"]
        for _, r in flag.iterrows():
            md.append(f"  - {r.case} {r.arm} {r.window} {r.comp}: ℓ 몫 {r.ell_share:.2f}, mean δh²/HPH {r.mr_dh2_HPH:.2f}, mean (He)²/HPH {r.mr_He2_HPH:.2f}")
        md.append("")
    if len(INFO):
        INFO.to_csv(OUT / "JUDGE_E5_INFO.csv", index=False, float_format="%.6g")
        md += ["실패 창 정보행렬(prior 표준편차 정규화, 반경·접선 좌표):", "", "| case | arm | 창 | 최소 고유값 [rad,tan,ψ] | 최소 고유벡터 |rad|,|tan|,|ψ| | 정규화 대각 rad/tan/ψ | corr(tan,ψ) |", "|---|---|---|---|---|---|---|"]
        for _, r in INFO[INFO.window == "FAIL"].iterrows():
            md.append(f"| {r.case} | {r.arm} | {r.t_lo:g}–{r.t_hi:g} | {r.eig0:.3g} | {r.vmin_rad:.2f}, {r.vmin_tan:.2f}, {r.vmin_psi:.2f} | {r.In_diag_rad:.3g}/{r.In_diag_tan:.3g}/{r.In_diag_psi:.3g} | {r.corr_tan_psi:+.2f} |")
        md.append("")
    if len(ONE):
        last = ONE[ONE.step == ONE.groupby(["case", "arm", "treat"]).step.transform("max")]
        first = ONE[ONE.step == 1]
        m = last.merge(first[["case", "arm", "treat", "head_err_deg", "tan_err_cm"]], on=["case", "arm", "treat"], suffixes=("", "_1"))
        m["d_abs_head"] = m.head_err_deg.abs() - m.head_err_deg_1.abs(); m["d_abs_tan"] = m.tan_err_cm.abs() - m.tan_err_cm_1.abs()
        m.to_csv(OUT / "JUDGE_E5_ONESTEP.csv", index=False, float_format="%.6g")
        md += ["같은 prior에서 20 packet 재생(실패 창 시작, seed 0): |Heading 오차| 변화(°), |접선 오차| 변화(cm)", "", "| case | arm | 시작 t | ID | PERM | RSC_TOTAL_8 | COV_RS |", "|---|---|---|---|---|---|---|"]
        for (c, arm), g in m.groupby(["case", "arm"]):
            d = g.set_index("treat")
            cell = lambda t_: f"{d.loc[t_, 'd_abs_head']:+.3f}° / {d.loc[t_, 'd_abs_tan']:+.2f}" if t_ in d.index else "NA"
            md.append(f"| {c} | {arm} | {g.t_start.iloc[0]:g} | {cell('ID')} | {cell('PERM')} | {cell('RSC_TOTAL_8')} | {cell('COV_RS')} |")
        md.append("")

    # ---------------------------------------------------------------- E6
    S1 = cat("E6_STEP1_*.csv"); S2 = cat("E6_STEP2_*.csv")
    e6 = {}
    if len(S2):
        fx = S2[S2.cell == "FIXED_UV"][["case", "seed", "head_rmse", "xy_rmse_cm"]].rename(columns={"head_rmse": "fh", "xy_rmse_cm": "fx"})
        M = S2[~S2.cell.str.startswith("FIXED")].merge(fx, on=["case", "seed"])
        M["rel_h"] = (M.head_rmse - M.fh) / M.fh; M["rel_x"] = (M.xy_rmse_cm - M.fx) / M.fx
        q = M.groupby(["case", "cell", "thr"]).agg(head_med=("head_rmse", "median"), xy_med=("xy_rmse_cm", "median"),
                                                   rel_h_med=("rel_h", "median"), rel_x_med=("rel_x", "median"),
                                                   abs_rel_h_med=("rel_h", lambda v: float(np.median(np.abs(v)))), abs_rel_x_med=("rel_x", lambda v: float(np.median(np.abs(v)))),
                                                   n_used_med=("n_used", "median"), t_div_med=("t_div", "median")).reset_index()
        q.to_csv(OUT / "JUDGE_E6.csv", index=False, float_format="%.6g")
        for c, g in q[(q.cell == "G0UV") & (q.thr == "p99")].groupby("case"):
            r = g.iloc[0]; e6[c] = dict(abs_rel_head=r.abs_rel_h_med, abs_rel_xy=r.abs_rel_x_med, equivalent=bool(r.abs_rel_h_med <= .05 and r.abs_rel_x_med <= .05))
        fq = S2[S2.cell.str.startswith("FIXED")].groupby(["case", "cell"])[["head_rmse", "xy_rmse_cm"]].median()
        md += ["## E6 gate × update 2×2 (10 seed 중앙값)", "", "| case | 고정UV Heading/XY | 칸 | thr | Heading | XY | 고정UV 대비 Heading 상대차 | 수용 수 |", "|---|---|---|---|---|---|---|---|"]
        for _, r in q.iterrows():
            f = fq.loc[(r.case, "FIXED_UV")]
            md.append(f"| {r.case} | {f.head_rmse:.3f} / {f.xy_rmse_cm:.2f} | {r.cell} | {r.thr} | {r.head_med:.3f} | {r.xy_med:.2f} | {r.rel_h_med:+.1%} | {r.n_used_med:.0f} |")
        md += ["", "G0UV ≡ 고정 UV 판정(p99, |상대차| 중앙값 ≤ 5%):", ""] + [f"- {c}: Heading {d['abs_rel_head']:.1%}, XY {d['abs_rel_xy']:.1%} → {d['equivalent']}" for c, d in e6.items()] + [""]
    if len(S1):
        q1 = S1.groupby(["case", "prior_from", "gate", "thr", "group"]).agg(n_med=("n", "median"), r0_med=("med_abs_eps_over_sqrtR0", "median"),
                                                                            rv_med=("med_abs_eps_over_sqrtRV", "median")).reset_index()
        q1.to_csv(OUT / "JUDGE_E6_STEP1.csv", index=False, float_format="%.6g")
        md += ["E6 1단계(같은 prior, p99): 수용 변화 packet의 |ε_s| 정규화 중앙값", "", "| case | prior | gate | 그룹 | n | /√R₀ | /√R_VAR |", "|---|---|---|---|---|---|---|"]
        for _, r in q1[q1.thr == "p99"].iterrows():
            md.append(f"| {r.case} | {r.prior_from} | {r.gate} | {r.group} | {r.n_med:.0f} | {r.r0_med:.2f} | {r.rv_med:.2f} |")
        md.append("")
    dec["E6"] = e6

    # ---------------------------------------------------------------- E7
    au = Path(__file__).resolve().parent / "E7_P0_AUDIT.json"
    if au.exists():
        a = json.loads(au.read_text()); dec["E7"] = a.get("verdict")
        md += ["## E7 P0 감사", "", f"- 판정: {a.get('verdict')}", f"- 근거: {a.get('summary')}", ""]

    (OUT / "DECISIONS.json").write_text(json.dumps(dec, indent=1, default=lambda o: o if not isinstance(o, (np.floating, np.bool_)) else o.item()))
    (OUT / "RESULTS_SUMMARY.md").write_text("\n".join(md) + "\n")
    print("\n".join(md[:60]))


if __name__ == "__main__":
    main()
