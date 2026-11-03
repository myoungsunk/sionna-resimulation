import json,hashlib,subprocess
from pathlib import Path
import numpy as np,pandas as pd
root=Path('/mnt/d/codex/MBVAR_PRR_001_20261103');pkg=root/'research/MBVAR_PRR_001_20261103';s=pkg/'S3';r=s/'runs/EVAL_001';dev=s/'runs/DEV_001';cache=Path('/mnt/d/codex/MBVAR_PRR_001_20261103_inputs/S1_INPUTS');code='e68482d262665fff7d0c43749758a523fbf0f4e4'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def blob(c,p):return subprocess.check_output(['git','--git-dir='+str(root/'.git'),'show',c+':'+str(p.relative_to(root))])
for name in ('MATERIALIZED_INPUTS.json','EPSILON_INPUTS.json'):
 p=pkg/'S1'/name;assert p.read_bytes()==blob(code,p)
ml=json.loads((pkg/'S1/MATERIALIZED_INPUTS.json').read_bytes());el=json.loads((pkg/'S1/EPSILON_INPUTS.json').read_bytes())
for path,h in ml.items():assert sha(cache/path)==h,path
for path,h in el.items():assert sha(cache/'evaluator_epsilon_r1'/path)==h,path
go=json.loads(blob('ad34485e9cab7b7201400e89d20fedfe8164e139',s/'audit/GO_S3_LOCKED_EVAL.json'))
assert sha(dev/'RUN_MANIFEST.json')==go['dev_manifest_sha256']=='31de994d04c60f66983a420559d5548a41b7eab9cbc2718e81f1b07121e89853'
final=blob('dfd90f46adda11fbab2665d862cffb005fa93248',pkg/'S2/audit/FINAL_RESULTS.json')
assert hashlib.sha256(final).hexdigest()==go['s2_final_sha256'];assert sha(pkg/'S2/runs/EVAL_001/RUN_MANIFEST.json')==go['s2_manifest_sha256']
dha=json.loads((dev/'ARTIFACT_HASHES.json').read_text())
for name,h in dha.items():assert sha(dev/name)==h,name
print('LOCKS_PASS',len(ml),len(el),len(dha),'devmanifest',go['dev_manifest_sha256'],flush=True)
sm=pd.read_csv(r/'PAIRED_SUMMARY.csv');sc=pd.read_csv(r/'SCORES_PER_SEED.csv');factor=pd.read_csv(r/'FACTORIAL_CONTRASTS.csv');cross=pd.read_csv(r/'CROSS_STAGE_PAIRED.csv');ep=pd.read_csv(r/'EVENT_ENDPOINTS.csv');ev=json.loads((r/'EVENTS.json').read_text())
print('EVENT_DISPOSITIONS',pd.Series([e['disposition'] for e in ev]).value_counts().to_dict())
print('COHORTS',ep.groupby(['route','bias','channel','arm','disposition']).agg(n=('already_accurate','size'),already_accurate=('already_accurate','sum'),censored=('censored','sum')).to_string())
primary=sm[sm.window=='primary'];acc=primary[primary.metric.isin(['heading_rmse_deg','xy_rmse_m'])]
pro=acc[(acc.route=='R5')|(acc.channel=='Native_LoS')].copy()
pro['pass']= (pro.ratio_median<=1.05)&(pro.ratio_p90<=1.2)&(pro.near_zero_margin_violations==0)
print('PROTECTION',pro[['route','bias','channel','arm','metric','ratio_median','ratio_p90','near_zero_n','near_zero_margin_violations','pass']].to_string(index=False))
print('CALIBRATION',primary[primary.metric.isin(['heading_coverage95','nees4','heading_p95_deg','heading_max_deg','xy_p95_m','xy_max_m'])][['route','bias','channel','arm','metric','baseline_median','method_median','paired_delta_median','delta_ci_low','delta_ci_high','baseline_max','method_max','mean_distance_to_target_delta']].to_string(index=False))
print('R4_NEES_MEAN_WORST',sc[(sc.window=='primary')&(sc.channel=='Full')&(sc.route=='R4')].groupby(['bias','arm']).nees4.agg(['mean','max']).to_string())
rows=[]
for keys,tb in sc[(sc.window=='primary')&(sc.channel=='Full')].groupby(['route','bias']):
 tb=tb.set_index(['arm','seed'])
 for arm,base in [('D_CP','B'),('D_CP','C_CP')]:
  for metric in ('heading_rmse_deg','xy_rmse_m','heading_coverage95','nees4'):
   a=tb.loc[base,metric].sort_index().to_numpy();b=tb.loc[arm,metric].sort_index().to_numpy();d=b-a;idx=np.random.default_rng(20261103).integers(len(d),size=(10000,len(d)));lo,hi=np.quantile(np.median(d[idx],axis=1),[.025,.975]);rows.append(dict(route=keys[0],bias=keys[1],contrast=arm+'-'+base,metric=metric,median=float(np.median(d)),CI=[float(lo),float(hi)],decreased_fraction=float(np.mean(d<0))))
print('FACTORIAL_PAIRED_CI',json.dumps(rows))
# All emitted timing fields from the only authorized real 5Hz cohort; no new timing run.
tim=pd.read_csv(dev/'TIMING.csv');di=json.loads((dev/'TRACE_INDEX.json').read_text());clock=[]
for row in tim[tim.real_clock_5Hz].itertuples():
 ix=next(q for q in di if all(q[k]==getattr(row,k) for k in ('route','bias','channel','seed','arm','kind')))
 with np.load(dev/ix['file']) as f:
  assert np.all(f['arrival_to_emitted_ns']==f['latency_ns']+f['queue_wait_ns'])
  assert np.isclose(row.timed_p99_ms,np.quantile(f['arrival_to_emitted_ns'],.99)/1e6)
  assert np.isclose(row.timed_max_ms,f['arrival_to_emitted_ns'].max()/1e6)
  assert row.dropped_packets==0
  clock.append(dict(route=row.route,bias=row.bias,channel=row.channel,arm=row.arm,p99_ms=row.timed_p99_ms,max_ms=row.timed_max_ms,queue_max_ms=float(f['queue_wait_ns'].max()/1e6),kernel_max_ms=float(f['latency_ns'].max()/1e6)))
assert len(clock)==32
print('CLOCK32',json.dumps(clock));print('MEMORY_COLUMNS',tim.filter(regex='memory|rss|peak').describe().to_string())
print('MANIFEST',sha(r/'RUN_MANIFEST.json'))
