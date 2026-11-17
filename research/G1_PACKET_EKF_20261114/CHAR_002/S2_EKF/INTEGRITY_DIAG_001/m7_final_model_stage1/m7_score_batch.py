"""Freeze and execute the preregistered complete M7 offline assessment."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import importlib
import json
import os
from pathlib import Path
import sys
import traceback

from m7_prepare import ART, ROOT, check_records, item, provenance, read, utc, write
from m7_score_run import _contract, _load_scorers, aggregate, expected_groups, score_one_group


def freeze(out, workers):
    replay = out / 'replay'
    replay_contract = read(replay / 'RUN_CONTRACT.json')
    check_records(replay_contract)
    for name, count in (('MAIN', 1020), ('STRESS', 420)):
        receipt = read(replay / f'{name}_EXECUTION.json')
        if (receipt['status'] != 'PASS_EXECUTION' or receipt['completed'] != count
                or receipt['contract'] != item(replay / 'RUN_CONTRACT.json')):
            raise ValueError('Complete main and stress replay required before scoring freeze')
    if read(replay / 'MAIN_EXECUTION.json')['aliases_completed'] != 30:
        raise ValueError('All thirty exact DR aliases required')
    generation = out / 'input_generation'
    inputs = read(generation / 'RUN_CONTRACT.json')
    parent = read(inputs['parent_contract']['path'])
    directories = [ART / 'G1_INT_DIAG_001_20261115',
                   ART / 'G1_INT_DIAG_001_20261115/continuation_ks',
                   ART / 'G1_INT_DIAG_001_20261115/continuation_d2_d3',
                   ART / 'G1_EXPOSURE_M1_M4_20261116', Path(parent['s2'])]
    for directory in reversed(directories):
        sys.path.insert(0, str(directory))
    for module in ('verify_s2', 'ks_diagnostics', 'exposure_score', 'metrics_s2'):
        importlib.import_module(module)
    # Pin the actual imported local closure, plus all M7 Python sources.
    # The scoring gate verifies this closure in each new worker process.
    files = {p.resolve() for p in ROOT.glob('*.py')}
    for module in tuple(sys.modules.values()):
        source = getattr(module, '__file__', None)
        if source and str(source).endswith('.py'):
            source = Path(source).resolve()
            if any(source.is_relative_to(directory.resolve()) for directory in directories):
                files.add(source)
    stage = out / 'scoring'
    if stage.exists():
        raise FileExistsError('Preserve frozen scoring evidence')
    contract = provenance()
    contract.update(stage='M7_COMPLETE_OFFLINE_SCORING', authorization=dict(scoring='GO'),
                    replay_contract=item(replay / 'RUN_CONTRACT.json'), replay_root=str(replay.resolve()),
                    replay_executions=[item(replay / f'{name}_EXECUTION.json') for name in ('MAIN', 'STRESS')],
                    input_index=item(generation / 'INPUT_INDEX.json'),
                    evaluator_inputs=inputs['evaluator_inputs'],
                    offline_latents=dict(root=str(generation.resolve()), receipt=item(generation / 'INPUT_GENERATION_RECEIPT.json')),
                    scorer_assets=dict(module_dirs=list(map(str, directories)), files=[item(p) for p in sorted(files)],
                                       verify_module='verify_s2', block_module='ks_diagnostics',
                                       branch_module='exposure_score', metrics_module='metrics_s2'),
                    worker_processes=workers, expected_groups=expected_groups(),
                    bootstrap=dict(block_seconds=[5,10,20], draws=1500, seed=20261115,
                                   paired_across_arms=True, paired_across_conditions_and_gates=True),
                    interpretation='Fixed gate and mismatched-Q stress report only; unchanged frozen thresholds')
    check_records(contract)
    _load_scorers(contract['scorer_assets'])
    stage.mkdir()
    write(stage / 'RUN_CONTRACT.json', contract)
    _contract(stage / 'RUN_CONTRACT.json')
    print('FROZEN 70 score groups and 20 paired-condition seed groups', flush=True)


def score_job(path, group, output):
    receipt = score_one_group(path, group, output)
    return dict(group=group, status=receipt['status'])


def pair_job(path, seed, output):
    from m7_pairs import pair_seed
    receipt = pair_seed(path, seed, output)
    return dict(seed=seed, status=receipt['status'])


def passage_job(path, group, output):
    from m7_passages import annotate_group
    receipt = annotate_group(path, group, output)
    return dict(group=group,status=receipt['status'])


def run(out, phase):
    stage = out / 'scoring'
    path = stage / 'RUN_CONTRACT.json'
    contract, _, _, _ = _contract(path)
    pairs = phase == 'pairs'
    receipt_path = stage / f'{phase.upper()}_EXECUTION.json'
    if receipt_path.exists():
        raise FileExistsError('Preserve previous scoring batch receipt')
    jobs = list(range(10,30)) if pairs else expected_groups()
    receipt = dict(status='FAIL_EXECUTION', exit_code=1, started_utc=utc(), contract=item(path),
                   command=[sys.executable,*sys.argv], phase=phase, completed=0, expected=len(jobs))
    output = out / 'paired_comparisons' if pairs else stage
    function = pair_job if pairs else (passage_job if phase=='passages' else score_job)
    try:
        if phase!='score' and read(out / 'assessment/EXECUTION.json')['status'] != 'PASS_AGGREGATION':
            raise ValueError('Complete numerical assessment required before paired report')
        with ProcessPoolExecutor(max_workers=contract['worker_processes']) as pool:
            futures = {pool.submit(function,str(path),job,str(output)):job for job in jobs}
            for future in as_completed(futures):
                try:
                    result = future.result()
                except BaseException:
                    for pending in futures:
                        pending.cancel()
                    raise
                receipt['completed'] += 1
                print(f'{phase}: {receipt["completed"]}/{len(jobs)} PASS {result}', flush=True)
                stop = os.environ.get('MANAGED_PROCESS_STOP_FILE')
                if stop and Path(stop).exists():
                    for pending in futures:
                        pending.cancel()
                    raise InterruptedError('Managed stop requested')
        if pairs:
            from m7_pairs import aggregate_pairs
            aggregate_pairs(path, output, out / 'paired_assessment')
        elif phase=='passages':
            from m7_passages import aggregate_passages
            aggregate_passages(path,stage,out / 'passages_assessment')
        else:
            aggregate(path,stage,out / 'assessment')
        receipt.update(status='PASS_EXECUTION', exit_code=0)
    except BaseException as exc:
        receipt.update(error=f'{type(exc).__name__}: {exc}',traceback=traceback.format_exc())
        raise
    finally:
        receipt['finished_utc'] = utc()
        write(receipt_path,receipt)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('freeze','score','pairs','passages'))
    parser.add_argument('output',type=Path)
    parser.add_argument('--workers',type=int,default=3)
    args = parser.parse_args()
    if args.phase == 'freeze':
        if not 1 <= args.workers <= 4:
            raise ValueError('Use one to four scoring workers')
        freeze(args.output,args.workers)
    else:
        run(args.output,args.phase)
