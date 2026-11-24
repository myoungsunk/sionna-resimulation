"""Build N1–N6 wheel, gyro, and initial-state inputs with the frozen M7 law."""

import argparse
import hashlib
import json
from pathlib import Path
import runpy

import numpy as np


M7_INPUTS_SHA256 = '505392cc3e3e233e60fd8eec87ebacaed14ec320295bd940bdb0b1a3084a3e47'
INPUT_INDEX_SHA256 = '6e6a0b8ec2d6d95e71694649f959af37f80b5ebec73d5857e19cf69d848b5ba0'
SENSOR_SOURCES = {
    'sensors': '2285db90b465e13f90c99d66ae0ba867602abc148a1b1ba0bc02a565e9681118',
    'sensor_v2': 'e74cd4657b9784f5a5ef06b6bbeae9bce807d1942ddc9046a1513186dde7be40',
}
EVALUATORS = {
    'R2': '90e4e2ad81a277290178ce50ba021ed2164ce2efcdf2b97908eb6104005da8c6',
    'R4': 'b5cd93a576c300b2ba371c3755e1ab9e1c8141a742206a8bd69014b16fd20f60',
    'R5': 'b7b3fa5ce18f22108657c409d474747eea54b1cb8a8455c476c3235246d65661',
}
CONDITIONS = ('B0', 'L2_GYRO_ARW')
SEEDS = (*range(10, 30), *range(70, 90))
ROUTE_COUNTS = dict(N1=953, N2=941, N3=1341, N4=1274, N5=918, N6=962)
STEP_S = 0.2


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(path, expected):
    if sha(path) != expected:
        raise ValueError(f'Input checksum mismatch: {path}')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def generate(t, ids, truth, distance, angle, seed, sensor, configs, initial):
    first, second = (sensor.generate(t, distance, angle, cfg, seed) for cfg in configs)
    c0, latent0 = first
    c2, latent2 = second
    for key in c0.keys() - {'dtheta_gyro'}:
        np.testing.assert_array_equal(c0[key], c2[key])
    for latent in (latent0, latent2):
        if np.any(latent['true_bias_rad_s']):
            raise ValueError('M7 B0/L2 reference requires zero true gyro bias')
    x0, p0 = initial(sensor, truth, seed)
    base = dict(t=t, pose_id=ids, dt=c0['dt_s'], ds=c0['ds_odom'], x0=x0, P0=p0)
    np.testing.assert_allclose(c2['dtheta_gyro'] - angle, 4*(c0['dtheta_gyro'] - angle), rtol=0, atol=1e-10)
    return tuple(dict(base, gy=c['dtheta_gyro']) for c in (c0, c2))


def check_references(directory, sensor, configs, initial):
    index_path = directory / 'INPUT_INDEX.json'
    verify(index_path, INPUT_INDEX_SHA256)
    index = read(index_path)
    results = []
    for route, digest in EVALUATORS.items():
        path = directory / f'{route}_B0_Full_10__evaluator.npz'
        verify(path, digest)
        with np.load(path, allow_pickle=False) as evaluator:
            t, ids, truth = (evaluator[key] for key in ('t', 'pose_id', 'truth'))
        distance, angle = sensor.motion_increments(t, truth, convention='legacy-euler')
        packets = generate(t, ids, truth, distance, angle, 10, sensor, configs, initial)
        for condition, packet in zip(CONDITIONS, packets):
            expected = directory / 'inputs' / condition / 'seed10' / f'{route}_online.npz'
            verify(expected, index[condition]['10'][route]['sha256'])
            with np.load(expected, allow_pickle=False) as archive:
                for key, values in packet.items():
                    np.testing.assert_allclose(values, archive[key], atol=1e-10, rtol=0)
                error = max(float(np.max(np.abs(values - archive[key]))) for key, values in packet.items())
            results.append(dict(route=route, condition=condition, seed=10, max_abs_delta=error,
                                reference_sha256=sha(expected)))
    return results


def commanded_motion(samples):
    t = np.array([row['t'] for row in samples], dtype=np.float64)
    truth = np.array([[row['x'], row['y'], row['yaw']] for row in samples], dtype=np.float64)
    distance = np.r_[0., [row['v'] * STEP_S for row in samples[:-1]]]
    angle = np.r_[0., [row['omega'] * STEP_S for row in samples[:-1]]]
    np.testing.assert_allclose(np.diff(t), STEP_S, rtol=0, atol=1e-9)
    yaw_delta = (np.diff(truth[:, 2]) + np.pi) % (2*np.pi) - np.pi
    np.testing.assert_allclose(yaw_delta, angle[1:], rtol=0, atol=1e-9)
    measured = np.diff(truth[:, :2], axis=0)
    yaw_after = truth[1:, 2]
    planned = distance[1:, None] * np.column_stack((np.cos(yaw_after), np.sin(yaw_after)))
    np.testing.assert_allclose(measured, planned, rtol=0, atol=1e-9)
    yaw_before = truth[:-1, 2]
    lateral = -measured[:, 0]*np.sin(yaw_before) + measured[:, 1]*np.cos(yaw_before)
    checks = dict(max_commanded_delta_xy_m=float(np.max(np.abs(measured-planned))),
                  max_commanded_delta_yaw_rad=float(np.max(np.abs(yaw_delta-angle[1:]))),
                  max_lateral_start_heading_m=float(np.max(np.abs(lateral))))
    return t, truth, distance, angle, checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_root', type=Path)
    parser.add_argument('reference', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    m7_script = args.reference / 'm7_inputs.py'
    verify(m7_script, M7_INPUTS_SHA256)
    m7 = runpy.run_path(str(m7_script))
    sensor_files = {f'src/qclean_uwb/drivesim/{name}.py': dict(
        path=str(args.reference / f'{digest[:12]}_{name}.py'), sha256=digest)
        for name, digest in SENSOR_SOURCES.items()}
    sensor = m7['_sensor'](sensor_files)
    configs = m7['paired_configs'](sensor, dict(b0_N_deg_sqrt_s=.015, l2_N_deg_sqrt_s=.060))
    initial = m7['_initial']
    reference_checks = check_references(args.reference, sensor, configs, initial)
    inputs = args.run_root / 'inputs'
    contract = read(inputs / 'RUN_CONTRACT.json')
    samples_path = inputs / 'SAMPLES.json'
    verify(samples_path, contract['input_sha256']['SAMPLES.json'])
    samples = read(samples_path)
    if len(samples) != sum(ROUTE_COUNTS.values()) or len(samples) != contract['expected_observations']:
        raise ValueError('N1–N6 source timeline row count differs')
    args.output.mkdir(exist_ok=False)
    outputs, geometry_checks = {}, {}
    for route, count in ROUTE_COUNTS.items():
        rows = [sample for sample in samples if sample['route'] == route]
        if [sample['sequence_index'] for sample in rows] != list(range(count)):
            raise ValueError(f'Invalid sequence index: {route}')
        ids = np.arange(count, dtype=np.int64)
        t, truth, distance, angle, checks = commanded_motion(rows)
        geometry_checks[route] = checks
        truth_path = args.output / f'{route}_evaluator.npz'
        with truth_path.open('xb') as handle:
            np.savez_compressed(handle, t=t, pose_id=ids, truth=truth)
        outputs[truth_path.name] = sha(truth_path)
        for seed in SEEDS:
            packets = generate(t, ids, truth, distance, angle, seed, sensor, configs, initial)
            for condition, packet in zip(CONDITIONS, packets):
                path = args.output / condition / f'seed{seed}' / f'{route}_controls.npz'
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open('xb') as handle:
                    np.savez_compressed(handle, **packet)
                outputs[path.relative_to(args.output).as_posix()] = sha(path)
    report = dict(status='PASS', controls=2*len(SEEDS)*len(ROUTE_COUNTS), seeds=SEEDS,
                  startup_planning='Use recorded v and omega; verify positions against end-of-step heading',
                  numpy_version=np.__version__, samples_sha256=sha(samples_path),
                  m7_inputs_sha256=M7_INPUTS_SHA256, m7_input_index_sha256=INPUT_INDEX_SHA256,
                  sensor_source_sha256=SENSOR_SOURCES, sensor_config={key: cfg.manifest() for key, cfg in zip(CONDITIONS, configs)},
                  source_sha256=sha(Path(__file__)), geometry_checks=geometry_checks, reference_checks=reference_checks,
                  output_sha256=outputs)
    with (args.output / 'CONTROLS_REPORT.json').open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps(dict(status='PASS', controls=report['controls'], baseline_cases=len(reference_checks))))


if __name__ == '__main__':
    main()
