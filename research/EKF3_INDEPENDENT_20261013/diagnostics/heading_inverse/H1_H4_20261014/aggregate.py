from pathlib import Path
import sys, json, hashlib, warnings
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'OPT/FULL'
OUT=ROOT/'ANALYSIS'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def rms(x):
 a=np.asarray(x,dtype=float);a=a[np.isfinite(a)]
 return float(np.sqrt(np.mean(a*a))) if len(a) else np.nan
def quant(x,q):
 a=np.asarray(x,dtype=float);a=a[np.isfinite(a)]
 return float(np.quantile(a,q)) if len(a) else np.nan
def summary_groups(df,keys,fn):
 rows=[]
 for key,g in df.groupby(keys,sort=True,dropna=False):
  key=key if isinstance(key,tuple) else (key,)
  rows.append(dict(zip(keys,key))|fn(g))
 return pd.DataFrame(rows)
def h12(g):
 gaps=[a for v in g.root_gaps_deg for a in json.loads(v)]
 return dict(n=len(g),no_root_pct=100*g.no_exact_solution.mean(),multiple_pct=100*((g.root_count>1)&~g.flat_solution).mean(),flat_pct=100*g.flat_solution.mean(),
  unique_n=int(g.unique_error_deg.notna().sum()),unique_RMSE_deg=rms(g.unique_error_deg),oracle_n=int(g.oracle_error_deg.notna().sum()),oracle_lower_bound_RMSE_deg=rms(g.oracle_error_deg),oracle_error_median_deg=quant(g.oracle_error_deg,.5),oracle_error_p95_deg=quant(g.oracle_error_deg,.95),oracle_error_over90_n=int((g.oracle_error_deg>90).sum()),
  roots_median=g.root_count.median(),roots_max=g.root_count.max(),root_gap_p05_deg=quant(gaps,.05),root_gap_median_deg=quant(gaps,.5),
  nominal_band_width_median_deg=g.band_width_deg.median(),nominal_band_width_p95_deg=g.band_width_deg.quantile(.95),nominal_band_truth_pct=100*g.band_truth.mean(),
  s_residual_RMS=rms(g.s_residual),hpsi_abs_p05=quant(abs(g.hpsi),.05),hpsi_abs_median=quant(abs(g.hpsi),.5),known_xy_sigma_median_deg=quant(g.sigma_heading_known_xy_deg,.5),known_xy_sigma_p95_deg=quant(g.sigma_heading_known_xy_deg,.95),theta_clip_n=int(g.theta_clipped.sum()))
def h3(g):
 ok=g[['H1_prior_error_deg','H2_prior_error_deg','selected_error_deg']].notna().all(axis=1)
 p=g[ok];valid=g.selected_error_deg.notna();v=g[valid]
 return dict(n=len(g),selected_n=int(valid.sum()),paired_n=len(p),no_root_pct=100*g.no_exact_solution.mean(),multiple_pct=100*(g.root_count>1).mean(),
  DR_RMSE_deg=rms(g.dr_heading_error_deg),H3_conditional_RMSE_deg=rms(g.selected_error_deg),H3_abs_p95_deg=quant(abs(g.selected_error_deg),.95),
  paired_DR_RMSE_deg=rms(p.dr_heading_error_deg),paired_H1_RMSE_deg=rms(p.H1_prior_error_deg),paired_H2_RMSE_deg=rms(p.H2_prior_error_deg),paired_H3_RMSE_deg=rms(p.selected_error_deg),
  paired_H1_abs_median_deg=quant(abs(p.H1_prior_error_deg),.5),paired_H2_abs_median_deg=quant(abs(p.H2_prior_error_deg),.5),paired_H3_abs_median_deg=quant(abs(p.selected_error_deg),.5),
  paired_H1_abs_p95_deg=quant(abs(p.H1_prior_error_deg),.95),paired_H2_abs_p95_deg=quant(abs(p.H2_prior_error_deg),.95),paired_H3_abs_p95_deg=quant(abs(p.selected_error_deg),.95),
  paired_MP_MSE_delta_deg2=float((p.H2_prior_error_deg**2-p.H1_prior_error_deg**2).mean()),paired_position_MSE_delta_deg2=float((p.selected_error_deg**2-p.H2_prior_error_deg**2).mean()),
  selected_not_nearest_truth_root_pct=100*v.selected_not_oracle.mean(),position_RMSE_m=rms(g.position_error_m),nominal_band_truth_pct=100*g.band_truth.mean(),
  paired_H2_nominal_band_truth_pct=100*p.H2_band_truth.mean(),paired_H3_nominal_band_truth_pct=100*p.band_truth.mean(),
  rf_linear_term_abs_median_deg=quant(abs(g.rf_term_deg),.5),rf_linear_term_abs_p95_deg=quant(abs(g.rf_term_deg),.95),
  position_linear_term_abs_median_deg=quant(abs(g.position_term_deg),.5),position_linear_term_abs_p95_deg=quant(abs(g.position_term_deg),.95),
  rf_linear_term_RMS_deg=rms(g.rf_term_deg),position_linear_term_RMS_deg=rms(g.position_term_deg),linear_cross_mean_deg2=g.cross_deg2.mean(),
  linear_remainder_abs_median_deg=quant(abs(g.linear_remainder_deg),.5),linear_remainder_abs_p95_deg=quant(abs(g.linear_remainder_deg),.95),
  invalid_linear_n=int((~np.isfinite(g.linear_error_deg)).sum()),theta_clip_n=int(g.theta_clipped.sum()))
def h4(g):
 a=g[g.applied];multi=g[g.root_count>1];shrunk=g[g.heading_cov_ratio<1-1e-12]
 return dict(n=len(g),applied_n=len(a),applied_pct=100*g.applied.mean(),heading_RMSE_deg=rms(g.heading_error_deg),heading_NEES_mean=g.heading_NEES.mean(),heading95_pct=100*g.heading95.mean(),
  prior_std_median_deg=g.prior_heading_std_deg.median(),post_std_median_deg=g.post_heading_std_deg.median(),cov_ratio_median=g.heading_cov_ratio.median(),
  applied_cov_ratio_median=a.heading_cov_ratio.median(),applied_weight_median=a.weight.median(),applied_weight_p05=a.weight.quantile(.05),applied_R_multiplier_p95=a.R_multiplier.quantile(.95),
  NIS_median=g.NIS.median(),NIS_p95=g.NIS.quantile(.95),no_root_pct=100*g.no_exact_solution.mean(),multiple_pct=100*(g.root_count>1).mean(),
  nominal_band_truth_pct=100*g.band_truth.mean(),band_width_median_deg=g.band_width_deg.median(),
  applied_heading_MSE_delta_deg2=a.heading_squared_error_change.mean()*(180/np.pi)**2,applied_harm_pct=100*(a.heading_squared_error_change>0).mean(),
  shrunk_n=len(shrunk),shrunk_heading95_pct=100*shrunk.heading95.mean(),multi_root_heading95_pct=100*multi.heading95.mean())

def branch_diagnostic(b):
 # Post-hoc descriptive partition using the already frozen nominal band;
 # no new error threshold, estimator, root selector, or acceptance gate.
 cache=Path('D:/SLAM_bot/artifacts/EKF3_ROBUST_FUSION_20261013/M0')
 truths={c:np.load(cache/(c+'_full.npz'))['truth'][:,2]*180/np.pi for c in b.case.unique()}
 labels=[];near_has=[]
 for row in b.itertuples(index=False):
  intervals=json.loads(row.band_intervals_deg);roots=json.loads(row.roots_deg)
  def component(angle):
   if not np.isfinite(angle):return -1
   for i,(a,z) in enumerate(intervals):
    if (angle-a)%360+a<=z+1e-8:
     return 0 if i==len(intervals)-1 and len(intervals)>1 and abs(intervals[-1][1]-intervals[0][0]-360)<1e-8 else i
   return -1
  tc=component(truths[row.case][row.sample_index]);sc=component(row.selected_heading_deg)
  near_has.append(tc>=0 and any(component(r)==tc for r in roots))
  labels.append('TRUTH_OUTSIDE_NOMINAL_BAND' if tc<0 else 'NO_SELECTED_POINT' if not np.isfinite(row.selected_heading_deg) else 'SAME_BAND_COMPONENT' if sc==tc else 'OTHER_BAND_COMPONENT')
 d=b.copy();d['band_branch_class']=labels;d['truth_component_has_exact_root']=near_has
 return summary_groups(d,['stage','band_branch_class'],lambda g:dict(n=len(g),selected_n=int(g.selected_error_deg.notna().sum()),selected_RMSE_deg=rms(g.selected_error_deg),selected_abs_median_deg=quant(abs(g.selected_error_deg),.5),linear_remainder_abs_median_deg=quant(abs(g.linear_remainder_deg),.5),linear_remainder_abs_p95_deg=quant(abs(g.linear_remainder_deg),.95),truth_component_with_exact_root_pct=100*g.truth_component_has_exact_root.mean()))

def main():
 OUT.mkdir(exist_ok=False)
 receipt=json.loads((DATA/'RECEIPT.json').read_text());assert receipt['status']=='PASS'
 for n,h in receipt['output_sha256'].items():assert sha(DATA/n)==h,n
 for p,h in receipt['source_sha256'].items():assert sha(Path(p))==h,p
 a=pd.read_csv(DATA/'H12_RF.csv.gz');b=pd.read_csv(DATA/'H3_DR.csv.gz')
 columns=['stage','case','channel','range_model','seed','arm','model','sample_index','t_s','root_count','no_exact_solution','band_truth','band_width_deg','applied','heading_error_deg','prior_heading_error_deg','heading_NEES','heading95','prior_heading_std_deg','post_heading_std_deg','heading_cov_ratio','weight','R_multiplier','NIS','heading_squared_error_change']
 c=pd.read_csv(DATA/'H4_EKF.csv.gz',usecols=columns)
 assert len(a)==receipt['H12_rows'] and len(b)==receipt['H3_rows'] and len(c)==receipt['H4_rows']
 assert not a.duplicated(['case','sample_index','channel']).any()
 assert not b.duplicated(['stage','case','seed','sample_index']).any()
 assert not c.duplicated(['stage','case','seed','channel','range_model','arm','model','sample_index']).any()
 assert np.allclose(c.heading_error_deg**2-c.prior_heading_error_deg**2,c.heading_squared_error_change*(180/np.pi)**2,rtol=1e-10,atol=1e-10)
 files={
 'H12_POOLED.csv':summary_groups(a,['channel'],h12),'H12_CASES.csv':summary_groups(a,['case','channel'],h12),
 'H3_POOLED.csv':summary_groups(b,['stage'],h3),'H3_CASE_SEED.csv':summary_groups(b,['stage','case','seed'],h3),
 'H4_POOLED.csv':summary_groups(c,['stage','channel','range_model','arm','model'],h4),
 'H4_CASE_SEED.csv':summary_groups(c,['stage','case','seed','channel','range_model','arm','model'],h4)}
 files['H3_BAND_COMPONENT_DIAGNOSTIC.csv']=branch_diagnostic(b)
 pair=a[a.channel=='los'].merge(a[a.channel=='full'],on=['case','sample_index'],suffixes=('_los','_full'),validate='one_to_one')
 def paired_rf(g):
  good=g[['oracle_error_deg_los','oracle_error_deg_full']].notna().all(axis=1);v=g[good]
  return dict(n=len(g),paired_exact_root_n=len(v),oracle_only_LoS_RMSE_deg=rms(v.oracle_error_deg_los),oracle_only_Full_RMSE_deg=rms(v.oracle_error_deg_full),
   oracle_only_mean_MSE_delta_deg2=float((v.oracle_error_deg_full**2-v.oracle_error_deg_los**2).mean()),
   LoS_nominal_band_truth_pct=100*g.band_truth_los.mean(),Full_nominal_band_truth_pct=100*g.band_truth_full.mean())
 files['H12_PAIRED_CASES.csv']=summary_groups(pair,['case'],paired_rf)
 # Paired descriptive effects per trajectory/seed, not independent time samples.
 u=files['H3_CASE_SEED.csv'];units=[]
 for st,g in u.groupby('stage'):
  units.append(dict(stage=st,case_seed_units=len(g),MP_MSE_worse_units=int((g.paired_MP_MSE_delta_deg2>0).sum()),position_MSE_worse_units=int((g.paired_position_MSE_delta_deg2>0).sum()),
   median_unit_MP_MSE_delta_deg2=g.paired_MP_MSE_delta_deg2.median(),median_unit_position_MSE_delta_deg2=g.paired_position_MSE_delta_deg2.median()))
 files['H3_UNIT_EFFECTS.csv']=pd.DataFrame(units)
 # Model contrasts retain identical timestamps and cell identities.
 keys=['stage','case','seed','channel','range_model','arm','sample_index']
 base=c[c.model=='M0'][keys+['heading_error_deg','heading95']]
 paired=[]
 for name in ['RF_HUBER_ONLY','RF_CAUCHY']:
  q=c[c.model==name].merge(base,on=keys,suffixes=('','_M0'),validate='one_to_one')
  assert len(q)==len(base)
  q['MSE_delta']=q.heading_error_deg**2-q.heading_error_deg_M0**2
  paired.append(summary_groups(q,['stage','case','seed','channel','range_model','arm'],lambda g:dict(model=name,n=len(g),heading_MSE_delta_deg2=g.MSE_delta.mean(),coverage_delta_pp=100*(g.heading95.astype(float)-g.heading95_M0.astype(float)).mean())))
 files['H4_PAIRED_UNITS.csv']=pd.concat(paired,ignore_index=True)
 for n,d in files.items():d.to_csv(OUT/n,index=False)
 p=pd.read_csv(DATA/'H4_PARITY.csv');assert (p[['state_max','prior_cov_max','NIS_max','posterior_cov_max']]<=1e-8).all().all()
 # Algebraic decomposition identity; this is a calculation check, not a linearization-validity claim.
 z=b[['rf_term_deg','position_term_deg','cross_deg2','linear_error_deg']].dropna()
 assert np.allclose(z.linear_error_deg**2,z.rf_term_deg**2+z.position_term_deg**2+z.cross_deg2,rtol=1e-11,atol=1e-8)
 record=dict(status='PASS',input_receipt_sha256=sha(DATA/'RECEIPT.json'),script_sha256=sha(Path(__file__)),counts=dict(H12=len(a),H3=len(b),H4=len(c)),parity_groups=len(p),parity_max=p[['state_max','prior_cov_max','NIS_max','posterior_cov_max']].max().to_dict(),outputs={n:sha(OUT/n) for n in files},scientific_PASS=False)
 (OUT/'AGGREGATION_RECEIPT.json').write_text(json.dumps(record,indent=2,allow_nan=False))
 print(json.dumps(record,indent=2))
 print(files['H12_POOLED.csv'].to_string(index=False))
 print(files['H3_POOLED.csv'][['stage','n','paired_n','paired_DR_RMSE_deg','paired_H1_RMSE_deg','paired_H2_RMSE_deg','paired_H3_RMSE_deg']].to_string(index=False))
if __name__=='__main__':main()
