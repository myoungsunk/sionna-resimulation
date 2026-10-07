import os,sys,time,json,subprocess,hashlib,datetime
from pathlib import Path
import numpy as np
W=Path('/job');S=W/'source';D=S/'results/DRIVE_SIM_20261007';L=W/'logs';R=D/'B_RESTART_20261007_01a115bd'
ENV=dict(os.environ,PYTHON='/opt/rt-env/bin/python',NPROC='16',PYTHONPATH='/job/runtime_packages:/job/source/src',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
PY='/opt/rt-env/bin/python'
def state(stage,kind,**kw):
 r=dict(stage=stage,state=kind,timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),source_commit='1b9cf190244f91d0097a82106a02ec1dd5f53220',**kw)
 (W/'PIPELINE_B_STATUS.json').write_text(json.dumps(r,indent=2))
 print(json.dumps(r),flush=True)
def run(stage,args):
 state(stage,'RUNNING')
 with (L/('B_01a115bd_'+stage+'.log')).open('w') as f:
  rc=subprocess.call(args,cwd=S,env=ENV,stdout=f,stderr=subprocess.STDOUT)
 with (W/'PIPELINE_B_EXECUTION.jsonl').open('a') as f:f.write(json.dumps(dict(stage=stage,command=args,exit_code=rc))+'\n')
 if rc:raise RuntimeError(stage+' exit '+str(rc))
def wait_status(file):
 while True:
  p=W/file
  if p.exists():
   r=json.loads(p.read_text())
   if r['state']=='FAILED':raise RuntimeError(file+' failed')
   if r['state']=='COMPLETE':return r
  time.sleep(10)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for c in iter(lambda:f.read(1<<20),b''):h.update(c)
 return h.hexdigest()

try:
 parity=json.loads((D/'S2/PARITY_REPORT.json').read_text());assert parity['all_passed'] is True
 g3={y:json.loads((D/'S2'/('G3_continuity_y'+y+'.json')).read_text()) for y in ['0','0.35']}
 assert all(g['passed_relaxed_2e13'] is True for g in g3.values())
 decision=dict(method='B',G3_tolerance_s=2e-13,user_authorized=True,original_G3_strict={y:g['passed_strict_prereg_tol'] for y,g in g3.items()},G3_relaxed={y:g['passed_relaxed_2e13'] for y,g in g3.items()},thresholds_changed=True,original_reports_preserved=True,result_root=str(R.relative_to(S)),S6_claim_boundary='diagnostic; L1/L2 FAIL retained')
 (R/'ROUTE_DECISION.json').write_text(json.dumps(decision,indent=2))
 for y in ['0','0.35']:
  for m in ['0','45']:
   dst=R/'S2'/('H_y'+y+'_m'+m+'.npy');assert not dst.exists()
   run('apply_y'+y+'_m'+m,[PY,'scripts/drive_sim/rf_b_apply.py','--poses',str(D/'S1'/('rf_poses_y'+y+'.json')),'--traces',str(D/'S2'/('traces_y'+y)),'--mount',m,'--out',str(dst)])
   h=np.load(dst,mmap_mode='r');poses=json.loads((D/'S1'/('rf_poses_y'+y+'.json')).read_text())
   assert h.shape==(len(poses),257,2,2) and np.isfinite(h).all()
   man=json.loads(dst.with_suffix('.manifest.json').read_text());assert man['config']['report']['complete'] is True
   del h
 wait_status('LUT_STATUS.json')
 l1=json.loads((D/'S4/hs_lut_meta.json').read_text());l2=json.loads((D/'S4/LUT_LOS_CHECK.json').read_text())
 (R/'LUT_LIMITATIONS.json').write_text(json.dumps(dict(L1=l1,L2=l2,S6_result_status='diagnostic_with_LUT_gate_failure',LUT_thresholds_changed=False),indent=2))
 run('lut_mismatch',[PY,'scripts/drive_sim/lut_mismatch.py','--s1',str(D/'S1'),'--h-dir',str(R/'S2'),'--lut',str(D/'S4/hs_lut_2deg.npy'),'--out',str(R/'S4/LUT_MISMATCH.json')])
 run('snr_calibration',[PY,'scripts/drive_sim/snr_calibration.py','--s1',str(D/'S1'),'--h-dir',str(R/'S2'),'--out',str(R/'S3/SNR_CALIBRATION.json'),'--snr-db','60','50','40','30','20','10'])
 run('S6_experiments',[PY,'scripts/drive_sim/run_experiments.py','--s1',str(D/'S1'),'--h-dir',str(R/'S2'),'--lut',str(D/'S4/hs_lut_2deg.npy'),'--out',str(R/'S6'),'--snr-db','30','10','--mismatch-sigma','0.18','--pos-process-std','0.01','--seeds','50','--nproc','4'])
 run('S6_analysis',[PY,'scripts/drive_sim/analyze_experiments.py','--results',str(R/'S6'),'--out',str(R/'S6/ANALYSIS')])
 state('S6_analysis','COMPLETE',method='B',G3_tolerance_s=2e-13,result_root=str(R.relative_to(S)),scientific_PASS=False)
except Exception as e:
 state('pipeline_B','FAILED',error=str(e));raise
