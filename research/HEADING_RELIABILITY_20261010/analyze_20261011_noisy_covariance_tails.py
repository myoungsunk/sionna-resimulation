#!/usr/bin/env python3
"""Independent 12case noisy-receiver endpoint covariance/methodology root-cause audit.

Operates on ORIGINAL, immutable FINAL_CONTROL_SUMMARY_CURRENT and full csv.
Does not optimize R or run a changed filter; separates endpoint RMSE, NEES tails,
prior-kind effects, and the impact of range-only/LoS-only/full-RF updates.
"""
from pathlib import Path
import argparse, math, json
import numpy as np, pandas as pd

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/"results/DRIVE_SIM_NOISY_PROBE_20261010/RUN_01a125b3/SUMMARY_FINAL"
Q95=7.814727903251179
def main():
 p=argparse.ArgumentParser();p.add_argument("--out",required=True,type=Path);o=p.parse_args().out
 o.mkdir(parents=True,exist_ok=True)
 orig=pd.read_csv(SOURCE/"FINAL_SEED_PRIOR_KIND_METRICS.csv")
 full=pd.read_csv(SOURCE/"FINAL_ALL_RESULTS.csv",low_memory=False)
 print("FULL_RESULT_COLUMNS",full.columns.to_list(),flush=True)
 assert len(full)==53280
 assert not orig.duplicated(["case","drift","snr","arm","seed","prior_kind"]).any()
 assert set(orig.arm)=={"A","B","C","D","G1","G2"}
 nseed=orig.seed.nunique()
 assert nseed==5
 rows=[]
 for (prior,snr,arm),g in orig.groupby(["prior_kind","snr","arm"]):
  v=g.nees_pose_df3.to_numpy(float)
  rows.append(dict(prior_kind=prior,snr_db=snr,arm=arm,n_seed_units=len(g),n_stations=int(g.stations.sum()),
                   nees_mean=float(v.mean()),nees_median=float(np.median(v)),
                   nees_p90=float(np.quantile(v,.90)),
                   nees_p99=float(np.quantile(v,.99)),
                   nees_gt7_815=float(np.mean(v>Q95)),
                   nees_max=float(v.max()),
                   heading_rmse_deg_mean=float(g.heading_endpoint_rmse_deg.mean()),
                   pos_rmse_mean_m=float(g.position_endpoint_rmse_m.mean()),
                   pose_coverage_mean=float(g.pose_coverage95.mean()),
                   heading_coverage_mean=float(g.heading_coverage95.mean()),
                   mean_s_nis_pregate=float(g.s_nis_pre_gate.mean()) if g.s_nis_pre_gate.notna().any() else None,
                   mean_s_nis_accepted=float(g.s_nis_accepted.mean()) if g.s_nis_accepted.notna().any() else None,
                   mean_s_reject_rate=float(g.s_reject_rate.mean()) if g.s_reject_rate.notna().any() else None,
                   mean_range_nis_pregate=float(g.range_nis_pre_gate.mean()) if g.range_nis_pre_gate.notna().any() else None))
 tab=pd.DataFrame(rows)
 tab.to_csv(o/"BY_PRIOR_SNR_ARM_COVARIANCE_TAILS.csv",index=False)
 compare=[]
 for (prior,snr),g in orig.groupby(["prior_kind","snr"]):
  pa=g.pivot(index=["case","drift","seed"],columns="arm",values=["nees_pose_df3","heading_endpoint_rmse_deg","position_endpoint_rmse_m","pose_coverage95"])
  if any((x not in pa.columns.get_level_values(1)) for x in "ABCD"):continue
  for metric in ("nees_pose_df3","heading_endpoint_rmse_deg","position_endpoint_rmse_m","pose_coverage95"):
   for x,y in [("B","A"),("C","B"),("D","B"),("D","C")]:
    d=pa[(metric,x)]-pa[(metric,y)]
    d=d.dropna()
    compare.append(dict(prior_kind=prior,snr_db=snr,metric=metric,contrast=f"{x} minus {y}",
                        n=len(d),mean_delta=float(d.mean()),median_delta=float(d.median()),
                        p10=float(d.quantile(.1)),p90=float(d.quantile(.9)),
                        fraction_delta_negative=float((d<0).mean())))
 pd.DataFrame(compare).to_csv(o/"PAIRED_PRIOR_SNR_SENSOR_CONTRASTS.csv",index=False)
 fields=full.columns.to_list()
 meta=dict(status="COMPLETED_INDEPENDENT_SUMMARY_RECOMPUTATION",
           n_raw_rows=int(len(full)),n_case=full.case.nunique(),n_prior_kinds=full.prior_kind.nunique(),
           seed_ids=list(map(int,sorted(orig.seed.unique()))),
           fundamental_unit="case×drift×seed×snr×prior_kind station-endpoint summary",
           source_stage="fixed true XY with scripted yaw, range+s repeated, not full drive EKF",
           columns=fields,
           warnings=["mean NEES is strongly impacted by rare enormous outliers: show median/p90/p99",
                     "PSD proof does not guarantee expected true error covariance",
                     "C uses LoS s only; range is full RF, and even C can be inconsistent",
                     "G1/G2 also suppress range packet count",
                     "5 gyro/wheel seeds; same corridor geometry",
                     "new native full five channels not demonstrated equivalent to legacy Method-B seven",
                     "site/point mixture and full-route dynamic control not executed in this dataset"],
           scientific_PASS=False)
 (o/"PROVENANCE_AND_CHECKS.json").write_text(json.dumps(meta,indent=2,allow_nan=False))
 with (o/"RESULTS_KO.md").open("w",encoding="utf-8") as f:
  f.write("# 신규 12케이스 fixed-truth noisy rotation — 공분산 과신 진단\n\n")
  f.write("본 분석은 업로드된 저장 CSV에서 NEES 극단값·prior 종류·range/s 순차 갱신의 기여를 독립 재집계합니다. 새 시뮬레이션이나 모델 튜닝이 아닙니다.\n\n")
  f.write("## SNR 30 주요 prior-kind별\n\n")
  wanted=tab[(tab.snr_db==30)]
  f.write(wanted[["prior_kind","arm","n_seed_units","nees_mean","nees_median","nees_p90","nees_max","pose_coverage_mean","heading_rmse_deg_mean"]].round(4).to_markdown(index=False))
  f.write("\n\n## 동일 사전 상태/seed 대조\n\n")
  comp=pd.DataFrame(compare)
  f.write(comp[(comp.snr_db==30)&comp.metric.isin(["nees_pose_df3","heading_endpoint_rmse_deg"])].round(4).to_markdown(index=False))
  f.write("\n\n동일한 복도/원 RF 반복이므로 통계적 독립 환경 검증이 아니며, 현재 필터의 네트워크 전체 NEES와 직접 비교하지 않습니다. F01/F02 OPEN.\n")
 print("COV_TAIL_SUMMARY",json.dumps(dict(raw=len(full),columns=fields[:30],
   table=tab[(tab.snr_db==30)&(tab.prior_kind=="LEGACY_SAVED_POST_ODOM")][["arm","nees_mean","nees_median","nees_p90","nees_max","pose_coverage_mean"]].to_dict("records"))),flush=True)
if __name__=="__main__":main()
