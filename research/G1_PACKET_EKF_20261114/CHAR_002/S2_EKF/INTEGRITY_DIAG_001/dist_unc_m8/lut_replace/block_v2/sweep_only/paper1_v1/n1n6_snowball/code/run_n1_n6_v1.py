"""Run the V1 filter laws on validated N1–N6 inputs and compare old runs first."""

import argparse
from concurrent.futures import ProcessPoolExecutor
import csv
import hashlib
import json
from multiprocessing import get_context
from pathlib import Path
import pickle
import sys
import time

import numpy as np
import pandas as pd


ROUTES = tuple(f'N{i}' for i in range(1, 7))
CONDITIONS = ('B0', 'L2_GYRO_ARW')
SEEDS = (*range(10, 30), *range(70, 90))
ARMS = ('H0', 'H1S', 'H2S-SWB', 'H2S-SWB-U0', 'H2')
OUTPUT = {}


def sha(path):
    with Path(path).open('rb') as handle:
        digest = hashlib.sha256()
        for block in iter(lambda: handle.read(1024*1024), b''):
            digest.update(block)
        return digest.hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')


def arrays(path):
    with np.load(path, allow_pickle=False) as archive:
        return {key: archive[key] for key in archive.files}


def setup(args):
    sys.path.insert(0, '/home/claude/m8')
    import common
    import m8_replay
    from run_m8s3 import ZERO_SB, sweep_packet
    from v1_common import E3, EXIST, bin3, rho_hat
    from rebuild_n1_n6_v1_swb import load_swb, swap_env

    root = args.root
    calibration = root / 'v1_calibration'
    parameters = calibration / 'attempt_02'
    cal = read(parameters / 'V1_CALIBRATION_REPORT.json')
    model_path = parameters / 'CAL_V1_REBUILT_CANDIDATE.pkl'
    tables_path = args.reference / 'CAL_V1_TABLES.json'
    if cal['status'] != 'PASS_TABLES' or cal['sha256']['v1_tables'] != sha(tables_path):
        raise ValueError('V1 calibration does not bind to the archived variance tables')
    with model_path.open('rb') as handle:
        g, rr, rs = pickle.load(handle)
    rr, rs = np.asarray(rr), np.asarray(rs)
    old_tables = read(tables_path)
    np.testing.assert_array_equal(rr, old_tables['Rrr'])
    np.testing.assert_array_equal(rs, old_tables['Rss'])
    swb, swb_provenance = load_swb(args.reference / 'sw_block_farst.py',
                                  Path('/home/claude/m8cal/SWEEP_FEATURES.csv.gz'),
                                  args.reference / 'V0_BLOCK_RSS.json')
    env = common.env()
    scorer, _, branch_metrics = common.scorers()
    sigma = common.PARAMS['R2']['sigma_b']
    if sigma != [.005]*5 or any(common.PARAMS[route]['sigma_b'] != sigma for route in ('R4', 'R5')):
        raise ValueError('Expected the same frozen D5 sigma_b for R2/R4/R5')
    OUTPUT.update(common=common, m8=m8_replay, sweep_packet=sweep_packet, zero=ZERO_SB, g=g,
                  rr=rr, rs=rs, edges=E3, features=EXIST, bin3=bin3, rho_hat=rho_hat,
                  env=env, env_swb=swap_env(env, swb), score=scorer, branch=branch_metrics, sigma=sigma,
                  provenance=dict(adapter_sha256=sha(__file__), calibration_sha256=sha(model_path),
                                  variance_table_sha256=sha(tables_path), swb=swb_provenance,
                                  native_source_hashes=env['native_source_hashes']))


def v1_replay(packet, truth, condition, features):
    base = OUTPUT
    r7, m8 = base['common'].R7, base['m8']
    bins = base['bin3'](base['rho_hat'](packet['z'][:, 0]))
    mu = base['g'].predict(features[base['features']])
    rr, rs = base['rr'][bins], base['rs'][bins]
    zero = np.zeros(len(mu))
    sweep = base['sweep_packet'](packet, mu, zero, rr, rs)
    uncorrected = base['sweep_packet'](packet, zero, zero, rr, rs)
    table = dict(edges=base['edges'].tolist(), c1=[0., 0., 0.], c0=base['rs'].tolist())
    reference = dict(condition=condition, rref_policy='own', sigma_rad=0., sigma_b=base['sigma'])
    swb = dict(table=table, sigma_b=base['zero'], condition=condition, **m8.ARM_MODES['F0'])
    traces = (
        r7.replay(packet, base['env'], 'H0', **reference),
        r7.replay(sweep, base['env'], 'H1', **dict(reference, sigma_b=base['zero'])),
        m8.replay_m8(sweep, base['env_swb'], 'F0', **swb),
        m8.replay_m8(uncorrected, base['env_swb'], 'F0', **swb),
        r7.replay(packet, base['env'], 'H2', **reference),
    )
    result = {}
    for arm, trace in zip(ARMS, traces):
        rows = np.asarray(base['score'](trace, truth))
        branch = base['branch'](trace, truth, packet['t'])
        heading = (trace['x'][:, 2] - truth[:, 2] + np.pi) % (2*np.pi) - np.pi
        result[arm] = dict(n=len(rows), sums=rows.sum(0).tolist(), mirror=int(branch['mirror_fail_count']),
                           hbias_deg=float(np.degrees(heading.mean())), accept=float(np.mean(trace['mask'])))
    return result


def summary(record):
    mean = np.array(record['sums']) / record['n']
    return dict(head=float(np.sqrt(mean[0])), xy=float(np.sqrt(mean[1])), nees3=float(mean[2]),
                pose95=float(mean[3]), xy95=float(mean[4]), head95=float(mean[5]), mirror=record['mirror'],
                hbias=record['hbias_deg'])


def preflight(args):
    setup(args)
    reference_hashes = {
        'OBSERVATION_FEATURES_LABELS.csv.gz': '6a69a36ad0f521e33a130a1bc1fbde5a4b7aae17ba62ec347ccc611fdd5c6fe4',
        'V1_PERSEED.csv': '100d542368f2e63e1cf20acfeec2dddd97513a7dd423943eecaab2e1e3d081b0',
        'R4_PERSEED.csv': '57ef446404024ba8ce78f2dbe2cdf44d1a51ff40027aaf97e8bee61340bbf5e8',
    }
    if any(sha(args.reference / name) != expected for name, expected in reference_hashes.items()):
        raise ValueError('Archived V1 metric or feature checksum differs')
    old = pd.read_csv(args.reference / 'OBSERVATION_FEATURES_LABELS.csv.gz')
    reference = pd.concat([pd.read_csv(args.reference / 'V1_PERSEED.csv'),
                           pd.read_csv(args.reference / 'R4_PERSEED.csv').assign(grp='R4')])
    base = OUTPUT['common']
    checks = []
    for condition in CONDITIONS:
        for route in ('R2', 'R4', 'R5'):
            packet = base.packet(condition, 10, route)
            selected = old[(old.case == f'{route}_aB_m0') & (old.channel == 'full')].set_index('pose_id').loc[packet['pose_id']]
            scored = v1_replay(packet, base.TRUTH[route]['truth'], condition, selected)
            for arm, result in scored.items():
                expected = reference[(reference.cond == condition) & (reference.seed == 10)
                                     & (reference.arm == arm) & (reference.grp == route)]
                if len(expected) != 1:
                    raise ValueError('Archived V1 metric row is missing or duplicated')
                deltas = {name: abs(float(value) - float(expected.iloc[0][name]))
                          for name, value in summary(result).items()}
                checks.append(dict(condition=condition, route=route, seed=10, arm=arm, absolute_deltas=deltas))
                print(json.dumps(checks[-1]), flush=True)
    passed = all(row['absolute_deltas']['mirror'] == 0 and max(row['absolute_deltas'].values()) <= 1e-8
                 for row in checks)
    write(args.output, dict(status='PASS' if passed else 'FAIL', tolerance=1e-8, checked=len(checks),
                           provenance=OUTPUT['provenance'], reference_sha256=reference_hashes, checks=checks))
    if not passed:
        raise ValueError('Reconstructed V1 failed archived-seed metric parity')


def filter_one(job):
    condition, seed = job
    start = time.monotonic()
    result = {}
    for route in ROUTES:
        rf, truth, features = OUTPUT['cases'][route]
        packet = arrays(OUTPUT['controls'] / condition / f'seed{seed}' / f'{route}_controls.npz')
        np.testing.assert_array_equal(packet['t'], rf['t'])
        np.testing.assert_array_equal(packet['pose_id'], rf['pose_id'])
        packet.update({key: rf[key] for key in ('z', 'muMB', 'muBASE', 'R', 'D')})
        result[route] = v1_replay(packet, truth, condition, features)
    directory = OUTPUT['directory'] / condition / f'seed{seed}'
    directory.mkdir(parents=True)
    write(directory / 'RES.json', result)
    return condition, seed, time.monotonic()-start


def execute(args):
    setup(args)
    preflight_report = read(args.preflight)
    if preflight_report['status'] != 'PASS' or preflight_report['provenance'] != OUTPUT['provenance']:
        raise ValueError('N1–N6 V1 preflight was not passed with these assets')
    if any(read(args.root / name)['status'] != 'PASS' for name in ('CIR_PASS.json', 'v1_controls/CONTROLS_REPORT.json')):
        raise ValueError('Missing CIR or controls PASS')
    features = pd.read_csv(args.root / 'cir_features/OBSERVATION_FEATURES.csv.gz')
    controls = args.root / 'v1_controls'
    cases = {}
    for route in ROUTES:
        name = f'{route}_aB_m0'
        rf = arrays(args.h2 / f'{name}.npz')
        evaluator = arrays(controls / f'{route}_evaluator.npz')
        for field in ('t', 'pose_id'):
            np.testing.assert_array_equal(rf[field], evaluator[field])
        rows = features[features.case == name].set_index('pose_id').loc[rf['pose_id']]
        np.testing.assert_allclose(rows[['range_m', 's_fp']], rf['z'], rtol=0, atol=1e-12)
        np.testing.assert_array_equal(rows['global_pose_id'], rf['global_pose_id'])
        cases[route] = (rf, evaluator['truth'], rows)
    args.output.mkdir(exist_ok=False)
    OUTPUT.update(cases=cases, controls=controls, directory=args.output)
    jobs = [(cond, seed) for cond in CONDITIONS for seed in SEEDS]
    start = time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=get_context('fork')) as pool:
        for condition, seed, seconds in pool.map(filter_one, jobs):
            print(json.dumps(dict(condition=condition, seed=seed, wall_s=seconds)), flush=True)
    with (args.output / 'V1_PERSEED.csv').open('x', encoding='utf-8', newline='') as handle:
        writer = None
        for condition, seed in jobs:
            result = read(args.output / condition / f'seed{seed}/RES.json')
            for route in ROUTES:
                for arm in ARMS:
                    record = dict(condition=condition, seed=seed, route=route, arm=arm, **summary(result[route][arm]))
                    if writer is None:
                        writer = csv.DictWriter(handle, fieldnames=list(record))
                        writer.writeheader()
                    writer.writerow(record)
    write(args.output / 'V1_REPLAY_REPORT.json', dict(status='PASS', replays=len(jobs)*len(ROUTES)*len(ARMS),
          wall_s=time.monotonic()-start, preflight_sha256=sha(args.preflight), provenance=OUTPUT['provenance'],
          controls_report_sha256=sha(controls/'CONTROLS_REPORT.json'),
          cir_report_sha256=sha(args.root/'cir_features/CIR_FEATURES_REPORT.json'),
          perseed_sha256=sha(args.output/'V1_PERSEED.csv')))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('preflight', 'execute'))
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--preflight', type=Path)
    parser.add_argument('--h2', type=Path)
    parser.add_argument('--workers', type=int, default=16)
    args = parser.parse_args()
    if args.action == 'preflight':
        preflight(args)
    else:
        if args.preflight is None or args.h2 is None:
            parser.error('execute requires --preflight and --h2')
        execute(args)


if __name__ == '__main__':
    main()
