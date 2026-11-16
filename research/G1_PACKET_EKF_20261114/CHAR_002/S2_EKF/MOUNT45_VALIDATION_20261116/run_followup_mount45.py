"""Run C1–C6 with the frozen mount +45 B/B0 V3 inputs and legacy decision rules."""

import argparse
from pathlib import Path
import sys
import types

import numpy as np

from run_ks_mount45 import DIAG, DIAGNOSTICS, LOCK as KS_LOCK, OUT as KS, ROOT, check, load_bound, receipt, role_receipt, source


LEGACY = DIAG / 'continuation_checks_c1_c8'
OUT = ROOT / 'followup'
LOCK = OUT / 'RUN_CONTRACT.json'
TEMPLATE = LEGACY / 'run_followup.py'


def adapted_text():
    original = TEMPLATE.read_text(encoding='utf-8')
    changes = {
        '            prior[donor] = load(D23 / "d2" / f"M3_{route}_donor_{donor}.npz")':
            '            prior[donor] = replay_donor(route, donor, case, env, D23)',
        '        rows = {a: r4_rows[a] for a in ("LORO", "a", "a_prime")}':
            '        if "a_prime" not in base_traces:\n'
            '            base_traces["a_prime"] = replay_ks(r4, *env, choices["a"], uncap_slow=True)\n'
            '            r4_rows["a_prime"] = trace_out("C2", "uncapped_unity_reference", base_traces["a_prime"])\n'
            '        rows = {a: r4_rows[a] for a in ("LORO", "a", "a_prime")}',
    }
    for before, after in changes.items():
        assert original.count(before) == 1, before
        original = original.replace(before, after)
    return original


def replay_donor(fold, donor, cases, env, root):
    from d0_d5 import replay_sigma
    from replay_s2 import parity

    donor_case = cases[donor]
    packet, controls, mask, spec = (donor_case[k] for k in ('packet', 'controls', 'mask', 'spec'))
    ref = replay_sigma(packet, controls, mask, *env, spec, cases[fold]['table'])
    expected = source.npz(root / 'd2' / f'M3_{fold}_donor_{donor}.npz')
    parity(ref | {'t': packet['t'], 'pose_id': packet['pose_id']},
           {k: expected[k] for k in ('prior', 'Reff', 't', 'pose_id', 'mask')})
    return ref


def freeze():
    paths = role_receipt(KS / 'execution', KS_LOCK)
    original = source.load(LEGACY / 'RUN_CONTRACT_C1_C6.json')
    OUT.mkdir()
    clone = OUT / 'run_followup_bound.py'
    with clone.open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(adapted_text())
    v3 = source.load(KS / 'execution/V3.json')
    traces = ['a', 'b', 'c'] + (['a_prime'] if v3['a_prime_executed'] else [])
    assert all((KS / 'execution' / f'V3_{arm}.npz') in paths for arm in traces)
    source.write(LOCK, {'question': 'G1-INT-001/KS-C1-C6/M45-B-B0', 'role': 'IMPLEMENTER',
        'frozen_utc': source.utc(), 'source': receipt(clone), 'governance': original['governance'],
        'rules': original['rules'], 'inherited_V3_traces': traces, 'inputs': list(map(receipt, (
            Path(__file__), TEMPLATE, KS_LOCK, LEGACY / 'RUN_CONTRACT_C1_C6.json', *paths))),
        'C4_R_ref': 'Original R_ref, reconstruct donor H and Pprior with the holdout fold sigma and compare to frozen M3 identity.',
        'C2_unity': 'Recompute uncapped unity only within C2 if V3 did not trigger a prime; same frozen C2 cap/uncap rule.'})


def load_module():
    locked = source.load(LOCK)
    for record in [locked['source'], *locked['governance'], *locked['inputs']]:
        check(record)
    _, ks = load_bound()
    sys.modules['run_ks'] = ks
    bound = types.ModuleType('run_followup_bound')
    clone = Path(locked['source']['path'])
    bound.__file__ = str(clone)
    exec(compile(clone.read_text(encoding='utf-8'), str(clone), 'exec'), vars(bound))
    bound.BASE_LOCK, bound.LOCK_FILE, bound.RESULT = KS_LOCK, LOCK, KS / 'execution'
    bound.BASE_TRACES = tuple(locked['inherited_V3_traces'])
    bound.COMMIT = source.load(KS_LOCK)['plan_commit']
    bound.replay_donor = replay_donor
    return bound


def run():
    load_module().run(OUT / 'execution')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('freeze', 'run'))
    {'freeze': freeze, 'run': run}[parser.parse_args().stage]()
