#!/usr/bin/env python3
"""Independent stdlib auditor: historic 392-row 4-arm decomposition + 24 fixed/self contrasts.
No filter implementation import, no LFS; raw archived CSV Git blob SHA pinned.
"""
from __future__ import annotations
import csv,hashlib,io,json,pathlib,sys,urllib.request
GIT="ac9941f4fe5463a325c4c3899c1d9af73d4b6be4"
ROOT="https://raw.githubusercontent.com/myoungsunk/sionna-resimulation/"+GIT+"/"
PB="research/DS_MASK_CAUSAL_X1_X2_20261026/pol_bias_model/results/run_40652679303/PB_SCORES.csv"
D2="research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_premodel_diag_20261029/results/D2_GATE_SCORES.csv"
SHA_BLOB={PB:"10cab3f8ab2a08750669877f80f60a055e1b605d",D2:"efe55ff9b13b6c6c70f2820e26bacc88ca460d26"}
ARM=("BB_ORIG","MB_ORIG","BB_VAR","MB_VAR")
def fetch(path):
 with urllib.request.urlopen(ROOT+path,timeout=90) as z:b=z.read()
 sha=hashlib.sha1(("blob "+str(len(b))+"\0").encode()+b).hexdigest()
 if sha!=SHA_BLOB[path]:raise SystemExit("ERR_SOURCE_BLOB "+path+" "+sha)
 return list(csv.DictReader(io.StringIO(b.decode())))
def contrast(a,b,c,d):
 # Main effects are rmse *contrasts*, not linear state contributions.
 return {"mean_only":b-a,"var_only":c-a,"combined":d-a,
         "var_given_mean":d-b,"mean_given_var":d-c,"interaction":d-b-c+a}
def output_csv(path,rows):
 with path.open("w",newline="") as f:
  wr=csv.DictWriter(f,fieldnames=list(rows[0]));wr.writeheader();wr.writerows(rows)
def main(out):
 out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
 rows=fetch(PB);gate=fetch(D2)
 if len(rows)!=392:raise SystemExit("ERR_PB_ROWS")
 by={}
 for x in rows:
  key=(x["case"],x["bias"])
  (by.setdefault(key,{}))[x["arm"]]=x
 assert len(by)==28 and all(all(a in g for a in ARM) for g in by.values())
 metrics=[];groups={}
 for (case,bias),arms in sorted(by.items()):
  for metric,col in [("heading_deg","head_rmse"),("xy_cm","xy_rmse_cm")]:
   a,b,c,d=(float(arms[z][col]) for z in ARM)
   con=contrast(a,b,c,d)
   assert abs(con["interaction"]-(con["var_given_mean"]-con["var_only"]))<1e-10
   metrics.append(dict(case=case,bias=bias,metric=metric,y00=a,y10=b,y01=c,y11=d,**con))
 if len(metrics)!=56:raise SystemExit("ERR_FACTOR_ROWS")
 summary={}
 for metric in ("heading_deg","xy_cm"):
  summary[metric]={}
  for effect in ("mean_only","var_only","combined","var_given_mean","mean_given_var","interaction"):
   v=sorted(row[effect] for row in metrics if row["metric"]==metric)
   summary[metric][effect]=dict(improved=sum(x<0 for x in v),worse=sum(x>0 for x in v),
     mean=sum(v)/len(v),median=(v[13]+v[14])/2,min=v[0],max=v[-1])
 bygate={}
 for row in gate:
  if row["arm"]=="MB_VAR":bygate.setdefault((row["case"],row["bias"]),{})[row["gate"]]=row
 compared=[]
 for key,p in bygate.items():
  if set(p)!={"fixed","self"}:raise SystemExit("ERR_GATE_MODE")
  x,y=p["fixed"],p["self"]
  compared.append(dict(case=key[0],bias=key[1],delta_head=float(y["head_rmse"])-float(x["head_rmse"]),
    delta_xy=float(y["xy_rmse_cm"])-float(x["xy_rmse_cm"]),delta_n_used=int(y["n_used"])-int(x["n_used"])))
 if len(compared)!=24:raise SystemExit("ERR_GATE_24")
 if not all(r["delta_head"]>0 and r["delta_xy"]>0 for r in compared):raise SystemExit("ERR_GATE_WORSE_24")
 if summary["heading_deg"]["combined"]["improved"]!=23 or summary["xy_cm"]["combined"]["improved"]!=20:
  raise SystemExit("ERR_OLD_COUNT")
 output_csv(out/"RA4_28X2_HISTORIC_EFFECTS.csv",metrics)
 output_csv(out/"RA4_24_GATE_EFFECTS.csv",compared)
 qa=dict(status="PASS_HISTORIC_RETROSPECTIVE_ONLY",source_git_sha=GIT,source_blob_sha=SHA_BLOB,
   n_pb=392,n_conditions=28,n_metrics=56,n_gate_pairs=24,summary=summary,
   gate=dict(both_worse=24,mean_head_worse=sum(r["delta_head"] for r in compared)/24,
       mean_xy_worse=sum(r["delta_xy"] for r in compared)/24,
       min_delta_n_used=min(r["delta_n_used"] for r in compared),
       max_delta_n_used=max(r["delta_n_used"] for r in compared)),
   conclusion="Mean correction alone ≠ variance alone ≠ combined. SOURCE REPLAY only; same one corridor and gyro repeated.",
   unresolved="full new 336-arm self-gate/prior computation is a separate optional run; no claim of completion here.",
   science_release=False,independent_human_auditor=False)
 (out/"RA4_HISTORICAL_QA.json").write_text(json.dumps(qa,indent=2))
 print(json.dumps(qa),flush=True)
if __name__=="__main__":main(sys.argv[1] if len(sys.argv)>1 else "ra4_historical_out")
