"""Run the audited V3/V4 CLIs in independent cell processes; no estimator edits."""
from pathlib import Path
import os,sys,json,hashlib,subprocess,time,datetime,concurrent.futures,threading
root=Path(__file__).parent
stage=sys.argv[1]
assert stage in ('V3','V4')
out=root/'development_20261013'/stage
out.mkdir(parents=True,exist_ok=False)
pkg=root/'research/DR_EKF_DIAGNOSIS_20261013/followup_v2'
sys.path.insert(0,str(pkg))
import common as C
from v5_independent import expected_hashes
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False),encoding='utf-8')
before=expected_hashes()
revision='f936492b240fae9d6e76b5c227f716b0477a0cad'
for rel,h in before.items():
 b=subprocess.check_output(['git','-C',str(root),'show',revision+':'+rel])
 assert hashlib.sha256(b).hexdigest()==h,rel
C.git_frozen_spec()
cells=[(r,l) for r in ['R2','R4','R5'] for l in [0,1,2]]
plan=dict(stage=stage,world='gauss_level',routes=['R2','R4','R5'],levels=[0,1,2],seeds='8000:8032',n_seeds=32,full_route=True,
          methods=['BASE','MEAN2','COV2','BOTH2'] if stage=='V3' else ['none','bg','sf','eps','bg+sf','bg+eps','sf+eps','bg+sf+eps'],
          max_cell_processes=4,source_revision=revision,local_checkout_head=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip(),
          source_identity='every input byte verified against source_revision; checkout HEAD is an older partial clone',
          input_sha256=before,started_utc=now(),claim='development diagnostic only; no D6 or V5 verdict')
save(out/'RUN_PLAN.json',plan)
if stage=='V3':
 with (out/'pytest.log').open('x') as log:
  p=subprocess.run([sys.executable,'-m','pytest','-q','tests/test_dr_ekf_followup_v2.py'],cwd=root,stdout=log,stderr=subprocess.STDOUT)
 assert p.returncode==0,'Regression test failure'
print(stage,'SOURCE VERIFIED; START',len(cells),'CELLS',flush=True)
env=os.environ.copy()
for k in ['OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS','NUMEXPR_NUM_THREADS']:env[k]='1'
env['PYTHONUNBUFFERED']='1'
lock=threading.Lock();receipts=[]
stop=Path(os.environ['MANAGED_PROCESS_STOP_FILE'])
def run(cell):
 route,lv=cell;name=f'{route}_d{lv}'
 if stop.exists():raise RuntimeError('Stop requested')
 script='v3_second_order.py' if stage=='V3' else 'v4_calibration.py'
 cmd=[sys.executable,'-u',str(pkg/script),'--out',str(out/name),'--world','gauss_level','--routes',route,'--levels',str(lv),'--seeds','8000:8032']
 if stage=='V3':cmd+=['--steps','0']
 start=now();t=time.monotonic()
 with (out/(name+'.log')).open('x') as log:p=subprocess.run(cmd,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
 receipt=dict(cell=name,command=cmd,exit_code=p.returncode,started_utc=start,ended_utc=now(),elapsed_s=time.monotonic()-t)
 save(out/(name+'_RECEIPT.json'),receipt)
 with lock:
  receipts.append(receipt);save(out/'PROGRESS.json',dict(completed=len(receipts),total=9,receipts=receipts))
 print(stage,name,'EXIT',p.returncode,round(receipt['elapsed_s'],1),'s',flush=True)
 return receipt
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 for rec in pool.map(run,cells):pass
after=expected_hashes();assert before==after,'Input changed during execution'
assert all(r['exit_code']==0 for r in receipts),'One or more cells failed; no completed aggregate'
rows=[];info=[]
filename='V3_SECOND_ORDER_ABLATION.json' if stage=='V3' else 'V4_CALIBRATION_ABLATION.json'
for route,lv in cells:
 cellout=out/f'{route}_d{lv}'
 d=json.loads((cellout/filename).read_text());rows+=d['rows']
 manifest=json.loads((cellout/(stage+'_MANIFEST.json')).read_text())
 assert manifest['world']=='gauss_level' and manifest['seeds']=='8000:8032'
 assert manifest['routes']==[route] and manifest['levels']==[lv]
 if stage=='V4':info+=json.loads((cellout/'V4_IDENTIFIABILITY_PROXY.json').read_text())['rows']
assert len(rows)==(36 if stage=='V3' else 72)
if stage=='V3':
 assert all(r['n_seeds']==32 and not r['limited_horizon'] for r in rows)
else:
 assert all(r['n']==32 for r in rows)
save(out/filename,dict(status='DEVELOPMENT_ONLY' if stage=='V3' else 'DEVELOPMENT_DIAGNOSTIC',rows=rows,plan=plan))
if stage=='V4':save(out/'V4_IDENTIFIABILITY_PROXY_ALL.json',dict(rows=info,note='same route proxy repeated across drift jobs; not independent samples'))
files={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()}
save(out/'COMPLETION.json',dict(status='EXECUTION_COMPLETE',finished_utc=now(),all_exit_codes_zero=True,rows=len(rows),episodes=len(rows)*32,inputs_unchanged=True,source_revision=revision,output_sha256=files))
print(stage,'EXECUTION_COMPLETE',len(rows),'ROWS',len(rows)*32,'EPISODES',flush=True)
