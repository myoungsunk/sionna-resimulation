"""Read-only case/pose joined sensitivity-versus-physical-multipath analysis.
Source C1 is the EKF-prior Jacobian. C1B.g is the GT Jacobian
from original R2DIAG; verify its definition in R2DIAG source before interpreting.
"""
import pandas as pd, numpy as np, pathlib, json
ROOT=pathlib.Path(__file__).resolve().parents[2]
P=ROOT/"research/DS_MASK_CAUSAL_X1_X2_20261026/pol_azimuth_alloc"
a=pd.read_csv(P/"C1_PACKETS.csv.gz",usecols=["case","bias","arm","pose_id","t_s","scoring","accepted","h_psi","ds_dpsi_per_deg","d_gt_m"])
b=pd.read_csv(P/"C1B_PACKETS.csv.gz",usecols=["case","bias","arm","pose_id","e_true","r_base","g","s_pred_allGT"])
keys=["case","bias","arm","pose_id"]
v=a.merge(b,on=keys,validate="one_to_one")
assert len(v)==len(a) and v["g"].notna().all()
v=v[(v["case"].isin(["R4_aB_m0","R5_aB_m0"]))&(v["bias"]=="B0")&(v["arm"]=="BB")].copy()
v["abs_e"]=abs(v.e_true);v["abs_g"]=abs(v.g);v["abs_prior_g"]=abs(v.h_psi)
print("ROWS",len(v),flush=True)
print("COLUMNS",json.dumps(v.columns.tolist()),flush=True)
print("GT_VS_PRIOR_G_SAMPLES",v[["case","pose_id","g","h_psi","e_true"]].head(3).to_json(orient="records"),flush=True)
top_cases={"R4_aB_m0":[29,38,194,234,500,525,528,729],"R5_aB_m0":[401,465,507,979,980,982,983]}
for case,pids in top_cases.items():
 q=v[(v.case==case)&(v.pose_id.isin(pids))]
 print("POINTS",case,q[["pose_id","t_s","d_gt_m","g","h_psi","e_true","r_base","accepted","scoring"]].to_json(orient="records",double_precision=12),flush=True)
for case,sub in v.groupby("case"):
 for filtname,filt in [("all",sub),("score",sub[sub.scoring])]:
  for gtype in ["g","h_psi"]:
   ss=filt.copy()
   ss["quantile_bin"]=pd.qcut(abs(ss[gtype]),4,duplicates="drop")
   for bin,group in ss.groupby("quantile_bin",observed=True):
    print("BIN",json.dumps({"case":case,"pop":filtname,"gtype":gtype,"sensitivity_bin":str(bin),"n":len(group),"median_abs_g":float(abs(group[gtype]).median()),"mean_abs_e":float(group.abs_e.mean()),"rms_e":float(np.sqrt(np.mean(group.e_true**2))),"frac_abs_e_gt_0p2":float(np.mean(group.abs_e>.2)),"frac_abs_e_gt_0p3":float(np.mean(group.abs_e>.3))}),flush=True)
  for val in [.002,.005,.01,.02,.03]:
   group=filt[abs(filt["g"])*np.pi/180 < val]
   if len(group):
    print("LOWG",json.dumps({"case":case,"pop":filtname,"g_GT_per_deg_max":val,"n":len(group),"n_e_gt0p2":int((group.abs_e>.2).sum()),"max_abs_e":float(group.abs_e.max()),"max_idx":int(group.loc[group.abs_e.idxmax(),"pose_id"])}),flush=True)
v.to_csv("/tmp/sensitivity_vs_multipath.csv",index=False)
