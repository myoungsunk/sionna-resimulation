"""Rebind the original SC/KI executor to completed +45 B/B0 diagnostics."""

import argparse
import sys

from run_diag_mount45 import DIAG, LOCK as DIAG_LOCK, OUT as DIAGNOSTICS, ROOT, ROUTES, check, receipt, source


SRC = DIAG / 'structure_sc_ki'
OUT = ROOT / 'structure'
LOCK = OUT / 'RUN_CONTRACT.json'
sys.path.insert(0, str(SRC))


def authenticate_diagnostic(name, filename):
    run_path = DIAGNOSTICS / name / 'EXECUTION.json'
    run = source.load(run_path)
    assert run['status'] == 'PASS_EXECUTION' and run['run_contract_sha256'] == source.sha(DIAG_LOCK)
    return source.checked(run_path.parent / filename, run['outputs'][filename])


def freeze():
    parent = source.load(DIAG_LOCK)
    templates = source.load(SRC / 'RUN_CONTRACT.json')
    m1 = authenticate_diagnostic('d2', 'M3_FITS_AND_PAIR_TABLES.json')
    d5 = authenticate_diagnostic('d5', 'FOLDS.json')
    d3 = authenticate_diagnostic('d3', 'RESULTS.json')
    sigmas, fits = source.load(d5), source.load(m1)
    cells = []
    for cell in parent['cells']:
        route = cell['route']
        name = f'B_B0_{route}.npz'
        required = set(ROUTES) - {route}
        fit, sigma = fits[route], sigmas[route]
        assert fit['held_out_route'] == route and set(fit['donor_routes']) == set(sigma['donor_routes']) == required
        assert set(fit['fits']) == {'r', 's'} and fit['q_knots_m'] == parent['M1']['q_knots_m']
        assert len(sigma['sigma_b']) == len(fit['q_knots_m']) and min(sigma['sigma_b']) > 0
        for channel in fit['fits'].values():
            assert len(channel['q_knots']) == len(fit['q_knots_m']) and all(0 <= q <= 1 for q in channel['q_knots'])
            assert channel['ell_m'] in parent['M1']['ell_d_m'] and channel['ell_deg'] in parent['M1']['ell_psi_deg']
        cells.append(cell | {'fixed_gate_trace': receipt(authenticate_diagnostic('d0', name)),
                             'loro_trace': receipt(authenticate_diagnostic('d5', name)), 'donors': sorted(required),
                             'sigma_b': sigma['sigma_b'], 'kernel': {'q_knots_m': fit['q_knots_m'], 'fits': {
                                 key: {k: noises[k] for k in ('q_knots', 'ell_m', 'ell_deg')}
                                 for key, noises in fit['fits'].items()}}})
    assert tuple(c['route'] for c in cells) == ROUTES
    extras = [DIAGNOSTICS / step / 'EXECUTION.json' for step in ('d0', 'd5', 'd1', 'd2', 'd3')]
    bindings = [SRC / name for name in ('RUN_CONTRACT.json', 'run_structure.py', 'structure.py', 'score_structure.py')]
    OUT.mkdir(exist_ok=False)
    source.write(LOCK, {**templates, 'study': 'G1-INT-001/M45-B-B0', 'prior_publication_commit': None,
        'frozen_utc': source.utc(), 'scope': templates['scope'] | {'mount_deg': 45.}, 'cells': cells,
        'sources': list(map(receipt, (source.Path(__file__), *bindings))) + parent['sources'],
        'prerequisites': list(map(receipt, (DIAG_LOCK, m1, d5, d3, *extras))),
        'frozen_m1_fit': receipt(m1), 'frozen_loro_fit': receipt(d5)})


def run():
    import run_structure

    contract = source.load(LOCK)
    old = source.load(SRC / 'RUN_CONTRACT.json')
    for key in ('M2_thresholds', 'noise', 'SC', 'KI', 'implementation_gates', 'score'):
        assert contract[key] == old[key], key
    entries = (contract['sources'] + contract['governance'] + contract['s2_sources'] + contract['prerequisites']
               + list(contract['model_assets'].values()))
    for cell in contract['cells']:
        entries += [cell[key] for key in ('online', 'evaluator', 'archive_trace', 'fixed_gate_trace', 'loro_trace')]
    for item in entries:
        check(item)
    prior = source.load(DIAG_LOCK)
    original_cases = run_structure.cases_from

    def mount45_cases(lock):
        return {route: item | {'spec': source.SPEC} for route, item in original_cases(lock).items()}

    run_structure.authenticate = lambda path: (contract, prior)
    run_structure.cases_from = mount45_cases
    run_structure.execute(LOCK, OUT / 'execution')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('freeze', 'run'))
    {'freeze': freeze, 'run': run}[parser.parse_args().stage]()
