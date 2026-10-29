#!/usr/bin/env python3
"""A4 source-locked 3-canary 32x2 factorial paired contrasts across factors."""
import argparse,datetime,json,pathlib
import numpy as np
import pandas as pd

CASE_SET={"R5_aA_m0","R5_aB_m0","R2_aA_m45"}
F=("init_xy_alt","init_heading_alt","gyro_bias_L2","wheel_noise_alt","gyro_noise_alt")
METRICS=("head_deg","xy_cm","head_z_rms","xy_nees","head_cov95","xy_cov95","n_accepted")
def must(v,m):
    if not v:raise RuntimeError(m)
def main(source,out):
    source=pathlib.Path(source);out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
    paths=list(source.rglob("A4_SENSOR_INIT_32X2.csv"))
    qpaths=list(source.rglob("A4_FACTORIAL_QA.json"))
    must(len(paths)==len(qpaths)==3,"ERR_FACTORIAL_CASES_MISSING "+str((len(paths),len(qpaths))))
    rows=pd.concat([pd.read_csv(p) for p in paths],ignore_index=True)
    must(set(rows["case"])==CASE_SET and len(rows)==192 and rows[F+["gate","case"]].drop_duplicates().shape[0]==192,"ERR_DUPLICATE_FACTORIAL")
    for p in qpaths:
        q=json.loads(p.read_text());must(q["status"]=="PASS_A4_FACTORIAL_TECHNICAL","ERR_NONPASS_SOURCE")
    main=[]
    for (case,gate),g in rows.groupby(["case","gate"]):
      for fac in F:
        other=[f for f in F if f!=fac]
        vals=[]
        for key,sub in g.groupby(other):
          must(len(sub)==2 and set(sub[fac])=={0,1},"ERR_UNPAIRED_FACTOR")
          v0=sub[sub[fac]==0].iloc[0];v1=sub[sub[fac]==1].iloc[0]
          vals.append({m:float(v1[m]-v0[m]) for m in METRICS})
        must(len(vals)==16,"ERR_16_PAIRS")
        for metric in METRICS:
          a=np.array([r[metric] for r in vals])
          main.append(dict(case=case,gate=gate,factor=fac,metric=metric,
             paired_blocks=16,average_effect_1_minus_0=float(a.mean()),
             median_effect=float(np.median(a)),min_effect=float(a.min()),max_effect=float(a.max()),
             n_decreased=int((a<0).sum()),n_increased=int((a>0).sum()),
             interpretation="ONE_CORRIDOR_SINGLE_SEED_ALT_NOT_INDEPENDENT_RF",
             wheel_noise_changes_Q=bool(fac=="wheel_noise_alt")))
    contrasts=pd.DataFrame(main)
    contrasts.to_csv(out/"A4_3CASE_FACTOR_CONTRASTS.csv",index=False)
    pp=list(source.rglob("A4_FIRST_FLIP_ONE_PACKET.csv"))
    must(len(pp)==1,"ERR_FIRST_FLIP_EVIDENCE_COUNT "+str(len(pp)))
    first=pd.read_csv(pp[0])
    must(set(first["arm"])=={"SELF_NATURAL","SELF_FORCE_FIRST_REJECT","BASE_FIXED","BASE_FORCE_FIRST_ACCEPT"},"ERR_FIRST_FLIP_ARMS")
    first.to_csv(out/"A4_R5A_FIRST_PACKET_COUNTERFACTUAL.csv",index=False)
    e=first.set_index("arm")
    summary=dict(status="PASS_A4_PAIRED_EFFECT_ACCOUNTING",n_cases=3,n_policies=2,
        n_factorial_cells_per_case=32,n_gate_trajectories_per_case=64,
        n_computed_effect_rows=len(contrasts),
        first_flip_k=int(e.loc["SELF_NATURAL","first_flip_packet"]),
        r5a_self_natural_h=float(e.loc["SELF_NATURAL","head_deg"]),
        r5a_first_rejected_h=float(e.loc["SELF_FORCE_FIRST_REJECT","head_deg"]),
        r5a_self_natural_xy=float(e.loc["SELF_NATURAL","xy_cm"]),
        r5a_first_rejected_xy=float(e.loc["SELF_FORCE_FIRST_REJECT","xy_cm"]),
        r5a_first_reject_heading_gain_deg=float(e.loc["SELF_NATURAL","head_deg"]-e.loc["SELF_FORCE_FIRST_REJECT","head_deg"]),
        r5a_first_reject_xy_gain_cm=float(e.loc["SELF_NATURAL","xy_cm"]-e.loc["SELF_FORCE_FIRST_REJECT","xy_cm"]),
        claim_limit="single forced acceptance decision with subsequent adaptive gates, does not apportion total RMSE",
        original_truth="scoring_only",source_reused=True,independent_scene_count=1,
        self_review_only=True,science_release=False,
        utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (out/"A4_FACTOR_AGG_QA.json").write_text(json.dumps(summary,indent=2)+"\n")
    print("A4_FACTOR_AGG_FINAL "+json.dumps(summary),flush=True)
    for z in contrasts[(contrasts["metric"].isin(["head_deg","xy_cm"]))&(contrasts["gate"]=="SELF_NIS")].to_dict("records"):
        print("A4_FACTOR_EFFECT "+json.dumps({k:z[k] for k in ("case","factor","metric","average_effect_1_minus_0","n_decreased","n_increased")}),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source",required=True);p.add_argument("--out",required=True);x=p.parse_args();main(x.source,x.out)
