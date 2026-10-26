import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import threading
import time

ROOT = Path('/home/KMS/OFFICE_M0_RF_20261026_01a17631')
IMAGE = 'sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f'
BANK = Path('/home/KMS/OFFICE_SNOWBALL_20261008_819fa93/source')
COMMIT = 'b38a65748ae75c6678d87a6a963e8102ba392a78'
LOCK = threading.Lock()
STATE = {'status': 'STARTING', 'started_epoch': time.time(), 'source_commit': COMMIT,
         'image_id': IMAGE, 'parallel_full': 8, 'cpu_per_batch': 4, 'memory_gib_per_batch': 8,
         'target_hours': 8, 'completed': [], 'active': [], 'failed': []}

def save():
    temp = ROOT / 'SNOWBALL_STATUS.tmp'
    temp.write_text(json.dumps(STATE, indent=2))
    os.replace(str(temp), str(ROOT / 'SNOWBALL_STATUS.json'))

def command(stage, batch=None, pilot=False):
    name = 'office-m0-01a17631-' + (batch.lower() if batch else stage)
    cmd = ['docker', 'run', '--rm', '--name', name, '--network', 'none',
           '--label', 'campaign=office-m0-20261026-01a17631', '--cpus', '4', '--memory', '8g',
           '-e', 'PYTHONUNBUFFERED=1', '-e', 'GITHUB_SHA=' + COMMIT,
           '-e', 'OMP_NUM_THREADS=4', '-v', str(ROOT) + ':/run']
    for bank in ['LP_plus45_bank.npz', 'LP_minus45_bank.npz']:
        cmd += ['-v', str((BANK / bank).resolve()) + ':/run/source/' + bank + ':ro']
    cmd += ['--entrypoint', '/opt/rt-env/bin/python', IMAGE,
            '/run/pipeline.py', stage, '--root', '/run']
    if batch:
        cmd += ['--batch', batch]
    if pilot:
        cmd += ['--pilot']
    return cmd

def run(stage, batch=None, pilot=False):
    key = batch or stage
    with LOCK:
        STATE['active'].append(key)
        save()
    started = time.time()
    with (ROOT / 'LOGS' / (key + '.log')).open('wb') as log:
        cmd = command(stage, batch, pilot)
        log.write((json.dumps({'command': cmd, 'started_epoch': started}) + '\n').encode())
        log.flush()
        rc = subprocess.call(cmd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    with LOCK:
        STATE['active'].remove(key)
        item = {'job': key, 'exit_code': rc, 'elapsed_seconds': time.time() - started}
        STATE['completed' if rc == 0 else 'failed'].append(item)
        save()
    return rc

def pool(batches, workers, pilot):
    # Submit only one wave; failures prohibit dispatch of further work.
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        pending = {}
        iterator = iter(batches)
        for batch in list(batches)[:workers]:
            next(iterator)
            pending[executor.submit(run, 'batch', batch, pilot)] = batch
        while pending:
            done, _ = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
            failed = False
            for future in done:
                del pending[future]
                if future.result() != 0:
                    failed = True
            if failed or STATE['failed']:
                for future in pending:
                    future.result()
                return False
            for unused in done:
                batch = next(iterator, None)
                if batch:
                    pending[executor.submit(run, 'batch', batch, pilot)] = batch
    return True

def main():
    lockpath = ROOT / 'LAUNCH_LOCK.json'
    with lockpath.open('x') as f:
        json.dump({'pid': os.getpid(), 'started_epoch': time.time()}, f)
    archive = ROOT / 'INPUTS.tar.gz'
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == '6db5a88148b4fe0050816fb5956ced4c3acbc02cb309c9b32b170a706c06fe6b'
    with tarfile.open(str(archive)) as tar:
        for member in tar.getmembers():
            dest = (ROOT / member.name).resolve()
            assert str(dest).startswith(str(ROOT) + '/') and not member.issym() and not member.islnk()
            assert not dest.exists(), 'Refuse overwrite: ' + str(dest)
        tar.extractall(str(ROOT))
    (ROOT / 'LOGS').mkdir()
    save()
    if run('selftest'):
        raise RuntimeError('Prepared-input selftest failed')
    matrices = json.loads((ROOT / 'MATRICES.json').read_text())
    STATE['status'] = 'PILOT_RUNNING'
    save()
    if not pool(matrices['pilot']['batch'], 3, True):
        raise RuntimeError('Pilot failed; full campaign prohibited')
    STATE['status'] = 'FULL_RUNNING'
    save()
    if not pool(matrices['full']['batch'], 8, False):
        raise RuntimeError('Full batch failed; new dispatch stopped')
    STATE['status'] = 'AGGREGATING'
    save()
    if run('aggregate'):
        raise RuntimeError('Aggregate verification failed')
    STATE['status'] = 'COMPLETE_QA_PASS'
    STATE['finished_epoch'] = time.time()
    STATE['raw_paths_location'] = str(ROOT / 'BATCHES')
    STATE['archives_location'] = str(ROOT)
    save()

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        STATE['status'] = 'FAILED_STOP'
        STATE['error'] = repr(exc)
        save()
        raise
