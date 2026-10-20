#!/usr/bin/env python3
"""Summarize predeclared event-level RF physical traits vs prior causal RF-skip
effects, NO fitted decision rule, NOT independent environment generalization.
"""
import pathlib,sys,csv,json,math
root=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
rows=[]
for p in sorted(root.rglob("*_PHYSICAL_EVENTS.csv")):
 with p.open(newline="") as f:
  for r in csv.DictReader(f):
   if not r.get("skip_gain_reference_deg"):continue
   if r["status"]!="PHYSICAL_EVAL_ONLY":continue
   r["source"]=p.name
   rows.append(r)
assert len(rows)>=8,len(rows)
def val(r,k):
 try:return float(r[k])
 except (ValueError,TypeError,KeyError):return float("nan")
def auc(xs,ys):
 pp=[x for x,y in zip(xs,ys) if y==1];nn=[x for x,y in zip(xs,ys) if y==0]
 if not pp or not nn:return None
 return (sum((p>n)+.5*(p==n) for p in pp for n in nn))/(len(pp)*len(nn))
feat=["s_full_minus_los_RMS","d_s_interference_rms","d_s_detector_rms","FP_mismatch_fraction",
      "MP_over_LoS_median","destructive_fraction","port_alignment_median",
      "direct_fraction","RMS_s_after_half_amplitude"]
checks=[]
for subset in ["all","direct_frac_ge_0p75"]:
 selected=[r for r in rows if subset=="all" or val(r,"direct_fraction")>=.75]
 for k in feat:
  scored=[(val(r,k),float(r["skip_gain_reference_deg"])) for r in selected]
  scored=[x for x in scored if math.isfinite(x[0]) and math.isfinite(x[1])]
  xs=[x for x,y in scored];ys=[int(y>.2) for x,y in scored]
  checks.append({"subset":subset,"metric":k,"n":len(xs),"n_harmful_RF":sum(ys),"n_beneficial_RF":len(xs)-sum(ys),
                 "observed_AUC_high_metric_predicts_harm":auc(xs,ys),"mean_if_RF_harm":sum(x for x,y in zip(xs,ys) if y)/sum(ys) if sum(ys) else None,
                 "mean_if_RF_help":sum(x for x,y in zip(xs,ys) if not y)/(len(xs)-sum(ys)) if len(xs)>sum(ys) else None,
                 "method":"descriptive same-case, not a predictive model; threshold .2deg from reference exploratory cutoff"})
with (out/"PHYSICS_EVENT_DISCRIMINATION.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=list(checks[0]));w.writeheader();w.writerows(checks)
with (out/"PHYSICS_EVENT_JOINED.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=sorted(set().union(*(a.keys() for a in rows))));w.writeheader();w.writerows(rows)
print("N_EVENTS",len(rows),"HARMFUL",[a["route"]+"/"+a["anchor"]+"/"+a["region"]+"/v"+a["visit"] for a in rows if val(a,"skip_gain_reference_deg")>.2])
for s in checks:print("DESCRIPTIVE_AUC",json.dumps(s))
