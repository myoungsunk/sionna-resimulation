#!/usr/bin/env python3
"""P1/P4: source-backed MB_VAR failures, no filter rerun; per-case paired contrasts."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
p=argparse.ArgumentParser();p.add_argument("--scores",required=True);p.add_argument("--out",required=True);a=p.parse_args()
out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
df=pd.read_csv(a.scores); req={"case","bias","arm","head_rmse","xy_rmse_cm","range_rmse_cm","head_z_rms","xy_cov95","head_bias"}
assert req<=set(df.columns),req-set(df.columns)
assert len(df)==28*14 and not df.duplicated(["case","bias","arm"]).any()
rows=[]
for (case,bias),grp in df.groupby(["case","bias"]):
 s=grp.set_index("arm")
 def v(arm,key):return float(s.loc[arm,key])
 B,M,V=[z+"_ORIG" for z in ("BB","MB")]+["MB_VAR"]
 row=dict(case=case,bias=bias,route=case.split("_")[0],mount_deg=float(s.loc[V,"mount"]),anchor=str(s.loc[V,"anchor"]))
 for metric in ["head_rmse","xy_rmse_cm","range_rmse_cm","head_z_rms","xy_cov95","head_bias"]:
  for label,arm in [("BB",B),("MB",M),("VAR",V)]:
   row[metric+"_"+label]=v(arm,metric)
  row[metric+"_VAR_minus_BB"]=v(V,metric)-v(B,metric)
  row[metric+"_VAR_minus_MB"]=v(V,metric)-v(M,metric)
 row["head_improve_vs_BB"]=v(V,"head_rmse")<v(B,"head_rmse")
 row["xy_improve_vs_BB"]=v(V,"xy_rmse_cm")<v(B,"xy_rmse_cm")
 row["both_improve"]=bool(row["head_improve_vs_BB"] and row["xy_improve_vs_BB"])
 row["failure_axis"]="BOTH" if not row["head_improve_vs_BB"] and not row["xy_improve_vs_BB"] else ("HEAD_ONLY" if not row["head_improve_vs_BB"] else ("XY_ONLY" if not row["xy_improve_vs_BB"] else "PASS_BOTH"))
 row["heading_ratio_VAR_BB"]=v(V,"head_rmse")/v(B,"head_rmse")
 rows.append(row)
res=pd.DataFrame(rows).sort_values(["case","bias"])
res.to_csv(out/"P4_CONDITION_LEDGER.csv",index=False,float_format="%.16g")
fail=res[~res.both_improve].copy()
fail.to_csv(out/"P4_FAILURES.csv",index=False,float_format="%.16g")
case=res.groupby("case").agg(n=("bias","size"),both_success=("both_improve","sum"),head_success=("head_improve_vs_BB","sum"),xy_success=("xy_improve_vs_BB","sum"),worst_h_ratio=("heading_ratio_VAR_BB","max")).reset_index()
case.to_csv(out/"P4_CASE_CLUSTERS.csv",index=False,float_format="%.16g")
evidence=dict(status="OBSERVED_PAIRWISE_SCORE_AUDIT_NOT_PACKET_CAUSAL_ATTRIBUTION",conditions=len(res),failures=len(fail),head_success=int(res.head_improve_vs_BB.sum()),xy_success=int(res.xy_improve_vs_BB.sum()),both_success=int(res.both_improve.sum()),fail_cases=fail.groupby("case").size().to_dict(),failure_axis_counts=fail.failure_axis.value_counts().to_dict(),input_sha256=hashlib.sha256(Path(a.scores).read_bytes()).hexdigest(),nonindependence="gyro bias 4 levels share RF packets; failures grouped by route/case; no independent trial p-values")
assert (evidence["conditions"],evidence["head_success"],evidence["xy_success"],evidence["both_success"])==(28,23,20,19)
(out/"P4_DECISION.json").write_text(json.dumps(evidence,indent=2),encoding="utf8")
print(json.dumps(evidence,indent=2))
