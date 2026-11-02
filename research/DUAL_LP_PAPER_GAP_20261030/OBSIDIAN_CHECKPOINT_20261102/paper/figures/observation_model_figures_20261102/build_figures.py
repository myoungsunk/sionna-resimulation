"""Render existing published aggregates only; no simulation, fitting or EKF replay."""
from pathlib import Path
import hashlib, json, sys
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parent
SRC, TAB, OUT = ROOT/"sources", ROOT/"tables", ROOT/"plots"
for p in (TAB, OUT): p.mkdir(exist_ok=True)
plt.rcParams.update({"font.family":"Times New Roman", "font.size":9,
 "axes.labelsize":9, "axes.titlesize":9, "legend.fontsize":8,
 "xtick.labelsize":8, "ytick.labelsize":8, "axes.linewidth":0.65,
 "lines.linewidth":1.2, "pdf.fonttype":42, "ps.fonttype":42,
 "svg.fonttype":"none", "savefig.facecolor":"white"})
ROUTES = ["R2_aB_m0","R4_aB_m0","R5_aB_m0"]
LABELS = ["R2-B","R4-B","R5-B"]
COLORS = ["#222222","#0072B2","#D55E00","#009E73"]
generated = []
def finish(fig, name):
    for ax in fig.axes:
        ax.spines[["top","right"]].set_visible(False)
        ax.grid(axis="y", color=".88", linewidth=.45)
        ax.set_axisbelow(True)
    fig.tight_layout(pad=.7)
    for ext in ("png","pdf","svg"):
        path=OUT/f"{name}.{ext}"
        fig.savefig(path,dpi=600)
        generated.append(str(path.relative_to(ROOT)))
    plt.close(fig)
def export(df,name):
    df.to_csv(TAB/name,index=False,encoding="utf-8-sig")
    assert len(df)>0, name
    assert not np.isinf(df.select_dtypes("number").to_numpy()).any(), name
    return df

# A: distance bins: equal-width category slots, not fictitious numeric bin centres.
dist = pd.read_csv(SRC/"D3_EPS_BY_DISTANCE.csv")
sel = dist[dist.case.isin(ROUTES)].copy()
export(sel, "A_distance_residuals.csv")
fig, axs = plt.subplots(2,3,figsize=(7.16,4.1),sharex="col")
for j,case in enumerate(ROUTES):
    d=sel[(sel.case==case)&(sel.comp=="r")]
    bins=sorted(d.rho_lo.unique())
    labels=[f"{lo:g}–{hi:g}" if hi<99 else f"{lo:g}–99" for lo,hi in
        d[d.background=="BB"].sort_values("rho_lo")[["rho_lo","rho_hi"]].values]
    for bg,c,m in [("BB",COLORS[0],"o"),("MB",COLORS[1],"s")]:
        a=d[d.background==bg].sort_values("rho_lo")
        assert a.rho_lo.tolist()==bins
        axs[0,j].plot(range(len(a)),100*a.rms_eps,marker=m,color=c,label=bg+" mean")
    a=sel[(sel.case==case)&(sel.comp=="s")&(sel.background=="BB")].sort_values("rho_lo")
    axs[1,j].plot(range(len(a)),a.rms_eps,"o-",color=COLORS[2],label="Residual RMS")
    axs[1,j].plot(range(len(a)),a.sqrt_mean_Rbase,"s--",color=COLORS[0],label=r"$\sqrt{\langle R^B_{ss}\rangle}$")
    axs[1,j].plot(range(len(a)),a.sqrt_mean_Rvar,"^:",color=COLORS[1],label="With lookup (true distance)")
    axs[0,j].set_title(f"({chr(97+j)}) {LABELS[j]}: range")
    axs[1,j].set_title(f"({chr(100+j)}) {LABELS[j]}: polarization")
    axs[1,j].set_xticks(range(len(labels)),labels,rotation=25)
    axs[1,j].set_xlabel("True horizontal distance bin (m)")
    for ax in axs[:,j]: ax.set_ylim(bottom=0)
axs[0,0].set_ylabel("Range residual RMS (cm)")
axs[1,0].set_ylabel("Signed-s residual / std. scale")
for ax in axs[0]: ax.set_ylim(0,20.5)
for ax in axs[1]: ax.set_ylim(0,.30)
axs[0,0].legend(frameon=False)
axs[1,0].legend(frameon=False,fontsize=6.2)
finish(fig,"A_distance_residuals")

# B: summaries only. No synthetic autocorrelation curves.
temp=pd.read_csv(SRC/"D3_EPS_TEMPORAL.csv")
temp=temp[temp.case.isin(ROUTES)&(temp.background=="BB")&(temp.comp=="s")].set_index("case").loc[ROUTES].reset_index()
export(temp,"B_temporal_summary.csv")
fig,axs=plt.subplots(1,3,figsize=(7.16,2.25))
for ax,col,title,unit in zip(axs,["lag1_r","acf_1e_s","acf_1e_m"],
 ["(a) Lag-1 autocorrelation","(b) First 1/e time lag","(c) Travel at 1/e lag"],
 ["Correlation","Time (s)","Travel distance (m)"]):
    v=temp[col].to_numpy()
    ax.bar(LABELS,v,color=COLORS[1],width=.52)
    for i,y in enumerate(v): ax.text(i,y+max(v)*.035,f"{y:.3g}",ha="center",fontsize=8)
    ax.set_ylim(0,1 if col=="lag1_r" else max(v)*1.25)
    ax.set_title(title);ax.set_ylabel(unit)
finish(fig,"B_temporal_summary")

# C: exact current manuscript selected scores, four arms on B0/self.
scores=pd.read_csv(SRC/"SELECTED_12_CONDITIONS_RECHECK.csv")
assert len(scores)==12 and not scores.duplicated(["case","bias"]).any()
export(scores,"selected_12_conditions.csv")
b0=scores[scores.bias=="B0"].set_index("case").loc[ROUTES].reset_index()
export(b0,"C_B0_four_arm_scores.csv")
arms=[("baseline","BB_ORIG"),("mean_only","MB_ORIG"),("variance_only","BB_VAR"),("combined","MB_VAR")]
fig,axs=plt.subplots(1,2,figsize=(7.16,2.75))
for ax,metric,unit,title in zip(axs,["H_deg","XY_cm"],["Heading RMSE (deg)","XY RMSE (cm)"],["(a) Heading","(b) Position"]):
    x=np.arange(3);w=.18
    for k,(prefix,label) in enumerate(arms):
        y=b0[f"{prefix}_{metric}"].to_numpy()
        ax.bar(x+(k-1.5)*w,y,w,color=COLORS[k],label=label)
    ymax=max(b0[f"{prefix}_{metric}"].max() for prefix,_ in arms)
    ax.set_xticks(x,LABELS);ax.set_ylim(0,ymax*1.35);ax.set_ylabel(unit);ax.set_title(title)
axs[0].legend(frameon=False,ncol=2,fontsize=7)
finish(fig,"C_B0_four_arm_scores")

# D: all conditions retained, baseline-relative reductions; negative = worsening.
order=[(r,b) for r in ROUTES for b in ["B0","L0","L1","L2"]]
s=scores.set_index(["case","bias"]).loc[order].reset_index()
h=100*(1-s.combined_H_deg/s.baseline_H_deg)
xy=100*(1-s.combined_XY_cm/s.baseline_XY_cm)
assert np.allclose(h,s.heading_reduction_pct,atol=1e-8)
assert np.allclose(xy,s.xy_reduction_pct,atol=1e-8)
assert (h>0).sum()==12 and (xy>0).sum()==8
fig,axs=plt.subplots(1,2,figsize=(7.16,3.55),sharey=True)
labels=[f"{LABELS[ROUTES.index(r)]} / {b}" for r,b in order]
for ax,v,title in zip(axs,[h,xy],["(a) Heading RMSE reduction","(b) XY RMSE reduction"]):
    yy=np.arange(12)
    ax.barh(yy,v,color=[COLORS[1] if a>=0 else COLORS[2] for a in v],height=.62)
    ax.axvline(0,color="black",linewidth=.7)
    ax.set_yticks(yy,labels);ax.set_title(title);ax.set_xlabel("Reduction vs BB_ORIG (%)")
    ax.set_xlim(min(-15,float(min(v))-4),max(v)+9)
    for i,a in enumerate(v): ax.text(a+(0.7 if a>=0 else -.7),i,f"{a:.1f}",va="center",ha="left" if a>=0 else "right",fontsize=7)
    for boundary in [3.5,7.5]: ax.axhline(boundary,color=".8",linewidth=.6)
axs[0].invert_yaxis()
finish(fig,"D_all12_performance_change")

# E: document-reported, rounded physical diagnostics; never represented as raw replay.
phys=pd.DataFrame({"route":LABELS,"n":[829,592,1265],"median_abs_H_spsi_rad_inv":[.461,1.775,.405],
 "full_minus_los_s_rms":[.113,.117,.095],"post_mean_s_residual_rms":[.107,.123,.093],
 "evidence_level":["DOCUMENT_REPORTED_ROUNDED"]*3,"mask":["t>=30 s; gate-unselected; true-pose active-branch"]*3})
export(phys,"E_physical_diagnostics_document_reported.csv")
fig,axs=plt.subplots(1,3,figsize=(7.16,2.35))
for ax,col,title,ylabel in zip(axs,["median_abs_H_spsi_rad_inv","full_minus_los_s_rms","post_mean_s_residual_rms"],
 [r"(a) Heading sensitivity $|H_{s\psi}|$","(b) Full–LoS signed-s difference","(c) Post-mean signed-s residual"],
 [r"Median (rad$^{-1}$)","RMS","RMS"]):
    v=phys[col]
    ax.bar(LABELS,v,color=COLORS[1],width=.5)
    for i,y in enumerate(v): ax.text(i,y+max(v)*.035,f"{y:.3f}",ha="center",fontsize=8)
    ax.set_ylim(0,max(v)*1.25);ax.set_title(title,fontsize=8);ax.set_ylabel(ylabel)
finish(fig,"E_physical_diagnostics_document_reported")

# No observations in this schema: it is a requested-data template.
schema=["scene_id","route_id","anchor_id","mount_deg","seed","packet_id","t_s","channel_treatment","arm",
 "gt_x_m","gt_y_m","gt_psi_rad","rho_true_m","rho_lookup_m","incidence_deg","los_bearing_rad",
 "tap_full","tap_los","P_plus_full","P_minus_full","P_plus_los","P_minus_los","s_full","s_los",
 "h_s_gt","h_s_prior","H_spsi_gt_rad_inv","H_spsi_prior_rad_inv","fd_stable_gt","fd_stable_prior",
 "mu_r_m","mu_s","R_ss_base","R_ss_added","R_ss_used","eps_r_m","eps_s","delta_h_s","nu_s",
 "Kpsi_eps","Kpsi_delta_h","heading_error_prior_rad","heading_error_post_rad","xy_error_post_m",
 "nis","accepted","mask_id","source_sha256"]
pd.DataFrame(columns=schema).to_csv(TAB/"REQUIRED_packet_schema_EMPTY.csv",index=False)
notes=[
 ("F0","Matched LoS / Full / Full+model mechanism and performance","NOT_READY","Matched raw packet and recursive traces; cannot infer from aggregates"),
 ("F1","Fixed-position direct-path yaw response","EXISTING","../fig01_los_azimuth; normal incidence only"),
 ("F2","Route physical sensitivity and Full-LoS distortion","DOC_SUMMARY_READY_RAW_PENDING","E; raw time/distance sensitivity still required"),
 ("F3","Distance-conditioned range and polarization residuals","AGGREGATE_READY","A; true-distance bins; old diagnostic masks"),
 ("F4","Temporal persistence","SUMMARY_READY_CURVE_PENDING","B; no full ACF or time trace"),
 ("F5","Mean/variance mechanism at common prior","NOT_READY","Common sample trace required; original 896 strata have incompatible masks"),
 ("F6","Four-arm recursive performance and gyro-bias dependence","AGGREGATE_READY","C/D; selected 12, one physical scene")]
pd.DataFrame(notes,columns=["figure_id","purpose","status","available_or_required"]).to_csv(TAB/"figure_requirements.csv",index=False,encoding="utf-8-sig")
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
reg=json.loads((ROOT/"source_register.json").read_text())
for entry in reg["sources"]:
    entry["local_sha256"]=sha(ROOT/entry["local_file"])
    # Git blob hash validates exact UTF-8 content against the pinned Git tree.
    data=(ROOT/entry["local_file"]).read_bytes()
    blob=hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
    entry["local_git_blob_sha"]=blob
    entry["byte_identical_to_git_blob"]=blob==entry["git_blob_sha"]
gov=Path("C:/Users/Myoungsun Kim/.codex/research-governance")
contracts={str(p):sha(p) for p in gov.rglob("*.md") if p.name in ["COMMON_CONTRACT.md","ROLE_PROPOSER.md","ROLE_IMPLEMENTER.md"]}
manifest={"question_id":"FIG-PREP-LOS-MP-MODEL-20261102","created_utc":datetime.now(timezone.utc).isoformat(),
 "activity":"Existing-data figure preparation; PROPOSER -> IMPLEMENTER; self-check only",
 "new_RT_or_EKF_runs":False,"source_register":reg,"governance_local_fallback_sha256":contracts,
 "font":font_manager.findfont("Times New Roman"),"formats":{"width_in":7.16,"png_dpi":600,"vector":["pdf","svg"],"pdf_fonttype":42},
 "checks":{"selected_conditions":len(scores),"heading_improved":int((h>0).sum()),"xy_improved":int((xy>0).sum()),
 "packet_template_rows":0,"raw_packet_reconstruction":False},
 "outputs":{str(p.relative_to(ROOT)):sha(p) for p in sorted(list(TAB.glob("*"))+list(OUT.glob("*")))},
 "limitations":["Single scene; reused RF across gyro biases","E values are rounded document summaries",
 "A true-rho diagnostic Rvar is not logged runtime R_used","B full-time mask differs from A/E t>=30",
 "No matched LoS recursive performance or cumulative causal decomposition"]}
(ROOT/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"plots":len(generated)//3,"tables":len(list(TAB.glob("*.csv"))),"checks":manifest["checks"],
 "source_byte_identity":{a["local_file"]:a["byte_identical_to_git_blob"] for a in reg["sources"]}},ensure_ascii=False))

