"""N4-A-E: read-only event-level audit of the N4-A stored traces.
No model fitting, filter reruns, RF ground truth inference or causal claims.
"""
import argparse,ast,csv,gzip,hashlib,io,json,math,os,statistics,subprocess,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
ART_SHA="83735d5551b6a70aec05874c73ac873cc9f4e09b3e45a6900f9af39098ff3ce3"
SOURCE_BLOB="f51b84ea3e02d1282f8a25277cd4842b1bbb738a"
METHODS=("R0_J4","SOFT_G5_MEAN_RS")
BIAS=("L0","L1","L2")
FIELDS=("pose_nees","xy_cond_nees","xy_small_axis_nees","xy_large_axis_nees",
 "rf_innovation_r_m","rf_innovation_s_after_mean_correction",
 "cov_xy_cond_det_ratio_post_over_prior","cov_heading_variance_ratio_post_over_prior",
 "risk_pbad_G5","normalized_pose_condition","xy_cond_lambda_min_m2",
 "xy_cond_error_m","rf_update_jump_heading_deg","rf_update_jump_bias_dps",
 "prior_pose_nees","post_minus_prior_nees")

def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def blob(p):
 p=Path(p);h=hashlib.sha1(b"blob "+str(p.stat().st_size).encode()+b"\0")
 with open(p,"rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def save(p,v):Path(p).write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
def audit(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 err=[];head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
 if os.getenv("GITHUB_ACTIONS")!="true":err.append("GITHUB_ACTIONS_REQUIRED")
 if head!=os.getenv("GITHUB_SHA"):err.append("HEAD_CHANGED")
 f=ROOT/"research/R5_N4A_NEES_20261015/n4a_nees_rootcause.py"
 if not f.is_file() or blob(f)!=SOURCE_BLOB:err.append("BASE_N4A_SOURCE_CHANGED")
 try:ast.parse((HERE/"n4a_events.py").read_text())
 except Exception as e:err.append("SYNTAX:"+str(e))
 w=ROOT/".github/workflows/r5-n4a-events.yml"
 if not w.exists():err.append("WORKFLOW_MISSING")
 elif not(0<=w.read_text().find("n4a_events.py --phase pre")<
         w.read_text().find("n4a_events.py --phase run") and
         "if: always()" in w.read_text()):err.append("WORKFLOW_AUDIT_ORDER")
 rec={"decision":"GO" if not err else "HOLD","source_commit":head,
   "parent_n4a_artifact_sha":ART_SHA,"errors":err}
 save(out/"PRE_AUDIT.json",rec)
 print("EVENT_PRE "+json.dumps(rec),flush=True)
 return 0 if not err else 2
def member(z,name):
 a=[q for q in z.namelist() if q==name or q.endswith("/"+name)]
 if len(a)!=1:raise ValueError("NONUNIQUE_ARCHIVE_MEMBER:"+name)
 return a[0]
def rows(z,name):
 with gzip.open(io.BytesIO(z.read(member(z,name))),"rt",encoding="utf8",newline="") as f:
  return list(csv.DictReader(f))
def val(r,name):
 a=r.get(name)
 return float(a) if a not in ("",None,"nan","NaN","None") else None
def stats(v):
 a=sorted(v)
 if not a:return {"n":0,"median":None,"mean":None}
 return {"n":len(a),"median":float(statistics.median(a)),"mean":float(statistics.mean(a))}
def median_field(rows,field):
 v=[val(r,field) for r in rows];return stats([x for x in v if x is not None])
def events(trigger):
 out=[];start=None
 for i,yes in enumerate(trigger+[False]):
  if yes and start is None:start=i
  if not yes and start is not None:
   out.append((start,i-1));start=None
 return out
def execute(archive,pre,out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 a=json.loads(Path(pre).read_text())
 if a["decision"]!="GO" or a["source_commit"]!=os.getenv("GITHUB_SHA"):
  raise RuntimeError("AUDIT_NOT_GO")
 if sha(archive)!=ART_SHA:raise RuntimeError("INPUT_SHA_CHANGED")
 all_events=[];comparisons=[];field_summaries=[];gate_changes=[]
 with zipfile.ZipFile(archive) as z:
  if z.testzip():raise RuntimeError("ZIP_CRC_FAILED")
  original=json.loads(z.read(member(z,"N4A_FINAL.json")))
  if original["status"]!="N4A_ARCHIVED_POSE_NEES_DECOMPOSITION_COMPLETE" or not original["source_score_parity_pass"]:
   raise RuntimeError("UPSTREAM_N4A_NOT_PASS")
  for case in ("R2_aA_m0","R2_aA_m45"):
   for bias in BIAS:
    d={m:rows(z,f"N4A_TRACE_{case}_full_{bias}_{m}.csv.gz") for m in METHODS}
    for m,x in d.items():
     if len(x)!=979 or sum(r["eval"]=="True" for r in x)!=829:
      raise RuntimeError("UPSTREAM_TRACE_INCOMPLETE:"+m)
    left,right=(d[m] for m in METHODS)
    if any((x["pose_id"],x["t_s"])!=(y["pose_id"],y["t_s"]) for x,y in zip(left,right)):
     raise RuntimeError("PAIRED_TRACE_ALIGNMENT")
    evaluated=[(a,b) for a,b in zip(left,right) if b["eval"]=="True"]
    nees=[val(y,"pose_nees") for x,y in evaluated]
    ref=[val(x,"pose_nees") for x,y in evaluated]
    mean=statistics.mean(nees)
    threshold=sorted(nees)[-math.ceil(.05*len(nees))]
    severe=[v>1000 for v in nees]
    periods=events(severe)
    # The high-nees episodes are defined before checking RF features.
    for first,last in periods:
     chosen=evaluated[first:last+1]
     preceding=evaluated[max(0,first-5):first]
     following=evaluated[last+1:min(len(evaluated),last+6)]
     records=[y for x,y in chosen];old=[x for x,y in chosen]
     all_events.append({
      "case":case,"bias":bias,"start_s":val(records[0],"t_s"),
      "end_s":val(records[-1],"t_s"),"frames":len(records),
      "max_pose_nees":max(val(x,"pose_nees") for x in records),
      "mean_pose_nees":statistics.mean(val(x,"pose_nees") for x in records),
      "mean_xy_cond_nees":statistics.mean(val(x,"xy_cond_nees") for x in records),
      "mean_small_axis_contribution":statistics.mean(val(x,"xy_small_axis_nees") for x in records),
      "mean_joint4_pose_nees":statistics.mean(val(x,"pose_nees") for x in old),
      "mean_abs_range_innovation":statistics.mean(abs(val(x,"rf_innovation_r_m")) for x in records),
      "mean_abs_s_innovation":statistics.mean(abs(val(x,"rf_innovation_s_after_mean_correction")) for x in records),
      "gate_G5_accept_fraction":statistics.mean(x["gate_accepted"]=="True" for x in records),
      "gate_J4_accept_fraction":statistics.mean(x["gate_accepted"]=="True" for x in old),
      "gate_changed_count":sum(x["gate_accepted"]!=y["gate_accepted"] for x,y in chosen),
      "preceding5_mean_nees":statistics.mean(val(x,"pose_nees") for _,x in preceding) if preceding else None,
      "following5_mean_nees":statistics.mean(val(x,"pose_nees") for _,x in following) if following else None,
      "mean_xy_eigen_min":statistics.mean(val(x,"xy_cond_lambda_min_m2") for x in records),
      "mean_xy_cond_error":statistics.mean(val(x,"xy_cond_error_m") for x in records),
     })
    top=[(x,y) for x,y in evaluated if val(y,"pose_nees")>=threshold]
    rest=[(x,y) for x,y in evaluated if val(y,"pose_nees")<threshold]
    for group,sub in (("top5pct",top),("remaining95pct",rest)):
     new=[y for x,y in sub];old=[x for x,y in sub]
     for f in FIELDS:
      good=[val(r,f) for r in new];good=[v for v in good if v is not None]
      before=[val(r,f) for r in old];before=[v for v in before if v is not None]
      field_summaries.append({"case":case,"bias":bias,"group":group,"field":f,
       "G5_median":stats(good)["median"],"Joint4_median":stats(before)["median"],
       "G5_mean":stats(good)["mean"],"Joint4_mean":stats(before)["mean"]})
    for tag,sub in (("all829",evaluated),("top5pct",top),("other95pct",rest)):
     for risk_group in ("both_accept","G5_only_accept","J4_only_accept","both_reject"):
      keep=[]
      for x,y in sub:
       key=("G5_only_accept" if y["gate_accepted"]=="True" and x["gate_accepted"]=="False" else
         "J4_only_accept" if x["gate_accepted"]=="True" and y["gate_accepted"]=="False" else
         "both_accept" if x["gate_accepted"]=="True" else "both_reject")
       if key==risk_group:keep.append((x,y))
      gate_changes.append({"case":case,"bias":bias,"region":tag,
       "gate_group":risk_group,"n":len(keep),
       "mean_G5_pose_nees":statistics.mean(val(y,"pose_nees") for x,y in keep) if keep else None,
       "mean_J4_pose_nees":statistics.mean(val(x,"pose_nees") for x,y in keep) if keep else None})
    comparisons.append({"case":case,"bias":bias,"frames":len(evaluated),
      "G5_pose_nees_mean":mean,"J4_pose_nees_mean":statistics.mean(ref),
      "G5_gt1000_count":sum(severe),"G5_gt1000_event_count":len(periods),
      "G5_top5_threshold":threshold,
      "G5_top5_sum_share":sum(val(y,"pose_nees") for x,y in top)/sum(nees),
      "G5_only_gate_count":sum(y["gate_accepted"]=="True" and x["gate_accepted"]=="False" for x,y in evaluated),
      "J4_only_gate_count":sum(x["gate_accepted"]=="True" and y["gate_accepted"]=="False" for x,y in evaluated)})
    print("EVENT_CASE "+json.dumps(comparisons[-1]),flush=True)
 def export(name,records):
  with (out/name).open("w",newline="",encoding="utf8") as f:
   w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
 export("N4A_EVENT_WINDOWS.csv",all_events)
 export("N4A_EVENT_FIELDS.csv",field_summaries)
 export("N4A_GATE_CROSS_TABS.csv",gate_changes)
 export("N4A_EVENT_COMPARISONS.csv",comparisons)
 focus=next(x for x in comparisons if x["case"]=="R2_aA_m0" and x["bias"]=="L2")
 if abs(focus["G5_pose_nees_mean"]-5957.582129835652)>1e-5:
  raise RuntimeError("N4A_PREVIOUS_POSE_NEES_PARITY_FAILED")
 result={"status":"N4A_EXTREME_EVENT_AUDIT_PASS",
   "reference_artifact_sha256":ART_SHA,"source_commit":os.getenv("GITHUB_SHA"),
   "event_definition":"maximal contiguous eval windows with G5 Pose NEES >1000; top5% is separate distribution slice",
   "comparison":comparisons,"event_windows":all_events,
   "observations_only":True,
   "limitations":["Innovation and gate comparisons are from separate filter priors",
     "A co-occurring gate change cannot prove physical cause",
     "G5 innovation s includes its learned signed-mean correction whereas J4 uses raw s",
     "The stored N4A trace does not contain first-path tap transition IDs",
     "No new estimator, time-matched gate intervention or independent scene"],
   "N4B_training_GO":"CONDITIONAL"}
 save(out/"EVENT_FINAL.json",result)
 print("EVENT_FINAL "+json.dumps({"status":result["status"],"focus":focus,
     "windows":len(all_events),"l2_m0_windows":[r for r in all_events if r["case"]=="R2_aA_m0" and r["bias"]=="L2"]}),flush=True)
 return 0
if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("--phase",choices=("pre","run"),required=True)
 p.add_argument("--out",required=True);p.add_argument("--input");p.add_argument("--audit")
 a=p.parse_args()
 raise SystemExit(audit(a.out) if a.phase=="pre" else execute(a.input,a.audit,a.out))
