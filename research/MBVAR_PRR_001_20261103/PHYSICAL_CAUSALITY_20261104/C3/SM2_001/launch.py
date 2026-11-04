"""Windows launcher checks published code/GO bytes before starting pinned WSL."""
import argparse,json,subprocess,sys,os
from pathlib import Path
from authority import HERE,sha,read,bindings,verify_inputs,check_go

BRANCH='refs/heads/proposal/sm2-c3-yaw-only-audit-20261104'
REPO=HERE.parents[4]
def git(*args):return subprocess.check_output(['git','-C',str(REPO),*args])
def main():
 p=argparse.ArgumentParser();p.add_argument('--preflight',action='store_true');p.add_argument('--tests',action='store_true');args=p.parse_args()
 plan=read(HERE/'PLAN.json');lock=read(HERE/'INPUT_LOCK.json')
 verify_inputs(lock,windows=True)
 if args.tests:
  child='/mnt/d/'+(HERE/'test_preflight.py').as_posix()[3:]
  command=[*plan['runtime_command'],'-B',child]
  raise SystemExit(subprocess.call(command))
 go=read(HERE/'GO_CANARY.json');check_go(go,plan,bindings(plan))
 revision=git('ls-remote','origin',BRANCH).decode().split()[0]
 for n in [*plan['bound_files'],'GO_CANARY.json','audit/C3_SPEC_REAUDIT_RESULT.json']:
  relative=(HERE/n).relative_to(REPO).as_posix()
  if git('show',revision+':'+relative)!=(HERE/n).read_bytes():raise ValueError('published bytes mismatch '+n)
 output=HERE/'CANARY_001'
 if output.exists():raise ValueError('preserve existing output')
 if args.preflight:
  print(json.dumps(dict(status='PREFLIGHT_PASS',published_revision=revision,authorized=4,max_calls=1040)),flush=True);return
 linux='/mnt/d/'+HERE.as_posix()[3:]
 cmd=[*plan['runtime_command'],'-B',linux+'/producer.py','--go',linux+'/GO_CANARY.json','--out',plan['output_linux'],'--revision',revision]
 print(json.dumps(dict(command=cmd,published_revision=revision,managed_process_run=os.environ.get('MANAGED_PROCESS_RUN_ID'))),flush=True)
 raise SystemExit(subprocess.call(cmd))

if __name__=='__main__':main()
