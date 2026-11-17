"""Freeze and run actual SourceFFD M7 prerequisite checks before main replays."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
import traceback

import numpy as np

import check_m7_replay as verify
from m7_inputs import KEYS, arrays, checked, resolve_input
from m7_prepare import ART, BASE, M6, ROOT, check_records, item, provenance, read, utc, write
from m7_replay import load_environment, replay
from m7_spec import CONDITIONS, ROUTES, expected_cells


def output_of(directory, name):
    receipt=read(directory/'EXECUTION.json')
    if receipt['status']!='PASS_EXECUTION' or receipt['exit_code']!=0:
        raise ValueError(f'Archive stage did not pass: {directory}')
    record=dict(path=str(directory/name),sha256=receipt['outputs'][name])
    checked(record)
    return record


def freeze(out):
    stage=out/'precheck'
    if stage.exists():
        raise FileExistsError('Preserve existing prerequisite evidence')
    inputs=read(out/'input_generation/RUN_CONTRACT.json')
    inp=read(out/'input_generation/INPUT_CHECKS.json')
    if inp['status']!='PASS_SELF_CHECK' or inp['candidate_count']!=120:
        raise ValueError('Actual paired input checks have not passed')
    independent=read(out/'h5prime/INDEPENDENT_CHECKS.json')
    if independent['status']!='PASS_H5P_INDEPENDENT_RECALCULATION':
        raise ValueError('Actual H5P donor check has not passed')
    estimate=read(checked(inputs['frozen_M6_parameters']))
    qprime=read(out/'h5prime/H5P_DONOR_FIT.json')['fit']['folds']
    old=M6/'attempt_02'
    contract=provenance()
    contract.update(stage='ACTUAL_SOURCEFFD_PRECHECK',authorization=dict(checks='GO',replay='HOLD'),
        parent_contract=inputs['parent_contract'],model_assets=inputs['model_assets'],cells=inputs['cells'],
        input_index=item(out/'input_generation/INPUT_INDEX.json'),
        input_contract=item(out/'input_generation/RUN_CONTRACT.json'),
        input_checks=item(out/'input_generation/INPUT_CHECKS.json'),
        input_execution=item(out/'input_generation/INPUT_GENERATION_RECEIPT.json'),
        h5prime_contract=item(out/'h5prime/RUN_CONTRACT.json'),
        h5prime_output=item(out/'h5prime/H5P_DONOR_FIT.json'),
        h5prime_checks=item(out/'h5prime/INDEPENDENT_CHECKS.json'),
        M6_parameters=inputs['frozen_M6_parameters'],
        original_M6_replay=item(BASE/'gm_theta_m6/gm_replay.py'),
        parameters={r:dict(sigma_rad=estimate['k2']['folds'][r]['sigma_rad'],
            q_table=[estimate['distance_edges_m'],estimate['hybrid']['folds'][r]['q_s'],estimate['hybrid']['folds'][r]['supported_bins']],
            qprime_table=[estimate['distance_edges_m'],qprime[r]['q_s'],qprime[r]['supported_bins']],
            sigma_b=next(c['sigma_b'] for c in inputs['cells'] if c['route']==r)) for r in ROUTES},
        archives={r:dict(G0=output_of(old/'implementation',f'seed10/{r}_G0.npz'),
                         G1=output_of(old/'seed10',f'seed10/{r}_G1_LORO.npz'),
                         G1KI=output_of(old/'seed10',f'seed10/{r}_G1_KI.npz')) for r in ROUTES},
        expected_cells=expected_cells(),tolerance=1e-10,
        frozen_code_hashes=verify.code_hashes())
    check_records(contract)
    stage.mkdir()
    write(stage/'RUN_CONTRACT.json',contract)
    print('FROZEN actual SourceFFD prerequisite contract',flush=True)


def run(out):
    stage=out/'precheck'
    contract=read(stage/'RUN_CONTRACT.json')
    if contract['authorization']['checks']!='GO':
        raise ValueError('checks GO absent')
    if (stage/'EXECUTION.json').exists():
        raise FileExistsError('Preserve existing execution')
    check_records(contract)
    receipt=dict(status='FAIL_EXECUTION',exit_code=1,started_utc=utc(),
                 command=[sys.executable,*sys.argv],contract=item(stage/'RUN_CONTRACT.json'),
                 python=sys.version,numpy=np.__version__,outputs={})
    try:
        env=load_environment(checked(contract['parent_contract']))
        receipt['native_source_hashes']=env['native_source_hashes']
        index=read(checked(contract['input_index']))
        reports={}
        for condition in CONDITIONS:
            for route in ROUTES:
                started=time.perf_counter()
                packet=arrays(checked(resolve_input(index,condition,10,route)))
                cell=next(c for c in contract['cells'] if c['route']==route)
                fixed=arrays(checked(cell['fixed_gate_trace']))['mask']
                params=contract['parameters'][route]
                archived={k:arrays(checked(v)) for k,v in contract['archives'][route].items()}
                report=verify.run_checks(packet,env,sigma_b=params['sigma_b'],sigma_rad=params['sigma_rad'],
                    q_table=params['q_table'],q_prime_table=params['qprime_table'],fixed_mask=fixed,
                    reference_R=archived['G0']['Reff'],archived=archived if condition=='B0' else None,
                    frozen_code_hashes=contract['frozen_code_hashes'],condition=condition)
                # Actual SourceFFD measurement-causality check, separate from
                # the analytic synthetic test used during implementation.
                args=dict(sigma_b=params['sigma_b'],sigma_rad=params['sigma_rad'],q_table=params['q_table'],condition=condition)
                base=replay(packet,env,'H3',**args)
                at=len(packet['t'])//2
                changed=dict(packet,z=packet['z'].copy())
                changed['z'][at:]+=[2.,.3]
                other=replay(changed,env,'H3',**args)
                for key in ('x','P','mask','R_ref','Reff'):
                    np.testing.assert_array_equal(base[key][:at],other[key][:at])
                for key in ('prior','Pprior','R_ref','Reff','a','alpha'):
                    np.testing.assert_array_equal(base[key][at],other[key][at])
                report['actual_measurement_causality']='PASS_EXACT'
                report['seconds']=time.perf_counter()-started
                name=f'{condition}_{route}_CHECKS.json'
                write(stage/name,report)
                reports[f'{condition}/{route}']=item(stage/name)
                print(f'PASS {condition}/{route}: {report["seconds"]:.2f}s',flush=True)
        # Check the explicit gyro GQG^T effect at actual arm priors and controls.
        gyro={}
        for route in ROUTES:
            p=arrays(checked(resolve_input(index,'L2_GYRO_ARW',10,route)))
            max_error=0.
            x,P=p['x0'].copy(),p['P0'].copy()
            for i in range(1,len(p['t'])):
                controls={k:p[k] for k in ('ds','gy','dt')}
                lo,pl=verify.predict_navigation(env['core'],env['online'],x,P,i,controls,.015)
                hi,ph=verify.predict_navigation(env['core'],env['online'],x,P,i,controls,.060)
                G=env['core'].transition(x,*[p[k][i] for k in ('ds','gy','dt')])[2]
                expected=np.outer(G[:,1],G[:,1])*(np.deg2rad(.060)**2-np.deg2rad(.015)**2)*p['dt'][i]
                np.testing.assert_allclose(ph-pl,expected,atol=1e-10,rtol=0.)
                np.testing.assert_array_equal(lo,hi)
                max_error=max(max_error,float(np.max(np.abs(ph-pl-expected))))
                x,P=hi,ph
            gyro[route]=dict(status='PASS',max_abs_error=max_error,steps=len(p['t'])-1)
        write(stage/'CHECKS.json',dict(status='PASS_M7_PRE_REPLAY_CHECKS',cases=reports,actual_GQGt=gyro,
            input_checks=contract['input_checks'],h5prime_checks=contract['h5prime_checks'],
            actual_native_parity='PASS',scientific_performance='NOT_ASSESSED',
            complete_cases=9,absolute_tolerance=1e-10))
        check_records(contract)
        receipt.update(status='PASS_EXECUTION',exit_code=0)
    except BaseException as exc:
        receipt.update(error=f'{type(exc).__name__}: {exc}',traceback=traceback.format_exc())
        raise
    finally:
        receipt['finished_utc']=utc()
        receipt['outputs']={p.name:item(p)['sha256'] for p in stage.glob('*.json') if p.name not in ('RUN_CONTRACT.json','EXECUTION.json')}
        write(stage/'EXECUTION.json',receipt)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=('freeze','run'))
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    {'freeze':freeze,'run':run}[args.phase](args.output)
