"""Supervise an additive BLOCK_C sweep with the frozen original M7 runtime.

Host Python 3.6 compatible; all numerical work runs in the pinned RT image.
"""
import argparse
import concurrent.futures
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

from blockc_centerline_host import (FFD, IMAGE, REFERENCE, SOURCE, read,
                                    run_container, sha, snapshot, utc, write)

PREVIOUS = Path('/home/KMS/BLOCK_C_CENTERLINE_SWEEP_20261117T0956Z_OT9sPHzh')
H_SHA = {
    'R2': 'b3b4c61e23286b86c78b6e87f5b9b5358121cbde7717bae73e5650cc900b546c',
    'R4': '30743ca017615bbfede78a8350739262a756d47ac2213c60b08eb109cebfe1b0',
    'R5': 'a4858372414f81156b25fde2e14d57fc0e1a3f987782a5b268dbdf14bcf174b3',
}


def prepare(root, commit):
    inputs = root / 'inputs'
    if any(inputs.iterdir()):
        raise ValueError('Inputs must be empty')
    previous = PREVIOUS / 'inputs'
    plan_names = ('SCENE_ENTRY.json', 'rf_poses.json', 'rf_tasks.json', 'STATIONS.json',
                  'SAMPLES.json', 'TIMELINE.csv', 'INPUT_VALIDATION.json', 'ORIGINAL_BLOCK_C_CASES.json')
    for name in plan_names:
        shutil.copyfile(str(previous / name), str(inputs / name))
    shutil.copytree(str(previous / 'scene'), str(inputs / 'scene'))
    reference = read(REFERENCE)
    source_config = SOURCE / 'results/SIONNA_NATIVE41_REFRESH_20260925_01a0d84e/CONFIG.json'
    solver = read(source_config)['solver']
    if solver != reference['block_c_solver']:
        raise ValueError('Original solver config and frozen reference differ')
    for name, digest in list(FFD.items()) + list(reference['method_b_sha256'].items()):
        if sha(SOURCE / name) != digest:
            raise ValueError('Original source or FFD checksum differs: ' + name)
    config = dict(solver=solver, base_node_bins=list(range(0, 257, 16)),
                  node_policy='unchanged original rf_b_trace.trace_position adaptive boundary bisection',
                  finite_face_guard=False, native_los_override=False, post_filter=False,
                  H_full_synthesis='unchanged original rf_store.h_for_antenna_yaws',
                  H_LoS_definition='LoS contribution extracted from the same full original trace')
    write(inputs / 'M7_RT_CONFIG.json', config)
    baseline_dir = inputs / 'baselines'
    baseline_dir.mkdir(mode=0o700)
    baselines = []
    routes = SOURCE / 'results/DRIVE_SIM_20261007/S1/routes'
    full_h = SOURCE / 'results/DRIVE_SIM_20261007/SNOWBALL_ROUTES_01a11669/S2'
    for route in ('R2', 'R4', 'R5'):
        poses_path = routes / ('rf_poses_' + route + '.json')
        tasks_path = routes / ('rf_tasks_' + route + '_m0.json')
        all_poses, all_tasks = read(poses_path), read(tasks_path)
        if [p['pose_id'] for p in all_poses] != list(range(len(all_poses))):
            raise ValueError('Original pose IDs are not original H row indices')
        original_ids = [0, len(all_poses)//2, len(all_poses)-1]
        poses, tasks = [], []
        for new_id, original_id in enumerate(original_ids):
            p = copy.deepcopy(all_poses[original_id])
            p['pose_id'] = new_id
            poses.append(p)
            original_task = next(t for t in all_tasks if original_id in t['pose_ids'])
            tasks.append(dict(task_id=new_id, tag=original_task['tag'], x=p['x'], y=p['y'],
                              pose_ids=[new_id], antenna_yaw_deg=[p['yaw_body_deg']]))
        directory = baseline_dir / route
        directory.mkdir(mode=0o700)
        write(directory / 'rf_poses.json', poses)
        write(directory / 'rf_tasks.json', tasks)
        h_path = full_h / ('H_' + route + '_aB_m0.npy')
        if sha(h_path) != H_SHA[route]:
            raise ValueError('Original H checksum differs: ' + route)
        baselines.append(dict(route=route, original_pose_ids=original_ids,
                              original_H_path=str(h_path), original_H_sha256=H_SHA[route],
                              original_poses_path=str(poses_path), original_poses_sha256=sha(poses_path),
                              original_tasks_path=str(tasks_path), original_tasks_sha256=sha(tasks_path)))
    old = read(previous / 'RUN_CONTRACT.json')
    contract = dict(old)
    contract.update(question_id='BLOCK-C-CENTERLINE-SWEEP-M7-001', created_utc=utc(), code_commit=commit,
                    source_commit=reference['method_b_commit'], production='M7_ORIGINAL',
                    difference_from_M7_original='new exact-centerline station/yaw plan only; unchanged original full RT pipeline',
                    method_b_commit=reference['method_b_commit'], method_b_sha256=reference['method_b_sha256'],
                    ffd_sha256=FFD, runtime_image=IMAGE, baselines=baselines,
                    source_solver_config=dict(path=str(source_config), sha256=sha(source_config)),
                    previous_F1_run_preserved=str(PREVIOUS),
                    previous_pose_plan_sha256={name: sha(previous / name) for name in plan_names},
                    current_code_sha256={p.name: sha(p) for p in sorted((root / 'code').glob('*.py'))},
                    input_sha256={p.relative_to(inputs).as_posix(): sha(p)
                                  for p in sorted(inputs.rglob('*')) if p.is_file()},
                    stop_rule='all three original-route baseline controls must pass array_equal before new-station generation')
    write(inputs / 'RUN_CONTRACT.json', contract)
    write(root / 'RESOURCE_BEFORE.json', snapshot(root))
    print(json.dumps(dict(status='PREPARED', root=str(root), baselines=baselines,
                          stations=40, unique_poses=1440, observations=1480)))


def execute(root, commit):
    started, before = utc(), time.monotonic()
    try:
        contract = read(root / 'inputs/RUN_CONTRACT.json')
        if commit != contract['code_commit']:
            raise ValueError('Code commit differs from prepared contract')
        base = ['/run/code/run_blockc_m7_sweep.py', '--inputs', '/run/inputs',
                '--source', '/ref', '--code-commit', commit, '--source-commit', contract['source_commit']]
        (root / 'baseline').mkdir(mode=0o700)
        bstart = time.monotonic()
        def run_baseline(item):
            route = item['route']
            original_h = '/ref/' + Path(item['original_H_path']).relative_to(SOURCE).as_posix()
            return run_container(root, 'baseline_' + route, base +
                ['--out', '/run/baseline/' + route, '--poses', '/run/inputs/baselines/' + route + '/rf_poses.json',
                 '--tasks', '/run/inputs/baselines/' + route + '/rf_tasks.json', '--baseline-H', original_h,
                 '--baseline-pose-ids'] + [str(i) for i in item['original_pose_ids']])
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            receipts = list(pool.map(run_baseline, contract['baselines']))
        manifests = {}
        for item in contract['baselines']:
            route = item['route']
            path = root / 'baseline' / route / 'MANIFEST.json'
            manifest = read(path)
            comparison = manifest['baseline_comparison']
            if (manifest['status'] != 'PASS' or not comparison['array_equal']
                    or comparison['max_abs_delta_h'] != 0
                    or comparison['H_sha256'] != item['original_H_sha256']
                    or comparison['pose_ids'] != item['original_pose_ids']):
                raise ValueError('Original baseline compatibility failed: ' + route)
            manifests[route] = sha(path)
        write(root / 'BASELINE_PASS.json', dict(status='PASS', routes=['R2', 'R4', 'R5'],
                    manifest_sha256=manifests, poses=9, complex_coefficients=9*257*4,
                    max_abs_delta_h=0, wall_s=time.monotonic()-bstart, receipts=receipts))
        (root / 'attempts/production').mkdir(parents=True, mode=0o700)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(run_container, root, 'shard%d' % i,
                       base + ['--out', '/run/attempts/production/shard%d' % i,
                               '--shard-index', str(i), '--shard-count', '4']) for i in range(4)]
            production = [future.result() for future in futures]
        finish = run_container(root, 'finish', ['/run/code/finish_blockc_m7_sweep.py',
                    '--root', '/run', '--model-source', '/model', '--banks-dir', '/ref', '--code-commit', commit])
        write(root / 'RUN_SUCCESS.json', dict(status='PASS', started_utc=started, finished_utc=utc(),
                    wall_s=time.monotonic()-before, production=production, finish=finish))
    except Exception:
        write(root / 'RUN_FAILURE.json', dict(status='FAIL', started_utc=started, finished_utc=utc(),
                    wall_s=time.monotonic()-before, traceback=traceback.format_exc()))
        raise
    finally:
        write(root / 'RESOURCE_AFTER.json', snapshot(root))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'execute', 'launch'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--code-commit', required=True)
    args = parser.parse_args()
    if args.root.resolve().parent != Path('/home/KMS') or not args.root.name.startswith('BLOCK_C_CENTERLINE_M7_'):
        raise ValueError('Unexpected new run root')
    if args.action == 'prepare':
        prepare(args.root, args.code_commit)
    elif args.action == 'execute':
        execute(args.root, args.code_commit)
    else:
        with (args.root / 'logs/supervisor.log').open('x') as log:
            process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'execute',
                       '--root', str(args.root), '--code-commit', args.code_commit],
                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        write(args.root / 'SUPERVISOR.json', dict(pid=process.pid, root=str(args.root), started_utc=utc()))
        print(json.dumps(dict(pid=process.pid, root=str(args.root))))


if __name__ == '__main__':
    main()
