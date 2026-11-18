"""Prepare and supervise interior stations with original M7 RT settings.

Only 104 interior positions are authorized here. Host Python 3.6 compatible.
"""
import argparse
import concurrent.futures
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

from blockc_centerline_host import (FFD, IMAGE, REFERENCE, SOURCE, read,
                                    run_container, sha, snapshot, utc, write)

PREVIOUS = Path('/home/KMS/BLOCK_C_CENTERLINE_M7_20261118_dhdj70s5')
FAR_PREVIOUS = Path('/home/KMS/BLOCK_C_M7_FAR_P1_20261118_927et1yb')
Y_ROWS = [-0.45, -0.30, 0.30, 0.45]


def verify_prior_stations(inputs, contract):
    if sha(inputs / 'STATIONS.json') != contract['input_sha256']['STATIONS.json']:
        raise ValueError('Previous station table checksum differs: ' + str(inputs))


def prepare(root, commit):
    inputs = root / 'inputs'
    if any(inputs.iterdir()):
        raise ValueError('Inputs must be empty')
    previous = PREVIOUS / 'inputs'
    prior = read(previous / 'RUN_CONTRACT.json')
    reference = read(REFERENCE)
    for name, digest in list(FFD.items()) + list(reference['method_b_sha256'].items()):
        if sha(SOURCE / name) != digest:
            raise ValueError('Original source or FFD checksum differs: ' + name)
    original_config = SOURCE / 'results/SIONNA_NATIVE41_REFRESH_20260925_01a0d84e/CONFIG.json'
    if read(original_config)['solver'] != read(previous / 'M7_RT_CONFIG.json')['solver']:
        raise ValueError('Full original solver settings differ')
    for name in ('SCENE_ENTRY.json', 'M7_RT_CONFIG.json', 'ORIGINAL_BLOCK_C_CASES.json'):
        if sha(previous / name) != prior['input_sha256'][name]:
            raise ValueError('Previous frozen input checksum differs: ' + name)
        shutil.copyfile(str(previous / name), str(inputs / name))
    shutil.copytree(str(previous / 'scene'), str(inputs / 'scene'))
    shutil.copytree(str(previous / 'baselines'), str(inputs / 'baselines'))
    for name, digest in prior['input_sha256'].items():
        if name.startswith(('scene/', 'baselines/')) and sha(inputs / name) != digest:
            raise ValueError('Frozen mesh or original baseline table differs: ' + name)
    for item in prior['baselines']:
        if sha(Path(item['original_H_path'])) != item['original_H_sha256']:
            raise ValueError('Original baseline H differs: ' + item['route'])
    verify_prior_stations(previous, prior)
    original_stations = read(previous / 'STATIONS.json')
    original_x = [station['x'] for station in original_stations]
    expected_original_x = [(120+45*i)/100.0 for i in range(40)]
    expected_x = [(435+45*i)/100.0 for i in range(26)]
    xs = [x for x in original_x if 4.35 <= x <= 15.60]
    if original_x != expected_original_x or xs != expected_x:
        raise ValueError('Expected precisely the original 26 interior x stations')
    far_inputs = FAR_PREVIOUS / 'inputs'
    far_contract = read(far_inputs / 'RUN_CONTRACT.json')
    verify_prior_stations(far_inputs, far_contract)
    far_stations = read(far_inputs / 'STATIONS.json')
    far_positions = set((station['x'], station['y']) for station in far_stations)
    far_x = sorted(set(station['x'] for station in far_stations))
    expected_far_x = [x for x in expected_original_x if x not in expected_x]
    mid_positions = set((x,y) for x in xs for y in Y_ROWS)
    if (far_x != expected_far_x
            or far_positions != set((x,y) for x in expected_far_x for y in Y_ROWS)
            or len(far_stations) != len(far_positions)
            or far_positions.intersection(mid_positions)
            or set(far_x).intersection(xs)
            or sorted(far_x+xs) != expected_original_x):
        raise ValueError('Original x stations must partition completely with no far/interior overlap')
    poses, tasks, stations, samples = [], [], [], []
    for x in xs:
        for y in Y_ROWS:
            task_id, station_id = len(tasks), 'MP%03d' % (len(tasks)+1)
            ids = list(range(len(poses), len(poses)+36))
            for pose_id, yaw in zip(ids, range(-180, 180, 10)):
                poses.append(dict(pose_id=pose_id, x=x, y=y, yaw_body_deg=yaw))
            tasks.append(dict(task_id=task_id, tag=station_id, x=x, y=y, pose_ids=ids,
                              antenna_yaw_deg=list(range(-180, 180, 10))))
            stations.append(dict(station_id=station_id, station_index=task_id,
                                 x=x, y=y, z=0.45, side='left' if x < 10 else 'right'))
            for j, yaw in enumerate(range(-180, 181, 10)):
                samples.append(dict(set='BLOCKC_MID', station_id=station_id,
                    sequence_index=len(samples), station_sequence_index=j, protocol='full360_10deg',
                    planned_rel_deg=yaw, achieved_rel_deg=yaw, pose_id=ids[j % 36], x=x, y=y,
                    yaw_body_deg=poses[ids[j % 36]]['yaw_body_deg']))
    checks = dict(positions=len(stations), unique_rf_poses=len(poses), observation_rows=len(samples),
        x_values=xs, y_values=Y_ROWS, no_centerline_rows=all(p['y'] != 0 for p in poses),
        position_duplicates=len(stations)-len(set((s['x'], s['y']) for s in stations)),
        physical_pose_duplicates=len(poses)-len(set((p['x'], p['y'], p['yaw_body_deg']) for p in poses)),
        endpoints_reuse_same_pose=all(samples[i*37]['pose_id']==samples[i*37+36]['pose_id'] for i in range(104)),
        minimum_rotated_body_wall_clearance_m=1.2-0.45-((0.281/2)**2+(0.306/2)**2)**0.5,
        overlap_with_previous_far_positions=len(mid_positions.intersection(far_positions)),
        original_x_partition_complete=sorted(far_x+xs)==expected_original_x,
        complete_cartesian_grid=set((s['x'], s['y']) for s in stations)==set((x,y) for x in xs for y in Y_ROWS))
    if (len(stations),len(poses),len(samples)) != (104,3744,3848):
        raise ValueError('Interior coverage differs')
    if (checks['position_duplicates'] or checks['physical_pose_duplicates']
            or not checks['complete_cartesian_grid'] or not checks['endpoints_reuse_same_pose']
            or checks['minimum_rotated_body_wall_clearance_m'] < 0.05):
        raise ValueError('Pose integrity or geometry check failed')
    for name, data in [('rf_poses.json', poses), ('rf_tasks.json', tasks),
                       ('STATIONS.json', stations), ('SAMPLES.json', samples),
                       ('INPUT_VALIDATION.json', dict(status='PASS', checks=checks))]:
        write(inputs / name, data)
    with (inputs / 'TIMELINE.csv').open('x', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(samples[0]))
        writer.writeheader()
        writer.writerows(samples)
    contract = dict(question_id='BLOCK-C-M7-MID-SWEEP-001', created_utc=utc(), code_commit=commit,
        source_commit=prior['source_commit'], method_b_commit=prior['method_b_commit'],
        method_b_sha256=prior['method_b_sha256'], ffd_sha256=prior['ffd_sha256'],
        runtime_image=IMAGE, production='M7_ORIGINAL', baselines=prior['baselines'],
        source_solver_config=prior['source_solver_config'], governance=prior['governance'],
        geometry='BLOCK_C', anchor='B', anchor_xyz_m=[10,0,2.65], receiver_z_m=0.45, mount_deg=0,
        expected_positions=104, expected_poses=3744, expected_observations=3848, shard_count=4,
        x_values_m=xs, y_values_m=Y_ROWS, x_spacing_within_side_m=0.45,
        unique_yaw_deg=list(range(-180,180,10)), observation_yaw_deg=list(range(-180,181,10)),
        heading_frame='absolute world yaw in degrees',
        endpoint_rule='-180 and +180 observations share one RF pose_id', clean_h=True,
        thermal_noise='not added; repeated endpoint is not an independent spatial sample',
        previous_M7_centerline_preserved=str(PREVIOUS),
        previous_M7_far_preserved=str(FAR_PREVIOUS),
        previous_far_stations_sha256=sha(far_inputs/'STATIONS.json'),
        previous_config_sha256=sha(previous/'M7_RT_CONFIG.json'),
        difference_from_M7_original='new interior position/yaw plan only; unchanged original RT pipeline',
        scope='104 interior positions only; existing data and FAIL records and G-T2/G-V seals preserved; no x=1.0 endpoint, dense or +/-0.15 rows, heading error or c0 analysis',
        statistical_claim_boundary='spatial independence and c0 precision targets are user hypotheses; not evaluated by this generation',
        stop_rule='original baseline parity before generation; stop after 104 positions and G4/G8 integrity validation',
        current_code_sha256={p.name:sha(p) for p in sorted((root/'code').glob('*.py'))},
        input_sha256={p.relative_to(inputs).as_posix():sha(p) for p in sorted(inputs.rglob('*')) if p.is_file()})
    write(inputs/'RUN_CONTRACT.json',contract)
    write(root/'RESOURCE_BEFORE.json',snapshot(root))
    print(json.dumps(dict(status='PREPARED',root=str(root),checks=checks)))


def execute(root, commit):
    started, before = utc(), time.monotonic()
    try:
        contract = read(root/'inputs/RUN_CONTRACT.json')
        if commit != contract['code_commit']:
            raise ValueError('Code commit differs from prepared contract')
        base=['/run/code/run_blockc_m7_sweep.py','--inputs','/run/inputs','--source','/ref',
              '--code-commit',commit,'--source-commit',contract['source_commit']]
        (root/'baseline').mkdir(mode=0o700)
        bstart=time.monotonic()
        def run_baseline(item):
            route=item['route']
            original_h='/ref/'+Path(item['original_H_path']).relative_to(SOURCE).as_posix()
            return run_container(root,'baseline_'+route,base+['--out','/run/baseline/'+route,
                '--poses','/run/inputs/baselines/'+route+'/rf_poses.json',
                '--tasks','/run/inputs/baselines/'+route+'/rf_tasks.json','--baseline-H',original_h,
                '--baseline-pose-ids']+[str(i) for i in item['original_pose_ids']])
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            baseline_receipts=list(pool.map(run_baseline,contract['baselines']))
        manifests={}
        for item in contract['baselines']:
            route=item['route'];path=root/'baseline'/route/'MANIFEST.json'
            manifest=read(path);comparison=manifest['baseline_comparison']
            if (manifest['status']!='PASS' or not comparison['array_equal']
                    or comparison['max_abs_delta_h']!=0
                    or comparison['H_sha256']!=item['original_H_sha256']
                    or comparison['pose_ids']!=item['original_pose_ids']):
                raise ValueError('Original baseline compatibility failed: '+route)
            manifests[route]=sha(path)
        write(root/'BASELINE_PASS.json',dict(status='PASS',routes=['R2','R4','R5'],
            manifest_sha256=manifests,poses=9,complex_coefficients=9252,max_abs_delta_h=0,
            wall_s=time.monotonic()-bstart,receipts=baseline_receipts))
        (root/'attempts/production').mkdir(parents=True,mode=0o700)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures=[pool.submit(run_container,root,'shard%d'%i,base+
                ['--out','/run/attempts/production/shard%d'%i,'--shard-index',str(i),
                 '--shard-count','4']) for i in range(4)]
            production=[future.result() for future in futures]
        finish=run_container(root,'finish',['/run/code/finish_blockc_m7_far_sweep.py',
            '--root','/run','--model-source','/model','--banks-dir','/ref','--code-commit',commit])
        write(root/'RUN_SUCCESS.json',dict(status='PASS',started_utc=started,finished_utc=utc(),
            wall_s=time.monotonic()-before,production=production,finish=finish))
    except Exception:
        write(root/'RUN_FAILURE.json',dict(status='FAIL',started_utc=started,finished_utc=utc(),
            wall_s=time.monotonic()-before,traceback=traceback.format_exc()))
        raise
    finally:
        write(root/'RESOURCE_AFTER.json',snapshot(root))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','execute','launch'])
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--code-commit',required=True)
    args=parser.parse_args()
    if args.root.resolve().parent!=Path('/home/KMS') or not args.root.name.startswith('BLOCK_C_M7_MID_'):
        raise ValueError('Unexpected run root')
    if args.action=='prepare':prepare(args.root,args.code_commit)
    elif args.action=='execute':execute(args.root,args.code_commit)
    else:
        with (args.root/'logs/supervisor.log').open('x') as log:
            process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'execute',
                '--root',str(args.root),'--code-commit',args.code_commit],stdout=log,
                stderr=subprocess.STDOUT,start_new_session=True)
        write(args.root/'SUPERVISOR.json',dict(pid=process.pid,root=str(args.root),started_utc=utc()))
        print(json.dumps(dict(pid=process.pid,root=str(args.root))))


if __name__=='__main__':main()
