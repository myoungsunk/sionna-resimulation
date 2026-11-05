"""Verify immutable publication before G4 and pin the original Windows runtime."""
import argparse,subprocess,os,sys,json
from authority import HERE,read,bindings,check_go,verify_inputs,verify_scope
REPO=HERE.parents[4];BRANCH='refs/heads/proposal/sm2-c3-yaw-only-audit-20261104'
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--tests',action='store_true');ap.add_argument('--preflight',action='store_true');args=ap.parse_args()
 p=read(HERE/'PLAN.json');lock=read(HERE/'INPUT_LOCK.json');verify_scope(p,lock);verify_inputs(lock)
 env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
 if args.tests:raise SystemExit(subprocess.call([p['python_executable'],'-B',str(HERE/'test_g4.py')],env=env))
 go=read(HERE/p['go_file']);check_go(p,go)
 def git(*a):return subprocess.check_output(['git','-C',str(REPO),*a])
 revision=git('ls-remote','origin',BRANCH).decode().split()[0]
 for n in [*p['bound_files'],p['go_file'],p['spec_audit'],p['code_audit']]:
  rel=(HERE/n).relative_to(REPO).as_posix()
  if git('show',revision+':'+rel)!=(HERE/n).read_bytes():raise ValueError('published code/GO drift '+n)
 if (HERE/p['output']).exists():raise ValueError('preserve prior output')
 if args.preflight:print(json.dumps(dict(status='G4_PREFLIGHT_PASS',revision=revision)),flush=True);return
 command=[p['python_executable'],'-B',str(HERE/'run.py'),'--revision',revision]
 print(json.dumps(dict(command=command,code_revision=revision,managed_run=os.environ.get('MANAGED_PROCESS_RUN_ID'))),flush=True)
 raise SystemExit(subprocess.call(command,env=env))
if __name__=='__main__':main()
