"""Run the 24 new BLOCK_C centerline positions with frozen M7 tracing."""

import ast
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time
import traceback

from blockc_centerline_host import IMAGE, SOURCE, read, run_container, sha, snapshot, utc, write


PRIOR = Path('/home/KMS/BLOCK_C_CENTERLINE_M7_20261118_dhdj70s5')
CENTERS_CM = {'P016': 795, 'P010': 525, 'P003': 210}
OFFSETS_CM = (-16, -12, -8, -4, 4, 8, 12, 16)
YAWS = list(range(-180, 180, 10))
WORKERS = 12
CODE_COMMIT = '1a0f3c1b15be8e07c1884dbd1e42a1bb6c9b74f4'


def verify(path, digest):
    if sha(path) != digest:
        raise ValueError('Frozen SHA-256 differs: ' + str(path))


def prepare(root):
    inputs, previous = root / 'inputs', PRIOR / 'inputs'
    prior = read(previous / 'RUN_CONTRACT.json')
    completion = read(PRIOR / 'results/completion.json')
    if (completion['status'] != 'PASS' or prior['runtime_image'] != IMAGE
            or completion['run_contract_sha256'] != sha(previous / 'RUN_CONTRACT.json')):
        raise ValueError('Previous centerline run contract or result differs')
    for key in ('method_b_sha256', 'ffd_sha256'):
        for name, digest in prior[key].items():
            verify(SOURCE / name, digest)
    verify(previous / 'STATIONS.json', prior['input_sha256']['STATIONS.json'])
    verify(previous / 'rf_poses.json', prior['input_sha256']['rf_poses.json'])
    for rel, digest in prior['input_sha256'].items():
        if rel in ('SCENE_ENTRY.json', 'M7_RT_CONFIG.json', 'ORIGINAL_BLOCK_C_CASES.json') or rel.startswith(('scene/', 'baselines/')):
            verify(previous / rel, digest)
            dst = inputs / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(previous / rel), str(dst))
    for h in ('H_full.npy', 'H_LoS.npy'):
        rel = 'H/BLOCKC_B/' + h
        verify(PRIOR / 'results' / rel, completion['output_sha256'][rel])

    existing = {s['station_id']: s for s in read(previous / 'STATIONS.json')}
    existing_xy = {(s['x'], s['y']) for s in existing.values()}
    existing_poses = {(p['x'], p['y'], p['yaw_body_deg']): p['pose_id']
                      for p in read(previous / 'rf_poses.json')}
    run_id = root.name
    stations, poses, tasks, samples, comparison_poses, comparison_observations = [], [], [], [], [], []
    for center, x_cm in CENTERS_CM.items():
        if (existing[center]['x'], existing[center]['y'], existing[center]['z']) != (x_cm / 100.0, 0.0, 0.45):
            raise ValueError('Center station coordinates differ: ' + center)
        for dx_cm in (-16, -12, -8, -4, 0, 4, 8, 12, 16):
            x, y = (x_cm + dx_cm) / 100.0, 0.0
            sid = center if dx_cm == 0 else '{}_DX_{}{:02d}CM'.format(center, 'M' if dx_cm < 0 else 'P', abs(dx_cm))
            position = dict(station_id=sid, center_station_id=center, dx_cm=dx_cm, x=x, y=y, z=0.45)
            if dx_cm == 0:
                pose_ids = [existing_poses[x, y, yaw] for yaw in YAWS]
            else:
                if (x, y) in existing_xy:
                    raise ValueError('New location overlaps existing grid: ' + sid)
                pose_ids = list(range(len(poses), len(poses) + len(YAWS)))
                task_id = len(tasks)
                stations.append(dict(position, station_index=task_id))
                tasks.append(dict(task_id=task_id, tag=sid, x=x, y=y, pose_ids=pose_ids, antenna_yaw_deg=YAWS))
                poses.extend(dict(pose_id=i, x=x, y=y, yaw_body_deg=yaw) for i, yaw in zip(pose_ids, YAWS))
            for i, yaw in zip(pose_ids, YAWS):
                comparison_poses.append(dict(position, run_id=run_id if dx_cm else PRIOR.name, pose_id=i, yaw_body_deg=yaw))
            for j, yaw in enumerate(range(-180, 181, 10)):
                row = dict(position, station_sequence_index=j, protocol='full360_10deg',
                           planned_rel_deg=yaw, achieved_rel_deg=yaw, pose_id=pose_ids[j % 36], yaw_body_deg=YAWS[j % 36])
                comparison_observations.append(dict(row, run_id=run_id if dx_cm else PRIOR.name,
                                                    sequence_index=len(comparison_observations)))
                if dx_cm:
                    samples.append(dict(row, set='BLOCKC_NEAR', sequence_index=len(samples)))

    counts = (len(stations), len(poses), len(samples), len(comparison_poses), len(comparison_observations))
    if counts != (24, 864, 888, 972, 999) or len({(s['x'], s['y']) for s in stations}) != 24:
        raise ValueError('Incorrect station coverage: ' + str(counts))
    for i in range(0, len(comparison_observations), 37):
        first, last = comparison_observations[i], comparison_observations[i + 36]
        if (first['run_id'], first['pose_id']) != (last['run_id'], last['pose_id']):
            raise ValueError('Endpoint alias differs: ' + first['station_id'])
    for name, data in (('STATIONS', stations), ('rf_poses', poses), ('rf_tasks', tasks), ('SAMPLES', samples),
                       ('COMPARISON_RF_POSES', comparison_poses), ('COMPARISON_OBSERVATIONS', comparison_observations)):
        write(inputs / (name + '.json'), data)
    with (inputs / 'TIMELINE.csv').open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(samples[0]))
        writer.writeheader()
        writer.writerows(samples)
    write(inputs / 'INPUT_VALIDATION.json', dict(status='PASS', positions=24, poses=864, observations=888,
          comparison_poses=972, comparison_observations=999, step_cm=4, offsets_cm=OFFSETS_CM))
    contract = dict(prior, question_id='BLOCK-C-M7-NEAR-STATION-SWEEP-001', created_utc=utc(),
                    code_commit=CODE_COMMIT, code_overlay='blockc_m7_near_20261119.py; checksummed below',
                    shard_count=WORKERS, expected_positions=24, expected_poses=864, expected_observations=888,
                    centerline_reference=dict(run_id=PRIOR.name, root=str(PRIOR),
                        run_contract_sha256=sha(previous / 'RUN_CONTRACT.json'),
                        rf_poses_sha256=prior['input_sha256']['rf_poses.json'],
                        H_full_sha256=completion['output_sha256']['H/BLOCKC_B/H_full.npy'],
                        H_LoS_sha256=completion['output_sha256']['H/BLOCKC_B/H_LoS.npy']),
                    center_station_x_cm=CENTERS_CM, offsets_cm=OFFSETS_CM,
                    x_start_m=min(s['x'] for s in stations), x_end_m=max(s['x'] for s in stations), station_spacing_m=0.04,
                    scope='24 new centerline positions; G4 and G8; G-T2/G-V sealed',
                    current_code_sha256={p.name: sha(p) for p in sorted((root / 'code').glob('*.py'))},
                    input_sha256={p.relative_to(inputs).as_posix(): sha(p) for p in sorted(inputs.rglob('*')) if p.is_file()})
    write(inputs / 'RUN_CONTRACT.json', contract)
    write(root / 'RESOURCE_BEFORE.json', snapshot(root))
    return contract


def hash_rows(path, ids):
    """Read exact complex128 payload bytes for selected C-order NPY rows."""
    with path.open('rb') as stream:
        version = stream.read(8)
        if version == b'\x93NUMPY\x01\x00':
            length = struct.unpack('<H', stream.read(2))[0]
        elif version in (b'\x93NUMPY\x02\x00', b'\x93NUMPY\x03\x00'):
            length = struct.unpack('<I', stream.read(4))[0]
        else:
            raise ValueError('Unexpected NPY magic: ' + str(path))
        header = ast.literal_eval(stream.read(length).decode('ascii').strip())
        if header['descr'] != '<c16' or header['fortran_order'] or header['shape'][1:] != (257, 2, 2):
            raise ValueError('Unexpected baseline H layout: ' + str(path))
        start, stride, digest = stream.tell(), 257 * 2 * 2 * 16, hashlib.sha256()
        for i in ids:
            if not 0 <= i < header['shape'][0]:
                raise ValueError('Invalid baseline pose ID: ' + str(i))
            stream.seek(start + i * stride)
            row = stream.read(stride)
            if len(row) != stride:
                raise ValueError('Truncated baseline H: ' + str(path))
            digest.update(row)
    return digest.hexdigest()


def execute(root):
    start, started = time.monotonic(), utc()
    try:
        contract = prepare(root)
        base = ['/run/code/run_blockc_m7_sweep.py', '--inputs', '/run/inputs', '--source', '/ref',
                '--code-commit', CODE_COMMIT, '--source-commit', contract['source_commit']]
        baseline_start = time.monotonic()
        (root / 'baseline').mkdir()

        def baseline(item):
            route, original, ids = item['route'], Path(item['original_H_path']), item['original_pose_ids']
            original_ref = '/ref/' + original.relative_to(SOURCE).as_posix()
            receipt = run_container(root, 'baseline_' + route, base + ['--out', '/run/baseline/' + route,
                '--poses', '/run/inputs/baselines/' + route + '/rf_poses.json',
                '--tasks', '/run/inputs/baselines/' + route + '/rf_tasks.json', '--baseline-H', original_ref,
                '--baseline-pose-ids'] + [str(i) for i in ids])
            out = root / 'baseline' / route
            manifest = out / 'MANIFEST.json'
            comparison = read(manifest)['baseline_comparison']
            old_digest = hash_rows(original, ids)
            new_digest = hash_rows(out / 'mount0/H_full.npy', range(len(ids)))
            if (comparison['H_sha256'] != item['original_H_sha256'] or comparison['pose_ids'] != ids
                    or comparison['max_abs_delta_h'] != 0 or old_digest != new_digest):
                raise ValueError('Original M7 byte parity failed: ' + route)
            return route, sha(manifest), receipt, dict(route=route, pose_ids=ids, byte_equal=True,
                original_bytes_sha256=old_digest, regenerated_bytes_sha256=new_digest)

        with ThreadPoolExecutor(max_workers=3) as pool:
            checks = list(pool.map(baseline, contract['baselines']))
        write(root / 'BASELINE_BYTE_CHECK.json', dict(status='PASS', checks=[v[3] for v in checks]))
        write(root / 'BASELINE_PASS.json', dict(status='PASS', routes=[v[0] for v in checks], poses=9,
            max_abs_delta_h=0, complex_coefficients=9252, wall_s=time.monotonic() - baseline_start,
            manifest_sha256={v[0]: v[1] for v in checks}, receipts=[v[2] for v in checks]))

        (root / 'attempts/production').mkdir(parents=True)
        production_start = time.monotonic()

        def produce(index):
            name = 'shard{}'.format(index)
            return run_container(root, name, base + ['--out', '/run/attempts/production/' + name,
                '--shard-index', str(index), '--shard-count', str(WORKERS)])

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            production = list(pool.map(produce, range(WORKERS)))
        production_wall = time.monotonic() - production_start
        finish = run_container(root, 'finish', ['/run/code/finish_blockc_m7_far_sweep.py',
            '--root', '/run', '--model-source', '/model', '--banks-dir', '/ref', '--code-commit', CODE_COMMIT])
        write(root / 'RUN_SUCCESS.json', dict(status='PASS', started_utc=started, finished_utc=utc(),
            wall_s=time.monotonic() - start, production_wall_s=production_wall, production=production, finish=finish))
    except Exception:
        write(root / 'RUN_FAILURE.json', dict(status='FAIL', started_utc=started, finished_utc=utc(),
            wall_s=time.monotonic() - start, traceback=traceback.format_exc()))
        raise
    finally:
        write(root / 'RESOURCE_AFTER.json', snapshot(root))


if __name__ == '__main__':
    action, root_arg = sys.argv[1:]
    root = Path(root_arg).resolve()
    if root.parent != Path('/home/KMS') or not root.name.startswith('BLOCK_C_M7_NEAR_20261119_'):
        raise ValueError('Invalid run root: ' + str(root))
    if action == 'launch':
        with (root / 'logs/supervisor.log').open('x') as log:
            process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'execute', str(root)],
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        write(root / 'SUPERVISOR.json', dict(pid=process.pid, run_id=root.name, started_utc=utc(), command=process.args))
        print(root, process.pid)
    elif action == 'execute':
        execute(root)
    else:
        raise ValueError('Invalid action: ' + action)
