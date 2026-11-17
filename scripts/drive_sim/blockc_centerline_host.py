"""Prepare and supervise an additive, isolated BLOCK_C centerline RT run.

This host-side launcher intentionally uses only the Python 3.6 standard library.
RT and validation execute in the already qualified, pinned Docker image.
"""
import argparse
import concurrent.futures
import csv
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

IMAGE = 'sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f'
LEGACY = Path('/home/KMS/COOL_DIJKSTRA_20261007_01a11582/source')
SOURCE = Path('/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source')
RUNTIME = Path('/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages')
MODEL = Path('/home/KMS/RUN2_20261113T072631Z/inputs/results/DRIVE_SIM_20261007/CAUSE_CHECK_A23_EXECUTION_20261010/retrieved/source')
CASES = Path('/home/KMS/DRIVE_SIM_POST_A23_SUPPLEMENT_20261010_01a12449/BLOCK_C/CASES.json')
REFERENCE = Path('/home/KMS/G1_RT_TB3_FINITE_FACE_PRODUCTION_20261115T122037Z_HS1vMs/frozen/REFERENCE.json')
FFD = {'LP_plus45_bank.npz': 'b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b',
       'LP_minus45_bank.npz': '39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9'}


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1048576), b''):
            h.update(data)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, data):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write('\n')


def snapshot(root):
    mem = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        name, value = line.split(':', 1)
        if name in ('MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'):
            mem[name + '_KiB'] = int(value.split()[0])
    return dict(utc=utc(), user=os.getlogin() if os.isatty(0) else os.environ.get('USER'),
                cpu_count=os.cpu_count(), load_average=list(os.getloadavg()), memory=mem,
                run_disk=shutil.disk_usage(str(root))._asdict())


def prepare(root, commit):
    inputs = root / 'inputs'
    if any(inputs.iterdir()):
        raise ValueError('Inputs must be a new, empty directory')
    bindings = next(c['material_bindings'] for c in read(CASES) if c['case'] == 'R2_aB_m0')
    scene_dir = inputs / 'scene'
    scene_dir.mkdir(mode=0o700)
    copied = []
    for binding in bindings:
        name = binding['object'] + '.ply'
        candidates = LEGACY.glob('results/CORRIDOR_SCAN2_20261007/*/scene/' + name)
        original = next((p for p in candidates if sha(p) == binding['ply_sha256']), None)
        if original is None:
            raise ValueError('Cannot locate exact original mesh: ' + name)
        shutil.copyfile(str(original), str(scene_dir / name))
        item = dict(binding)
        item['ply'] = name
        copied.append(dict(path=str(original), sha256=sha(original)))
        binding['ply'] = name
    scene = dict(geometry='BLOCK_C', dimensions_m=[20.0, 2.4, 2.7],
                 anchors_xyz_m={'B': [10.0, 0.0, 2.65]}, rx_z_m=0.45,
                 material_bindings=bindings)
    poses, tasks, stations, samples = [], [], [], []
    for station in range(40):
        x, sid = (120 + 45 * station) / 100.0, 'P%03d' % (station + 1)
        ids = list(range(station * 36, (station + 1) * 36))
        for pid, yaw in zip(ids, range(-180, 180, 10)):
            poses.append(dict(pose_id=pid, x=x, y=0.0, yaw_body_deg=yaw))
        tasks.append(dict(task_id=station, tag=sid, x=x, y=0.0, pose_ids=ids,
                          antenna_yaw_deg=list(range(-180, 180, 10))))
        stations.append(dict(station_id=sid, station_index=station, x=x, y=0.0, z=0.45))
        for j, yaw in enumerate(range(-180, 181, 10)):
            samples.append(dict(set='BLOCKC_CENTERLINE', station_id=sid,
                                sequence_index=len(samples), station_sequence_index=j,
                                protocol='full360_10deg', planned_rel_deg=yaw,
                                achieved_rel_deg=yaw, pose_id=ids[j % 36],
                                x=x, y=0.0, yaw_body_deg=poses[ids[j % 36]]['yaw_body_deg']))
    for filename, data in [('SCENE_ENTRY.json', scene), ('rf_poses.json', poses),
                           ('rf_tasks.json', tasks), ('STATIONS.json', stations),
                           ('SAMPLES.json', samples)]:
        write(inputs / filename, data)
    with (inputs / 'TIMELINE.csv').open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(samples[0]))
        writer.writeheader()
        writer.writerows(samples)
    shutil.copyfile(str(root / 'config/PRODUCTION_F1.json'), str(inputs / 'PRODUCTION_F1.json'))
    shutil.copyfile(str(CASES), str(inputs / 'ORIGINAL_BLOCK_C_CASES.json'))
    ref = read(REFERENCE)
    for name, expected in list(FFD.items()) + list(ref['method_b_sha256'].items()):
        if sha(SOURCE / name) != expected:
            raise ValueError('Frozen source/bank mismatch: ' + name)
    checks = dict(stations=40, unique_rf_poses=len(poses), observation_rows=len(samples),
                  exact_centerline=all(p['y'] == 0 for p in poses),
                  physical_pose_duplicates=len(poses) - len(set((p['x'], p['y'], p['yaw_body_deg']) for p in poses)),
                  original_meshes_sha_match=all(sha(scene_dir / b['ply']) == b['ply_sha256'] for b in bindings),
                  endpoints_reuse_same_pose=all(samples[i*37]['pose_id'] == samples[i*37+36]['pose_id'] for i in range(40)),
                  station_lattice_error_m=max(abs(stations[i]['x'] - (1.2 + 0.45*i)) for i in range(40)),
                  minimum_rotated_body_wall_clearance_m=1.2 - ((0.281/2)**2 + (0.306/2)**2)**0.5)
    assert checks['exact_centerline'] and checks['original_meshes_sha_match']
    assert checks['physical_pose_duplicates'] == 0 and checks['endpoints_reuse_same_pose']
    assert checks['station_lattice_error_m'] < 1e-12
    write(inputs / 'INPUT_VALIDATION.json', dict(status='PASS', checks=checks))
    files = sorted(p for p in inputs.rglob('*') if p.is_file())
    contract = dict(question_id='BLOCK-C-CENTERLINE-SWEEP-001', created_utc=utc(), code_commit=commit,
                    geometry='BLOCK_C', anchor='B', anchor_xyz_m=[10.0, 0.0, 2.65],
                    x_start_m=1.20, x_end_m=18.75, station_spacing_m=0.45, y_m=0.0,
                    receiver_z_m=0.45, mount_deg=0, heading_frame='absolute world yaw in degrees',
                    unique_yaw_deg=list(range(-180, 180, 10)), observation_yaw_deg=list(range(-180, 181, 10)),
                    endpoint_rule='-180 and +180 observations share one RF pose_id',
                    clean_h=True, thermal_noise='not added; repeated endpoint is not an independent spatial sample',
                    production='adopted F1 plus pre-field finite-face guard',
                    difference_from_M7_original='refraction true -> false; finite-face guard enabled; new exact centerline poses',
                    source_cases=dict(path=str(CASES), sha256=sha(CASES)), original_mesh_sources=copied,
                    method_b_commit=ref['method_b_commit'], method_b_sha256=ref['method_b_sha256'],
                    ffd_sha256=FFD, runtime_image=IMAGE,
                    governance={'COMMON_CONTRACT_sha256': 'a5cca7d8a8d5f20f4a89ea9b6509da0b8d7506626aac4a47fa1d27891ff5ebdb',
                                'ROLE_IMPLEMENTER_sha256': '2380fb1fe7302870a6c2d825cc2e65a73e91138677e095b4e51db43ab9ea90da'},
                    scope='new BLOCK_C only; no heading estimation or sealed G-T2/G-V reads',
                    input_sha256={p.relative_to(inputs).as_posix(): sha(p) for p in files})
    write(inputs / 'RUN_CONTRACT.json', contract)
    write(root / 'RESOURCE_BEFORE.json', snapshot(root))
    print(json.dumps(dict(status='PREPARED', root=str(root), checks=checks)))


def run_container(root, label, program_args):
    name = 'blockc-' + root.name.split('_')[-1] + '-' + label
    cmd = ['docker', 'run', '--pull=never', '--network', 'none', '--rm', '--name', name,
           '--user', '1001:1001', '--cpus', '1', '--cpu-shares', '128',
           '--memory', '12g', '--memory-swap', '12g',
           '-v', str(root) + ':/run', '-v', str(root / 'code') + ':/run/code:ro',
           '-v', str(SOURCE) + ':/ref:ro', '-v', str(RUNTIME) + ':/runtime_packages:ro',
           '-v', str(MODEL) + ':/model:ro', '-w', '/ref']
    for env in ['HOME=/run/cache', 'TMPDIR=/run/scratch', 'PYTHONDONTWRITEBYTECODE=1',
                'OMP_NUM_THREADS=1', 'OPENBLAS_NUM_THREADS=1', 'MKL_NUM_THREADS=1',
                'PYTHONPATH=/run/code:/runtime_packages:/ref:/ref/src']:
        cmd += ['-e', env]
    cmd += ['--entrypoint', '/usr/bin/nice', IMAGE, '-n', '15', '/opt/rt-env/bin/python', '-u'] + program_args
    start = time.monotonic()
    started = utc()
    with (root / 'logs' / (label + '.log')).open('x') as log:
        result = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)
    receipt = dict(label=label, started_utc=started, finished_utc=utc(), wall_s=time.monotonic()-start,
                   exit_code=result.returncode, command=cmd)
    write(root / 'logs' / (label + '_receipt.json'), receipt)
    if result.returncode:
        raise RuntimeError(label + ' failed; see its preserved log')
    return receipt


def execute(root, commit):
    started, start = utc(), time.monotonic()
    try:
        base = ['/run/code/run_blockc_centerline_sweep.py', '--inputs', '/run/inputs',
                '--source', '/ref', '--code-commit', commit]
        pilot = run_container(root, 'pilot', base + ['--out', '/run/attempts/pilot',
                              '--task-id', '0', '--task-id', '20', '--task-id', '39'])
        if read(root / 'attempts/pilot/MANIFEST.json')['status'] != 'PASS':
            raise ValueError('Pilot manifest did not pass')
        write(root / 'PILOT_PASS.json', pilot)
        (root / 'attempts/production').mkdir(mode=0o700)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(run_container, root, 'shard%d' % i,
                       base + ['--out', '/run/attempts/production/shard%d' % i,
                               '--shard-index', str(i), '--shard-count', '4']) for i in range(4)]
            production = [f.result() for f in futures]
        finish = run_container(root, 'finish', ['/run/code/finish_blockc_centerline_sweep.py',
                    '--root', '/run', '--model-source', '/model', '--banks-dir', '/ref', '--code-commit', commit])
        write(root / 'RUN_SUCCESS.json', dict(status='PASS', started_utc=started, finished_utc=utc(),
                    wall_s=time.monotonic()-start, pilot=pilot, production=production, finish=finish))
    except Exception:
        write(root / 'RUN_FAILURE.json', dict(status='FAIL', started_utc=started, finished_utc=utc(),
                    wall_s=time.monotonic()-start, traceback=traceback.format_exc()))
        raise
    finally:
        write(root / 'RESOURCE_AFTER.json', snapshot(root))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'execute', 'launch'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--code-commit', required=True)
    args = parser.parse_args()
    if args.root.resolve().parent != Path('/home/KMS') or not args.root.name.startswith('BLOCK_C_CENTERLINE_SWEEP_'):
        raise ValueError('Unexpected run root')
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
