"""Managed owner of one phase-specific original-runtime C1b process."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
BOUND = ('conditional.py','legacy.py','score.py','run.py','launch.py','test_conditional.py',
         'PLAN.json','INPUT_LOCK.json','CONTRACT_KO.md','GOVERNANCE.json','../C1A_001/core.py')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase',choices=('dev','remaining'))
    args = parser.parse_args()
    plan = json.loads((HERE/'PLAN.json').read_bytes())
    phase = plan['phases'][args.phase]
    go_path = HERE/phase['go']
    go = json.loads(go_path.read_bytes())
    authorized = dict(stage='C1b_only',phase=args.phase,routes=plan['routes'],biases=plan['biases'],
                      seeds=phase['seeds'],output=phase['output'])
    if go.get('schema') != 'C1B_GO_V1' or go.get('decision') != 'GO' or go.get('authorized') != authorized:
        raise ValueError('phase-specific C1b GO required')
    if go.get('bindings_sha256') != {n:sha(HERE/n) for n in BOUND}:
        raise ValueError('pre-launch code/contract hash mismatch')
    if args.phase == 'remaining':
        audit = HERE/'audit/C1B_DEV_RESULT_AUDIT_RESULT.json'
        if sha(audit) != go.get('prerequisite_sha256') or json.loads(audit.read_bytes()).get('decision') != 'ACCEPT':
            raise ValueError('independent DEV acceptance required')
    result_path = HERE/('RUN_RESULT_'+args.phase.upper()+'.json')
    log_path = HERE/('EXECUTION_'+args.phase.upper()+'.log')
    if result_path.exists() or log_path.exists() or (HERE/phase['output']).exists():
        raise ValueError('preserve previous phase evidence')
    stop = os.environ.get('MANAGED_PROCESS_STOP_FILE')
    if stop and Path(stop).exists():
        raise RuntimeError('stop before phase')
    command = [*plan['runtime_command'],str(HERE/'run.py'),args.phase]
    env = dict(os.environ)
    for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
        env[key] = '1'
    stamp = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    record = dict(status='RUNNING',phase=args.phase,start_utc=stamp(),command=command,
                  go_sha256=sha(go_path),managed_run_id=os.environ.get('MANAGED_PROCESS_RUN_ID'))
    def save():
        result_path.write_bytes((json.dumps(record,indent=2)+'\n').encode())
    save()
    try:
        with log_path.open('x',encoding='utf8') as log:
            process = subprocess.Popen(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                       text=True,encoding='utf8',errors='replace')
            for line in process.stdout:
                log.write(line);log.flush();print(line.rstrip(),flush=True)
            record['exit_code'] = process.wait()
        manifest = HERE/phase['output']/'MANIFEST.json'
        result = json.loads(manifest.read_bytes()) if manifest.exists() else {}
        record['result_status'] = result.get('status','MISSING')
        if record['exit_code'] != 0 or record['result_status'] != 'NUMERICAL_PASS_PENDING_INDEPENDENT_RESULT_AUDIT':
            raise RuntimeError('first phase failure; no automatic retry or expansion')
        record['status'] = record['result_status']
    except BaseException as exc:
        record.update(status='STOP',error=repr(exc))
        raise
    finally:
        record['end_utc'] = stamp();save()


if __name__ == '__main__':
    main()
