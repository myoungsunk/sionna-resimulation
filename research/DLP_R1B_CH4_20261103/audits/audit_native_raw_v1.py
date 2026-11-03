#!/usr/bin/env python3
"""Independent, read-only Native canary audit. Never imports a Native RT runtime.

This program does not import r1b_native or its observer. It reconstructs archived
channels from all retained coefficients/delays, separately evaluates an inverse
DFT, and recomputes the canonical frozen SourceFFD at the original CSV poses.
Only the explicitly requested audit receipt is written. Scientific thresholds
are read from the already frozen V2 contract and are never fitted to outcomes.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import importlib.metadata
import json
import math
import pathlib
import subprocess
import sys
import time

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
BASE = ROOT / 'research/DLP_R1B_CH4_20261103'
CONTRACT_SHA = 'a31a537dd35823d10c1d74ee0cf488d439b7ba2c70114309e024b451a9468596'
MANIFEST_SHA = '5bd9943bdcad4d7d5e4e413101c9fcaa49821fdc43404a7e16998be0053f86b7'
RUN_COMMIT = '24d657af7773d1c0347e843ece6b49e9c2d55ac2'
N = 257
C = 299792458.0
FREQ = 6250400000.0 + 1950000.0 * np.arange(N)
EXPECTED_IDS = [0, 150, 221, 440, 458, 476, 696, 916]


def digest(path):
    with pathlib.Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def read_json(path):
    return json.loads(pathlib.Path(path).read_text())


def resolve(path):
    p = pathlib.Path(path)
    return p if p.is_absolute() else ROOT / p


def hash_specs(obj):
    if isinstance(obj, dict):
        if isinstance(obj.get('path'), str) and isinstance(obj.get('sha256'), str):
            yield obj
        for value in obj.values():
            yield from hash_specs(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from hash_specs(value)


class Audit:
    def __init__(self):
        self.failed = []
        self.count = 0

    def check(self, condition, code, detail=None):
        self.count += 1
        if not bool(condition):
            self.failed.append({'code': code, 'detail': detail})
        return bool(condition)

    def need(self, condition, code, detail=None):
        if not self.check(condition, code, detail):
            raise ValueError(code)


def direct_dft_observer(h):
    """Explicit inverse DFT, sin-squared Hann, independently selected RX/tap."""
    k = np.arange(N, dtype=float)
    t = np.arange(4 * N, dtype=float)
    window = np.sin(np.pi * k / (N - 1)) ** 2
    phase = 2 * np.pi * np.outer(t, k) / (4 * N)
    kernel = np.cos(phase) + 1j * np.sin(phase)
    cir = kernel @ (window[:, None] * h[:, :, 0]) / 4
    mag = np.abs(cir)
    maxima = [float(max(mag[:, port])) for port in (0, 1)]
    branch = 0 if maxima[0] >= maxima[1] else 1
    tap = next(index for index, value in enumerate(mag[:, branch])
               if value >= 0.3 * maxima[branch])
    powers = np.real(cir[tap] * np.conj(cir[tap]))
    out = {'r_m': float(tap * C / (4 * N * 1950000.0)),
           's': float((powers[0] - powers[1]) / sum(powers)),
           'tap': tap, 'strong_port': branch,
           'power_plus': float(powers[0]), 'power_minus': float(powers[1])}
    return out, cir


def original_fft_math(h):
    """Archive equality check, distinct from the direct-DFT oracle above."""
    win = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N) / (N - 1))
    return np.fft.ifft(h[:, :, 0] * win[:, None], n=4 * N, axis=0) * N


def load_canonical_source(contract):
    # These source modules are numerical only. Do not import corridor_sionna_run,
    # sionna, mitsuba, drjit, the acquisition implementation or its observer.
    sys.path[:0] = [str(ROOT / 'research/FFD_P0P3_20261016'),
                   str(ROOT / 'research/EKF4_RANGE_S_STAGED_20261014'),
                   str(ROOT / 'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src')]
    import source_model
    import p0_initial
    banks = []
    for spec in contract['inputs']['banks']:
        with np.load(resolve(spec['path']), allow_pickle=False) as archive:
            banks.append(p0_initial.P.Bank({key: archive[key] for key in archive.files}))
    return source_model.SourceFFD(banks=banks), p0_initial


def audit_source(source, independent, state, xyz, case, saved, tolerance, audit, prefix):
    physical = source.physical_h_col(state[None], case)[0]
    direct = independent.direct(source.banks, xyz[None],
                                np.array([np.degrees(state[2])]), case['anchor'])[0, :, :, 0]
    model, jac, diag = source.batch(state[None], case, return_diagnostics=True)
    norm = np.linalg.norm(direct)
    internal = float(np.linalg.norm(physical - direct) / norm)
    canonical_rel = float(np.linalg.norm(physical - saved['source_physical_h']) /
                          np.linalg.norm(physical))
    direct_archive_rel = float(np.linalg.norm(direct - saved['source_independent_h']) / norm)
    audit.check(internal <= tolerance['source_direct_relative_max'], prefix + ':SOURCE_DIRECT')
    audit.check(canonical_rel <= tolerance['source_direct_relative_max'], prefix + ':SOURCE_ARCHIVE_H')
    audit.check(direct_archive_rel <= tolerance['source_direct_relative_max'], prefix + ':DIRECT_ARCHIVE_H')
    audit.check(np.max(np.abs(model[0] - saved['source_model_h'])) <= tolerance['observer_abs'],
                prefix + ':SOURCE_ARCHIVE_PREDICTION')
    audit.check(np.array_equal(jac[0], saved['source_model_H']), prefix + ':SOURCE_ARCHIVE_JACOBIAN_EXACT')
    audit.check(np.array_equal(jac[0, :, 3], np.zeros(2)), prefix + ':SOURCE_BIAS_COLUMN_ZERO')
    detector, _ = direct_dft_observer(np.stack([physical, physical], axis=-1))
    audit.check(abs(detector['s'] - model[0, 1]) <= tolerance['observer_abs'], prefix + ':SOURCE_OBSERVER_S')
    audit.check(detector['tap'] == int(diag['tap'][0]), prefix + ':SOURCE_OBSERVER_TAP')
    audit.check(detector['strong_port'] == int(diag['strong_port'][0]), prefix + ':SOURCE_OBSERVER_BRANCH')
    audit.check(abs(detector['r_m'] - float(diag['native_range'][0])) <= tolerance['observer_abs'],
                prefix + ':SOURCE_OBSERVER_RANGE')
    # Use half the acquisition step as an independent central-difference check.
    step = tolerance['fd_step'] / 2
    finite_differences = []
    for axis in range(3):
        plus, minus = state.copy(), state.copy()
        plus[axis] += step
        minus[axis] -= step
        hp, _, dp = source.batch(plus[None], case, return_diagnostics=True)
        hm, _, dm = source.batch(minus[None], case, return_diagnostics=True)
        stable = all(np.array_equal(diag[key], d[key])
                     for key in ('tap', 'strong_port', 'cells') for d in (dp, dm))
        fd = float((hp[0, 1] - hm[0, 1]) / (2 * step))
        analytic = float(jac[0, 1, axis])
        error = abs(fd - analytic)
        relative = error / max(abs(analytic), 1e-30)
        good = error <= tolerance['stable_jac_abs'] or (
            abs(analytic) > 1e-6 and relative <= tolerance['stable_jac_rel'])
        status = ('PASS' if good else 'FAIL') if stable else 'BOUNDARY_NOT_FD_PASS'
        audit.check(status != 'FAIL', prefix + ':SOURCE_FD_' + str(axis))
        finite_differences.append({'axis': axis, 'step': step, 'stable': stable,
                                  'analytic': analytic, 'fd': fd, 'abs_error': error,
                                  'relative_error': relative, 'status': status})
    return physical, model[0], diag, {'source_direct_relative': internal,
        'canonical_archive_relative': canonical_rel, 'independent_archive_relative': direct_archive_rel,
        'source_detector': detector, 'fd': finite_differences}


def audit_mode(saved, mode, freq, object_ids, tolerance, audit, prefix):
    h = saved['H_' + mode]
    cir = saved['CIR_' + mode]
    offsets = saved[mode + '_path_offsets']
    counts = saved[mode + '_path_counts']
    tau = saved[mode + '_tau_s']
    coefficient = saved[mode + '_a']
    interaction = saved[mode + '_interactions']
    objects = saved[mode + '_objects']
    pfx = prefix + ':' + mode
    audit.need(h.shape == (N, 2, 2) and cir.shape == (4 * N, 2), pfx + ':CHANNEL_SHAPE')
    audit.need(offsets.shape == (N + 1,) and counts.shape == (N,), pfx + ':INDEX_SHAPE')
    audit.need(offsets[0] == 0 and offsets[-1] == len(tau) and
               np.array_equal(np.diff(offsets), counts) and np.all(counts > 0), pfx + ':PATH_INDEX')
    depth = 1 if mode == 'los' else 3
    audit.need(coefficient.shape == (2, 2, len(tau)) and interaction.shape == (depth, len(tau))
               and objects.shape == interaction.shape, pfx + ':RAW_SHAPE')
    audit.need(all(np.isfinite(array).all() for array in (h, cir, tau, coefficient)), pfx + ':FINITE')
    audit.check(np.all(tau > 0), pfx + ':POSITIVE_PATH_DELAY')
    audit.check(set(np.unique(interaction).tolist()).issubset({0, 1, 4}), pfx + ':ALLOWED_INTERACTIONS')
    audit.check(set(np.unique(objects[interaction != 0]).tolist()).issubset(object_ids), pfx + ':OBJECT_MAP')
    audit.check(np.all(objects[interaction == 0] == 4294967295), pfx + ':INACTIVE_OBJECT_SENTINEL')
    if mode == 'los':
        audit.check(np.all(counts == 1) and np.all(interaction == 0), pfx + ':SINGLE_DIRECT_PATH')
    reconstituted = np.empty_like(h)
    compensated = np.empty_like(h)
    for bin_id in range(N):
        left, right = offsets[bin_id:bin_id + 2]
        phasor = np.exp(-2j * np.pi * freq[bin_id] * tau[left:right])
        for rx in range(2):
            for tx in range(2):
                terms = coefficient[rx, tx, left:right] * phasor
                reconstituted[bin_id, rx, tx] = np.sum(terms)
                compensated[bin_id, rx, tx] = complex(math.fsum(terms.real), math.fsum(terms.imag))
    # The raw stored values permit exact recreation of the acquisition expression.
    # The second fsum computation separately exposes accumulation roundoff.
    audit.check(np.array_equal(h, reconstituted), pfx + ':RAW_H_RECONSTRUCTION_EXACT')
    fft = original_fft_math(reconstituted)
    audit.check(np.array_equal(cir, fft), pfx + ':ARCHIVED_CIR_EXACT')
    observation, dft_cir = direct_dft_observer(reconstituted)
    # No physical threshold is introduced by this numerical-accounting check.
    # The explicit-DFT phase has O(N*eps) rounding; this bound tests arithmetic.
    roundoff_bound = 64 * np.finfo(float).eps * N * np.max(np.sum(np.abs(h[:, :, 0]), axis=0)) / 4
    cir_error = float(np.max(np.abs(dft_cir - cir)))
    audit.check(cir_error <= roundoff_bound, pfx + ':INDEPENDENT_DFT_ROUNDOFF',
                {'max_abs': cir_error, 'float64_bound': float(roundoff_bound)})
    audit.check(abs(observation['s']) <= 1 + 1e-12 and
                observation['power_plus'] + observation['power_minus'] > 0, pfx + ':T13_SIGNED_POWER')
    return {'observation': observation, 'path_count_min': int(min(counts)),
            'path_count_max': int(max(counts)), 'total_path_count': int(sum(counts)),
            'raw_H_exact': bool(np.array_equal(h, reconstituted)),
            'raw_H_compensated_max_abs': float(np.max(np.abs(h - compensated))),
            'archived_CIR_exact': bool(np.array_equal(cir, fft)),
            'direct_DFT_CIR_max_abs': cir_error, 'direct_DFT_roundoff_bound': float(roundoff_bound),
            'active_surface_ids': sorted(set(np.unique(objects[interaction != 0]).tolist())),
            'interaction_values': sorted(set(np.unique(interaction).tolist()))}


def audit_pose(path, row, contract, source, independent, env, audit):
    prefix = 'POSE_' + str(row['pose_id'])
    before = len(audit.failed)
    report_path = path.with_suffix('.json')
    metadata = read_json(report_path)
    raw_hash = digest(path)
    audit.need(metadata['raw_sha256'] == raw_hash, prefix + ':RAW_HASH')
    audit.need(metadata['raw_file'] == path.name, prefix + ':RAW_FILENAME')
    with np.load(path, allow_pickle=False) as archive:
        saved = {key: archive[key] for key in archive.files}
    tolerance = contract['tolerances']
    state = np.array([float(row['x']), float(row['y']), np.radians(float(row['yaw_body_deg'])), 0.])
    xyz = np.array([state[0], state[1], 0.45])
    anchor = np.array([10., 0., 2.65])
    case = {'anchor': anchor.tolist(), 'robot_z_m': 0.45, 'mount_deg': 0.}
    audit.check(int(saved['pose_id']) == int(row['pose_id']) == metadata['pose_id'], prefix + ':POSE_ID')
    audit.check(abs(float(saved['t_s']) - float(row['t_s'])) <= 1e-9, prefix + ':TIMESTAMP')
    audit.check(abs(metadata['t_s'] - float(row['t_s'])) <= 1e-9, prefix + ':METADATA_TIMESTAMP')
    audit.check(metadata['phase'] == row['phase'], prefix + ':PHASE')
    audit.check(np.max(np.abs(saved['xyz_m'] - xyz)) <= 1e-6, prefix + ':POSITION')
    audit.check(abs(np.degrees(float(saved['psi_rad']) - state[2])) <= 1e-6, prefix + ':BODY_YAW')
    audit.check(np.array_equal(saved['anchor_xyz_m'], anchor), prefix + ':ANCHOR_B')
    audit.need(np.array_equal(saved['freq_hz'], FREQ), prefix + ':FREQUENCY_GRID')
    physical, model, diag, source_metrics = audit_source(source, independent, state, xyz, case,
                                                       saved, tolerance, audit, prefix)
    modes = {}
    object_ids = set(map(int, env['native_object_id_to_surface_name']))
    for mode in ('los', 'full'):
        modes[mode] = audit_mode(saved, mode, FREQ, object_ids, tolerance, audit, prefix)
        observation = modes[mode]['observation']
        for key in ('r_m', 's', 'power_plus', 'power_minus'):
            error = abs(observation[key] - metadata[mode][key])
            audit.check(error <= tolerance['observer_abs'], prefix + ':' + mode + ':METADATA_' + key,
                        {'abs_difference': error})
        for key in ('tap', 'strong_port'):
            audit.check(observation[key] == metadata[mode][key], prefix + ':' + mode + ':METADATA_' + key)
        audit.check(modes[mode]['path_count_min'] == metadata[mode]['min_paths'] and
                    modes[mode]['path_count_max'] == metadata[mode]['max_paths'], prefix + ':' + mode + ':METADATA_COUNTS')
    geometric = float(np.linalg.norm(xyz - anchor) / C)
    delay_max = float(np.max(np.abs(saved['los_tau_s'] - geometric)))
    audit.check(delay_max <= tolerance['los_delay_abs_s'], prefix + ':LOS_GEOMETRIC_DELAY')
    direct_count, full_direct_relative = [], []
    offsets = saved['full_path_offsets']
    for bin_id in range(N):
        left, right = offsets[bin_id:bin_id + 2]
        tau = saved['full_tau_s'][left:right]
        untouched = np.all(saved['full_interactions'][:, left:right] == 0, axis=0)
        is_direct = untouched & (np.abs(tau - geometric) <= tolerance['los_delay_abs_s'])
        indices = np.flatnonzero(is_direct)
        direct_count.append(len(indices))
        if len(indices) == 1:
            idx = left + int(indices[0])
            channel = saved['full_a'][:, :, idx] * np.exp(-2j * np.pi * FREQ[bin_id] * saved['full_tau_s'][idx])
            los = saved['H_los'][bin_id]
            full_direct_relative.append(float(np.linalg.norm(channel - los) / np.linalg.norm(los)))
    full_unique = int(sum(count == 1 for count in direct_count))
    full_direct_max = max(full_direct_relative, default=None)
    audit.check(full_unique == N, prefix + ':FULL_UNIQUE_DIRECT')
    audit.check(full_direct_max is not None and full_direct_max <= tolerance['full_direct_relative_max'],
                prefix + ':FULL_DIRECT_VS_LOS')
    native_complex = float(np.linalg.norm(saved['H_los'][:, :, 0] - physical) /
                           np.linalg.norm(saved['H_los'][:, :, 0]))
    native_s = abs(modes['los']['observation']['s'] - float(model[1]))
    tap_mismatch = int(modes['los']['observation']['tap'] != int(diag['tap'][0]))
    branch_mismatch = int(modes['los']['observation']['strong_port'] != int(diag['strong_port'][0]))
    audit.check(native_complex <= tolerance['native_complex_relative_max'], prefix + ':NATIVE_SOURCE_COMPLEX_MAX')
    audit.check(native_s <= tolerance['native_s_abs_max'], prefix + ':NATIVE_SOURCE_S_MAX')
    audit.check(tap_mismatch == 0, prefix + ':NATIVE_SOURCE_TAP')
    audit.check(branch_mismatch == 0, prefix + ':NATIVE_SOURCE_BRANCH')
    recomputed = {'source_direct_relative': source_metrics['source_direct_relative'],
        'los_delay_abs_s': delay_max, 'full_unique_direct_bins': full_unique,
        'full_direct_vs_separate_los_relative_max': full_direct_max,
        'native_source_complex_relative': native_complex, 'native_source_s_abs': native_s,
        'native_source_tap_mismatch': tap_mismatch, 'native_source_port_mismatch': branch_mismatch,
        'source_model_range_m': float(model[0]), 'source_model_s': float(model[1]),
        'source_detector_range_m': float(diag['native_range'][0]),
        'source_tap': int(diag['tap'][0]), 'source_strong_port': int(diag['strong_port'][0])}
    for key, value in recomputed.items():
        audit.check(value is not None and metadata[key] is not None and
                    abs(value - metadata[key]) <= tolerance['observer_abs'], prefix + ':METADATA_' + key)
    audit.check(digest(path) == raw_hash, prefix + ':RAW_UNCHANGED_DURING_AUDIT')
    return {'pose_id': int(row['pose_id']), 'status': 'PASS' if len(audit.failed) == before else 'HOLD',
            'raw_path': str(path.relative_to(ROOT)), 'raw_sha256': raw_hash,
            'metadata_sha256': digest(report_path), 'recomputed_metrics': recomputed,
            'source_checks': source_metrics, 'native_modes': modes,
            'acquisition_seconds_as_recorded': metadata['acquisition_seconds'],
            'max_rss_mib_as_recorded': metadata['max_rss_mib']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=pathlib.Path, default=BASE / 'runs/P0_CANARY_V2')
    parser.add_argument('--out', type=pathlib.Path, required=True)
    args = parser.parse_args()
    audit = Audit()
    started = time.monotonic()
    contract_path = BASE / '00_REQUEST_CONTRACT_FROZEN_V2.json'
    manifest_path = BASE / '02_INPUT_HASH_MANIFEST_V2.json'
    receipt = {'schema': 'DLP_R1B_CH4_INDEPENDENT_RAW_CANARY_AUDIT_V1',
        'actor': '/root/r1_preflight_audit', 'status': 'HOLD_AUDIT_INCOMPLETE',
        'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'independence': {'separate_agent': True, 'separate_process': True,
            'same_host': True, 'native_rt_executed_by_auditor': False,
            'acquisition_code_imported': False, 'scientific_signoff': False},
        'bindings': {'contract_sha256': digest(contract_path), 'input_manifest_sha256': digest(manifest_path),
            'audit_script_sha256': digest(__file__), 'expected_execution_commit': RUN_COMMIT},
        'not_authorized': ['production before measured cost lock and required review',
                           'P2/P3 before complete917 acquisition', 'P4', 'scientific performance claims']}
    try:
        audit.need(digest(contract_path) == CONTRACT_SHA, 'FROZEN_CONTRACT_HASH')
        audit.need(digest(manifest_path) == MANIFEST_SHA, 'FROZEN_MANIFEST_HASH')
        contract, manifest = read_json(contract_path), read_json(manifest_path)
        audit.need(contract['canary']['pose_ids'] == EXPECTED_IDS, 'PRESELECTED_POSES')
        audit.need(contract['canary']['bins'] == list(range(N)), 'ALL_257_BINS')
        checked = {}
        checks = 0
        for spec in list(hash_specs(contract)) + list(hash_specs(manifest)):
            path = resolve(spec['path']).resolve()
            if path not in checked:
                checked[path] = {'sha256': digest(path), 'bytes': path.stat().st_size}
            info = checked[path]
            audit.need(info['sha256'] == spec['sha256'], 'INPUT_SHA', spec['path'])
            if 'bytes' in spec:
                audit.need(info['bytes'] == spec['bytes'], 'INPUT_BYTES', spec['path'])
            checks += 1
        receipt['input_hash_audit'] = {'comparisons': checks, 'unique_paths': len(checked), 'status': 'PASS'}
        # Bind source code and all threshold contracts to the actual recorded commit.
        commit_files = [contract_path, manifest_path] + [resolve(spec['path'])
            for spec in [contract['request_reference'], *contract['code_files'], *contract['inherited_contract_files']]]
        for path in commit_files:
            archived = subprocess.check_output(['git', 'show', RUN_COMMIT + ':' + str(path.relative_to(ROOT))], cwd=ROOT)
            audit.need(hashlib.sha256(archived).hexdigest() == digest(path), 'RUN_COMMIT_SOURCE_BYTES', str(path))
        receipt['commit_bound_files'] = len(commit_files)
        with resolve(contract['inputs']['pose_csv']['path']).open(newline='') as handle:
            rows = list(csv.DictReader(handle))
        audit.need(len(rows) == 917 and [int(row['pose_id']) for row in rows] == list(range(917)), '917_POSE_IDS')
        audit.need(sum(float(row['t_s']) >= 30 for row in rows) == 767, '767_EVALUATION_POSES')
        env_path = args.run / 'ENVIRONMENT.json'
        env = read_json(env_path)
        audit.need(env['source_git_sha'] == RUN_COMMIT, 'ENVIRONMENT_EXECUTION_COMMIT')
        audit.need(env['packages'] == contract['runtime']['required_packages'], 'ENVIRONMENT_PACKAGES')
        audit.need(env['variant'] == contract['runtime']['mitsuba_variant'] and env['threads'] == 1, 'ENVIRONMENT_BACKEND')
        audit.need(env['python'] == contract['runtime']['python_actual'], 'ENVIRONMENT_PYTHON')
        bindings = env['material_bindings']
        reference = read_json(resolve(contract['inputs']['material_reference']['path']))[0]['material_bindings']
        key = lambda items: {item['object']: [item['ply_sha256'], item['itu_type'], item['thickness_m']] for item in items}
        audit.need(key(bindings) == key(reference), 'ORIGINAL_MATERIAL_BINDINGS')
        surface_map = env['native_object_id_to_surface_name']
        audit.need(len(surface_map) == 6 and set(surface_map.values()) == set(key(reference)), 'SIX_SURFACE_MAP')
        for binding in bindings:
            audit.need(digest(args.run / '_scene' / (binding['object'] + '.ply')) == binding['ply_sha256'],
                       'ACTUAL_SCENE_MESH_HASH', binding['object'])
        receipt['environment_audit'] = {'status': 'PASS', 'environment_sha256': digest(env_path),
                                       'object_id_to_surface': surface_map, 'mesh_count': len(bindings)}
        source, independent = load_canonical_source(contract)
        for name in ('numpy', 'scipy'):
            audit.need(importlib.metadata.version(name) == contract['runtime']['required_packages'][name], 'AUDITOR_PACKAGE_' + name)
        completed = [pose for pose in EXPECTED_IDS if (args.run / ('pose_%04d.json' % pose)).exists()]
        audit.need(completed == EXPECTED_IDS[:len(completed)], 'COMPLETED_PREFIX_ORDER')
        actual_ids = sorted(int(path.stem.split('_')[1]) for path in args.run.glob('pose_[0-9][0-9][0-9][0-9].json'))
        audit.need(actual_ids == sorted(completed), 'NO_EXTRA_COMPLETED_POSES')
        records = []
        for pose in completed:
            records.append(audit_pose(args.run / ('pose_%04d.npz' % pose), rows[pose],
                                      contract, source, independent, env, audit))
            print(json.dumps({'audit_pose_id': pose, 'status': records[-1]['status'],
                              'metric': records[-1]['recomputed_metrics']}), flush=True)
        receipt['completed_pose_ids'] = completed
        receipt['records'] = records
        metrics = [record['recomputed_metrics'] for record in records]
        if metrics:
            rel = np.array([item['native_source_complex_relative'] for item in metrics])
            s_error = np.array([item['native_source_s_abs'] for item in metrics])
            aggregate = {'complex_max': float(max(rel)), 'complex_rms': float(np.sqrt(np.mean(rel ** 2))),
                         's_max': float(max(s_error)), 's_rmse': float(np.sqrt(np.mean(s_error ** 2))),
                         'tap_mismatches': sum(item['native_source_tap_mismatch'] for item in metrics),
                         'port_mismatches': sum(item['native_source_port_mismatch'] for item in metrics)}
            receipt['independently_recomputed_metrics'] = aggregate
        complete = completed == EXPECTED_IDS
        qa_path = args.run / '03_RF_CANARY_QA.json'
        final = complete and qa_path.exists()
        if final:
            qa = read_json(qa_path)
            tolerance = contract['tolerances']
            audit.check(aggregate['complex_rms'] <= tolerance['native_complex_relative_rms'], 'EIGHT_POSE_COMPLEX_RMS')
            audit.check(aggregate['s_rmse'] <= tolerance['native_s_rmse'], 'EIGHT_POSE_S_RMSE')
            audit.check(qa['contract_sha256'] == CONTRACT_SHA and qa['source_git_sha'] == RUN_COMMIT, 'QA_PROVENANCE')
            audit.check(qa['canary_pose_ids'] == EXPECTED_IDS and qa['completed_pose_ids'] == EXPECTED_IDS, 'QA_POPULATION')
            for key, value in aggregate.items():
                audit.check(abs(qa['metrics'][key] - value) <= tolerance['observer_abs'], 'QA_METRIC_' + key)
            audit.check(qa['phase_or_gain_fit'] is False and qa['raw_retained'] is True and
                        qa['scientific_supported'] is False, 'QA_CLAIM_BOUNDARIES')
            audit.check(qa['status'] == 'PASS' and all(qa['checks'].values()), 'QA_STATUS_ACCOUNTING')
            seconds = [record['acquisition_seconds_as_recorded'] for record in records]
            cost = {'median_pose_seconds': float(np.median(seconds)), 'max_pose_seconds': float(max(seconds)),
                    'projected_917_pose_cpu_hours_median': float(np.median(seconds) * 917 / 3600),
                    'projected_917_pose_cpu_hours_max': float(max(seconds) * 917 / 3600),
                    'max_rss_mib': max(record['max_rss_mib_as_recorded'] for record in records)}
            for key, value in cost.items():
                audit.check(abs(qa['measured_cost'][key] - value) <= tolerance['observer_abs'], 'QA_COST_' + key)
            receipt['recorded_cost_arithmetic'] = cost
            receipt['qa_sha256'] = digest(qa_path)
        if (args.run / 'FAILURE.json').exists():
            audit.check(False, 'ACQUISITION_FAILURE_PRESENT', read_json(args.run / 'FAILURE.json'))
        forbidden_imports = [name for name in sys.modules if name.split('.')[0] in ('sionna', 'mitsuba', 'drjit', 'r1b_native', 'corridor_sionna_run')]
        audit.check(not forbidden_imports, 'NO_NATIVE_OR_ACQUISITION_IMPORT', forbidden_imports)
        receipt['canary_complete'] = complete
        receipt['qa_complete'] = final
        receipt['status'] = ('HOLD_INDEPENDENT_RAW_AUDIT' if audit.failed else
                             'PASS_BOUNDED_CANARY_RAW_AUDIT' if final else 'IN_PROGRESS_AUDITED_PREFIX')
    except Exception as exc:
        import traceback
        receipt['exception'] = repr(exc)
        receipt['traceback'] = traceback.format_exc()
        receipt['status'] = 'HOLD_INDEPENDENT_RAW_AUDIT'
    receipt['checks_performed'] = audit.count
    receipt['failed_checks'] = audit.failed
    receipt['audit_elapsed_seconds'] = time.monotonic() - started
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        raise FileExistsError('Append-only audit output already exists: ' + str(args.out))
    args.out.write_text(json.dumps(receipt, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    print(json.dumps({'status': receipt['status'], 'failed': audit.failed, 'receipt': str(args.out),
                      'receipt_sha256': digest(args.out)}), flush=True)
    return 0 if receipt['status'] == 'PASS_BOUNDED_CANARY_RAW_AUDIT' else 3 if receipt['status'] == 'IN_PROGRESS_AUDITED_PREFIX' else 2


if __name__ == '__main__':
    raise SystemExit(main())
