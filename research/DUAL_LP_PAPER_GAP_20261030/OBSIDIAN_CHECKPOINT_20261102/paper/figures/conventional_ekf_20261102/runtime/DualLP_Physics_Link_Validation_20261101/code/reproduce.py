"""Run in a NEW destination; preserve this delivery's evidence and output files."""
from __future__ import annotations
import argparse,os,shutil,subprocess,sys,json,datetime,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def link_or_copy(src,dst):
    try:os.link(src,dst)
    except OSError:shutil.copy2(src,dst)
    return dst
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--dest',required=True,type=Path);ap.add_argument('--workers',type=int,default=3);ap.add_argument('--figures',action='store_true');a=ap.parse_args()
    if os.name!='posix':raise RuntimeError('Use Linux or WSL: original reconstruction uses fork workers.')
    dest=a.dest.expanduser().resolve()
    if dest.exists():raise FileExistsError('Use a new destination; existing results are never overwritten: '+str(dest))
    if a.workers<1:raise ValueError('workers must be positive')
    subprocess.run([sys.executable,str(ROOT/'code/fetch_missing_inputs.py'),'--verify-only'],check=True)
    dest.mkdir(parents=True)
    ignore=shutil.ignore_patterns('__pycache__','*.pyc')
    for name in ('code','evidence'):
        shutil.copytree(ROOT/name,dest/name,ignore=ignore)
    shutil.copytree(ROOT/'recovered',dest/'recovered',copy_function=link_or_copy,ignore=ignore)
    (dest/'contracts').mkdir();(dest/'logs').mkdir()
    for name in ('CONFIG_LOCK.json','RECONSTRUCTION_SCOPE.md'):
        shutil.copy2(ROOT/'contracts'/name,dest/'contracts'/name)
    env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    steps=[('replay_validation.py',['--workers',str(a.workers)]),('physics_validation.py',[]),('shadow_validation.py',[]),('quality_and_comparison.py',[]),('mean_lineage_validation.py',[]),('trace_contract_checks.py',[]),('finalize_reports.py',[])]
    if a.figures:steps.insert(-1,('make_figures.py',[]))
    for name,args in steps:
        print('RUN',name,flush=True)
        with (dest/'logs'/(Path(name).stem+'.log')).open('w') as log:
            subprocess.run([sys.executable,str(dest/'code'/name),*args],cwd=dest,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    manifest=json.loads((ROOT/'MANIFEST.json').read_text())
    manifest['created_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    manifest['reproduced_from_delivery']=str(ROOT)
    manifest['execution_location']='user requested new destination'
    manifest['environment']=json.loads((dest/'results/REPLAY_QA.json').read_text())['environment']
    manifest['config_sha256']=hashlib.sha256((dest/'contracts/CONFIG_LOCK.json').read_bytes()).hexdigest()
    manifest['input_lock_sha256']=hashlib.sha256((dest/'contracts/INPUT_LOCK.json').read_bytes()).hexdigest()
    (dest/'MANIFEST.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False))
    subprocess.run([sys.executable,str(dest/'code/package_delivery.py'),'--no-zip'],cwd=dest,check=True)
    print('COMPLETED',dest)
if __name__=='__main__':main()
