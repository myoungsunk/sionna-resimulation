#!/usr/bin/env python3
"""DLP-R1B-CH4-001: frozen Native RT canary, gated acquisition and raw assembly.

Both arms call the original PathSolver independently for every frequency.
No phase fitting, interpolation, channel substitution or empirical correction.
The historical solver/antenna/SourceFFD files are imported without modifications.
"""
from __future__ import annotations
import argparse, csv, datetime, hashlib, importlib.metadata, json, os, pathlib
import platform, resource, subprocess, sys, time, traceback
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
BASE = ROOT / 'research/DLP_R1B_CH4_20261103'
C = 299792458.0
N = 257
PARTIAL_STATE = None
LAST_NATIVE_RETURN = None

def sha(p):
    with pathlib.Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def readj(p):
    return json.loads(pathlib.Path(p).read_text())

def writej(p, obj):
    p = pathlib.Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + '\n')

def require(ok, message):
    if not bool(ok):
        raise RuntimeError(message)

def resolve(p):
    p = pathlib.Path(p)
    return p if p.is_absolute() else ROOT / p

def load_contract(path):
    c = readj(path)
    require(c['contract_id'] == 'DLP-R1B-CH4-001' and c['status'] == 'FROZEN', 'CONTRACT_NOT_FROZEN')
    for a in [c['request_reference'], c['inputs']['pose_csv'], c['inputs']['material_reference'],
              c['inputs']['solver_reference'], c['inputs']['trajectory_manifest'],
              *c['code_files'], *c['inherited_contract_files']]:
        require(sha(resolve(a['path'])) == a['sha256'], 'SOURCE_HASH_MISMATCH:' + a['path'])
    with resolve(c['inputs']['pose_csv']['path']).open(newline='') as f:
        rows = list(csv.DictReader(f))
    require(len(rows) == 917, 'R1_SAMPLE_COUNT')
    require([int(r['pose_id']) for r in rows] == list(range(917)), 'R1_POSE_ORDER')
    times = np.array([float(r['t_s']) for r in rows])
    require(np.all(np.diff(times) > 0) and (times >= 30).sum() == 767, 'R1_TIMESTAMPS')
    return c, rows

def source_modules():
    historical = ROOT / 'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src'
    sys.path[:0] = [str(historical), str(ROOT / 'research/EKF4_RANGE_S_STAGED_20261014'),
                   str(ROOT / 'research/FFD_P0P3_20261016'), str(ROOT / 'scripts')]
    import source_model as SM
    import p0_initial as SI
    return SM, SI

def observer(h):
    h = np.asarray(h)
    require(h.shape == (N, 2, 2) and np.isfinite(h).all(), 'INVALID_NATIVE_CHANNEL')
    w = .5 - .5 * np.cos(2 * np.pi * np.arange(N) / (N - 1))
    cir = np.fft.ifft(h[:, :, 0] * w[:, None], n=4 * N, axis=0) * N
    mag = np.abs(cir)
    port = int(np.argmax(mag.max(axis=0)))
    peak = float(mag[:, port].max())
    require(peak > 0, 'ZERO_SIGNAL')
    tap = int(np.flatnonzero(mag[:, port] >= .3 * peak)[0])
    p = np.abs(cir[tap]) ** 2
    require(np.all(p >= 0) and float(p.sum()) > 0, 'INVALID_POWER')
    s = float((p[0] - p[1]) / p.sum())
    require(np.isfinite(s) and abs(s) <= 1 + 1e-12, 'INVALID_SIGNED_S')
    return {'r_m': tap * C / (4 * N * 1950000.0), 's': s, 'tap': tap,
            'strong_port': port, 'power_plus': float(p[0]), 'power_minus': float(p[1])}, cir

def initialize(c, banks_dir, out):
    SM, SI = source_modules()
    dictionaries = []
    for spec in c['inputs']['banks']:
        p = pathlib.Path(banks_dir) / pathlib.Path(spec['path']).name
        require(sha(p) == spec['sha256'], 'BANK_SHA_MISMATCH:' + p.name)
        with np.load(p, allow_pickle=False) as z:
            dictionaries.append({k: z[k] for k in z.files})
    banks = [SI.P.Bank(d) for d in dictionaries]
    freq = banks[0].freqs_hz
    require(np.array_equal(freq, 6250400000.0 + 1950000.0 * np.arange(N)), 'FREQUENCY_GRID')
    require(np.array_equal(freq, banks[1].freqs_hz), 'PORT_FREQUENCY_MISMATCH')
    source = SM.SourceFFD(banks=banks)
    import corridor_sionna_run as CR
    import mitsuba as mi
    import drjit as dr
    dr.set_thread_count(1)
    versions = {n: importlib.metadata.version(n) for n in ['numpy', 'scipy', 'sionna-rt', 'mitsuba', 'drjit']}
    for n, v in c['runtime']['required_packages'].items():
        require(versions[n] == v, 'RUNTIME_VERSION:' + n)
    require(mi.variant() == 'llvm_ad_mono_polarized', 'WRONG_MITSUBA_VARIANT')
    setup = CR.CorridorSetup(anchor_x_m=10.0, anchor_y_m=0.0)
    require(np.allclose(setup.anchor_position, [10., 0., 2.65], atol=1e-12, rtol=0), 'WRONG_ANCHOR_B')
    require(setup.robot_antenna_z_m == .45 and all(v['passed'] for v in setup.validate()), 'INVALID_GEOMETRY')
    scene, bindings = CR.build_scene(setup, out / '_scene')
    prior = readj(resolve(c['inputs']['material_reference']['path']))[0]['material_bindings']
    key = lambda b: {x['object']: [x['ply_sha256'], x['itu_type'], x['thickness_m']] for x in b}
    require(key(bindings) == key(prior), 'C0_MESH_OR_MATERIAL_DRIFT')
    scene.add(CR.rt.Transmitter('tx', position=setup.anchor_position.tolist(), orientation=CR.euler(CR.ANCHOR_ROTATION)))
    scene.add(CR.rt.Receiver('rx', position=setup.robot_position(1.2, .35).tolist(), orientation=CR.euler(setup.robot_rotation(0.))))
    tx, rx = CR.make_ports(dictionaries)
    solver = CR.rt.PathSolver()
    original_cfg = readj(resolve(c['inputs']['solver_reference']['path']))['solver']
    require(c['rf']['solver_full'] == original_cfg, 'FULL_SOLVER_DRIFT')
    object_map = {str(int(np.asarray(obj.object_id).reshape(-1)[0])): name
                  for name, obj in scene.objects.items()}
    require(len(object_map) == len(bindings), 'NATIVE_OBJECT_ID_COLLISION')
    environment = {'packages': versions, 'python': sys.version, 'platform': platform.platform(),
                   'variant': mi.variant(), 'threads': 1, 'material_bindings': bindings,
                   'native_object_id_to_surface_name': object_map,
                   'source_git_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                   'utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    writej(out / 'ENVIRONMENT.json', environment)
    return CR, mi, scene, setup, solver, dictionaries, tx, rx, freq, source, SI, environment

def solve_one(CR, solver, scene, cfg, freq, fi, banks, tx, rx):
    global LAST_NATIVE_RETURN
    CR.set_bin(scene, banks, tx, rx, fi, float(freq[fi]))
    raw = solver(scene, **cfg)
    tau = np.asarray(raw.tau, dtype=np.float64).reshape(-1)
    n = len(tau)
    require(n > 0, 'NATIVE_PATH_MISSING')
    a = (np.asarray(raw.a[0]) + 1j * np.asarray(raw.a[1])).astype(np.complex128).reshape(2, 2, n)
    LAST_NATIVE_RETURN = {'fi': np.array(fi), 'max_depth': np.array(cfg['max_depth']),
                          'tau_s': tau, 'a': a}
    require(np.isfinite(tau).all() and np.isfinite(a).all(), 'NONFINITE_NATIVE_PATH')
    inter = np.asarray(raw.interactions).reshape(-1, n).astype(np.int8)
    objects = np.asarray(raw.objects).reshape(-1, n).astype(np.int64)
    h = (a * np.exp(-2j * np.pi * float(freq[fi]) * tau)[None, None, :]).sum(axis=-1)
    return h, tau, a, inter, objects

def fd_check(source, state, case):
    pred, jac, d0 = source.batch(state[None], case, return_diagnostics=True)
    records = []
    for axis in range(3):
        eps = 1e-5
        xp, xm = state.copy(), state.copy()
        xp[axis] += eps
        xm[axis] -= eps
        yp, _, dp = source.batch(xp[None], case, return_diagnostics=True)
        ym, _, dm = source.batch(xm[None], case, return_diagnostics=True)
        stable = all(np.array_equal(d0[k], d[k]) for k in ['tap', 'strong_port', 'cells'] for d in [dp, dm])
        fd = (yp[0, 1] - ym[0, 1]) / (2 * eps)
        err = abs(float(fd - jac[0, 1, axis]))
        rel = err / max(abs(float(jac[0, 1, axis])), 1e-30)
        passed = err <= 2e-5 or (abs(jac[0, 1, axis]) > 1e-6 and rel <= 1e-4)
        records.append({'axis': axis, 'stable': stable, 'analytic': float(jac[0, 1, axis]),
                        'fd': float(fd), 'abs_error': err, 'relative_error': rel,
                        'status': ('PASS' if passed else 'FAIL') if stable else 'BOUNDARY_NOT_FD_PASS'})
    return pred[0], jac[0], d0, records

def acquire_pose(c, row, engine, out):
    global PARTIAL_STATE, LAST_NATIVE_RETURN
    CR, mi, scene, setup, solver, banks, tx, rx, freq, source, SI, env = engine
    pose = int(row['pose_id'])
    state = np.array([float(row['x']), float(row['y']), np.radians(float(row['yaw_body_deg'])), 0.])
    xyz = setup.robot_position(state[0], state[1])
    scene.receivers['rx'].position = mi.Point3f(*xyz.tolist())
    scene.receivers['rx'].orientation = mi.Point3f(*CR.euler(setup.robot_rotation(float(row['yaw_body_deg']))))
    case = {'anchor': [10., 0., 2.65], 'robot_z_m': .45, 'mount_deg': 0.}
    ref = source.physical_h_col(state[None], case)[0]
    independent = SI.direct(source.banks, xyz[None], np.array([float(row['yaw_body_deg'])]), case['anchor'])[0, :, :, 0]
    internal = float(np.linalg.norm(ref - independent) / np.linalg.norm(independent))
    require(internal <= c['tolerances']['source_direct_relative_max'], 'SOURCE_INTERNAL_PARITY')
    pred, jac, diag, fd = fd_check(source, state, case)
    require(all(x['status'] != 'FAIL' for x in fd), 'SOURCE_STABLE_JACOBIAN_FAILED')
    payload = {'freq_hz': freq, 'source_physical_h': ref, 'source_independent_h': independent,
               'source_model_h': pred, 'source_model_H': jac, 'pose_id': np.array(pose),
               't_s': np.array(float(row['t_s'])), 'xyz_m': xyz, 'psi_rad': np.array(state[2]),
               'anchor_xyz_m': setup.anchor_position}
    started = time.monotonic()
    delay_error = 0.
    full_direct = []
    full_direct_parity = []
    data = {}
    for mode in ['los', 'full']:
        data[mode] = {'H': np.empty((N, 2, 2), np.complex128), 'offsets': [0],
                      'tau': [], 'a': [], 'inter': [], 'objects': [], 'counts': []}
    PARTIAL_STATE = {'pose_id': pose, 'payload': payload, 'data': data}
    LAST_NATIVE_RETURN = None
    for fi in range(N):
        for mode in ['los', 'full']:
            h, tau, a, inter, objects = solve_one(CR, solver, scene, c['rf']['solver_' + mode], freq, fi, banks, tx, rx)
            d = data[mode]
            d['H'][fi] = h
            d['tau'].append(tau)
            d['a'].append(a)
            d['inter'].append(inter)
            d['objects'].append(objects)
            d['offsets'].append(d['offsets'][-1] + len(tau))
            d['counts'].append(len(tau))
            geometric_delay = np.linalg.norm(xyz - setup.anchor_position) / C
            if mode == 'los':
                require(len(tau) == 1, 'NATIVE_LOS_NOT_SINGLE_PATH')
                delay_error = max(delay_error, float(np.max(abs(tau - geometric_delay))))
            else:
                # A direct path has zero interactions and matches geometric delay.
                direct = (np.count_nonzero(inter, axis=0) == 0) & (abs(tau - geometric_delay) <= c['tolerances']['los_delay_abs_s'])
                full_direct.append(int(direct.sum()))
                if direct.sum() == 1:
                    j = int(np.flatnonzero(direct)[0])
                    direct_h = a[:, :, j] * np.exp(-2j * np.pi * float(freq[fi]) * tau[j])
                    full_direct_parity.append(float(np.linalg.norm(direct_h - data['los']['H'][fi]) /
                                                    np.linalg.norm(data['los']['H'][fi])))
        if fi in [0, 64, 128, 192, 256]:
            print(json.dumps({'pose_id': pose, 'fi': fi, 'elapsed_s': round(time.monotonic() - started, 3),
                              'full_paths': data['full']['counts'][-1]}), flush=True)
    metrics = {'pose_id': pose, 't_s': float(row['t_s']), 'phase': row['phase'],
               'source_direct_relative': internal, 'los_delay_abs_s': delay_error,
               'full_unique_direct_bins': int(np.sum(np.asarray(full_direct) == 1)),
               'full_direct_vs_separate_los_relative_max': max(full_direct_parity) if full_direct_parity else None,
               'source_model_range_m': float(pred[0]), 'source_model_s': float(pred[1]),
               'source_detector_range_m': float(diag['native_range'][0]),
               'source_tap': int(diag['tap'][0]), 'source_strong_port': int(diag['strong_port'][0]),
               'fd': fd, 'acquisition_seconds': time.monotonic() - started}
    for mode, d in data.items():
        ob, cir = observer(d['H'])
        original = SI.O.observe(d['H'][None], freq, None, None)
        delta = max(abs(ob['r_m'] - float(original['range_m'][0])), abs(ob['s'] - float(original['s'][0])))
        require(delta <= c['tolerances']['observer_abs'] and ob['tap'] == int(original['index'][0]), 'OBSERVER_PARITY')
        payload['H_' + mode] = d['H']
        payload['CIR_' + mode] = cir
        payload[mode + '_path_offsets'] = np.asarray(d['offsets'], dtype=np.int64)
        payload[mode + '_tau_s'] = np.concatenate(d['tau'])
        payload[mode + '_a'] = np.concatenate(d['a'], axis=-1)
        payload[mode + '_interactions'] = np.concatenate(d['inter'], axis=-1)
        payload[mode + '_objects'] = np.concatenate(d['objects'], axis=-1)
        payload[mode + '_path_counts'] = np.asarray(d['counts'], dtype=np.int32)
        metrics[mode] = {**ob, 'observer_recompute_abs': delta, 'min_paths': int(min(d['counts'])), 'max_paths': int(max(d['counts']))}
    metrics['native_source_complex_relative'] = float(np.linalg.norm(data['los']['H'][:, :, 0] - ref) / np.linalg.norm(data['los']['H'][:, :, 0]))
    metrics['native_source_s_abs'] = abs(metrics['los']['s'] - float(pred[1]))
    metrics['native_source_tap_mismatch'] = int(metrics['los']['tap'] != metrics['source_tap'])
    metrics['native_source_port_mismatch'] = int(metrics['los']['strong_port'] != metrics['source_strong_port'])
    metrics['native_source_detector_range_abs'] = abs(metrics['los']['r_m'] - metrics['source_detector_range_m'])
    metrics['max_rss_mib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    dest = out / ('pose_%04d.npz' % pose)
    require(not dest.exists(), 'APPEND_ONLY_OUTPUT_COLLISION')
    np.savez_compressed(dest, **payload)
    metrics['raw_file'] = dest.name
    metrics['raw_sha256'] = sha(dest)
    writej(out / ('pose_%04d.json' % pose), metrics)
    PARTIAL_STATE = None
    LAST_NATIVE_RETURN = None
    return metrics

def preserve_partial(out):
    """Keep every completed native bin if a later check or solver call fails."""
    if PARTIAL_STATE is None:
        return None
    state = PARTIAL_STATE
    arrays = dict(state['payload'])
    counts = {}
    for mode, data in state['data'].items():
        n = len(data['counts'])
        counts[mode] = n
        arrays['H_' + mode + '_completed_bins'] = data['H'][:n].copy()
        arrays[mode + '_path_offsets'] = np.array(data['offsets'], dtype=np.int64)
        if n:
            arrays[mode + '_tau_s'] = np.concatenate(data['tau'])
            for key in ['a', 'inter', 'objects']:
                arrays[mode + '_' + key] = np.concatenate(data[key], axis=-1)
    if LAST_NATIVE_RETURN is not None:
        for key, value in LAST_NATIVE_RETURN.items():
            arrays['last_native_return_' + key] = value
    dest = pathlib.Path(out) / ('pose_%04d_FAILURE_PARTIAL.npz' % state['pose_id'])
    np.savez_compressed(dest, **arrays)
    return {'path': dest.name, 'sha256': sha(dest), 'completed_bins': counts,
            'not_complete_rf': True, 'never_allowed_as_paired917_input': True}

def run_canary(args):
    contract, rows = load_contract(args.contract)
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ids = contract['canary']['pose_ids']
    require(len(ids) >= 8 and len(set(ids)) == len(ids), 'INVALID_CANARY_UNIVERSE')
    engine = initialize(contract, args.banks, out)
    records = []
    started = time.monotonic()
    for i in ids:
        records.append(acquire_pose(contract, rows[i], engine, out))
        r = records[-1]
        t = contract['tolerances']
        # Stop expansion immediately on a complete per-pose physics failure.
        failed = (r['native_source_complex_relative'] > t['native_complex_relative_max'] or
                  r['native_source_s_abs'] > t['native_s_abs_max'] or
                  r['native_source_tap_mismatch'] != 0 or r['native_source_port_mismatch'] != 0 or
                  r['los_delay_abs_s'] > t['los_delay_abs_s'] or r['full_unique_direct_bins'] != N or
                  r['full_direct_vs_separate_los_relative_max'] is None or
                  r['full_direct_vs_separate_los_relative_max'] > t['full_direct_relative_max'])
        if failed:
            break
    rel = np.array([r['native_source_complex_relative'] for r in records])
    se = np.array([r['native_source_s_abs'] for r in records])
    tol = contract['tolerances']
    checks = {'complete_8_preselected_poses': len(records) == len(ids),
              'complex_max': bool(rel.max() <= tol['native_complex_relative_max']),
              'complex_rms': bool(np.sqrt(np.mean(rel ** 2)) <= tol['native_complex_relative_rms']),
              's_max': bool(se.max() <= tol['native_s_abs_max']),
              's_rmse': bool(np.sqrt(np.mean(se ** 2)) <= tol['native_s_rmse']),
              'tap_exact': all(r['native_source_tap_mismatch'] == 0 for r in records),
              'port_exact': all(r['native_source_port_mismatch'] == 0 for r in records),
              'delay': all(r['los_delay_abs_s'] <= tol['los_delay_abs_s'] for r in records),
              'full_direct_present': all(r['full_unique_direct_bins'] == N for r in records),
              'full_direct_los_parity': all(r['full_direct_vs_separate_los_relative_max'] is not None and
                                          r['full_direct_vs_separate_los_relative_max'] <= tol['full_direct_relative_max'] for r in records),
              'source_internal': all(r['source_direct_relative'] <= tol['source_direct_relative_max'] for r in records),
              'stable_jacobian': all(q['status'] != 'FAIL' for r in records for q in r['fd'])}
    seconds = [r['acquisition_seconds'] for r in records]
    qa = {'contract_id': contract['contract_id'], 'status': 'PASS' if all(checks.values()) else 'HOLD_RF_PARITY',
          'contract_sha256': sha(args.contract), 'source_git_sha': engine[-1]['source_git_sha'],
          'canary_pose_ids': ids, 'completed_pose_ids': [r['pose_id'] for r in records], 'checks': checks,
          'metrics': {'complex_max': float(rel.max()), 'complex_rms': float(np.sqrt(np.mean(rel ** 2))),
                      's_max': float(se.max()), 's_rmse': float(np.sqrt(np.mean(se ** 2))),
                      'tap_mismatches': sum(r['native_source_tap_mismatch'] for r in records),
                      'port_mismatches': sum(r['native_source_port_mismatch'] for r in records)},
          'measured_cost': {'canary_elapsed_s': time.monotonic() - started,
                            'median_pose_seconds': float(np.median(seconds)), 'max_pose_seconds': float(max(seconds)),
                            'projected_917_pose_cpu_hours_median': float(np.median(seconds) * 917 / 3600),
                            'projected_917_pose_cpu_hours_max': float(max(seconds) * 917 / 3600),
                            'max_rss_mib': max(r['max_rss_mib'] for r in records)},
          'phase_or_gain_fit': False, 'raw_retained': True, 'scientific_supported': False,
          'independent_audit': 'PENDING', 'records': records}
    writej(out / '03_RF_CANARY_QA.json', qa)
    print(json.dumps({'status': qa['status'], 'metrics': qa['metrics'], 'cost': qa['measured_cost']}), flush=True)
    return 0 if qa['status'] == 'PASS' else 2

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--contract', required=True)
    ap.add_argument('--banks', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    try:
        return run_canary(args)
    except Exception as exc:
        out = pathlib.Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        partial = preserve_partial(out)
        writej(out / 'FAILURE.json', {'status': 'HOLD_RF_PARITY', 'exception': repr(exc),
               'retained_partial': partial,
               'traceback': traceback.format_exc(), 'contract_sha256': sha(args.contract),
               'source_git_sha': subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip()})
        traceback.print_exc()
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
