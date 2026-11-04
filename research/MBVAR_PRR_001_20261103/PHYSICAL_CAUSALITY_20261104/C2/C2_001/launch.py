"""Managed Windows owner; fail closed before creating scientific output."""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
from authority import HERE,check,committed_revision,sha


def main():
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=('dev','remaining'));args=parser.parse_args()
    plan,phase,go,bindings=check(args.phase)
    revision=committed_revision(args.phase)
    result_path=HERE/('RUN_RESULT_'+args.phase.upper()+'.json');log_path=HERE/('EXECUTION_'+args.phase.upper()+'.log')
    if result_path.exists() or log_path.exists() or (HERE/phase['output']).exists():raise ValueError('preserve previous evidence')
    stop=os.environ.get('MANAGED_PROCESS_STOP_FILE')
    if stop and Path(stop).exists():raise RuntimeError('stop before phase')
    env=dict(os.environ,C2_CODE_REVISION=revision)
    for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):env[name]='1'
    command=[*plan['runtime_command'],str(HERE/'run.py'),args.phase]
    stamp=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
    record=dict(status='RUNNING',phase=args.phase,start_utc=stamp(),command=command,code_revision=revision,
                published_bound_files_match=True,go_sha256=sha(HERE/phase['go']),managed_run_id=os.environ.get('MANAGED_PROCESS_RUN_ID'))
    def save():result_path.write_bytes((json.dumps(record,indent=2)+'\n').encode('utf8'))
    save()
    try:
        with log_path.open('x',encoding='utf8') as log:
            child=subprocess.Popen(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8',errors='replace')
            for line in child.stdout:log.write(line);log.flush();print(line.rstrip(),flush=True)
            record['exit_code']=child.wait()
        path=HERE/phase['output']/'MANIFEST.json';manifest=json.loads(path.read_bytes()) if path.exists() else {}
        record['result_status']=manifest.get('status','MISSING')
        if record['exit_code']!=0 or record['result_status']!='NUMERICAL_PASS_PENDING_INDEPENDENT_RESULT_AUDIT':
            raise RuntimeError('first phase failure; no retry or expansion')
        record['status']=record['result_status']
    except BaseException as error:
        record.update(status='STOP',error=repr(error));raise
    finally:record['end_utc']=stamp();save()


if __name__=='__main__':main()
