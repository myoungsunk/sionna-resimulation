"""Authenticate anchor A +45 packets and score cells with anchor-specific frozen MB inputs."""

import argparse
import csv
import gzip
from pathlib import Path
import sys

import run_compare_mount45 as compare
from run_diag_mount45 import DIAG
from run_l2_mount45 import OUT as L2, stem as l2_stem
from check_observer import LIMITS

import numpy as np


source = compare.mount
ROOT, OUT = compare.ROOT, compare.ROOT / 'anchor_a_retry'
LOCK = OUT / 'RUN_CONTRACT.json'
X1 = source.X1_LOCK.parent
MR = source.P2 / 'research/PJ_DS_GATED_20261021/results_murec/MR_SERIES.csv.gz'
SPEC = source.SPEC | {'anchor': (4., 0., 2.65)}


def freeze():
    failed_lock = ROOT / 'anchor_a/RUN_CONTRACT.json'
    failed_receipt = ROOT / 'anchor_a/execution/EXECUTION.json'
    failed = source.load(failed_receipt)
    assert failed['status'] == 'FAIL_EXECUTION' and failed['contract_sha256'] == source.sha(failed_lock)
    b0_receipt = source.OUT / 'PARITY_RESULTS.json'
    l2_receipt = L2 / 'PACKET_PARITY.json'
    assert source.load(b0_receipt)['status'] == source.load(l2_receipt)['status'] == 'PASS'
    x1_index, v01b_manifest = X1 / 'OUTPUT_SHA256.json', source.FULL / 'SHA256SUMS.txt'
    legacy = {Path(x['path']).name: x['sha256'] for x in source.load(source.X1_LOCK)['files']}
    x1 = {x['path']: x['sha256'] for x in source.load(x1_index)['files']}
    full = {s[1].lstrip('*'): s[0] for line in v01b_manifest.read_text().splitlines()
            if len(s := line.split(maxsplit=1)) == 2}
    los_receipt = source.load(source.LOS_CHECK)

    def lookup_los(path):
        rows = los_receipt.get('assets', los_receipt.get('files', los_receipt.get('results', [])))
        row, = (x for x in rows if x.get('file') == path.name)
        return next(row[k] for k in ('actual_sha256', 'local_sha256', 'sha256') if k in row)

    base_contract = source.load(ROOT / 'comparison/RUN_CONTRACT.json')
    structural = ROOT / 'structure/RUN_CONTRACT.json'
    inputs = dict(base_contract['inputs_sha256'])
    inputs.update({str(p): source.sha(p) for p in (Path(__file__), v01b_manifest, source.LOS_CHECK, source.X1_LOCK,
        x1_index, b0_receipt, l2_receipt, structural, failed_receipt, failed_lock, DIAG / 'structure_sc_ki/structure.py',
        DIAG / 'd0_d5.py', ROOT / 'check_observer.py', source.STUDY / 'prepare_s2_extensions.py', compare.ORIGINAL / 'compare_dr.py')})
    inputs[str(MR)] = legacy[MR.name]
    inputs[str(source.OUT / 'e0_reference.py')] = source.load(b0_receipt)['source_sha256']['e0_reference.py']
    cases = {}
    for route in source.ROWS:
        full_name, los_name = f'H_{route}_aA_m45.npy', f'H_LoS_{route}_aA_m45.npy'
        full_path = (source.BLOCK / 'FULL_RF' if route == 'R2' else source.FULL) / full_name
        los_path = (source.BLOCK if route == 'R2' else source.LOS) / los_name
        inputs[str(full_path)] = legacy[full_name] if route == 'R2' else full[full_name]
        inputs[str(los_path)] = legacy[los_name] if route == 'R2' else lookup_los(los_path)
        case = {'Full': str(full_path), 'LoS': str(los_path), 'bias': {}}
        for bias in ('B0', 'L2'):
            base_path = (source.OUT / f'{source.stem(route)}__online.npz' if bias == 'B0' else
                         L2 / f'packets/{l2_stem(route)}__online.npz')
            if bias == 'L2':
                l2_hash = source.load(L2 / 'comparison/RUN_CONTRACT.json')['inputs_sha256'][str(base_path)]
                inputs[str(base_path)] = l2_hash
            references = {'controls': str(base_path), 'x1': None}
            key = f'x1/{route}_aA_m45_{bias}.npz'
            if key in x1:
                assert route == 'R2', key
                inputs[str(X1 / key)], references['x1'] = x1[key], str(X1 / key)
            case['bias'][bias] = references
        cases[route] = case
    for path, sha in inputs.items():
        source.checked(Path(path), sha)
    OUT.mkdir()
    source.write(LOCK, {'question': 'G1-CHAR002-S2-MOUNT45/ANCHOR-A', 'role': 'IMPLEMENTER',
        'frozen_utc': source.utc(), 'geometry': SPEC, 'cases': cases, 'inputs_sha256': inputs,
        'bias_order': ['B0', 'L2'], 'structure_contract': str(structural),
        'los_limits': {k: LIMITS[k] for k in ('los_s_p90_abs', 'los_tap_mismatches')},
        'retry': 'Check the common gate on RF update arms. The prediction-only DR trace has no RF gate field.',
        'scope': 'A R2 own X1 MB inputs, same bias-matched B controls. A R4/R5 RF and O30 only. SC/KI use frozen B kernel and sigma.'})


def verify_los(truth, los, model, observation, limits):
    error, mismatch = [], 0
    x = np.column_stack((truth, np.zeros(len(truth))))
    df = model.freqs[1] - model.freqs[0]
    for i in range(0, len(x), 64):
        h, _, diag = model.batch(x[i:i + 64], SPEC, gradient=False, return_diagnostics=True)
        arrival = observation.first_path_batch(observation.cir_batch(los[i:i + 64]), df)
        error.extend(np.abs(h[:, 1] - arrival['s']))
        mismatch += int(np.count_nonzero(diag['tap'] != arrival['index']))
    p90 = float(np.quantile(error, .9))
    return {'p90_abs_s': p90, 'tap_mismatches': mismatch,
            'pass': p90 <= limits['los_s_p90_abs'] and mismatch <= limits['los_tap_mismatches']}


def run():
    lock = source.load(LOCK)
    for path, sha in lock['inputs_sha256'].items():
        source.checked(Path(path), sha)
    sys.path[:0] = [str(compare.S2_RUN / 'executed_source_2a_2b'), str(compare.ORIGINAL), str(source.NATIVE / 'src'),
                    str(DIAG), str(DIAG / 'structure_sc_ki')]
    from compare_dr import replay_dr
    from d0_d5 import replay_sigma
    from e0_reference import reference
    from metrics_s2 import _summarize
    from prepare_s2_extensions import native_measurements
    from qclean_uwb.drivesim import observation
    from qclean_uwb.fp_sc.e0_baseline import load_original_model
    from replay_s2 import learned_replay, validate_trace
    from run_s2 import models, oracle_models
    from structure import replay_structure
    from verify_s2 import from_trace

    core, online, model, _ = load_original_model(source.NATIVE)
    train = models(source.load(ROOT / 'training/FIT.json'))
    yaw = source.load(ROOT / 'training/FIT_S2.json')
    cell, = [x for x in source.load(Path(lock['structure_contract']))['cells'] if x['route'] == 'R2']
    sigma, kernel = np.array(cell['sigma_b']), cell['kernel']
    with gzip.open(MR, 'rt', encoding='utf-8', newline='') as handle:
        mr = {(row['bias'], int(row['pose_id'])): (float(row['t_s']), float(row['abs_ds1']))
              for row in csv.DictReader(handle) if row['case'] == 'R2_aA_m45' and row['channel'] == 'full'}
    dest = OUT / 'execution'
    dest.mkdir()
    result, los_checks = {}, {}
    execution = {'command': [sys.executable, *sys.argv], 'started_utc': source.utc(),
                 'contract_sha256': source.sha(LOCK)}
    try:
        for bias in lock['bias_order']:
            for route, route_data in lock['cases'].items():
                target = f'A_{bias}_{route}'
                case = route_data['bias'][bias]
                b = source.npz(Path(case['controls']))
                rf, los = [np.load(route_data[key], mmap_mode='r', allow_pickle=False)[b['pose_id'], :, :, 0]
                           for key in ('Full', 'LoS')]
                observation_rows = native_measurements(observation, rf)
                if observation_rows.shape != (source.ROWS[route], 2) or not np.isfinite(observation_rows).all():
                    raise ValueError(f'Invalid O30 packet set: {target}')
                evaluator = source.npz(source.OUT / f'{source.stem(route)}__evaluator.npz')
                truth = evaluator['truth']
                for key in ('pose_id', 't'):
                    np.testing.assert_array_equal(b[key], evaluator[key])
                packet = {key: b[key] for key in ('t', 'pose_id', 'ds', 'gy', 'dt', 'x0')}
                packet.update(Hrf=rf, clean_Hrf=rf, z=observation_rows)
                source.save_npz(dest / f'{target}__evaluator.npz', evaluator | {'clean_H': los})
                path = dest / f'{target}__observations.npz'
                source.save_npz(path, packet)
                if route not in los_checks:
                    los_checks[route] = verify_los(truth, los, model, observation, lock['los_limits'])
                result[target] = {'status': 'PACKET_ONLY_NO_FROZEN_A_MB', 'n': len(rf), 'los': los_checks[route]}
                if not los_checks[route]['pass']:
                    result[target]['status'] = 'LOS_GEOMETRY_GATE_FAILED'
                    continue
                if not case['x1']:
                    continue
                ref = source.npz(Path(case['x1']))
                np.testing.assert_array_equal(ref['pose_id'], b['pose_id'])
                np.testing.assert_allclose(ref['t_s'], b['t'], atol=1e-12, rtol=0)
                np.testing.assert_allclose(ref['truth_scoring_only'], truth, atol=1e-12, rtol=0)
                parity_z = source.evaluate_parity({'z': ref['z']}, {'z': observation_rows})
                bb, mb = [list(ref['names']).index(k) for k in ('BB', 'MB')]
                series = np.array([mr[bias, int(i)] for i in b['pose_id']])
                np.testing.assert_allclose(series[:, 0], b['t'], atol=1e-12, rtol=0)
                packet.update(muBASE=ref['mu'][:, bb], muMB=ref['mu'][:, mb], R=ref['R'][:, bb],
                              P0=ref['Pprior'][0, bb], D=series[:, 1])
                controls = source.controls(packet)
                e0 = online.replay(packet, controls, 'W0', core, model, SPEC)
                validate_trace(e0)
                parity = source.evaluate_parity({k: e0[k] for k in compare.STATE_KEYS}, reference(model, SPEC, packet))
                mask = e0['mask']
                packet.update(prior=e0['prior'], Pprior=e0['Pprior'])
                packet.update({'trace_' + key: e0[key] for key in source.TRACE_FIELDS})
                source.save_npz(dest / f'{target}__online.npz', packet)
                dr, _ = replay_dr(packet, e0, core, online, source.TOL)
                traces = {'DR': dr, 'E0': e0}
                for arm, (r, s) in compare.FAMILIES.items():
                    traces[arm] = learned_replay(packet, controls, mask, core, online, model, SPEC, arm, train[r], train[s], yaw)
                rf_fit, pol_fit, _ = oracle_models(truth, observation_rows, model, SPEC, compare.TRAIN_CODE)
                traces['E5'] = learned_replay(packet, controls, mask, core, online, model, SPEC, 'E5', rf_fit, pol_fit, yaw)
                args = packet, controls, mask, core, online, model, SPEC, sigma
                traces['LORO'] = replay_sigma(*args)
                for arm in ('SC', 'KI'):
                    traces[arm] = replay_structure(*args, kernel, arm=arm)
                for arm, trace in traces.items():
                    if arm != 'DR':
                        np.testing.assert_array_equal(trace['mask'], mask)
                    np.testing.assert_array_equal(np.isfinite(trace['P']), True)
                    assert np.linalg.eigvalsh(trace['P']).min() > 0
                    source.save_npz(dest / f'{target}_{arm}_trace.npz', trace | {'pose_id': b['pose_id'], 't': b['t']})
                result[target] = {'status': 'ELIGIBLE_R2_DIAGNOSTIC', 'n': len(mask), 'accepted': int(mask.sum()),
                    'z_parity': parity_z, 'E0_parity': parity, 'los': los_checks[route],
                    'metrics': {k: _summarize(from_trace(x, truth)) for k, x in traces.items()}}
        source.write(dest / 'RESULTS.json', result)
        execution.update(status='PASS_EXECUTION', exit_code=0)
    except Exception as exc:
        execution.update(status='FAIL_EXECUTION', exit_code=1, reason=repr(exc))
        raise
    finally:
        execution['finished_utc'] = source.utc()
        execution['outputs'] = {p.name: source.sha(p) for p in dest.iterdir()}
        source.write(dest / 'EXECUTION.json', execution)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('freeze', 'run'))
    {'freeze': freeze, 'run': run}[parser.parse_args().stage]()
