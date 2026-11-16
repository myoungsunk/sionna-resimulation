"""Replay the frozen D0 → D5 → D1 → D2 → D3/M3 diagnostics at +45° B/B0."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys

for variable in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[variable] = '1'

import numpy as np

from check_observer import OUT as ROOT, PACKET_ROOT, ROUTES, source


OUT = ROOT / 'diagnostics'
LOCK = OUT / 'RUN_CONTRACT.json'
DIAG = ROOT.parent / 'G1_INT_DIAG_001_20261115'
CONT = DIAG / 'continuation_d2_d3'
STUDY = source.STUDY
STAGES = ('d0', 'd5', 'd1', 'd2', 'd3')
sys.path[:0] = list(map(str, (DIAG, CONT, STUDY, source.NATIVE / 'src')))


def receipt(path):
    return {'path': str(path), 'sha256': source.sha(path)}


def check(record):
    return source.checked(Path(record['path']), record['sha256'])


def patched_d1():
    original = (DIAG / 'd1_shuffle.py').read_text(encoding='utf-8')
    spec = 'spec = dict(SPEC, anchor=tuple(contract["anchors"][cell["anchor"]]))'
    sibling = '    sibling = cells[f"{cell[\'anchor\']}_L2_{cell[\'route\']}"]\n    sibling_packet = read_npz(verify_file(sibling["online"]))\n    sibling_delta = sibling_packet["z"] - b0_packet["z"]'
    for old, new in ((spec, spec[:-1] + ', mount_deg=contract["scope"]["mount_deg"])'),
                     (sibling, '    sibling_delta = np.zeros_like(b0_packet["z"])  # Single-level B/B0 contract')):
        assert original.count(old) == 1, old
        original = original.replace(old, new)
    return original


def freeze(comparison):
    from d2 import DEFAULTS as d2_defaults

    observer = ROOT / 'OBSERVER_RESULTS.json'
    assert source.load(observer)['status'] == 'PASS'
    execution = comparison.with_name('EXECUTION.json')
    prior = source.load(execution)
    assert prior['status'] == 'PASS_EXECUTION_AND_IMPLEMENTER_CHECK', 'D0 requires the completed DR and E0–E5 comparison'
    source.checked(comparison, prior['outputs_sha256'][comparison.name])
    legacy = source.load(DIAG / 'RUN_CONTRACT.json')
    continuation = source.load(CONT / 'CONTINUATION_CONTRACT.json')
    reference = source.load(PACKET_ROOT / 'PARITY_RESULTS.json')
    cells = []
    for route in ROUTES:
        original = reference['routes'][route]['output_sha256']
        cell = {'anchor': 'B', 'bias': 'B0', 'route': route}
        for role, key in (('online', 'online'), ('evaluator', 'evaluator'), ('e0_trace', 'archive_trace')):
            path = PACKET_ROOT / f'{source.stem(route)}__{role}.npz'
            cell[key] = receipt(source.checked(path, original[path.name]))
        cells.append(cell)
    OUT.mkdir(exist_ok=False)
    copy = OUT / 'd1_shuffle_mount45.py'
    with copy.open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(patched_d1())
    old_files = [DIAG / name for name in ('RUN_CONTRACT.json', 'd0_d5.py', 'd1_shuffle.py', 'e0_batch.py', 'summarize_run.py')]
    old_files += [CONT / name for name in ('CONTINUATION_CONTRACT.json', 'run_d2_d3.py', 'd2.py', 'd3.py', 'm3.py')]
    old_files += [STUDY / name for name in ('replay_s2.py', 'metrics_s2.py', 'verify_s2.py', 'run_s2.py')]
    source.write(LOCK, {
        'study': 'G1-INT-DIAG-001/M45', 'classification': 'DIAGNOSTIC_ONLY', 'frozen_utc': source.utc(),
        'scope': {'anchor': 'B', 'bias': 'B0', 'mount_deg': 45, 'seed': 10, 'n_expected': len(cells)},
        'anchors': {'B': source.SPEC['anchor']}, 'native': str(source.NATIVE), 's2': str(STUDY),
        'prerequisites': list(map(receipt, (observer, comparison, execution, PACKET_ROOT / 'PARITY_RESULTS.json'))),
        'sources': list(map(receipt, (Path(__file__), copy, *old_files))),
        'governance': legacy['governance'], 'cells': cells, 'ordered_steps': list(STAGES),
        'D5': legacy['D5'], 'D1': legacy['D1'] | {'total_replays': 1203, 'sibling_delta': 'zero for the single B/B0 level'},
        'D2': continuation['D2'] | {'execution_config': d2_defaults}, 'D3': continuation['D3'],
        'M1': continuation['M1'], 'M3': continuation['M3'],
        'd0_archive_limitation': 'Prior +45 generated E0 trace already matched two implementations; no historical +45 reference.',
    })


def baselines(stage, contract, target, core, online, model):
    import d0_d5

    if stage == 'd5':
        d0_d5.d5(contract['cells'], target, OUT / 'd0', source.load(OUT / 'd0/EXECUTION.json'), core, online,
                 model, source.SPEC)
        return
    results = {}
    for cell in contract['cells']:
        results[d0_d5.key_for(cell)] = d0_d5.d0_cell(cell, target, core, online, model, source.SPEC)
        print('D0', d0_d5.key_for(cell), 'PASS', flush=True)
    source.write(target / 'RESULTS.json', {'status': 'PASS_EXECUTION', 'tolerance': source.TOL, 'by_cell': results})


def replays():
    import summarize_run

    def batch(route):
        command = [sys.executable, '-B', '-X', 'utf8', str(OUT / 'd1_shuffle_mount45.py'),
                   '--contract', str(LOCK), '--cell', f'B_B0_{route}']
        subprocess.run(command, check=True, env=os.environ | {'PYTHONPATH': str(DIAG)})

    def report(root, data):
        content = ['# Mount +45° B·B0 D0 → D5 → D1', '', f"총 {data['total_d1_replays']:,}회 재생.", '',
                   *(f'- {key} `{value}`' for key, value in data['hypotheses'].items()), '',
                   '[원자료](RESULTS.json) · [동결 계약](RUN_CONTRACT.json)', '']
        with (root / 'REPORT_KO.md').open('x', encoding='utf-8') as handle:
            handle.write('\n'.join(content))

    with ThreadPoolExecutor(max_workers=len(ROUTES)) as pool:
        list(pool.map(batch, ROUTES))
    summarize_run.LEVELS = ('B_B0',)
    summarize_run.render_report = report
    summarize_run.verify_and_summarize(OUT)


def decompose(stage, contract, target, core, online, model):
    import d2
    import d3
    import run_d2_d3
    from d0_d5 import bind, key_for, identity

    run_d2_d3.PRIOR = OUT
    d2.LEVELS = ('B_B0',)
    cases = {}
    for cell in contract['cells']:
        key = key_for(cell)
        packet, truth = bind(cell)
        trace = source.npz(OUT / 'd0' / f'{key}.npz')
        identity(packet, trace, ('t', 'pose_id'))
        h, _ = model.batch(np.column_stack([truth, np.zeros(len(truth))]), source.SPEC, gradient=False)
        cases[key] = {'packet': packet, 'truth': truth, 'spec': source.SPEC,
                      'e0': trace, 'eps': packet['z'] - h - packet['muMB']}

    prior = source.load(OUT / 'RESULTS.json')
    by_cell = {}
    for key, case in cases.items():
        if stage == 'd2':
            arrays, by_cell[key] = d2.compute_case(case['packet'], case['truth'], case['e0'], case['eps'], core, online,
                                                   contract['D2']['execution_config'])
        else:
            arrays, by_cell[key] = d3.compute_case(case, core, online, model, contract['D3'], primary=key == 'B_B0_R4')
        source.save_npz(target / f'{key}.npz', arrays)
        print(stage.upper(), key, 'complete', flush=True)
    if stage == 'd2':
        s_only = prior['D1']['by_cell']['B_B0_R4']['s_only']
        gain = s_only['eligible']['xy95_coverage']['delta_from_e0'] if s_only['eligible'] else None
        update = d2.aggregate(by_cell, gain, s_only['valid_reps'], contract['D2']['execution_config'])
        run_d2_d3.d2_fit_m3(cases, target, core, online, model)
        result = {'by_cell': by_cell, 'aggregate': update, 'M3_file': 'M3_FITS_AND_PAIR_TABLES.json'}
    else:
        table = run_d2_d3.d3_m3_comparison(cases, OUT / 'd2', contract['D3'])
        source.write(target / 'M3_SLOW_SCALE_COMPARISON.json', table)
        result = {'by_cell': by_cell, 'M3_file': 'M3_SLOW_SCALE_COMPARISON.json'}
        result['decision'] = d3.priority(source.load(OUT / 'd2/RESULTS.json'), result, prior,
                                         contract['D3']['target_heading95'])
    source.write(target / 'RESULTS.json', result)


def require_previous(stage):
    for prev in STAGES[:STAGES.index(stage)]:
        path = OUT / prev / 'EXECUTION.json'
        run = source.load(path)
        if run['status'] != 'PASS_EXECUTION' or run['run_contract_sha256'] != source.sha(LOCK):
            raise ValueError(f'{stage} requires completed {prev}')
        for name, digest in run['outputs'].items():
            source.checked(OUT / prev / name, digest)


def run(stage):
    from qclean_uwb.fp_sc.e0_baseline import load_original_model

    contract = source.load(LOCK)
    for item in contract['prerequisites'] + contract['sources'] + contract['governance']:
        check(item)
    require_previous(stage)
    target = OUT / stage
    target.mkdir()
    result = {'started_utc': source.utc(), 'run_contract_sha256': source.sha(LOCK), 'command': sys.argv,
              'numpy': np.__version__, 'driver_sha256': source.sha(Path(__file__))}
    try:
        if stage == 'd1':
            replays()
        else:
            core, online, model, native = load_original_model(source.NATIVE)
            result['native_source_hashes'] = native
            step = baselines if stage in ('d0', 'd5') else decompose
            step(stage, contract, target, core, online, model)
        result.update(status='PASS_EXECUTION', exit_code=0)
    except Exception as error:
        result.update(status='FAIL_EXECUTION', exit_code=1, error=str(error))
        raise
    finally:
        result.update(finished_utc=source.utc(), outputs={p.relative_to(target).as_posix(): source.sha(p)
                      for p in target.rglob('*') if p.is_file()})
        source.write(target / 'EXECUTION.json', result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('freeze', 'ordered', *STAGES))
    parser.add_argument('--comparison', type=Path, default=ROOT / 'comparison/execution/RESULTS.json')
    args = parser.parse_args()
    if args.stage == 'freeze':
        freeze(args.comparison)
    elif args.stage == 'ordered':
        for stage in STAGES:
            run(stage)
    else:
        run(args.stage)
