"""Offline canonical export and manifest creation. NEVER dispatches a stage.

Run in the pinned Snowball container with <=3 logical CPUs. Existing outputs
are refused. Downloads/model load are a separate materialization receipt.
"""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import platform
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from qclean_uwb.fp_sc.followup.contracts import Policy, sha256, write_json, verify_files, authorize, ContractError
from qclean_uwb.fp_sc.followup.data import export_archive, load_case
from qclean_uwb.fp_sc.followup.runner import SOURCES_REQUIRED, code_paths
from qclean_uwb.fp_sc.e0_baseline import BANKS

P=Path('research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_SELECTIVE_CORRECTION_001')
PACK=Path('research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/C1/C1A_001/FROZEN_PACKETS')
RF=Path('results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C')

def prepare(root, output):
    root=root.resolve(); output=output.resolve()
    if not output.is_relative_to(root):raise ValueError('OUTPUT_OUTSIDE_REPOSITORY')
    output.mkdir(parents=True,exist_ok=False)
    old=json.loads((root/P/'E1_20261105/INPUT_LOCK.json').read_text())
    locked={r['path']:r['sha256'] for r in old['files']}
    verify_files(root,locked)
    baseline=P/'E0_20261105/A2_20261105/RUN_E0_A2_001/baseline'
    index=json.loads((root/baseline/'ARTIFACT_HASHES.json').read_text())
    verify_files(root,{str(baseline/rel):h for rel,h in index.items()})
    cases={}; exports={}
    for route,n in [('R2',979),('R4',742),('R5',1415)]:
        for channel in ('Full','Native_LoS'):
            cid=f'{route}_B0_{channel}_10'
            sources=dict(packet=str(PACK/f'algorithm_input/{route}_aB_m0_B0_{channel}.npz'),
                controls=str(baseline/f'{cid}_CONTROLS.npz'),trace=str(baseline/f'{cid}_REPLAY.npz'),
                truth=str(PACK/f'evaluator_truth/{route}_B0_TRUTH.npz'),
                full_H=str(RF/f'FULL_RF/H_{route}_aB_m0.npy'),los_H=str(RF/f'H_LoS_{route}_aB_m0.npy'),
                frequencies=str(RF/'freqs_hz.npy'))
            meta=dict(case_id=cid,route=route,bias='B0',channel=channel,sensor_seed=10,
                split='EXPOSED_DEV',noise_variance=0.,corpus='dynamic',environment_id='ORIGINAL_CORRIDOR')
            spec=dict(sources=sources,input_files={p:sha256(root/p) for p in sources.values()},
                      metadata=meta,control_origin='A2_REMATERIALIZED',detection_only=True)
            write_json(output/(cid+'_EXPORT_SPEC.json'),spec)
            exports[cid]=export_archive(root,spec,output/cid)
            rel=(output/cid).relative_to(root)
            cases[cid]=dict(online_npz=str(rel/'online.npz'),evaluator_npz=str(rel/'evaluator.npz'),
                           expected_rows=n,metadata=meta)
            for p in sources.values():locked[p]=sha256(root/p)
            for name in ('online.npz','evaluator.npz'):
                locked[str(rel/name)]=sha256(output/cid/name)
            case,ev=load_case(root,cases[cid],locked,None,detection_only=True)
            # Independent exact-array comparison of payload/prior and evaluator joins.
            with np.load(root/sources['trace']) as trace,np.load(root/sources['packet']) as packet:
                assert np.array_equal(case.prior,trace['prior'])
                assert np.array_equal(case.Pprior,trace['Pprior'])
                assert np.array_equal(case.t,packet['t']) and np.array_equal(case.pose_id,packet['pose_id'])
            assert len(case.t)==n and ev.truth.shape==(n,3)
            print('CANONICAL_FORMAT_PASS',cid,n,flush=True)
    policy=Policy()
    mapping=output/'MAPPING_NOT_RUN.json'
    write_json(mapping,dict(status='NOT_RUN',dynamic_mapping_validated=False,E1_02_GO=False))
    locked[str(mapping.relative_to(root))]=sha256(mapping)
    locked.update(BANKS)
    manifest=dict(schema='FP_SC_FOLLOWUP_STUDY_V1',execution_profile='VAB_DETECTION_ONLY_R1',
        candidate_mode='TWO_PORT_UNION',primary_arm='VAB',policy=asdict(policy),policy_sha256=policy.sha,
        environment=dict(python=platform.python_version(),numpy=np.__version__),
        code_files={p:sha256(root/p) for p in code_paths(root)},
        baseline_sources={p:sha256(root/p) for p in SOURCES_REQUIRED},input_files=locked,cases=cases,
        stage_config={'E1-02':{'case_ids':list(cases)}},mapping_reviewed=False,
        mapping_receipt=str(mapping.relative_to(root)),prerequisite_receipts={},
        preparation_only=True,static_controls='48_ORIGINAL_WAVEFORMS_LOCKED_SEPARATE_FROM_DYNAMIC_CASES')
    write_json(output/'MANIFEST_PREP_ONLY.json',manifest)
    write_json(output/'NO_EXECUTION_APPROVAL.json',dict(execute_science=False,stages=[],E2_GO=False))
    try:
        authorize(root,output/'MANIFEST_PREP_ONLY.json',output/'NO_EXECUTION_APPROVAL.json',['E1-02'],code_paths(root))
    except ContractError as e:
        assert str(e)=='SCIENCE_EXECUTION_NOT_AUTHORIZED'
    else:raise AssertionError('EXECUTION_GUARD_DID_NOT_REJECT')
    write_json(output/'OFFLINE_PREFLIGHT.json',dict(status='PASS_OFFLINE_FORMAT_CHECKS_EXECUTION_HOLD',
        original_input_hashes_verified=len(old['files']),cases=len(cases),dynamic_packets=6272,
        checks=['EXACT_TIMELINE_JOIN','PREMEASUREMENT_PRIOR_ARRAY_EQUAL','CANONICAL_SCHEMA',
                'NO_GUESSED_GYRO_BIAS','SOURCE_AND_OUTPUT_SHA','EXECUTION_DENIED'],
        cpu_affinity=sorted(os.sched_getaffinity(0)),
        blockers=['DYNAMIC_MAPPING_NOT_RUN','MAPPING_ACCEPTANCE_CRITERIA_NOT_FROZEN',
                  'PREREQUISITE_REVIEW_HOLD','EXPLICIT_E1_02_AUTHORIZATION_ABSENT',
                  'STATIC_48_NOT_IN_DYNAMIC_STAGE_CASE_LIST'],
        E1_02_started=False,E2_started=False,real_detection_calls=0,model_batch_calls=0,EKF_replay_calls=0))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();prepare(a.root,a.output)
