"""Freeze sources, extract B/B0 O30 packets, and replay the original W0."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys

import numpy as np


OUT = Path(__file__).resolve().parent
WORK = OUT.parents[1]
ART = WORK / 'artifacts'
INPUT = ART / 'G1_CHAR002_S2_INPUTS_20261115'
NATIVE = INPUT / 'source_minimal/research/FP_SC_RECOVERY_R0_R5_20261107/R45_sources'
LOCK = INPUT / 'source_minimal/research/FP_NATIVE_B_CAUSAL_ABLATION_20261108/RELEASE_INPUT_LOCK.json'
STUDY = WORK / 'g1_char002_s2_ekf_20261115/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF'
FULL = ART / 'V01B_DATA_DELIVERY_20261012_01a12ba0/checkout/research/V01B_DATA_REQUEST_20261011/DELIVERY_A_20261012'
MANIFEST = ART / 'DRIVE_SIM_ROUTES_20261007_01a11669/final_20261007T140446Z/results/S2'
LOS_ROOT = ART / 'dr_ekf_followup_audit_20261013'
LOS = LOS_ROOT / 'artifacts/i0_los_release_originals'
LOS_CHECK = LOS_ROOT / 'research/SINGLE_ANCHOR_CAL_IDENTIFIABILITY_20261013/out/rf_location_addendum/LOS_RELEASE_VERIFICATION.json'
BLOCK = ART / 'DRIVE_SIM_POST_A23_UPLOAD_20261010/supplement_retrieved/BLOCK_C'
ARCHIVE = WORK / 'OFFICE_CORRIDOR_TRANSFER_FIX_20261026/execution_33e9849'
P2 = ARCHIVE / 'p2'
P2_ART = ARCHIVE / 'p2_artifacts'
X1_LOCK = WORK / 'DS_MASK_CAUSAL_X0A_X1_20261026_01a1775b/INPUT_LOCK.json'
P0_MANIFEST = P2 / 'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json'
ROWS = {'R2': 979, 'R4': 742, 'R5': 1415}
TOL = 1e-10
SPEC = {'anchor': (10., 0., 2.65), 'robot_z_m': .45, 'mount_deg': 45.}
TRACE_FIELDS = ('prior', 'Pprior', 'h', 'H', 'K', 'Reff', 'mask')


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def checked(path, expected):
    assert sha(path) == expected, f'SHA-256 mismatch: {path}'
    return path


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, values):
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(values, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write('\n')


def npz(path):
    with np.load(path, allow_pickle=False) as files:
        return dict(files)


def save_npz(path, arrays):
    with path.open('xb') as handle:
        np.savez_compressed(handle, **arrays)


def stem(route):
    return f'{route}_aB_m45_B0_Full_10'


def utc():
    return datetime.now(timezone.utc).isoformat()


def freeze():
    release = {row['asset_name']: row['sha256'] for row in load(LOCK)['files']}
    los_lock = {row['file']: row for row in load(LOS_CHECK)['files']}
    x1 = {Path(row['path']): row['sha256'] for row in load(X1_LOCK)['files']}
    inputs = {}

    def bind(path, expected=None):
        inputs[str(path)] = sha(path) if expected is None else sha(checked(path, expected))

    for path in (LOCK, LOS_CHECK, X1_LOCK, FULL / 'DELIVERY_MANIFEST.json', BLOCK / 'freqs_hz.npy',
                 STUDY / 'prepare_s2_extensions.py', STUDY / 'replay_s2.py',
                 Path('C:/Users/Myoungsun Kim/.codex/research-governance/COMMON_CONTRACT.md'),
                 Path('C:/Users/Myoungsun Kim/.codex/research-governance/ROLE_IMPLEMENTER.md')):
        bind(path)
    for path, digest in x1.items():
        if path == P0_MANIFEST or path.name in ('OBSERVATION_FEATURES_LABELS.csv.gz', 'OOF_PARAMETERS.csv.gz', 'MR_SERIES.csv.gz'):
            bind(path, digest)
    for path in (NATIVE / 'src/qclean_uwb/fp_sc/e0_baseline.py',
                 NATIVE / 'src/qclean_uwb/drivesim/observation.py',
                 P2 / 'research/PJ_DS_GATED_20261021/mu_recursive.py',
                 P2 / 'research/PJ_DS_GATED_20261021/series_dump.py',
                 P2 / 'research/PHYSICS_RS_STAGED_20261015/code/features.py',
                 P2 / 'research/PJ_SEPARATE_RS_20261020/experiment.py',
                 P2 / 'research/R5_N4B_20261015/n4b_rf_errors.py'):
        bind(path, x1.get(path))
    for case in load(P0_MANIFEST)['cases']:
        for kind in ('full', 'samples'):
            path = P2 / case[f'{kind}_path']
            bind(path, x1.get(path))
    for route in ROWS:
        case = f'{route}_aB_m45'
        generation_path = MANIFEST / f'H_{case}.manifest.json'
        generation = load(generation_path)
        assert generation['config']['mount_deg'] == 45. and generation['config']['report']['complete']
        bind(generation_path)
        (generated,) = generation['outputs']
        bind(FULL / f'H_{case}.npy', generated['sha256'])
        los_path = LOS / f'H_LoS_{case}.npy'
        assert los_lock[los_path.name]['matches']
        bind(los_path, los_lock[los_path.name]['p0_sha256'])
        (grid,) = generation['inputs']
        bind(BLOCK / 'INPUTS' / f'rf_poses_{route}.json', grid['sha256'])
        for kind in ('online', 'evaluator'):
            name = f'{route}_B0_Full_10__{kind}.npz'
            bind(INPUT / 'locked_release' / name, release[name])
    write(OUT / 'RUN_CONTRACT.json', {
        'experiment': 'G1-CHAR002-S2-MOUNT45-B0', 'frozen_utc': utc(), 'role': 'IMPLEMENTER',
        'scope': {'anchor': 'B', 'mount_deg': 45, 'bias': 'B0', 'seed': 10, 'channel': 'Full', 'rows': ROWS},
        'baseline': 'Pinned SourceFFD / S1 W0 MB_VAR with parallel native POWER_DIAG BASE NIS gate 9.210340371976184.',
        'calibration': 'Historical POWER_DIAG POWER_BIN_JOINT and EXDS range HGB. Recreate original route-excluded folds, use historical held geometry for the existing POWER_DIAG near-site exclusion. Require release m0 parameter identity before using predictions on +45 RF. No new data enter fit.',
        'gate': 'm0 O30 and mu/R reproduction and archived W0 trace, then m45 W0 versus separate implementation; exact masks; normalized numerical error <= 1e-10. Historical frozen m45 trace unavailable.',
        'truth_boundary': 'Only evaluator contains body truth and LoS. Inference features use Full H of one packet. m0 B0 seed-10 controls and initialization are reused for identical path/body poses.',
        'reference_commits': {'s2_spec': '6c175a53fbbbb19f990881f7dfcf82a3760dab70', 'release_lock': load(LOCK)['source_commit'], 'original_calibration': load(X1_LOCK)['source_commit']},
        'inputs_sha256': inputs,
    })


def controls(packet):
    return {**{key: packet[key] for key in ('ds', 'gy', 'dt')}, 'x0': packet['x0'][:3]}


def evaluate_parity(expected, observed):
    errors = {}
    for key, value in expected.items():
        got = observed[key]
        assert got.shape == value.shape and np.isfinite(got).all() and np.isfinite(value).all(), key
        if value.dtype == bool:
            errors[key] = {'mismatches': int(np.count_nonzero(value != got))}
            assert np.array_equal(value, got), errors[key]
        else:
            delta = np.abs(value - got)
            norm = float(np.max(delta / np.maximum(1., np.abs(value))))
            errors[key] = {'max_abs': float(delta.max()), 'max_normalized': norm}
            assert norm <= TOL, (key, errors[key])
    return errors


def release_packet(route, kind):
    return npz(INPUT / 'locked_release' / f'{route}_B0_Full_10__{kind}.npz')


def evidence(route, extension, observation, original, core, model, reference):
    old = release_packet(route, 'online')
    ids, t = old['pose_id'], old['t']
    assert np.array_equal(ids, np.arange(ROWS[route]))
    assert np.allclose(t, .2 * ids, rtol=0, atol=1e-12)
    m0 = np.load(BLOCK / 'FULL_RF' / f'H_{route}_aB_m0.npy', mmap_mode='r')[ids, :, :, 0]
    assert np.array_equal(m0, old['Hrf'])
    z0 = extension.native_measurements(observation, m0)
    ctrl = controls(old)
    av = {key: old['trace_' + key] for key in TRACE_FIELDS}
    from replay_s2 import b0_reference
    av.update({key: value for key, value in b0_reference(old).items() if key in ('x', 'P')})
    spec0 = {**SPEC, 'mount_deg': 0.}
    old_native = original.replay(old, ctrl, 'W0', core, model, spec0)
    old_alt = reference(model, spec0, old)
    m0_results = {'observations': evaluate_parity({'z': old['z']}, {'z': z0}),
                  'native': evaluate_parity(av, old_native), 'alternate': evaluate_parity(av, old_alt)}
    print(route, 'frozen m0 archive parity PASS', flush=True)

    names = (f'H_{route}_aB_m45.npy', f'H_LoS_{route}_aB_m45.npy')
    arrays = [np.load(path, mmap_mode='r', allow_pickle=False) for path in (FULL / names[0], LOS / names[1])]
    grid = load(BLOCK / 'INPUTS' / f'rf_poses_{route}.json')
    assert len(grid) == arrays[0].shape[0] and all(row['pose_id'] == j for j, row in enumerate(grid))
    assert all(a.shape == (len(grid), 257, 2, 2) and a.dtype == np.complex128 for a in arrays)
    full_h, los_h = [a[ids, :, :, 0] for a in arrays]
    assert np.isfinite(full_h).all() and np.isfinite(los_h).all()
    z = extension.native_measurements(observation, full_h)
    cal = npz(OUT / f'{stem(route)}__calibration.npz')
    assert np.array_equal(cal['pose_id'], ids)
    cal_match = evaluate_parity({'z': z}, {'z': cal['z']})
    new = {key: old[key] for key in ('t', 'pose_id', 'x0', 'ds', 'gy', 'dt', 'P0')}
    new.update(Hrf=full_h, clean_Hrf=full_h, z=z)
    new.update({key: cal[key] for key in ('R', 'muMB', 'muBASE', 'D')})
    trace = original.replay(new, ctrl, 'W0', core, model, SPEC)
    alternate = reference(model, SPEC, new)
    comparison = evaluate_parity({key: trace[key] for key in (*TRACE_FIELDS, 'x', 'P')}, alternate)
    assert np.linalg.eigvalsh(trace['P']).min() > 0
    for key in ('prior', 'Pprior'):
        new[key] = trace[key]
    new.update({'trace_' + key: trace[key] for key in TRACE_FIELDS})
    assert new.keys() == old.keys()
    ev = release_packet(route, 'evaluator')
    assert np.array_equal(ev['pose_id'], ids) and np.array_equal(ev['t'], t)
    selected = [grid[i] for i in ids]
    xy = np.array([[row['x'], row['y']] for row in selected])
    angles = np.radians([row['yaw_body_deg'] for row in selected])
    assert np.max(np.abs(xy - ev['truth'][:, :2])) < 1e-6
    assert np.max(np.abs((angles - ev['truth'][:, 2] + np.pi) % (2 * np.pi) - np.pi)) < 1e-6
    evaluator = {**ev, 'clean_H': los_h}
    hashes = {}
    for suffix, packet in (('online', new), ('evaluator', evaluator), ('e0_trace', {'pose_id': ids, 't': t, **{key: val for key, val in trace.items() if key != 'latency_ns'}})):
        path = OUT / f'{stem(route)}__{suffix}.npz'
        save_npz(path, packet)
        reloaded = npz(path)
        assert reloaded.keys() == packet.keys() and all(np.array_equal(val, reloaded[key]) for key, val in packet.items())
        hashes[path.name] = sha(path)
    print(route, 'm45 W0 parity PASS', int(np.sum(trace['mask'])), '/', len(ids), flush=True)
    return {'rows': len(ids), 'gate_accept': int(np.sum(trace['mask'])), 'm0': m0_results,
            'm45_measurement_crosscheck': cal_match, 'm45': comparison, 'output_sha256': hashes}


def run():
    for path, expected in load(OUT / 'RUN_CONTRACT.json')['inputs_sha256'].items():
        checked(Path(path), expected)
    cal = load(OUT / 'CALIBRATION_PARITY.json')
    assert cal['status'] == 'PASS'
    for path, expected in cal['output_sha256'].items():
        checked(OUT / path, expected)
    sys.path[:0] = [str(NATIVE / 'src'), str(STUDY)]
    import prepare_s2_extensions as extension
    from e0_reference import reference
    from qclean_uwb.drivesim import observation
    from qclean_uwb.fp_sc.e0_baseline import load_original_model
    core, original, model, hashes = load_original_model(NATIVE)
    assert np.array_equal(np.load(BLOCK / 'freqs_hz.npy'), model.freqs)
    results = {route: evidence(route, extension, observation, original, core, model, reference) for route in ROWS}
    write(OUT / 'PARITY_RESULTS.json', {
        'status': 'PASS', 'utc': utc(), 'runtime': {'python': platform.python_version(), 'numpy': np.__version__},
        'contract_sha256': sha(OUT / 'RUN_CONTRACT.json'), 'calibration_receipt_sha256': sha(OUT / 'CALIBRATION_PARITY.json'),
        'source_sha256': {**hashes, **{name: sha(OUT / name) for name in ('prepare_mount45.py', 'calibration.py', 'e0_reference.py')}},
        'historical_m45_reference': 'Absent. m45 comparison is between recursive implementations with shared SourceFFD.',
        'routes': results,
    })


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=('freeze', 'run'))
    args = parser.parse_args()
    {'freeze': freeze, 'run': run}[args.stage]()
