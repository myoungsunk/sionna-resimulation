"""R5-3 preliminary held-route predictive tests of passive physical quality.
Measures oracle |s_full-s_nativeLoS| on held-out routes; NOT heading quality,
not calibrated EKF R, not external scene generalization.
"""
from __future__ import annotations
import argparse,ast,csv,hashlib,json,os,subprocess
from pathlib import Path
BASE=Path(__file__).resolve().parents[2]
DATA=BASE/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/OUTPUT"
HERE=BASE/"research/R5_FULLRF_HEADING_20261015"
def sha(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for chunk in iter(lambda:f.read(1<<20),b""):h.update(chunk)
 return h.hexdigest()
def save(p,d):Path(p).write_text(json.dumps(d,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
def pre(out):
 out.mkdir(parents=True,exist_ok=False)
 errs=[];known={}
 if os.environ.get("GITHUB_ACTIONS")!="true":errs.append("MUST_RUN_IN_ACTIONS")
 if subprocess.check_output(["git","rev-parse","HEAD"],cwd=BASE,text=True).strip()!=os.getenv("GITHUB_SHA"):
  errs.append("HEAD_MISMATCH")
 for fn in ("01_FEATURES.csv","02_LABELS_EVAL_ONLY.csv"):
  f=DATA/fn
  if not f.exists() or f.stat().st_size<100000:errs.append("FEATURE_MISSING:"+fn)
  else:known[fn]=sha(f)
 try:ast.parse((HERE/"r5_quality_held_route.py").read_text())
 except Exception as e:errs.append("SOURCE_SYNTAX:"+str(e))
 wf=BASE/".github/workflows/r5-quality-heldroute.yml"
 if not wf.exists():errs.append("WORKFLOW_MISSING")
 else:
  w=wf.read_text()
  if not (0<=w.find("r5_quality_held_route.py --phase pre")<w.find("r5_quality_held_route.py --phase run")):errs.append("AUDIT_ORDER")
 r={"stage":"R5_3","decision":"GO" if not errs else "HOLD",
    "git_sha":os.getenv("GITHUB_SHA"),"sha256":known,"errors":errs,
    "scope":"leave-one-route-out physical features for e_MP proxy only, not calibrated heading/R",
    "scientific_PASS":False}
 save(out/"PRE_AUDIT.json",r)
 print("R5_3_AUDIT "+json.dumps({"decision":r["decision"],"errors":errs}),flush=True)
 return 0 if not errs else 2
def run(out,preattr):
 import numpy as np
 import pandas as pd
 from sklearn.pipeline import make_pipeline
 from sklearn.impute import SimpleImputer
 from sklearn.preprocessing import StandardScaler
 from sklearn.linear_model import LogisticRegression, Ridge
 from sklearn.metrics import brier_score_loss, roc_auc_score
 out.mkdir(parents=True,exist_ok=False)
 a=json.loads(Path(preattr).read_text())
 if a["decision"]!="GO" or a["git_sha"]!=os.getenv("GITHUB_SHA"):raise RuntimeError("AUDIT_NOT_GO")
 for fn,h in a["sha256"].items():
  if sha(DATA/fn)!=h:raise RuntimeError("FEATURE_SHA_CHANGED")
 f=pd.read_csv(DATA/"01_FEATURES.csv")
 t=pd.read_csv(DATA/"02_LABELS_EVAL_ONLY.csv")
 key=["case","route","pose_id"]
 if f.duplicated(key).any() or t.duplicated(key).any():raise RuntimeError("NONUNIQUE_TRACE")
 data=f.merge(t,on=key,validate="one_to_one")
 if len(data)!=9519:raise RuntimeError("INCOMPLETE_SOURCE")
 labels=(np.abs(data["e_MP"].to_numpy(float))>.1).astype(int)
 groups=data["route"].to_numpy()
 features={
   "range_only":["range_m"],
   "range_power_s":["range_m","s","P5_log_power"],
   "cir_only":["D1_mean_ns","D1_diff_ns","D2_rx1","D2_rx2","P1_jsd","P2_peak_difference_ns","P3_early_asymmetry","P4_shape_L1"],
   "range_power_s_plus_CIR":["range_m","s","P5_log_power","D1_mean_ns","D1_diff_ns","D2_rx1","D2_rx2","P1_jsd","P2_peak_difference_ns","P3_early_asymmetry","P4_shape_L1"]
 }
 results=[];held_predictions=[]
 for hold in sorted(set(groups)):
  training=groups!=hold;test=groups==hold
  for name,columns in features.items():
   XX=data[columns].apply(pd.to_numeric,errors="coerce").replace([np.inf,-np.inf],np.nan).to_numpy(float)
   clf=make_pipeline(SimpleImputer(strategy="median"),StandardScaler(),
                     LogisticRegression(C=1.,max_iter=500,random_state=20261015))
   clf.fit(XX[training],labels[training])
   prob=np.clip(clf.predict_proba(XX[test])[:,1],1e-6,1-1e-6)
   true=labels[test]
   brier=float(brier_score_loss(true,prob))
   auc=float(roc_auc_score(true,prob)) if len(np.unique(true))==2 else None
   prior=float(np.mean(labels[training]))
   baseline=float(brier_score_loss(true,np.full(len(true),prior)))
   ece=float(sum(np.mean((prob>=i/10)&(prob<(i+1)/10))*
             abs(np.mean(true[(prob>=i/10)&(prob<(i+1)/10)])-
                 np.mean(prob[(prob>=i/10)&(prob<(i+1)/10)]))
             for i in range(10) if np.any((prob>=i/10)&(prob<(i+1)/10))))
   results.append({"held_route":hold,"model":name,
     "n_train":int(training.sum()),"n_test":int(test.sum()),
     "observed_bad_rate":float(true.mean()),"mean_predicted_bad_rate":float(prob.mean()),
     "brier":brier,"brier_train_prior_baseline":baseline,
     "brier_gain_vs_prior":baseline-brier,"auroc":auc,"ECE10":ece})
   for pid,pr,tr in zip(data.loc[test,"pose_id"].to_numpy(),prob,true):
    held_predictions.append({"held_route":hold,"case_pose":str(pid),
         "model":name,"bad_prob":float(pr),"oracle_bad_label_e_MP":int(tr)})
 frame=pd.DataFrame(results)
 frame.to_csv(out/"R5_3_HELDROUTE_SCORES.csv",index=False)
 pd.DataFrame(held_predictions).to_csv(out/"R5_3_HELDROUTE_PREDICTIONS.csv",index=False)
 agg=[]
 for name,g in frame.groupby("model"):
  agg.append({"model":name,"pooled_test_frames":int(g.n_test.sum()),
    "weighted_brier":float(np.average(g.brier,weights=g.n_test)),
    "weighted_prior_baseline":float(np.average(g.brier_train_prior_baseline,weights=g.n_test)),
    "weighted_gain":float(np.average(g.brier_gain_vs_prior,weights=g.n_test)),
    "mean_route_auroc":float(g.auroc.mean()),
    "worst_route_brier_gain":float(g.brier_gain_vs_prior.min())})
 final={"stage":"R5_3","status":"HELD_ROUTE_MP_PROXY_CROSSVALIDATION_COMPLETE",
   "source_rows":len(data),"per_route_results":results,"aggregated":agg,
   "measure":"P(abs(s_full - direct_native_LoS_s) > 0.1 | q)",
   "caution":["All three routes share a corridor; no independent-scene generalization",
              "Same simulation scene and noise-free RF; not heading <=5deg quality",
              "No online RF covariance updated; no R_s(q) calibrated",
              "Fraction of improved cross-validated proxy scores does not prove reduced heading RMSE or NEES"],
   "scientific_PASS":False}
 save(out/"R5_3_FINAL.json",final)
 print("R5_3_FINAL "+json.dumps({"status":final["status"],"aggregation":agg,"n":len(data)}),flush=True)
 return 0
if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("--phase",required=True,choices=["pre","run"])
 p.add_argument("--out",required=True)
 p.add_argument("--audit")
 a=p.parse_args()
 raise SystemExit(pre(Path(a.out)) if a.phase=="pre" else run(Path(a.out),a.audit))
