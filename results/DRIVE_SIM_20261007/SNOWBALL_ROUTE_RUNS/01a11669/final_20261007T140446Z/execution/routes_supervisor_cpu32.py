import os,sys,json,time,datetime,subprocess,hashlib
from pathlib import Path
import numpy as np
W=Path('/job');S=W/'source';D=S/'results/DRIVE_SIM_20261007';R=D/'SNOWBALL_ROUTES_01a11669';L=W/'logs';PY='/opt/rt-env/bin/python';S2=R/'S2'
ENV=dict(os.environ,PYTHON=PY,NPROC='32',S2_DIR=str(S2),PYTHONPATH='/runtime_packages:/job/source/src',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
SHA='0d4588f79116e221d874307f233d69ff0b13d99c'
def state(stage,status,**kw):
 rec=dict(stage=stage,state=status,timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),source_commit=SHA,RF_nproc=32,threads_per_process=1,**kw)
 (W/'STATUS.json').write_text(json.dumps(rec,indent=2));print(json.dumps(rec),flush=True)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def run(stage,args):
 state(stage,'RUNNING')
 with (L/(stage+'_cpu32.log')).open('x') as f:rc=subprocess.call(args,cwd=S,env=ENV,stdout=f,stderr=subprocess.STDOUT)
 with (W/'EXECUTION.jsonl').open('a') as f:f.write(json.dumps(dict(stage=stage,command=args,exit_code=rc,timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat()))+'\n')
 if rc:raise RuntimeError(stage+' exit '+str(rc))
def shell(stage):run(stage,['bash','scripts/drive_sim/run_rf_snowball.sh',stage])
def audit_traces(tasks,out):
 ts=json.loads(tasks.read_text());bad=[];screen=0;dropped=0;maxamp=0
 for t in ts:
  q=out/(t['tag']+'_trace_receipt.json');z=out/(t['tag']+'_trace.npz')
  if not q.exists() or not z.exists():bad.append(dict(tag=t['tag'],issue='MISSING'));continue
  doc=json.loads(q.read_text())
  if doc['status']!='OK':bad.append(dict(tag=t['tag'],issue=doc['status']))
  screen+=int(bool(doc.get('screen_exceeded')));dropped+=int(bool(doc.get('dropped_audit')));maxamp=max(maxamp,float(doc.get('max_dropped_rel_amp',0)))
 rep=dict(tasks=len(ts),missing_or_bad=bad,screen_exceeded_positions=screen,dropped_path_positions=dropped,max_dropped_rel_amp=maxamp,screen_is_reported_flag_per_A10b=True)
 assert not bad,str(rep)
 return rep
try:
 parity=json.loads((S2/'anchorB/PARITY_REPORT_ANCHOR_B.json').read_text())
 assert parity.get('all_passed') is True
 assert (R/'PARITY_STAGE_AUDIT.json').exists()
 shell('routes-trace')
 audit={}
 for route in ['R2','R4','R5']:
  for anchor in ['A','B']:audit[route+'_a'+anchor]=audit_traces(D/'S1/routes'/('rf_tasks_'+route+'_m0.json'),S2/('traces_'+route+'_a'+anchor))
 (R/'TRACE_AUDIT.json').write_text(json.dumps(audit,indent=2))
 shell('routes-continuity')
 g3={}
 for route in ['R2','R4','R5']:
  for anchor in ['A','B']:
   k=route+'_a'+anchor;g3[k]=json.loads((S2/('G3_continuity_'+k+'.json')).read_text())
 decision=dict(method='B',parity_all_passed=True,G3_authorized_tolerance_s=2e-13,G3_strict={k:g['passed_strict_prereg_tol'] for k,g in g3.items()},G3_relaxed={k:g['passed_relaxed_2e13'] for k,g in g3.items()},original_strict_preserved=True,screen_rule='A10b report only; parity gate retained')
 (R/'ROUTE_DECISION.json').write_text(json.dumps(decision,indent=2))
 if not all(decision['G3_relaxed'].values()):
  state('routes-continuity','BLOCKED_GATE',reason='authorized relaxed G3 failed; no apply/S6');sys.exit(3)
 for route in ['R2','R4','R5']:
  for a in ['A','B']:
   for m in ['0','45']:assert not (S2/('H_'+route+'_a'+a+'_m'+m+'.npy')).exists()
 shell('routes-apply')
 checks={}
 for route in ['R2','R4','R5']:
  poses=json.loads((D/'S1/routes'/('rf_poses_'+route+'.json')).read_text())
  assert {p['pose_id'] for p in poses}==set(range(len(poses)))
  for a in ['A','B']:
   for m in ['0','45']:
    p=S2/('H_'+route+'_a'+a+'_m'+m+'.npy');h=np.load(p,mmap_mode='r');man=json.loads(p.with_suffix('.manifest.json').read_text())
    assert h.shape==(len(poses),257,2,2) and np.isfinite(h).all() and man['config']['report']['complete'] is True
    checks[p.name]=dict(shape=list(h.shape),complete=True,sha256=sha(p));del h
 (R/'H_STORE_VALIDATION.json').write_text(json.dumps(checks,indent=2))
 run('lut_mismatch_routes',[PY,'scripts/drive_sim/lut_mismatch_routes.py','--s1-routes',str(D/'S1/routes'),'--h-dir',str(S2),'--lut',str(R/'S4/hs_lut_2deg.npy'),'--out',str(R/'S4/LUT_MISMATCH_ROUTES.json')])
 sigma=float(json.loads((R/'S4/LUT_MISMATCH_ROUTES.json').read_text())['overall']['rms']);assert np.isfinite(sigma) and sigma>0
 frozen=dict(timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),mismatch_sigma=sigma,source='S4/LUT_MISMATCH_ROUTES.json overall.rms',measurement_sha256=sha(R/'S4/LUT_MISMATCH_ROUTES.json'),fixed_once_before_S6=True,uses_evaluated_routes_disclosed=True,snr_db=[30,10],pos_process_std=0.01,seeds=50,S6_nproc=32)
 (R/'S0/SIGMA_ROUTES_PREREG.json').write_text(json.dumps(frozen,indent=2))
 (R/'S0/PREREG_AMENDMENT_SNOWBALL_ROUTES.md').write_text('# Snowball route sigma preregistration\n\nMeasured overall.rms is fixed once before S6: '+repr(sigma)+'. No performance results used. Measurement uses evaluated routes and anchors as disclosed by A9. Original S0 amendments and all other thresholds preserved.\n')
 run('S6_routes',[PY,'scripts/drive_sim/run_route_experiments.py','--s1-routes',str(D/'S1/routes'),'--h-dir',str(S2),'--lut',str(R/'S4/hs_lut_2deg.npy'),'--out',str(R/'S6_routes'),'--snr-db','30','10','--mismatch-sigma',repr(sigma),'--pos-process-std','0.01','--seeds','50','--nproc','32'])
 run('routes_analysis',[PY,'scripts/drive_sim/analyze_route_experiments.py','--results',str(R/'S6_routes'),'--out',str(R/'S6_routes/ANALYSIS')])
 state('routes_analysis','COMPLETE',mismatch_sigma=sigma,scientific_PASS=False,L1='FAIL_preserved',L2='FAIL_preserved')
except Exception as e:
 state('routes_pipeline','FAILED',error=str(e));raise
