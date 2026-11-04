"""Managed Windows launcher, sequential original-pose WSL captures, stop at first failure."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
SM0 = HERE.parent


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def main():
    plan = json.loads((HERE/'PLAN.json').read_text())
    go = json.loads((HERE/'GO_BATCH.json').read_text())
    if go.get('decision') != 'GO' or go.get('authorized') != plan['poses']:
        raise ValueError('batch scope GO')
    if go.get('execution_sha256') != {n:sha(HERE/n) for n in ('batch_runner.py','PLAN.json','EXECUTION_KO.md')}:
        raise ValueError('execution GO hash')
    status_path = HERE/'BATCH_RESULT.json'
    if status_path.exists():
        raise ValueError('preserve batch evidence, no rerun')
    state = dict(status='RUNNING',start_utc=stamp(),plan_sha256=sha(HERE/'PLAN.json'),
                 go_sha256=sha(HERE/'GO_BATCH.json'),results=[],managed_run_id=os.environ.get('MANAGED_PROCESS_RUN_ID'))

    def save():
        temp = status_path.with_suffix('.tmp')
        temp.write_text(json.dumps(state,indent=2)+'\n')
        temp.replace(status_path)

    save()
    try:
        for item in plan['poses']:
            stop = os.environ.get('MANAGED_PROCESS_STOP_FILE')
            if stop and Path(stop).exists():
                raise RuntimeError('cooperative stop between poses')
            case, pid = item['case'], item['pose_id']
            name = case+'_'+str(pid)
            output = HERE/'captures'/name
            if output.exists():
                raise ValueError('preserve capture '+name)
            log = HERE/(name+'.log')
            if log.exists():
                raise ValueError('preserve log '+name)
            command = [*plan['runtime_command'],plan['producer_linux'],
                '--source',plan['source_linux'],'--bank',plan['bank_linux'],
                '--case',case,'--pose-id',str(pid),'--go',plan['go_linux'],
                '--out',plan['capture_root_linux']+'/'+name]
            state['active'] = dict(case=case,pose_id=pid,start_utc=stamp(),command=command)
            save()
            print('SM0_POSE_START',name,flush=True)
            with log.open('x',encoding='utf8') as handle:
                child = subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8',errors='replace')
                for line in child.stdout:
                    handle.write(line)
                    handle.flush()
                    print(line.rstrip(),flush=True)
                code = child.wait()
            manifest = output/'MANIFEST.json'
            receipt = json.loads(manifest.read_text()) if manifest.exists() else {}
            state['results'].append(dict(case=case,pose_id=pid,exit_code=code,status=receipt.get('status','MISSING'),
                raw_sha256=receipt.get('raw_sha256'),manifest_sha256=sha(manifest) if manifest.exists() else None,
                log_sha256=sha(log),end_utc=stamp()))
            save()
            if code != 0 or receipt.get('status') != 'AMENDED_NUMERICAL_PASS':
                raise RuntimeError('first failing capture '+name)
            print('SM0_POSE_PASS',name,len(state['results']),flush=True)
        state['status'] = 'ALL_14_NUMERICAL_PASS_PENDING_INDEPENDENT_AUDIT'
    except BaseException as exc:
        state['status'] = 'STOP'
        state['error'] = repr(exc)
        raise
    finally:
        state['end_utc'] = stamp()
        state.pop('active',None)
        save()


if __name__ == '__main__':
    main()
