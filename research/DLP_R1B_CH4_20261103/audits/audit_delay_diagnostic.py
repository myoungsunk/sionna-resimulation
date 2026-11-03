#!/usr/bin/env python3
"""Offline diagnostic decomposition; never fits or corrects acceptance data."""
from __future__ import annotations
import datetime
import hashlib
import json
import pathlib
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
BASE = ROOT / 'research/DLP_R1B_CH4_20261103'
RUN = BASE / 'runs/P0_CANARY_V2'
OUT = BASE / 'audits/P0_DELAY_DIAGNOSTIC_INDEPENDENT.json'


def sha(path):
    with pathlib.Path(path).open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def main():
    records = []
    for pose in [0, 150, 221, 440, 458, 476, 696, 916]:
        path = RUN / ('pose_%04d.npz' % pose)
        with np.load(path, allow_pickle=False) as data:
            source_h = data['source_physical_h']
            native_h = data['H_los'][:, :, 0]
            coefficient = data['los_a'][:, 0, :].T
            frequency = data['freq_hz']
            delay = data['los_tau_s']
            geometric_delay = np.linalg.norm(data['xyz_m'] - np.array([10., 0., 2.65])) / 299792458.
            delta = delay - geometric_delay
            # All quantities are observed or determined by original geometry.
            # There is no estimated rotation, gain or phase alignment here.
            delay_component = source_h * np.expm1(-2j * np.pi * frequency[:, None] * delta[:, None])
            total_error = native_h - source_h
            remainder = total_error - delay_component
            source_coefficient = source_h * np.exp(2j * np.pi * frequency[:, None] * geometric_delay)
            coefficient_component = ((coefficient - source_coefficient) *
                                     np.exp(-2j * np.pi * frequency[:, None] * delay[:, None]))
            residual = total_error - delay_component - coefficient_component
            norm = np.linalg.norm(native_h)
            records.append({'pose_id': pose, 'raw_sha256': sha(path),
                'tau_error_mean_s': float(np.mean(delta)), 'tau_error_spread_s': float(np.ptp(delta)),
                'stored_tau_float32_round_trip_exact': bool(np.array_equal(delay, delay.astype(np.float32).astype(np.float64))),
                'native_source_relative_UNCHANGED_GATE_INPUT': float(np.linalg.norm(total_error) / norm),
                'known_delay_component_relative_DIAGNOSTIC_ONLY': float(np.linalg.norm(delay_component) / norm),
                'coefficient_remainder_relative_DIAGNOSTIC_ONLY': float(np.linalg.norm(remainder) / norm),
                'decomposition_reconstruction_relative': float(np.linalg.norm(residual) / norm),
                'predicted_delay_phase_rms_rad': float(np.sqrt(np.mean((2 * np.pi * frequency * delta) ** 2))),
                'observed_inner_product_phase_rad_DIAGNOSTIC_ONLY': float(np.angle(np.vdot(source_h, native_h)))})
    receipt = {'schema': 'DLP_R1B_CH4_INDEPENDENT_DELAY_DIAGNOSTIC_V1',
        'actor': '/root/r1_preflight_audit', 'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'bindings': {'audit_script_sha256': sha(__file__),
            'final_raw_audit_sha256': sha(BASE / 'audits/P0_CANARY_RAW_AUDIT_FINAL.json'),
            'contract_sha256': sha(BASE / '00_REQUEST_CONTRACT_FROZEN_V2.json')},
        'native_rt_calls': 0, 'fitted_parameters': 0, 'raw_data_modified': False,
        'thresholds_modified': False, 'acceptance_phase_alignment': False,
        'formulas': {'H_native': 'A_native * exp(-i 2pi f tau_native)',
            'H_source': 'A_source * exp(-i 2pi f tau_geometry)',
            'E_tau': 'H_source * (exp(-i 2pi f (tau_native-tau_geometry)) - 1)',
            'E_coefficient': '(A_native-A_source) * exp(-i 2pi f tau_native)',
            'identity': 'H_native-H_source = E_tau + E_coefficient'},
        'findings': {
            'all_stored_native_los_delays_float32_round_trip_exact': all(r['stored_tau_float32_round_trip_exact'] for r in records),
            'max_coefficient_remainder_relative': max(r['coefficient_remainder_relative_DIAGNOSTIC_ONLY'] for r in records),
            'max_decomposition_residual_relative': max(r['decomposition_reconstruction_relative'] for r in records),
            'interpretation': 'Known Native delay minus exact input-geometry delay accounts for the dominant complex mismatch. The coefficient remainder includes amplitude and intrinsic coefficient phase differences. Float32-compatible delays support a numerical-precision explanation; this alone does not isolate the exact runtime operation responsible.'},
        'acceptance': {'status': 'HOLD_RF_PARITY_UNCHANGED',
            'complex_rms': float(np.sqrt(np.mean([r['native_source_relative_UNCHANGED_GATE_INPUT'] ** 2 for r in records]))),
            'frozen_complex_rms_limit': 1e-4,
            'diagnostic_remainders_are_not_replacement_gate_metrics': True,
            'production_permitted': False}, 'records': records}
    if OUT.exists():
        raise FileExistsError('Append-only output already exists: ' + str(OUT))
    OUT.write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'output': str(OUT), 'sha256': sha(OUT), 'acceptance': receipt['acceptance']}))


if __name__ == '__main__':
    main()
