"""Run the available R2 cells of the frozen mount +45 V7 diagnostic."""

import argparse
import inspect
import sys
from pathlib import Path

import numpy as np

from run_diag_mount45 import DIAG, ROOT, source


OUT = ROOT / 'v7_r2'
LOCK = OUT / 'RUN_CONTRACT.json'
KS = ROOT / 'ks'
A = ROOT / 'anchor_a_final'
B0 = source.OUT
L2 = ROOT / 'l2'
L2_COMP = L2 / 'comparison'
V7_SOURCE = DIAG / 'continuation_ks/ks_diagnostics.py'


def freeze():
    files = {}

    def bind(path, digest=None):
        files[str(path)] = source.sha(path) if digest is None else digest
        source.checked(path, files[str(path)])
        return str(path)

    def parent(directory, receipt_name='EXECUTION.json', contract_key='contract_sha256'):
        receipt_path = directory / receipt_name
        receipt = source.load(receipt_path)
        assert receipt['status'].startswith('PASS') and receipt.get('exit_code', 0) == 0
        contract_dir = directory.parent if directory.name == 'execution' else directory
        bind(contract_dir / 'RUN_CONTRACT.json', receipt[contract_key])
        bind(receipt_path)
        return receipt

    parent_ks = parent(KS / 'execution')
    registration = source.load(KS / 'RUN_CONTRACT.json')
    bind(KS / 'execution/V7.json', parent_ks['outputs']['V7.json'])
    assert registration['rules']['V7_A_over_B'] == 2
    for record in registration['sources'] + registration['governance']:
        bind(Path(record['path']), record['sha256'])
    bind(Path(__file__))
    bind(ROOT / 'run_diag_mount45.py')

    a = parent(A / 'execution')
    a_contract = source.load(A / 'RUN_CONTRACT.json')
    a_results = source.load(Path(bind(A / 'execution/RESULTS.json', a['outputs']['RESULTS.json'])))
    l2 = parent(L2_COMP / 'execution')
    l2_contract = source.load(L2_COMP / 'RUN_CONTRACT.json')
    parity = source.load(Path(bind(L2 / 'PACKET_PARITY.json', l2_contract['parity_sha256'])))
    assert parity['status'] == 'PASS'
    b0 = parent(B0, 'PARITY_RESULTS.json')
    prior = source.load(ROOT / 'comparison/RUN_CONTRACT.json')
    for path, digest in prior['inputs_sha256'].items():
        if Path(path).is_relative_to(source.NATIVE):
            bind(Path(path), digest)
    diagnostic_lock = ROOT / 'diagnostics/RUN_CONTRACT.json'
    diagnostic = ROOT / 'diagnostics/d2/EXECUTION.json'
    d2 = source.load(diagnostic)
    assert d2['status'] == 'PASS_EXECUTION' and d2['exit_code'] == 0
    bind(diagnostic_lock, d2['run_contract_sha256'])
    bind(diagnostic)
    b0_d2 = bind(diagnostic.parent / 'B_B0_R2.npz', d2['outputs']['B_B0_R2.npz'])
    prior_metrics = source.STUDY / 'run_20261115_a/executed_source_2a_2b/metrics_s2.py'
    bind(prior_metrics, prior['inputs_sha256'][str(prior_metrics)])

    cells = {}
    for bias in ('B0', 'L2'):
        case = f'A_{bias}_R2'
        assert a_results[case]['status'] == 'ELIGIBLE_R2_DIAGNOSTIC'
        assert a_results[case]['E0_parity']['mask']['mismatches'] == 0
        for route in ('R4', 'R5'):
            assert a_contract['cases'][route]['bias'][bias]['x1'] is None
        x1 = a_contract['cases']['R2']['bias'][bias]['x1']
        bind(Path(x1), a_contract['inputs_sha256'][x1])
        cells[case] = {
            label: bind(A / 'execution' / name, a['outputs'][name])
            for label, name in {
                'packet': f'{case}__online.npz',
                'evaluator': f'{case}__evaluator.npz',
                'trace': f'{case}_E0_trace.npz',
            }.items()
        }
    cells['B_B0_R2'] = {
        label: bind(B0 / name, b0['routes']['R2']['output_sha256'][name])
        for label, kind in (('packet', 'online'), ('evaluator', 'evaluator'), ('trace', 'e0_trace'))
        for name in (f'{source.stem("R2")}__{kind}.npz',)
    }
    cells['B_L2_R2'] = {
        label: bind(path, l2_contract['inputs_sha256'][str(path)])
        for label, kind in (('packet', 'online'), ('evaluator', 'evaluator'), ('trace', 'e0_trace'))
        for path in (L2 / f'packets/R2_B_L2_m45_Full_10__{kind}.npz',)
    }
    bind(L2_COMP / 'execution/R2_E0_trace.npz', l2['outputs_sha256']['R2_E0_trace.npz'])
    lock = {
        'question': 'G1-INT-001/KS-TRANSFER/M45-V7-R2', 'role': 'IMPLEMENTER',
        'frozen_utc': source.utc(), 'evidence_commit': 'cba6a32fa3763012af8a0593960c0609ffbb456c',
        'scope': {'route': 'R2', 'bias': ['B0', 'L2'], 'mount_deg': 45., 'seed': 10},
        'classification': 'DIAGNOSTIC_ONLY', 'V7_A_over_B': registration['rules']['V7_A_over_B'],
        'cells': cells, 'D2_baseline': b0_d2, 'scorer': str(V7_SOURCE),
        'geometry': {'A': {k: a_contract['geometry'][k] for k in source.SPEC}, 'B': source.SPEC},
        'inputs_sha256': files,
        'boundary': 'V7 frozen scoring on R2 only. R4 polarization is primary and R5 range secondary. '
                    'Both remain blocked for A. No fitting, no new E0 gates, and no change to KS admission.',
    }
    OUT.mkdir()
    source.write(LOCK, lock)


def run():
    lock = source.load(LOCK)
    for path, digest in lock['inputs_sha256'].items():
        source.checked(Path(path), digest)
    sys.path[:0] = [str(V7_SOURCE.parent), str(source.STUDY / 'run_20261115_a/executed_source_2a_2b')]
    import ks_diagnostics
    from qclean_uwb.fp_sc.e0_baseline import load_original_model
    from replay_s2 import validate_trace

    assert Path(ks_diagnostics.__file__).resolve() == Path(lock['scorer']).resolve()
    # Bind the route list alone. Keep the original formula, block draws, and decisions.
    scorer = inspect.getsource(ks_diagnostics.v7)
    old = 'for route in ("R2", "R4", "R5"):'
    assert scorer.count(old) == 1
    scoped = vars(ks_diagnostics).copy()
    exec(compile(scorer.replace(old, 'for route in ("R2",):'), lock['scorer'], 'exec'), scoped)

    dest = OUT / 'execution'
    dest.mkdir()
    receipt = {'contract_sha256': source.sha(LOCK), 'started_utc': source.utc(),
               'command': [sys.executable, *sys.argv]}
    try:
        _, _, model, source_hashes = load_original_model(source.NATIVE)
        cases, grid = {}, {}
        for name, paths in lock['cells'].items():
            packet, evaluator, trace = [source.npz(Path(paths[k])) for k in ('packet', 'evaluator', 'trace')]
            validate_trace(trace)
            assert len(packet['t']) == source.ROWS['R2']
            for key in ('pose_id', 't'):
                np.testing.assert_array_equal(packet[key], evaluator[key])
                np.testing.assert_array_equal(packet[key], trace[key])
            for key in source.TRACE_FIELDS:
                np.testing.assert_array_equal(packet[f'trace_{key}'], trace[key])
            spec = lock['geometry'][name[0]]
            truth = evaluator['truth']
            expected, _ = model.batch(np.column_stack([truth, np.zeros(len(truth))]), spec, gradient=False)
            eps = packet['z'] - expected - packet['muMB']
            assert np.isfinite(eps).all()
            cases[name] = {'packet': packet, 'spec': spec, 'e0': trace, 'eps': eps}
            grid[name] = truth
        d2 = source.npz(Path(lock['D2_baseline']))
        b0 = cases['B_B0_R2']
        np.testing.assert_array_equal(d2['mask'], b0['e0']['mask'])
        np.testing.assert_allclose(b0['eps'], d2['truth_residual_r_s'], atol=1e-12, rtol=0)
        baseline_max_abs = float(np.max(np.abs(b0['eps'] - d2['truth_residual_r_s'])))

        for bias in lock['scope']['bias']:
            a_name, b_name = (f'{anchor}_{bias}_R2' for anchor in ('A', 'B'))
            np.testing.assert_array_equal(grid[a_name], grid[b_name])
            for field in ('ds', 'gy', 'dt', 'x0'):
                np.testing.assert_array_equal(cases[a_name]['packet'][field], cases[b_name]['packet'][field])
        result = scoped['v7'](cases, dest)
        assert set(result) == {'B0_R2', 'L2_R2'}
        for label, row in result.items():
            a, b = (cases[f'{anchor}_{label}'] for anchor in ('A', 'B'))
            use = a['e0']['mask'] & b['e0']['mask']
            assert row['n'] == int(np.count_nonzero(use)) > 0
            for anchor, case in (('A', a), ('B', b)):
                trace = case['e0']
                jac, variance = trace['H'][use, 1, 2], trace['Reff'][use, 1, 1]
                direct = np.dot(jac / variance, case['eps'][use, 1]) / np.sum(np.abs(jac) / np.sqrt(variance))
                np.testing.assert_allclose(direct, row['channels']['s_heading']['weighted_signed'][anchor],
                                           atol=1e-12, rtol=0)
        source.write(dest / 'V7_R2.json', {'status': 'PARTIAL_R2_ONLY', 'results': result,
                    'unavailable': ['B0_R4', 'B0_R5', 'L2_R4', 'L2_R5'],
                    'checks': {'B_B0_R2_D2_residual_max_abs': baseline_max_abs,
                               'packet_trace_grid': 'PASS', 'matched_pose_controls_truth': 'PASS',
                               'heading_weighted_sum': 'PASS', 'source_model_sha256': source_hashes}})
        receipt.update(status='PASS_EXECUTION', exit_code=0)
    except Exception as exc:
        receipt.update(status='FAIL_EXECUTION', exit_code=1, reason=repr(exc))
        raise
    finally:
        receipt['finished_utc'] = source.utc()
        receipt['outputs'] = {p.name: source.sha(p) for p in dest.iterdir()}
        source.write(dest / 'EXECUTION.json', receipt)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('freeze', 'run'))
    {'freeze': freeze, 'run': run}[parser.parse_args().stage]()
