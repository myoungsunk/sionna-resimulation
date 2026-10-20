#!/usr/bin/env python3
from pathlib import Path
import os,json,hashlib,zipfile
import pandas as pd,numpy as np
from scipy.stats import spearmanr
root=Path(os.environ['PJ_OUT']);files=sorted(root.rglob('*_SCORES.csv'));assert len(files)==28,('INCOMPLETE_RECURSIVE',len(files))
d=pd.concat([pd.read_csv(f) for f in files],ignore_index=True);assert len(d)==504 and not d.duplicated(['case','channel','bias','model','mode']).any()
q=pd.concat([pd.read_csv(f) for f in root.rglob('*_QA.csv')],ignore_index=True);assert q.max_x.fillna(0).max()<2e-10 and q.max_P.fillna(0).max()<2e-10
for c in root.rglob('*_TRACE.npz'):
    with np.load(c,allow_pickle=False) as z:
        assert np.all(np.linalg.eigvalsh(z['cov'])>0)
        for j,arm in enumerate(z['arms']):
            m=z['t_s']>=30;e=np.arctan2(np.sin(z['state'][m,j,2]-z['truth_scoring_only'][m,2]),np.cos(z['state'][m,j,2]-z['truth_scoring_only'][m,2]))
            rmse=np.degrees(np.sqrt(np.mean(e**2)));cover=np.mean(e*e/z['cov'][m,j,2,2]<=3.841458820694124)
            stem=c.name.removesuffix('_TRACE.npz');case,ch,b=stem.rsplit('_',2);row=d[(d.case==case)&(d.channel==ch)&(d.bias==b)&(d.model==arm)&(d['mode']=='NATURAL_RECURSIVE')];assert len(row)==1
            assert abs(rmse-row.heading_rmse_deg.iloc[0])<1e-9 and abs(cover-row.heading95.iloc[0])<1e-12

d.to_csv(root/'ALL_RECURSIVE_AND_FIXED_PRIOR_SCORES.csv',index=False);q.to_csv(root/'ALL_REAL_STEP_QA.csv',index=False)
nat=d[d['mode']=='NATURAL_RECURSIVE'];base=nat[nat.model=='POWER1'];compare=[]
for name in sorted(set(nat.model)-{'POWER1'}):
    x=nat[nat.model==name].merge(base,on=['case','bias','channel'],suffixes=['_candidate','_power'],validate='one_to_one')
    for channel in ['full','los']:
        g=x[x.channel==channel]
        err=abs(g.heading95_candidate-.95)-abs(g.heading95_power-.95)
        rr=g.heading_rmse_deg_candidate/g.heading_rmse_deg_power
        joint=(rr<1)&(err<0)
        compare.append({'model':name,'channel':channel,'n_case_bias':len(g),'heading_better_count':int((rr<1).sum()),'heading_worse_over10pct':int((rr>1.1).sum()),'heading_rmse_ratio_median':float(rr.median()),'heading_rmse_ratio_worst':float(rr.max()),'coverage_closer95_count':int((err<0).sum()),'rmse_and_coverage_better_count':int(joint.sum()),'mean_sigma_ratio_median':float((g.heading_sigma_deg_mean_candidate/g.heading_sigma_deg_mean_power).median())})
pd.DataFrame(compare).to_csv(root/'PAIRED_CANDIDATE_VS_POWER.csv',index=False)
measurement=next(root.rglob('MEASUREMENT_SCORES.csv'));md=pd.read_csv(measurement)
lines=['# Separate Range/s physical error models vs POWER1 — actual run','', 'Same frozen corridor, seven original cases, B0/L2, Full/Native-LoS. Developmental route-heldout, not unseen-environment validation.','', '## Models / full natural recursive B0']
cols=['case','model','heading_rmse_deg','heading_signed_bias_deg','heading95','heading_sigma_deg_mean','xy_rmse_m','bias_rmse_dps','accepted_fraction']
x=nat[(nat.channel=='full')&(nat.bias=='B0')][cols]
lines.append(x.round(5).to_markdown(index=False))
lines+=['','## Full natural recursive L2',nat[(nat.channel=='full')&(nat.bias=='L2')][cols].round(5).to_markdown(index=False),'','## Paired results vs POWER1 (14 Full case-bias observations, not independent scenes)',pd.DataFrame(compare).round(5).to_markdown(index=False)]
lines+=['','## Full measurement summaries by case (not recursive; all catalog poses)',md[(md.channel=='full')&md.model.isin(['POWER1','SEP_DIAG','SEP_GLOBAL','SEP_BIN'])][['case','model','r_rmse_m','s_rmse','range95','s95','joint95','conditional_error_nll','pred_rho_mean','empirical_corr','whitened_corr']].round(5).to_markdown(index=False)]
# Pure mean / covariance / correlation and gating comparisons in both common and natural priors
lines+=['','## Common POWER prior + same gate, B0 Full (no posterior trajectory repropagation for these single-step comparisons)',d[(d['mode']=='FIXED_POWER_PRIOR_AND_GATE')&(d.channel=='full')&(d.bias=='B0')][cols[:-1]].round(5).to_markdown(index=False)]
receipt={'technical_status':'PASS','scientific_improvement_approval':'NOT_AUTOMATIC','n_conditions':28,'n_natural_arm_trajectories':252,'n_fixed_prior_arm_scores':252,'n_source_core_step_checks':int(q.step.notna().sum()) if 'step' in q else 0,'max_core_state_diff':float(q.max_x.fillna(0).max()),'max_core_cov_diff':float(q.max_P.fillna(0).max()),'n_trace_rescored':28,'historical_power_B0_max_rounded_RMSE_difference_deg':float(q.historical_rounding_comparison_abs_deg.max()),'total_physical_scenes':1,'fresh_Sionna_runs':0,'regenerated_R4R5_M45_included':False,'R2_A_M45_included':True,'hyperparameter_selection_on_test':False,'features_selected_from_previous_data_analysis':True,'new_seed_generalization_test':False,'independent_analyst_review':False,'new_model_likelihood_normalization_proved':False,'method':'original SourceFFD and Range d+B_OLD, marginal Ridge30/bin variances, train-only joint residual correlation'}
(root/'FINAL_QA.json').write_text(json.dumps(receipt,indent=2)+'\n');lines+=['','## QA and limitations',json.dumps(receipt,ensure_ascii=False,indent=2)]
(root/'RESULTS.md').write_text('\n'.join(lines)+'\n')
for rec in compare:print('PAIR_SUMMARY',json.dumps(rec),flush=True)
for row in x.to_dict('records'):print('B0_FULL_RESULT',json.dumps(row),flush=True)
for row in md[(md.channel=='full')&(md.model.isin(['POWER1','SEP_DIAG','SEP_GLOBAL','SEP_BIN']))].to_dict('records'):print('MEASUREMENT_FULL',json.dumps(row),flush=True)
print('FINAL_VALIDATION_RECEIPT',json.dumps(receipt),flush=True)
manifest=[]
for p in sorted(root.rglob('*')):
    if p.is_file() and p.name!='SHA256_MANIFEST.json':
        with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
        manifest.append({'path':str(p.relative_to(root)),'bytes':p.stat().st_size,'sha256':h})
(root/'SHA256_MANIFEST.json').write_text(json.dumps({'files':manifest,'status':'EXECUTED_NOT_GLOBAL_MODEL_APPROVAL'},indent=2))
print('ALL_DONE',len(d),len(manifest),flush=True)
