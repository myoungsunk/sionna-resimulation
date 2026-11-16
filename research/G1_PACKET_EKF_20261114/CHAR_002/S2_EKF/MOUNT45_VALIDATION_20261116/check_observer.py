"""Check the mount-45 B/B0 packet grid and the SourceFFD observation on that grid."""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import platform
import subprocess
import sys

import numpy as np


OUT = Path(__file__).resolve().parent
WORK = OUT.parents[1]
PACKET_ROOT = WORK / 'artifacts/G1_CHAR002_S2_MOUNT45_20261116'
REPO = WORK / 'g1_mount45_b0_publication_20261116'
COMMIT = '5b044c43b0c5a3a201e80ecb957bbee5addc8cdd'
GOV = Path('C:/Users/Myoungsun Kim/.codex/research-governance')
sys.path.insert(0, str(PACKET_ROOT))
import prepare_mount45 as source

ROUTES = tuple(source.ROWS)
LIMITS = {'branch_fixed_normalized_derivative': 1e-6, 'yaw_equivalence_abs': 1e-12,
          'los_s_p90_abs': .005, 'los_tap_mismatches': 0, 'e0_h_normalized': source.TOL}
STEPS = (1e-5, 3e-6, 1e-6, 3e-7)
COMPONENTS = ('x_m', 'y_m', 'heading_rad', 'gyro_bias_rad_s')
PUBLISHED = 'research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/MOUNT45_B0_20261116'
RECEIPT = OUT / 'OBSERVER_CONTRACT.json'


def freeze():
    inputs = {}
    paths = [PACKET_ROOT / name for name in ('RUN_CONTRACT.json', 'PARITY_RESULTS.json', 'CALIBRATION_PARITY.json', 'CALIBRATION_MODEL_LOCK.json')]
    prior = source.load(paths[0])['inputs_sha256']
    for route in ROUTES:
        paths.extend(PACKET_ROOT / f'{source.stem(route)}__{kind}.npz' for kind in ('online', 'evaluator', 'e0_trace'))
        paths.extend(source.MANIFEST / f'H_{route}_aB_{mount}.manifest.json' for mount in ('m0', 'm45'))
        paths.append(source.BLOCK / 'FULL_RF' / f'H_{route}_aB_m0.npy')
        paths.extend(Path(path) for path in prior if any(token in Path(path).name for token in
                     (f'{route}_aB_m45', f'rf_poses_{route}', f'{route}_B0_Full_10')))
    for name in ('RUN_CONTRACT.json', 'PARITY_RESULTS.json'):
        git = subprocess.check_output(['git', '-c', 'gc.auto=0', '-C', str(REPO), 'show', f'{COMMIT}:{PUBLISHED}/{name}'])
        assert hashlib.sha256(git).hexdigest() == source.sha(PACKET_ROOT / name)
    for path in paths:
        digest = source.sha(path)
        assert str(path) not in prior or prior[str(path)] == digest, path
        inputs[str(path)] = digest
    source.write(RECEIPT, {
        'question': 'G1-CHAR002-S2-MOUNT45/CHECKLIST-01', 'role': 'IMPLEMENTER', 'frozen_utc': source.utc(),
        'publication_commit': COMMIT, 'branch': 'research/g1-sweep-heading-floor-spec-20261113',
        'governance': {name: source.sha(GOV / name) for name in ('COMMON_CONTRACT.md', 'ROLE_IMPLEMENTER.md')},
        'scope': {'routes': list(ROUTES), 'anchor': 'B', 'bias': 'B0', 'seed': 10, 'mount_deg': 45},
        'limits': LIMITS, 'fd_steps_m_rad': list(STEPS),
        'fd_rule': 'Centered derivative at the largest declared step with center, endpoints and half-step points on the same FFD cell, O30 tap and strongest-port branch. Report all exceptions. State 4 has zero direct sensitivity.',
        'los_rule': 'P0 style native tap equality plus G4 P90(abs(sFFDbatch-sLoS)) <= 0.005. The archived LoS itself is used only for this verification.',
        'paired_rf_rule': 'Legacy BLOCK_C m0 and V01B m45 must match their manifest hashes, same raw pose grid and shared RT traces with only --mount and --out changed. Claim is restricted to those paired legacy traces.',
        'inputs': inputs, 'code_sha256': source.sha(Path(__file__)),
    })


def same_branch(center, other):
    return ((center['tap'] == other['tap']) & (center['strong_port'] == other['strong_port'])
            & np.all(center['cells'] == other['cells'], axis=1))


def fd_batch(model, x, spec):
    _, jac, center = model.batch(x, spec, return_diagnostics=True)
    fd = np.full_like(jac, np.nan)
    used_step = np.zeros((len(x), 4))
    initial = np.zeros((len(x), 4), bool)
    for j in range(4):
        todo = np.arange(len(x))
        for i, eps in enumerate(STEPS):
            if not len(todo):
                break
            base = {key: value[todo] for key, value in center.items()}
            offsets = np.zeros((4, 4))
            offsets[:, j] = np.array([eps, -eps, eps / 2, -eps / 2])
            ends = [model.batch(x[todo] + off, spec, gradient=False, return_diagnostics=True) for off in offsets]
            stable = np.logical_and.reduce([same_branch(base, data[2]) for data in ends])
            if i == 0:
                initial[todo[~stable], j] = True
            active = todo[stable]
            fd[active, :, j] = (ends[0][0][stable] - ends[1][0][stable]) / (2 * eps)
            used_step[active, j] = eps
            todo = todo[~stable]
    return jac, fd, used_step, initial


def report_route(route, observation, model, frozen):
    parity = source.load(PACKET_ROOT / 'PARITY_RESULTS.json')['routes'][route]
    roles = ('online', 'evaluator', 'e0_trace')
    paths = [PACKET_ROOT / f'{source.stem(route)}__{kind}.npz' for kind in roles]
    for path in paths:
        source.checked(path, parity['output_sha256'][path.name])
    packet, evaluator, e0 = map(source.npz, paths)
    m0 = source.release_packet(route, 'online')
    m0_ev = source.release_packet(route, 'evaluator')
    assert all(np.array_equal(packet[k], other[k]) for other in (m0, evaluator, e0) for k in ('t', 'pose_id'))
    assert all(np.array_equal(packet[k], m0[k]) for k in ('x0', 'P0', 'ds', 'gy', 'dt'))
    assert np.array_equal(evaluator['truth'], m0_ev['truth'])
    ids = packet['pose_id']
    identities = [source.load(source.MANIFEST / f'H_{route}_aB_{m}.manifest.json') for m in ('m0', 'm45')]
    manifest0, manifest45 = identities
    assert manifest0['inputs'] == manifest45['inputs']
    assert manifest0['command'][:5] == manifest45['command'][:5]
    assert manifest0['config']['mount_deg'] == 0 and manifest45['config']['mount_deg'] == 45
    assert all(m['command'][5] == '--mount' and float(m['command'][6]) == m['config']['mount_deg']
               and m['command'][7] == '--out' and len(m['command']) == 9 for m in identities)
    actual_m0_hash = frozen['inputs'][str(source.BLOCK / 'FULL_RF' / f'H_{route}_aB_m0.npy')]
    full45 = source.FULL / f'H_{route}_aB_m45.npy'
    los45 = source.LOS / f'H_LoS_{route}_aB_m45.npy'
    assert actual_m0_hash == manifest0['outputs'][0]['sha256']
    assert np.array_equal(packet['Hrf'], np.load(full45, mmap_mode='r', allow_pickle=False)[ids, :, :, 0])
    assert np.array_equal(evaluator['clean_H'], np.load(los45, mmap_mode='r', allow_pickle=False)[ids, :, :, 0])
    h_input = source.load(source.BLOCK / 'INPUTS' / f'rf_poses_{route}.json')
    x_eval = np.array([[h_input[i]['x'], h_input[i]['y'], np.radians(h_input[i]['yaw_body_deg']), 0.] for i in ids])
    selected, offset, q0, archived = [], [], [], []
    for begin in range(0, len(ids), 64):
        x = x_eval[begin:begin + 64]
        h45, _, diag = model.batch(x, source.SPEC, gradient=False, return_diagnostics=True)
        yaw45 = x.copy()
        yaw45[:, 2] += np.radians(45.)
        zero = {**source.SPEC, 'mount_deg': 0.}
        h_offset, _ = model.batch(yaw45, zero, gradient=False)
        h_zero, _ = model.batch(x, zero, gradient=False)
        los_h = evaluator['clean_H'][begin:begin + len(x)]
        tap = observation.first_path_batch(observation.cir_batch(los_h), model.freqs[1] - model.freqs[0])
        selected.append(np.column_stack((h45[:, 1], diag['tap'])))
        offset.append(np.max(np.abs(h45 - h_offset), axis=1))
        q0.append(h_zero[:, 1])
        archived.append(np.column_stack((tap['s'], tap['index'])))
    pred, got = np.vstack(selected), np.vstack(archived)
    los_delta = np.abs(pred[:, 0] - got[:, 0])
    los_summary = {'p90_abs_s': float(np.quantile(los_delta, .9)), 'max_abs_s': float(los_delta.max()),
                   'rmse_s': float(np.sqrt(np.mean(los_delta**2))), 'tap_mismatches': int((pred[:, 1] != got[:, 1]).sum()),
                   'm0_counterfactual_rmse_s': float(np.sqrt(np.mean((np.concatenate(q0) - got[:, 0])**2))),
                   'yaw_equivalence_max_abs': float(np.max(np.concatenate(offset)))}
    jac, diff, step, initial = [np.concatenate(blocks) for blocks in zip(*(
        fd_batch(model, e0['prior'][start:start + 48], source.SPEC) for start in range(0, len(ids), 48)))]
    e0_difference = float(np.max(np.abs(jac - e0['H']) / np.maximum(1., np.abs(e0['H']))))
    absolute = np.abs(diff - jac)
    normalized = absolute / np.maximum(1., np.abs(jac))
    fd_summary = {}
    for j, name in enumerate(COMPONENTS):
        valid = step[:, j] > 0
        assert valid.any()
        worst = np.unravel_index(np.nanargmax(normalized[:, :, j]), normalized.shape[:2])
        fd_summary[name] = {'checked': int(valid.sum()), 'initial_boundary': int(initial[:, j].sum()),
                            'unresolved_boundary_pose_ids': ids[~valid].tolist(),
                            'max_abs': float(np.nanmax(absolute[:, :, j])), 'max_normalized': float(normalized[worst[0], worst[1], j]),
                            'worst_pose_id': int(ids[worst[0]]), 'worst_channel': ('r', 's')[worst[1]],
                            'exceedances': int(np.count_nonzero(normalized[:, :, j] > LIMITS['branch_fixed_normalized_derivative']))}
    source.save_npz(OUT / f'{route}_observer_evidence.npz', {'pose_id': ids, 'prior': e0['prior'],
        'analytic': jac, 'numeric': diff, 'fd_step': step, 'initial_boundary': initial,
        'los_prediction_s_tap': pred, 'los_archived_s_tap': got})
    passed = (los_summary['p90_abs_s'] <= LIMITS['los_s_p90_abs']
              and los_summary['tap_mismatches'] <= LIMITS['los_tap_mismatches']
              and los_summary['yaw_equivalence_max_abs'] <= LIMITS['yaw_equivalence_abs']
              and e0_difference <= LIMITS['e0_h_normalized']
              and all(row['exceedances'] == 0 for row in fd_summary.values()))
    return {'status': 'PASS' if passed else 'FAIL', 'rows': len(ids), 'LoS': los_summary, 'FD': fd_summary,
            'e0_h_max_normalized': e0_difference,
            'paired_legacy_trace': manifest0['command'][4], 'evidence_sha256': source.sha(OUT / f'{route}_observer_evidence.npz')}


def run():
    frozen = source.load(RECEIPT)
    assert frozen['code_sha256'] == source.sha(Path(__file__))
    for path, expected in frozen['inputs'].items():
        source.checked(Path(path), expected)
    sys.path.insert(0, str(source.NATIVE / 'src'))
    from qclean_uwb.drivesim import observation
    from qclean_uwb.fp_sc.e0_baseline import load_original_model
    _, _, model, native = load_original_model(source.NATIVE)
    started = datetime.now(timezone.utc).isoformat()
    results = {}
    for route in ROUTES:
        results[route] = report_route(route, observation, model, frozen)
        print(route, results[route]['status'], results[route]['LoS'], flush=True)
    result = {'status': 'PASS' if all(v['status'] == 'PASS' for v in results.values()) else 'FAIL',
              'contract_sha256': source.sha(RECEIPT), 'command': [sys.executable, *sys.argv],
              'started_utc': started, 'finished_utc': source.utc(), 'numpy': np.__version__,
              'python': platform.python_version(), 'native_sha256': native, 'routes': results}
    source.write(OUT / 'OBSERVER_RESULTS.json', result)
    if result['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=('freeze', 'run'))
    {'freeze': freeze, 'run': run}[parser.parse_args().stage]()
