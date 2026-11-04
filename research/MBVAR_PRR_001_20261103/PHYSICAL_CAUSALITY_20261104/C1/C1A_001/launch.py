"""Managed Windows owner of one foreground WSL C1a process."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
BOUND = ('core.py', 'evaluate.py', 'test_core.py', 'run.py', 'launch.py',
         'PLAN.json', 'CONTRACT_KO.md', 'INPUT_LOCK.json', 'GOVERNANCE.json')


def main():
    plan = json.loads((HERE/'PLAN.json').read_bytes())
    go = json.loads((HERE/'GO.json').read_bytes())
    if go.get('schema') != 'C1A_GO_V1' or go.get('decision') != 'GO' or go.get('authorized') != plan['authorized']:
        raise ValueError('fresh C1a-only GO required')
    if go.get('bindings_sha256') != {
            name: hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in BOUND}:
        raise ValueError('GO code/contract/scope bindings before process launch')
    if any((HERE/n).exists() for n in ('RUN_RESULT.json','EXECUTION.log','RESULTS_001')):
        raise ValueError('preserve prior outputs')
    stop = os.environ.get('MANAGED_PROCESS_STOP_FILE')
    if stop and Path(stop).exists():
        raise RuntimeError('stop before C1a')
    command = [*plan['runtime_command'],plan['runner_linux'],
               '--input',plan['input_linux'],'--out',plan['output_linux'],'--go',plan['go_linux']]
    stamp = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    record = dict(status='RUNNING',start_utc=stamp(),command=command,
                  managed_run_id=os.environ.get('MANAGED_PROCESS_RUN_ID'),
                  go_sha256=hashlib.sha256((HERE/'GO.json').read_bytes()).hexdigest())
    def save():
        (HERE/'RUN_RESULT.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
    save()
    try:
        with (HERE/'EXECUTION.log').open('x',encoding='utf8') as log:
            process = subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                       text=True,encoding='utf8',errors='replace')
            for line in process.stdout:
                log.write(line);log.flush();print(line.rstrip(),flush=True)
            record['exit_code'] = process.wait()
        manifest = HERE/'RESULTS_001/MANIFEST.json'
        result = json.loads(manifest.read_bytes()) if manifest.exists() else {}
        record['result_status'] = result.get('status','MISSING')
        if record['exit_code'] != 0 or record['result_status'] != 'NUMERICAL_PASS_PENDING_INDEPENDENT_RESULT_AUDIT':
            raise RuntimeError('C1a first failure; no automatic retry')
        record['status'] = record['result_status']
    except BaseException as exc:
        record.update(status='STOP',error=repr(exc))
        raise
    finally:
        record['end_utc'] = stamp();save()


if __name__ == '__main__':
    main()
