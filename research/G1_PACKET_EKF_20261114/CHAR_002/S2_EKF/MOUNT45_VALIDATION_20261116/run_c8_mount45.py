"""Replay the frozen mount +45 V3 result and independently score the resulting states."""

import argparse
import importlib.util
from pathlib import Path
import sys

# The runner is launched in isolated Python mode. Import only its explicit local inputs.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_ks_mount45 import DIAG, LOCK as KS_LOCK, OUT as KS, ROOT, check, load_bound, receipt, role_receipt, source


OUT = ROOT / 'c8'
LOCK = OUT / 'RUN_CONTRACT.json'
VERIFIER = DIAG / 'continuation_checks_c1_c8/c8/run_c8.py'


def freeze():
    paths = role_receipt(KS / 'execution', KS_LOCK)
    decision = source.load(KS / 'execution/V3.json')
    OUT.mkdir()
    source.write(LOCK, {
        'question': 'G1-INT-001/KS-C8/M45-B-B0', 'role': 'IMPLEMENTER_REPLAY',
        'frozen_utc': source.utc(), 'arms': list(decision['decisions']),
        'scope': 'Fresh isolated interpreter and output directory. Same host, authenticated input and frozen source.',
        'inputs': list(map(receipt, (Path(__file__), VERIFIER, KS_LOCK, *paths))),
    })


def run():
    import numpy as np

    if not sys.flags.isolated:
        raise ValueError('C8 replay requires an isolated interpreter (python -I)')
    lock = source.load(LOCK)
    for record in lock['inputs']:
        check(record)
    spec = importlib.util.spec_from_file_location('c8_reference_scoring', VERIFIER)
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    contract, ks = load_bound()
    from ks_fit import v1_v2, v8

    dest = OUT / 'execution'
    dest.mkdir()
    record = {'command': [sys.executable, *sys.orig_argv[1:]], 'started_utc': source.utc(),
              'contract_sha256': source.sha(LOCK)}
    try:
        core, online, model, _, primary, cases, fit_cases, preflight = ks.read_setup(contract)
        source.write(dest / 'PREFLIGHT.json', preflight)
        _, internal = v8(fit_cases)
        _, _, params = v1_v2(fit_cases, internal)
        params_path = dest / 'FITTED_PARAMETERS.json'
        source.write(params_path, params)
        original = KS / 'execution'
        if source.load(params_path) != source.load(original / params_path.name):
            raise ValueError('V3 refit differs from the frozen fitted parameters')
        source.write(dest / 'V3.json', ks.v3(params, cases, primary, core, online, model, dest))
        frozen = source.load(original / 'V3.json')
        if source.load(dest / 'V3.json') != frozen:
            raise ValueError('V3 scores, parameter application, or decisions changed')
        comparisons = {}
        for arm in lock['arms']:
            name = f'V3_{arm}.npz'
            replay = source.npz(dest / name)
            comparisons[arm] = verifier.compare(replay, original / name)
            scores = verifier.independently_score(replay, primary['R4']['truth'])
            for metric, value in scores.items():
                np.testing.assert_allclose(value, frozen['scores']['point']['R4'][arm][metric],
                                           atol=verifier.ATOL, rtol=verifier.ATOL)
            comparisons[arm]['separate_score_calculation'] = scores
        source.write(dest / 'TRACE_AND_SCORE_CHECKS.json', comparisons)
        record.update(status='PASS_C8_REPLAY', exit_code=0)
    except Exception as exc:
        record.update(status='FAIL_C8_REPLAY', exit_code=1, reason=repr(exc))
        raise
    finally:
        record['finished_utc'] = source.utc()
        record['outputs'] = {path.name: source.sha(path) for path in dest.iterdir() if path.is_file()}
        source.write(dest / 'EXECUTION.json', record)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('freeze', 'run'))
    {'freeze': freeze, 'run': run}[parser.parse_args().stage]()
