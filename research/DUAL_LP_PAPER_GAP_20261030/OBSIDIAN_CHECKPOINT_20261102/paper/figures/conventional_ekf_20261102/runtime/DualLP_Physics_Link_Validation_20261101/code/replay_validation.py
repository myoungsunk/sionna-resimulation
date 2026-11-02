"""V0/V2/V3 reconstruction using unchanged diag_mbvar.run.
OPENBLAS_NUM_THREADS=1 python code/replay_validation.py --workers 3
"""
from __future__ import annotations
import argparse,concurrent.futures as cf,multiprocessing as mp,time,sys,platform
from bootstrap import *
MODEL=None
def baseline(cb):
 case,bias=cb;D=load_data(case,bias,MODEL)
 tr,row=full_run(D,'BB','orig','self',MODEL);D['acc']=tr['used'].copy();save_data(D)
 print('BASE',case,bias,row['head_rmse'],row['xy_rmse_cm'],flush=True);return row
def other_runs(cb):
 case,bias=cb;D=read_data(case,bias)
 lock=json.loads((RESULTS/'CONSTANT_VARIANCE_TRAIN_LOCK.json').read_text());sg=math.sqrt(lock['held_route_constants'][case]['variance'])
 tab=(DG.HAND[0].copy(),np.full_like(DG.HAND[1],sg));rows=[]
 for arm,bg,mode in [('BB_VAR','BB','var'),('MB_ORIG','MB','orig'),('MB_VAR','MB','var'),('BB_CONST','BB','var'),('MB_CONST','MB','var')]:
  for gate in ['fixed','self']:
   tr,row=full_run(D,bg,mode,gate,MODEL,tab if arm.endswith('CONST') else None);rows.append(row)
   print('RUN',case,bias,arm,gate,round(row['head_rmse'],6),round(row['xy_rmse_cm'],6),flush=True)
 return rows
def legacy_parity(scores):
 old=pd.read_csv(LEGACY/'mbvar_premodel_diag_20261029/results/D2_GATE_SCORES.csv');old=old[old.case.isin(CASES)]
 primary=['head_rmse','head_bias','xy_rmse_cm','range_rmse_cm','head_z_rms','head_cov95','nees_xy','xy_cov95','n_used'];rows=[]
 for _,r in scores[~scores.arm.str.endswith('CONST')].iterrows():
  a=old[(old.case==r.case)&(old.bias==r.bias)&(old.arm==r.arm)&(old.gate==r.gate)];assert len(a)==1
  for col in primary:
   val=float(r[col]);ref=float(a.iloc[0][col]);rounded=float(format(val,'.6g'))
   rows.append(dict(case=r.case,bias=r.bias,arm=r.arm,gate=r.gate,metric=col,new_value=val,historical_csv_value=ref,new_at_6sig=rounded,abs_difference=abs(val-ref),pass_6sig=rounded==ref))
 f=pd.DataFrame(rows);f.to_csv(TABLES/'LEGACY_96x9_PARITY.csv',index=False)
 return dict(rows=96,metrics=len(f),passed=int(f.pass_6sig.sum()),all_pass=bool(f.pass_6sig.all()))
def control_parity():
 rows=[]
 for case in CASES:
  for bias in ['B0','L2']:
   d=read_data(case,bias);ref=C.load_control(case,bias)
   for arm,j in [('BB_ORIG',ref['jb']),('MB_ORIG',ref['jm'])]:
    tr=read_trace(case,bias,arm,'fixed');u=ref['acc'][:,j].astype(bool)
    e=tr['X']-ref['x'][:,j];e[:,2]=wrap(e[:,2])
    dss,gys,_=C.controls_from(ref['x'][:,ref['jb']],ref['prior'][:,ref['jb']],d['t'])
    row=dict(case=case,bias=bias,arm=arm,mask_mismatch=int(np.sum(tr['used']!=u)),xy_abs_max=float(np.max(abs(e[:,:2]))),heading_abs_max=float(np.max(abs(e[:,2]))),bg_abs_max=float(np.max(abs(e[:,3]))),P_abs_max=float(np.max(abs(tr['PX']-ref['P'][:,j]))),prior_abs_max=float(np.max(abs(tr['xp']-ref['prior'][:,j]))),Pprior_abs_max=float(np.max(abs(tr['Pp']-ref['Pprior'][:,j]))),nu_used_abs_max=float(np.max(abs(tr['nu'][u]-ref['nu'][u,j]))),J_used_abs_max=float(np.max(abs(tr['J'][u]-ref['H'][u,j]))),ds_abs_max=float(np.max(abs(d['ds'][1:]-dss[1:]))),gyro_abs_max=float(np.max(abs(d['gy'][1:]-gys[1:]))))
    row['pass']=bool(row['mask_mismatch']==0 and row['xy_abs_max']<=1e-8 and row['heading_abs_max']<=1e-10 and row['bg_abs_max']<=1e-10 and np.allclose(tr['PX'],ref['P'][:,j],atol=1e-10,rtol=1e-9));rows.append(row)
 f=pd.DataFrame(rows);f.to_csv(TABLES/'CONTROL_STATE_COVARIANCE_PARITY.csv',index=False)
 return dict(rows=len(f),passed=int(f['pass'].sum()),all_pass=bool(f['pass'].all()),max_xy_m=float(f.xy_abs_max.max()),max_heading_rad=float(f.heading_abs_max.max()),max_P=float(f.P_abs_max.max()))
def main():
 global MODEL
 ap=argparse.ArgumentParser();ap.add_argument('--workers',type=int,default=3);a=ap.parse_args()
 t0=time.time();MODEL=C.base_model();print('MODEL_LOADED',time.time()-t0,flush=True)
 cases=[(c,b) for c in CASES for b in BIASES]
 manifest=json.loads((REC/'RECOVERY_MANIFEST.json').read_text());assert all(digest(REC/f['path'])==f['sha256'] for f in manifest['files'])
 write_json(ROOT/'contracts/INPUT_LOCK.json',manifest)
 write_json(ROOT/'contracts/RECONSTRUCTION_START_RECEIPT.json',dict(start_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),config_sha256=digest(ROOT/'contracts/CONFIG_LOCK.json'),input_lock_sha256=digest(ROOT/'contracts/INPUT_LOCK.json'),code_sha256={p.name:digest(p) for p in Path(__file__).parent.glob('*.py')},prior_results_observed=True,independent_pre_run_audit='NOT_AVAILABLE',execution_class='RETROSPECTIVE_RECONSTRUCTION_SELF_REVIEW_ONLY'))
 with cf.ProcessPoolExecutor(max_workers=a.workers,mp_context=mp.get_context('fork')) as pool:base=list(pool.map(baseline,cases))
 vals={}
 for c in CASES:
  d=read_data(c,'B0');tr=read_trace(c,'B0','BB_ORIG','self');m=(d['t']>=30-1e-9)&np.isfinite(d['z']).all(1)
  vals[c]=dict(n=int(m.sum()),mean_variance=float(np.mean(tr['sigma_lookup'][m]**2)),baseline_trace_sha256=digest(trace_path(c,'B0','BB_ORIG','self')))
 const={c:dict(train_routes=[x for x in CASES if x!=c],variance=float(np.mean([vals[x]['mean_variance'] for x in CASES if x!=c]))) for c in CASES}
 write_json(RESULTS/'CONSTANT_VARIANCE_TRAIN_LOCK.json',dict(rule=CONFIG['constant_variance_rule'],training=vals,held_route_constants=const,created_before_treatment_scores=True,prior_published_results_already_seen=True,calculation_uses_evaluation_scores=False))
 print('CONSTANTS',const,flush=True)
 with cf.ProcessPoolExecutor(max_workers=a.workers,mp_context=mp.get_context('fork')) as pool:other=list(pool.map(other_runs,cases))
 rows=[]
 for r in base:rows.extend([r,{**r,'gate':'fixed'}])
 rows.extend(x for group in other for x in group)
 scores=pd.DataFrame(rows).sort_values(['case','bias','arm','gate']);scores.to_csv(TABLES/'RECURSIVE_144_LOGICAL_SCORES.csv',index=False,float_format='%.17g')
 qa=dict(historical_csv=legacy_parity(scores),control_trace=control_parity(),actual_full_recursions=132,logical_comparisons=len(scores),reference_mask_runs_extra=0,alias='12 BB_ORIG fixed traces reuse corresponding self run and its used mask',seconds=time.time()-t0,environment=dict(python=sys.version,numpy=np.__version__,pandas=pd.__version__,platform=platform.platform()),audit='SELF_REVIEW_ONLY')
 write_json(RESULTS/'REPLAY_QA.json',qa);print('QA',qa,flush=True)
 assert qa['historical_csv']['all_pass'] and qa['control_trace']['all_pass']
if __name__=='__main__':main()
