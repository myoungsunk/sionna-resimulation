from pathlib import Path
import json, hashlib, zipfile
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
SOURCE=Path('/mnt/data/RA4_336_factorial.zip')
CASES=['R2_aB_m0','R5_aB_m0','R4_aB_m0']
BIAS=['B0','L0','L1','L2']
if SOURCE.exists():
    with zipfile.ZipFile(SOURCE) as z:
        raw=z.read('RA4_336_ARMS.csv')
    (ROOT/'evidence/RA4_336_ARMS.csv').write_bytes(raw)
else:
    raw=(ROOT/'evidence/RA4_336_ARMS.csv').read_bytes()
df=pd.read_csv(ROOT/'evidence/RA4_336_ARMS.csv')
df=df[df['case'].isin(CASES)&df['variance'].isin(['NONE','LEGACY'])].copy()
assert len(df)==96
assert not df.duplicated(['case','bias','mean','variance','gate']).any()
# Selected D2_GATE_SCORES.csv values read using GitHub connector at frozen source SHA.
# These are explicit transcriptions, not claimed to be the complete source file.
d2={
'R2_aB_m0':[(1.20471,1.08471,6.82691,5.33032),(1.18425,1.05719,6.75355,5.21939),(1.11227,.96754,6.48212,4.91486),(.946667,.813331,5.77172,4.29523)],
'R5_aB_m0':[(1.07312,.64337,8.68815,4.45512),(1.04622,.634607,8.51929,4.45172),(.942829,.602274,7.83842,4.4488),(.715641,.615281,6.08819,4.64677)],
'R4_aB_m0':[(1.44183,1.43122,8.53629,9.43255),(1.4388,1.42706,8.53816,9.44908),(1.42666,1.40972,8.51784,9.44542),(1.39383,1.35839,8.53193,9.53833)]}
(ROOT/'evidence/D2_SELECTED_SELF_TRANSCRIPTION.json').write_text(json.dumps(d2,indent=2))
rows=[];checks=[]
for case in CASES:
 for i,bias in enumerate(BIAS):
  subset=df[(df['case']==case)&(df['bias']==bias)&(df.gate=='SELF_NIS')].set_index('arm')
  bb=subset.loc['BB_ORIG'];cv=subset.loc['MB_VAR_LEGACY'];vo=subset.loc['BB_VAR_LEGACY'];mo=subset.loc['MB_ORIG']
  vals=[bb.head_rmse_deg,cv.head_rmse_deg,bb.xy_rmse_cm,cv.xy_rmse_cm]
  for actual,ref in zip(vals,d2[case][i]):
   checks.append(float(f'{actual:.6g}')==ref)
  rows.append(dict(case=case,bias=bias,baseline_H_deg=vals[0],combined_H_deg=vals[1],baseline_XY_cm=vals[2],combined_XY_cm=vals[3],
    heading_reduction_pct=100*(1-vals[1]/vals[0]),xy_reduction_pct=100*(1-vals[3]/vals[2]),
    variance_only_H_deg=vo.head_rmse_deg,variance_only_XY_cm=vo.xy_rmse_cm,
    combined_beats_var_H=bool(cv.head_rmse_deg<vo.head_rmse_deg),combined_beats_var_XY=bool(cv.xy_rmse_cm<vo.xy_rmse_cm),
    mean_only_H_deg=mo.head_rmse_deg,mean_only_XY_cm=mo.xy_rmse_cm,
    combined_head_coverage95=cv.head_cov95,combined_xy_coverage95=cv.xy_cov95,
    n_accepted_baseline=int(bb.n_accepted),n_accepted_combined=int(cv.n_accepted)))
out=pd.DataFrame(rows)
assert all(checks),(len(checks),sum(checks))
out.to_csv(ROOT/'tables/SELECTED_12_CONDITIONS_RECHECK.csv',index=False)
# No effect is labelled an independent physical contribution: these are algorithm contrasts.
interactions=[]
for (case,bias,gate),g in df.groupby(['case','bias','gate']):
 g=g.set_index('arm')
 for metric in ['head_rmse_deg','xy_rmse_cm']:
  y00=g.loc['BB_ORIG',metric];y10=g.loc['MB_ORIG',metric];y01=g.loc['BB_VAR_LEGACY',metric];y11=g.loc['MB_VAR_LEGACY',metric]
  interactions.append(dict(case=case,bias=bias,gate=gate,metric=metric,y00=y00,y10=y10,y01=y01,y11=y11,mean_effect=y10-y00,var_effect=y01-y00,mean_given_var=y11-y01,var_given_mean=y11-y10,interaction=y11-y10-y01+y00))
pd.DataFrame(interactions).to_csv(ROOT/'tables/MEAN_VARIANCE_FIXED_SELF_CONTRASTS.csv',index=False)
# Source D3 values are pre-gate vs accepted scopes as stated in the review.
d3=pd.DataFrame([
 ['R2_aB_m0',822,.00671345,.00266213,-.025076,-.00696607,.0106481,.00743544,.020605,.0326244,2.80309,1.26093],
 ['R5_aB_m0',1236,.00706852,.00214373,-.0266911,-.000366134,.00421194,.00624973,.0259139,.0385675,2.14418,.577035],
 ['R4_aB_m0',578,.00635459,.00310812,-.00187592,-.00497312,.0112014,-.0238206,.0124914,.0206022,20.9559,11.5722]],
 columns=['case','accepted_scoring_n','range_Eeps2_BB','range_Eeps2_MB','range_mean_BB_m','range_mean_MB_m','s_Eeps2','s_mean','Rss_BB_mean','Rss_combined_mean','D_s_BB','D_s_combined'])
d3['range_RMS_BB_cm']=100*np.sqrt(d3.range_Eeps2_BB);d3['range_RMS_MB_cm']=100*np.sqrt(d3.range_Eeps2_MB)
d3['A_s_BB']=d3.s_Eeps2/d3.Rss_BB_mean;d3['A_s_combined']=d3.s_Eeps2/d3.Rss_combined_mean
d3.to_csv(ROOT/'tables/D3_SELECTED_B0_RECOMPUTED.csv',index=False)
# General algebra unit test ONLY: not a new RF or EKF experiment.
rng=np.random.default_rng(91);maxerr=0.
for i in range(100):
 a=rng.normal(size=(4,4));P=a@a.T+.2*np.eye(4)
 H=rng.normal(size=(2,4));b=rng.normal(size=(2,2));R=b@b.T+.3*np.eye(2)
 S=H@P@H.T+R;e=np.array([0.,1.]);lam=10**rng.uniform(-4,2)
 K=P@H.T@np.linalg.inv(S);Kp=P@H.T@np.linalg.inv(S+lam*np.outer(e,e))
 expected=(K@e)/(1+lam*(e@np.linalg.solve(S,e)))
 maxerr=max(maxerr,float(np.max(np.abs(Kp@e-expected))))
assert maxerr<1e-12
qa=dict(review_target_commit='1aac4d38',source_snapshot='6c7200091028fd3f0e55aa83b777d0f10b7cf063',
 source_D2_blob='efe55ff9b13b6c6c70f2820e26bacc88ca460d26',source_D3_blob='721ea9f3db5d70d11b546d75ae94d29fe381c4ae',
 ra4_csv_sha256=hashlib.sha256(raw).hexdigest(),selected_conditions=12,D2_transcribed_scalar_checks=len(checks),D2_checks_passed=sum(checks),
 combined_heading_improved=int((out.heading_reduction_pct>0).sum()),combined_xy_improved=int((out.xy_reduction_pct>0).sum()),
 variance_only_heading_improved=int((out.variance_only_H_deg<out.baseline_H_deg).sum()),
 combined_beats_variance_only_both=int((out.combined_beats_var_H&out.combined_beats_var_XY).sum()),
 matched_prior_gain_identity_maxerr=maxerr,new_RT=0,new_filter_replays=0,repo_writes=0,review_kind='SOURCE_REVIEW_AND_SAVED_OUTPUT_RECALCULATION_NOT_INDEPENDENT_SCIENCE_AUDIT')
(ROOT/'RECHECK_QA.json').write_text(json.dumps(qa,indent=2))
print(json.dumps(qa,indent=2))
print(out.groupby('case')[['heading_reduction_pct','xy_reduction_pct']].agg(['min','max']).to_string())
