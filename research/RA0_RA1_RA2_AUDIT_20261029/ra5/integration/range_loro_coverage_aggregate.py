#!/usr/bin/env python3
"""Aggregate route-heldout source-only coverage of deterministic RF model residual.
Two independent source route families per fold are insufficient for universal 95%
coverage; score is diagnostic only, not calibrated measurement R.
"""
import argparse,csv,json,math,pathlib,datetime
def must(v,msg):
    if not v:raise RuntimeError(msg)
def read(p):
    with p.open(newline="") as f:return list(csv.DictReader(f))
def dump(p,rows):
    with p.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main(src,out):
    src=pathlib.Path(src);out=pathlib.Path(out);out.mkdir(exist_ok=True,parents=True)
    files=list(src.rglob("RA5_RANGE_LORO_CASE_SCORES.csv"));must(len(files)==1,"ERR_SCORE_SOURCE")
    qa=json.loads((files[0].parent/"RA5_RANGE_LORO_QA.json").read_text())
    must(qa["status"]=="PASS_SEVEN_CASE_RETROSPECTIVE_LORO_DISTANCE_BIAS_DIAGNOSTIC","ERR_NONPASS")
    data=read(files[0]);must(len(data)==42,"ERR_N_CELLS")
    rows=[]
    for held in ("R2","R4","R5"):
        for modality in ("INT","SUB"):
            for model in ("CONSTANT","RANGE","GEOMETRY"):
                group=[r for r in data if r["held_route"]==held and r["modality"]==modality and r["bias_model"]==model]
                n=sum(int(r["n_valid"]) for r in group)
                must(n>0,"ERR_ZERO")
                mae=sum(int(r["n_valid"])*abs(float(r["mean_error_after_m"])) for r in group)/n
                rmse=math.sqrt(sum(int(r["n_valid"])*float(r["rmse_after_m"])**2 for r in group)/n)
                cov_naive=sum(int(r["n_valid"])*float(r["coverage95_train_in_sample"]) for r in group)/n
                cov_oof=sum(int(r["n_valid"])*float(r["coverage95_inner_two_route_oof"]) for r in group)/n
                floor=sum(int(r["n_valid"])*float(r["sigma_train_inner_two_route_oof_m"]) for r in group)/n
                rows.append(dict(held_route=held,modality=modality,mean_model=model,n=n,
                    rmse_model_error_m=rmse,mean_abs_case_bias_m=mae,
                    nominal_95_coverage_with_in_sample_sigma=cov_naive,
                    nominal_95_coverage_with_inner_route_oof_sigma=cov_oof,
                    inner_route_oof_model_sigma_m=floor,
                    unit="held_route_within_one_corridor",
                    method="TRAIN_ONLY_GAUSSIAN_RESIDUAL_INTERVAL",
                    actual_receiver_noise="NOT_INCLUDED",
                    hard_calibration="NOT_DEMONSTRATED"))
    dump(out/"RA5_RANGE_LORO_COVERAGE_BY_ROUTE.csv",rows)
    summary=dict(status="PASS_ROUTE_COVERAGE_ACCOUNTING_NOT_CALIBRATION_APPROVAL",
      n_held_routes=3,n_route_model_rows=len(rows),
      metric="unnoised deterministic Full H native and sub-tap distance model error",
      route_coverage=rows,source_n_cases=7,original_gt_used_offline=True,
      independent_physical_environments=1,online_validity="NOT_PROVEN",n_RT_calls=0,
      independent_auditor=False,science_release=False,
      utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (out/"RA5_RANGE_COVERAGE_QA.json").write_text(json.dumps({k:v for k,v in summary.items() if k!="route_coverage"},indent=2)+"\n")
    for r in rows:print("RA5_COVERAGE_BY_ROUTE "+json.dumps(r),flush=True)
    print("RA5_COVERAGE_FINAL "+json.dumps({k:v for k,v in summary.items() if k!="route_coverage"}),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--src",required=True);p.add_argument("--out",required=True)
    a=p.parse_args();main(a.src,a.out)
