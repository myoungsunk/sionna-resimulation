"""Freeze M7 after actual prerequisites and execute complete independent cells."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import os
from pathlib import Path
import sys
import traceback

import numpy as np

from m7_inputs import checked
from m7_prepare import ROOT, check_records, item, provenance, read, utc, write
from m7_replay import load_environment
from m7_run import _contract, run_cell
from m7_spec import MAIN_CONDITIONS, STRESS, expected_cells, validate_cell_index

_ENV=None
_CONTRACT=None
_OUTPUT=None


def freeze(out,workers):
    pre=out/'precheck'
    lock=read(pre/'RUN_CONTRACT.json')
    check_records(lock)
    checks=read(pre/'CHECKS.json')
    receipt=read(pre/'EXECUTION.json')
    if (checks['status']!='PASS_M7_PRE_REPLAY_CHECKS' or receipt['status']!='PASS_EXECUTION'
        or receipt['contract']!=item(pre/'RUN_CONTRACT.json')):
        raise ValueError('Actual native prerequisites have not passed')
    for name,digest in receipt['outputs'].items():
        if item(pre/name)['sha256']!=digest:
            raise ValueError('Prerequisite output drift')
    stage=out/'replay'
    if stage.exists():
        raise FileExistsError('Preserve existing frozen replay attempt')
    contract=provenance()
    # Scoring implementation may still be prepared independently; it cannot
    # change these hash-pinned candidate/runtime sources or decision inputs.
    runtime=('m7_batch.py','m7_run.py','m7_replay.py','m7_inputs.py','m7_spec.py','m7_prepare.py','m7_h5prime.py')
    contract.update(stage='M7_MAIN_AND_STRESS_REPLAY',authorization=dict(replay='GO'),
        sources=[item(ROOT/n) for n in runtime], parent_contract=lock['parent_contract'],
        decision_sources=[item(ROOT/n) for n in ('m7_assess.py','m7_report.py','m7_score.py','m7_score_run.py')],
        model_assets=lock['model_assets'],input_index=lock['input_index'],
        parameters=lock['parameters'],
        fixed_masks={c['route']:dict(c['fixed_gate_trace'],field='mask') for c in lock['cells']},
        expected_cells=expected_cells(),prerequisite_checks=item(pre/'CHECKS.json'),
        prerequisite_contract=item(pre/'RUN_CONTRACT.json'),prerequisite_execution=item(pre/'EXECUTION.json'),
        input_contract=lock['input_contract'],h5prime_output=lock['h5prime_output'],
        worker_processes=workers,process_noise='Input gyro N matched by condition; stress .060 injected/.015 filter',
        bootstrap=dict(block_seconds=[5,10,20],draws=1500,seed=20261115,paired_across_arms=True),
        acceptance=dict(route_coverage_min=.75,route_lower_min=.60,route_rmse_max_ratio=1.25,
                        pooled_pose_heading_min=.90,pooled_lower_min=.80,pooled_nees=[1.5,6.],
                        pooled_rmse_max_ratio=1.10,min_joint_seeds=18,total_seeds=20,mirror_events_max=0,
                        stress_and_fixed_report_only=True))
    check_records({k:contract[k] for k in ('sources','decision_sources','model_assets','input_index','prerequisite_checks')})
    stage.mkdir()
    write(stage/'RUN_CONTRACT.json',contract)
    print('FROZEN 1470 logical cells / 1440 physical replays',flush=True)


def initialize(contract_path,output):
    global _ENV,_CONTRACT,_OUTPUT
    data,_=_contract(contract_path)
    _ENV=load_environment(checked(data['parent_contract']))
    _CONTRACT,_OUTPUT=contract_path,output


def execute(cell):
    result=run_cell(_CONTRACT,cell,_OUTPUT,env=_ENV)
    return dict(id=cell['id'],status=result['status'],executed=result['executed'],trace=result['trace'])


def run(out,phase):
    stage=out/'replay'
    path=stage/'RUN_CONTRACT.json'
    contract,_=_contract(path)
    physical=[c for c in contract['expected_cells'] if c['execute'] and
              ((phase=='main' and c['condition'] in MAIN_CONDITIONS) or (phase=='stress' and c['condition']==STRESS))]
    aliases=[c for c in contract['expected_cells'] if phase=='main' and c['trace_alias_of']]
    receipt_path=stage/f'{phase.upper()}_EXECUTION.json'
    if receipt_path.exists():
        raise FileExistsError('Preserve previous batch receipt; individual cells support exact verified reuse')
    if phase=='stress' and read(stage/'MAIN_EXECUTION.json')['status']!='PASS_EXECUTION':
        raise ValueError('Main replay must complete before report-only stress')
    receipt=dict(status='FAIL_EXECUTION',exit_code=1,started_utc=utc(),command=[sys.executable,*sys.argv],
                 contract=item(path),python=sys.version,numpy=np.__version__,phase=phase,
                 physical_expected=len(physical),aliases_expected=len(aliases),completed=0,
                 workers=contract['worker_processes'])
    try:
        with (stage/f'{phase.upper()}_PROGRESS.jsonl').open('x',encoding='utf-8') as log:
            with ProcessPoolExecutor(max_workers=contract['worker_processes'],initializer=initialize,
                                     initargs=(str(path),str(stage))) as pool:
                futures={pool.submit(execute,c):c for c in physical}
                for future in as_completed(futures):
                    try:
                        result=future.result()
                    except BaseException:
                        for pending in futures:
                            pending.cancel()
                        raise
                    log.write(json.dumps(result,ensure_ascii=False,allow_nan=False)+'\n')
                    log.flush()
                    receipt['completed']+=1
                    if receipt['completed']%25==0 or receipt['completed']==len(physical):
                        print(f'{phase}: {receipt["completed"]}/{len(physical)} physical PASS',flush=True)
                    stop=os.environ.get('MANAGED_PROCESS_STOP_FILE')
                    if stop and Path(stop).exists():
                        for pending in futures:
                            pending.cancel()
                        raise InterruptedError('Managed stop requested')
            for cell in aliases:
                result=run_cell(path,cell,stage)
                log.write(json.dumps(dict(id=cell['id'],status=result['status'],executed=False),ensure_ascii=False)+'\n')
        receipt.update(status='PASS_EXECUTION',exit_code=0,aliases_completed=len(aliases))
    except BaseException as exc:
        receipt.update(error=f'{type(exc).__name__}: {exc}',traceback=traceback.format_exc())
        raise
    finally:
        receipt['finished_utc']=utc()
        write(receipt_path,receipt)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=('freeze','main','stress'))
    parser.add_argument('output',type=Path)
    parser.add_argument('--workers',type=int,default=6)
    args=parser.parse_args()
    if args.phase=='freeze':
        if not 1<=args.workers<=8:
            raise ValueError('Bounded local process count required')
        freeze(args.output,args.workers)
    else:
        run(args.output,args.phase)
