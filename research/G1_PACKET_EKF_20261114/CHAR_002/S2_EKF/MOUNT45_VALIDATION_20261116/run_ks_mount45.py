"""Run the frozen KS diagnostics in order on the verified +45 B/B0 branch."""

import argparse
import sys
import types

from run_diag_mount45 import DIAG, LOCK as DIAG_LOCK, OUT as DIAGNOSTICS, ROOT, ROUTES, check, receipt, source


LEGACY = DIAG / 'continuation_ks'
STRUCT = ROOT / 'structure'
D4 = ROOT / 'd4'
OUT = ROOT / 'ks'
LOCK = OUT / 'RUN_CONTRACT.json'
sys.path[:0] = [str(LEGACY), str(DIAG / 'structure_sc_ki')]


def role_receipt(stage, contract_path, hash_key='contract_sha256'):
    path = stage / 'EXECUTION.json'
    result = source.load(path)
    assert result['status'] == 'PASS_EXECUTION' and result['exit_code'] == 0
    assert result[hash_key] == source.sha(contract_path)
    return [path, *(source.checked(stage / name, digest) for name, digest in result['outputs'].items())]


def adapt_original():
    text = (LEGACY / 'run_ks.py').read_text(encoding='utf-8')
    changes = {
        'STRUCT / "run_01"': 'STRUCT / "execution"',
        '        if not np.array_equal(ka["table"], np.full_like(ka["table"], ka["table"][0])):\n            raise ValueError("Current-prior and inherited Rref lookup no longer equivalent")\n': '',
        'D4 / "run_02"': 'D4 / "execution"',
        'verification=item(D4 / "VERIFICATION.json")': 'verification=item(D4 / "execution" / "CHECKS.json")',
        'diag.v7(cases, out)': 'v7_missing_A(cases)',
    }
    for before, after in changes.items():
        assert text.count(before) >= 1, before
        text = text.replace(before, after)
    return text


def freeze():
    prev = source.load(LEGACY / 'RUN_CONTRACT_RETRY_03.json')
    paths = [DIAG_LOCK, STRUCT / 'RUN_CONTRACT.json', D4 / 'RUN_CONTRACT.json']
    for name in ('d0', 'd5', 'd2', 'd3'):
        paths.extend(role_receipt(DIAGNOSTICS / name, DIAG_LOCK, 'run_contract_sha256'))
    paths.extend(role_receipt(STRUCT / 'execution', paths[1]))
    paths.extend(role_receipt(D4 / 'execution', paths[2]))
    OUT.mkdir()
    clone = OUT / 'run_ks_bound.py'
    with clone.open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(adapt_original())
    sources = [source.Path(__file__), clone, LEGACY / 'PLAN_FROZEN.md', LEGACY / 'RUN_CONTRACT_RETRY_03.json']
    sources.extend(LEGACY / name for name in ('run_ks.py', 'ks_replay.py', 'ks_fit.py', 'ks_diagnostics.py'))
    contract = {k: prev[k] for k in ('governance', 'plan_commit', 'order', 'rules')}
    contract.update(question='G1-INT-001/KS-TRANSFER/M45-B-B0', role='IMPLEMENTER', frozen_utc=source.utc(),
                    scope={'mount_deg': 45., 'anchor': 'B', 'bias': 'B0', 'seed': 10, 'routes': list(ROUTES)},
                    sources=list(map(receipt, sources)), inputs=list(map(receipt, paths)),
                    route_reference_rule='R_ref uses inherited previous-posterior horizontal range in replay; kernel and feature bins use current prior.',
                    V7='Requires matching A/B on B0 or L2; A +45 has no authenticated frozen baseline. Record missing V7 and continue D6, which operates only on B/B0.')
    source.write(LOCK, contract)


def load_bound():
    import run_d2_d3
    import run_structure

    contract = source.load(LOCK)
    for record in contract['governance'] + contract['sources'] + contract['inputs']:
        check(record)
    source_contract = source.load(LEGACY / 'RUN_CONTRACT_RETRY_03.json')
    assert contract['rules'] == source_contract['rules'] and contract['order'] == source_contract['order']
    base = source.load(DIAG_LOCK)
    structural = source.load(STRUCT / 'RUN_CONTRACT.json')
    from qclean_uwb.fp_sc import e0_baseline
    # The imported readers take geometry from SPEC. W0/SC accept the resulting explicit spec per case.
    e0_baseline.SPEC = source.SPEC
    run_structure.authenticate = lambda: (structural, base)
    run_d2_d3.PRIOR = DIAGNOSTICS

    bound = types.ModuleType('run_ks')
    clone = OUT / 'run_ks_bound.py'
    bound.__file__ = str(clone)
    exec(compile(clone.read_text(encoding='utf-8'), str(clone), 'exec'), vars(bound))
    bound.authenticate = lambda path: contract
    bound.D23 = DIAGNOSTICS
    bound.STRUCT = STRUCT
    bound.D4 = D4
    bound.v7_missing_A = lambda cases: {'status': 'BLOCKED_A_FROZEN_M45_REFERENCE', 'cells_present': sorted(cases)}
    return contract, bound


def run():
    _, bound = load_bound()
    bound.execute(LOCK, OUT / 'execution')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('freeze', 'run'))
    {'freeze': freeze, 'run': run}[parser.parse_args().stage]()
