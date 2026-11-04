"""One newly authorized original-pose native canary. No expansion or attribution."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def main():
    plan = json.loads((HERE/'PLAN.json').read_text())
    go = json.loads((HERE/'GO_CANARY.json').read_text())
    only = [dict(case='R4_aB_m0',pose_id=194)]
    if plan['poses'] != only or go.get('decision') != 'GO' or go.get('authorized') != only:
        raise ValueError('new canary-only GO required')
    names = ('launch.py','PLAN.json','EXECUTION_KO.md','PR28_AUDIT_COMMENT.json')
    if go.get('execution_sha256') != {n:sha(HERE/n) for n in names}:
        raise ValueError('canary execution GO hash')
    stop = os.environ.get('MANAGED_PROCESS_STOP_FILE')
    if stop and Path(stop).exists():
        raise RuntimeError('stop before RT')
    for name in ('RUN_RESULT.json','EXECUTION.log','CAPTURE_001'):
        if (HERE/name).exists():
            raise ValueError('preserve previous evidence '+name)
    command = [*plan['runtime_command'],plan['producer_linux'],
        '--source',plan['source_linux'],'--bank',plan['bank_linux'],
        '--case','R4_aB_m0','--pose-id','194','--go',plan['go_linux'],
        '--out',plan['capture_linux']]
    record = dict(status='RUNNING',start_utc=stamp(),command=command,
        go_sha256=sha(HERE/'GO_CANARY.json'),plan_sha256=sha(HERE/'PLAN.json'),
        managed_run_id=os.environ.get('MANAGED_PROCESS_RUN_ID'))
    def save():
        (HERE/'RUN_RESULT.json').write_text(json.dumps(record,indent=2)+'\n')
    save()
    try:
        with (HERE/'EXECUTION.log').open('x',encoding='utf8') as f:
            child = subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8',errors='replace')
            for line in child.stdout:
                f.write(line);f.flush();print(line.rstrip(),flush=True)
            record['exit_code'] = child.wait()
        manifest = HERE/'CAPTURE_001/MANIFEST.json'
        receipt = json.loads(manifest.read_text()) if manifest.exists() else {}
        record['capture_status'] = receipt.get('status','MISSING')
        if record['exit_code'] != 0 or record['capture_status'] != 'AMENDED_NUMERICAL_PASS':
            raise RuntimeError('new canary first failure; no expansion')
        record.update(status='NUMERICAL_PASS_PENDING_INDEPENDENT_DATA_AUDIT',
            raw_sha256=sha(HERE/'CAPTURE_001/RAW.npz'),manifest_sha256=sha(manifest))
    except BaseException as exc:
        record.update(status='STOP',error=repr(exc))
        raise
    finally:
        record['end_utc'] = stamp()
        save()


if __name__ == '__main__':
    main()
