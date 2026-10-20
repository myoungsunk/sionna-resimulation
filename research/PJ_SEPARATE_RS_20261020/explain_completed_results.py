#!/usr/bin/env python3
"""Post hoc explanation only; no new models, calibration, gates, or EKF runs."""
from pathlib import Path
import os,json,hashlib
import numpy as np,pandas as pd
from scipy.stats import chi2
R=Path(os.environ['PJ_OUT']);out=R/'DIAGNOSTICS';out.mkdir(exist_ok=True)
d=pd.read_csv(R/'ALL_RECURSIVE_AND_FIXED_PRIOR_SCORES.csv');cases=sorted(d.case.unique());rows=[]
for case in cases:
 for bias in ['B0','L2']:
  for model in ['POWER1','POWER_DIAG','SEP_DIAG','SEP_GLOBAL','SEP_BIN','SEP_MU_PWR_COV','PWR_MU_SEP_COV','SEP_BIN_BOX_GATE']:
   s=d[(d.case==case)&(d.bias==bias)&(d.channel=='full')&(d.model==model)]
   n=s[s['mode']=='NATURAL_RECURSIVE'].iloc[0];f=s[s['mode']=='FIXED_POWER_PRIOR_AND_GATE'].iloc[0]
   rows.append({'case':case,'bias':bias,'model':model,'natural_heading_rmse_deg':n.heading_rmse_deg,'natural_heading95':n.heading95,'natural_mean_sigma_deg':n.heading_sigma_deg_mean,'same_prior_same_gate_heading_rmse_deg':f.heading_rmse_deg,'same_prior_same_gate_heading95':f.heading95,'common_prior_gate_disagreement':int(n.gate_disagreement_from_common_power_prior),'natural_accepted_fraction':n.accepted_fraction})
pd.DataFrame(rows).to_csv(out/'COMMON_PRIOR_VS_RECURSIVE.csv',index=False)
counts=[]
for p in R.rglob('*_UPDATE_ORIGINS.csv.gz'):
 t=pd.read_csv(p);t=t[(t.model=='SEP_BIN')&(t.t_s>=30)];a=t.joint_accept.astype(bool).to_numpy();b=((t.marginal_nis_r<=chi2.ppf(.995,1))&(t.marginal_nis_s<=chi2.ppf(.995,1))).to_numpy()
 counts.append({'case':t.case.iloc[0],'bias':t.bias.iloc[0],'n_sampled_packets':len(t),'joint_pass_box_reject':int((a&~b).sum()),'joint_reject_box_pass':int((~a&b).sum()),'gate_mismatch':int((a!=b).sum()),'fixed_prior':'POWER1','sample_stride':2})
pd.DataFrame(counts).to_csv(out/'CORRELATION_GATE_DISAGREEMENT.csv',index=False)
m=pd.read_csv(next(R.rglob('MEASUREMENT_SCORES.csv')));a=m[(m.channel=='full')&(m.model=='SEP_BIN')];b=m[(m.channel=='full')&(m.model=='POWER1')];k=a.merge(b,on='case',suffixes=['_sep','_power'])
mm={'range_rmse_better_cases':int((k.r_rmse_m_sep<k.r_rmse_m_power).sum()),'s_rmse_better_cases':int((k.s_rmse_sep<k.s_rmse_power).sum()),'measurement_joint_nll_better_cases':int((k.conditional_error_nll_sep<k.conditional_error_nll_power).sum()),'total_cases':len(k),'note':'all held-route catalogs including probes; not timed recursive evaluation rows'}
report=['# Additional failure analysis: original finished outputs only','','## Marginal measurement comparison',json.dumps(mm,indent=2),'','## B0 natural vs fixed POWER prior for major ablations']
q=pd.DataFrame(rows);q=q[(q.bias=='B0')&q.model.isin(['POWER1','SEP_BIN','SEP_MU_PWR_COV','PWR_MU_SEP_COV'])];report.append(q.round(6).to_markdown(index=False))
report+=['','## Full L2 results',d[(d.channel=='full')&(d.bias=='L2')&(d['mode']=='NATURAL_RECURSIVE')&d.model.isin(['POWER1','SEP_DIAG','SEP_BIN'])][['case','model','heading_rmse_deg','heading95','heading_sigma_deg_mean']].round(6).to_markdown(index=False),'','## Different acceptance geometry at same prior',pd.DataFrame(counts).to_markdown(index=False)]
(out/'DIAGNOSTIC_REPORT.md').write_text('\n'.join(report)+'\n')
for x in rows:
 if x['bias']=='B0' and x['model'] in ['POWER1','SEP_BIN','SEP_MU_PWR_COV','PWR_MU_SEP_COV']:print('COMMON_VS_RECURSIVE',json.dumps(x),flush=True)
print('MEASUREMENT_AGGREGATE',json.dumps(mm),flush=True)
for x in counts:print('GATE_GEOMETRY',json.dumps(x),flush=True)
for x in d[(d.channel=='full')&(d.bias=='L2')&(d['mode']=='NATURAL_RECURSIVE')&d.model.isin(['POWER1','SEP_DIAG','SEP_BIN'])][['case','model','heading_rmse_deg','heading95','heading_sigma_deg_mean']].to_dict('records'):print('L2_MAIN',json.dumps(x),flush=True)
manifest=[]
for p in sorted(out.rglob('*')):
 if p.is_file():manifest.append({'path':str(p.relative_to(out)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(out/'SHA256_MANIFEST.json').write_text(json.dumps({'files':manifest,'no_model_fitting':True,'no_new_EKF':True},indent=2))
