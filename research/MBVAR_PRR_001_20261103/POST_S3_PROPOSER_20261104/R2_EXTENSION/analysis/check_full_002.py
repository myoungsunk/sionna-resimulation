from pathlib import Path
import json,hashlib,numpy as np,pandas as pd
base=Path(__file__).resolve().parents[3]; root=Path(__file__).resolve().parents[1]; run=root/'FULL_002'; digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
m=json.loads((run/'MANIFEST.json').read_text()); assert m['status']=='COMPLETE'
h=json.loads((run/'ARTIFACT_HASHES.json').read_text()); assert all(digest(run/p)==s for p,s in h.items())
assert all(digest(base/p)==s for p,s in m['code_sha256'].items())
par=json.loads((run/'PARITY.json').read_text()); assert len(par)==320 and all(v['parity']['passed'] and v['parity']['mask_exact'] and v['parity']['source_ids_exact'] and v['parity']['pretreatment_prior_matches_natural'] for v in par)
nidx=json.loads((run/'NATURAL_INDEX.json').read_text()); pix=json.loads((run/'PAIR_INDEX.json').read_text()); ev=pd.read_csv(run/'EVENT_RESULTS.csv'); ns=pd.read_csv(run/'NATURAL_SUMMARY.csv'); co=pd.read_csv(run/'POLICY_COUNTS.csv')
assert (len(nidx),len(pix),len(ev),len(ns),len(co))==(240,320,320,640,160)
assert not ev.event.duplicated().any() and not ns.duplicated(['stage','bias','seed','arm','window']).any() and not co.duplicated(['stage','bias','seed','arm']).any()
assert co.attempts.sum()==320 and sum(v['parity']['max_state_abs'] for v in par)==0 and sum(v['parity']['max_covariance_abs'] for v in par)==0
assert set(co.seed)==set(range(10,30)) and set(co.bias)=={'B0','L2'}
max_n=0.;max_e=0.
truths={b:dict(np.load(root/'inputs'/('R2_aB_m0_'+b+'_TRUTH.npz'))) for b in ['B0','L2']}
for ix in nidx:
 a=dict(np.load(run/ix['file'])); labels=truths[ix['bias']]; assert np.array_equal(a['pose_id'],labels['pose_id'])
 e=a['x'][:,:3]-labels['truth']; e[:,2]=np.angle(np.exp(1j*e[:,2])); head=np.degrees(e[:,2]);xy=np.linalg.norm(e[:,:2],axis=1)
 rows=ns[(ns.bias==ix['bias'])&(ns.seed==ix['seed'])&(ns.arm==ix['arm'])]
 if ix['stage']!='S2_S3_SHARED':rows=rows[rows.stage==ix['stage']]
 for _,r in rows.iterrows():
  s=np.ones(len(head),bool) if r.window=='all' else a['t']>=30
  expected=[np.sqrt(np.mean(head[s]**2)),np.sqrt(np.mean(xy[s]**2)),np.mean(e[s,2]**2/a['P'][s,2,2]<=3.841458820694124)]
  max_n=max(max_n,float(np.max(np.abs(np.array(expected)-r[['heading_rmse_deg','xy_rmse_m','heading_coverage95']].to_numpy(dtype=float)))))
lookup=ev.set_index('event')
for ix in pix:
 r=lookup.loc[ix['event']]; a=dict(np.load(run/ix['file'])); tr=truths[r.bias]['truth'][a['sample_index']]; t=a['t']; sel=t<=t[0]+20+1e-9
 for branch in ['on','off']:
  error=a[branch+'_x'][:,:3]-tr; head=abs(np.degrees(np.angle(np.exp(1j*error[:,2]))));xy=np.linalg.norm(error[:,:2],axis=1)
  for metric,vals in [('head',head),('xy',xy)]:
   expected=np.trapezoid(vals[sel],t[sel]); observed=r[branch+'_'+metric+'_int_20']; max_e=max(max_e,abs(float(expected-observed)))
 assert np.array_equal(a['pose_id'],truths[r.bias]['pose_id'][a['sample_index']])
assert max_n<1e-12 and max_e<1e-10
out=dict(status='SELF_CHECK_PASS',manifest_status=m['status'],hashes_verified=len(h),code_hashes_verified=len(m['code_sha256']),natural_traces=len(nidx),pairs=len(pix),policy_cells=len(co),natural_summary_rows=len(ns),exact_on_natural_state_and_covariance=True,all_registered_mask_sourceid_prior_parity=True,natural_summary_max_abs=max_n,raw20s_integral_max_abs=max_e,effect_counts=ev.effect.value_counts().to_dict(),applied=int(ev.applied.sum()),disposition=ev.disposition.value_counts().to_dict(),note='Self-check, not independent audit; seed repeats share original R2 RF data, calibration overlap retained.')
(root/'analysis'/'FULL_002_CHECKS.json').write_text(json.dumps(out,indent=2),encoding='utf8');print(json.dumps(out))
