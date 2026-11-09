"""Run declared research ablations after a scoped precheck lock exists.

Diagnostic activity is authorized by the experiment request; failed utility
never becomes a deployment recommendation. Each subprocess owns its recursion.
"""
from __future__ import annotations
import argparse,concurrent.futures,datetime,hashlib,json,subprocess,sys,time
from pathlib import Path

MODES=('OFF','OBSERVE_ONLY','ACTIVE_R','ACTIVE_S','ACTIVE_RS','DR_ONLY','NAIVE_YAW_CLIP')

def run(a):
    lock=json.loads(a.policy_lock.read_text())
    for s in a.strata:
        if s not in lock['policies']:raise ValueError('PRECHECK_SCOPE_MISSING '+s)
        if set(lock['policies'][s])!={'R2','R4','R5'}:raise ValueError('PRECHECK_ROUTES_MISSING')
    a.out.mkdir(parents=True,exist_ok=True);logs=a.out/'logs';logs.mkdir(exist_ok=True)
    manifest=a.out/f'GRID_{a.name}.json'
    if manifest.exists():raise FileExistsError('GRID_MANIFEST_ALREADY_EXISTS')
    script=Path(__file__).with_name('experiment.py')
    tasks=[(s,m,r) for s in a.strata for m in a.modes for r in ('R2','R4','R5')]
    record={'status':'RUNNING','strata':a.strata,'modes':a.modes,'workers':a.workers,
       'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
       'policy_lock_sha256':hashlib.sha256(a.policy_lock.read_bytes()).hexdigest(),
       'purpose':'Predeclared diagnostic ablations; independent of whether selection chose OFF',
       'runtime_code_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (script,script.with_name('mcg.py'))},'jobs':[]}
    def save():manifest.write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    save()
    def job(task):
        s,m,r=task;out=a.out/s/m;lp=logs/f'{s}_{m}_{r}.log'
        role={'OFF':'parity_baseline','OBSERVE_ONLY':'observe_only','DR_ONLY':'motion_only_diagnostic','NAIVE_YAW_CLIP':'negative_control_prior_correction_threshold'}.get(m,'predeclared_tau2_diagnostic')
        cmd=[sys.executable,str(script),'active','--route',r,'--stratum',s,'--mode',m,'--tau','2','--span','5',
             '--archives',str(a.archives),'--out',str(out),'--policy-role',role,'--policy-lock',str(a.policy_lock)]
        start=time.monotonic()
        with lp.open('w') as f:
            result=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=False)
        return {'stratum':s,'mode':m,'route':r,'exit_code':result.returncode,'elapsed_s':time.monotonic()-start,'command':cmd,'log':str(lp)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
        for f in concurrent.futures.as_completed([pool.submit(job,t) for t in tasks]):
            item=f.result();record['jobs'].append(item);save();print('GRID_CASE',item['stratum'],item['mode'],item['route'],'exit',item['exit_code'],flush=True)
    record['status']='EXECUTION_COMPLETE' if all(x['exit_code']==0 for x in record['jobs']) else 'EXECUTION_FAILED'
    record['ended_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();save()
    if record['status']!='EXECUTION_COMPLETE':raise RuntimeError('ONE_OR_MORE_GRID_JOBS_FAILED; inspect manifest and preserved logs')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--archives',type=Path,required=True);p.add_argument('--policy-lock',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--strata',nargs='+',choices=['B_FROZEN','B_BIAS_COV'],default=['B_FROZEN','B_BIAS_COV']);p.add_argument('--modes',nargs='+',choices=MODES,default=list(MODES));p.add_argument('--workers',type=int,default=6);p.add_argument('--name',required=True);a=p.parse_args()
    if not 1<=a.workers<=9:p.error('workers must be in 1..9')
    run(a)
