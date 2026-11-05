"""A2-only separate result review; does not rerun RF, FFD, or filter policy.

Reuses the separately authored Cholesky Joseph and motion arithmetic from the
E0 result checker, and independently binds every saved control to the new A2
registry or the original R2 archive. No production FP-SC function is imported.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent))
import audit_e0_results as arithmetic


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def array_sha(a):return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def js(path):return json.loads(Path(path).read_text())


def inputs_and_controls(repo,run,a2):
    checks=[];identity_files=[];code=js(a2/'CODE_LOCK.json')['files'];input_lock=js(a2/'INPUT_LOCK.json')
    for path,expected in code.items():
        checks.append({'name':'code:'+path,'pass':sha(repo/path)==expected})
    total_bytes=0
    for entry in input_lock['files']:
        path=repo/entry['path'];total_bytes+=path.stat().st_size;identity_files.append(entry['path'])
        checks.append({'name':'input:'+entry['path'],'pass':path.stat().st_size==entry['size_bytes'] and sha(path)==entry['sha256']})
    output_hashes=js(run/'ARTIFACT_HASHES.json')
    for path,expected in output_hashes.items():checks.append({'name':'output:'+path,'pass':sha(run/path)==expected})
    registry=js(a2/'controls/REGISTRY.json');historical=js(repo/arithmetic.BASE/'A0_R3_REFIT/BASE_INPUTS.json')['controls']
    control_records=[]
    for route,n in arithmetic.COUNTS.items():
        for bias in ('B0','L2'):
            key=f'{route}_aB_m0_{bias}_10'
            if route=='R2':
                relative=arithmetic.BASE/'POST_S3_PROPOSER_20261104/R2_EXTENSION/inputs'/f'{key}.npz'
                original=arithmetic.npz(repo/relative);identity='EXACT_ARCHIVED_ORIGINAL'
                original_lock=js(repo/arithmetic.BASE/'POST_S3_PROPOSER_20261104/R2_EXTENSION/inputs/INPUT_LOCK.json')
                checks.append({'name':'original_R2_payload:'+key,'pass':sha(repo/relative)==original_lock['files'][relative.name]})
            else:
                entry=registry['entries'][key];relative=Path(entry['file']);original=arithmetic.npz(repo/relative);identity='LINUX_REMATERIALIZED_ORIGINAL_RECIPE'
                checks.append({'name':'new_control_payload:'+key,'pass':sha(repo/relative)==entry['sha256']})
                for name,record in entry['arrays'].items():
                    a=original[name]
                    checks.append({'name':'new_control_array:'+key+':'+name,'pass':array_sha(a)==record['sha256'] and list(a.shape)==record['shape'] and a.dtype.str==record['dtype']})
                historical_matches={name:array_sha(original[name])==historical[key][name] for name in ('ds','gy','dt','x0')}
                checks.append({'name':'historical_mismatch_truthful:'+key,'pass':historical_matches=={'ds':False,'gy':True,'dt':True,'x0':True}})
                control_records.append({'key':key,'identity':identity,'original_historical_array_matches':historical_matches})
            for channel in ('Full','Native_LoS'):
                cell=f'{route}_{bias}_{channel}_10';saved=arithmetic.npz(run/'baseline'/f'{cell}_CONTROLS.npz')
                packet=arithmetic.npz(repo/arithmetic.PACKETS/'algorithm_input'/f'{route}_aB_m0_{bias}_{channel}.npz')
                for name in ('ds','gy','dt','x0'):
                    checks.append({'name':'saved_replay_control:'+cell+':'+name,'pass':np.array_equal(saved[name],original[name]) and array_sha(saved[name])==array_sha(original[name])})
                if route!='R2':
                    for name in ('t','pose_id'):checks.append({'name':'new_control_packet_grid:'+cell+':'+name,'pass':np.array_equal(original[name],packet[name])})
                record=js(run/'baseline'/f'{cell}.json')
                if route!='R2':checks.append({'name':'recorded_explicit_control_identity:'+cell,'pass':record['controls']['kind']==identity and record['controls']['historical_identity']['status']=='UNRESOLVED_EXACT_HISTORICAL_DS_BYTES'})
    return {'status':'PASS' if all(c['pass'] for c in checks) else 'FAIL','checks':checks,
            'input_files_rehashed':len(input_lock['files']),'input_bytes_rehashed':total_bytes,
            'code_files_rehashed':len(code),'result_files_rehashed':len(output_hashes),
            'controls_identities':control_records,'new_control_payloads':4,'original_R2_control_payloads':2}


def main():
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();repo=args.repo.resolve();run=args.run.resolve();out=args.output.resolve();a2=repo/arithmetic.E0/'A2_20261105'
    manifest=js(run/'RUN_MANIFEST.json')
    if manifest.get('amendment')!='A2_REMATERIALIZED_CONTROLS' or manifest['status']=='RUNNING':raise ValueError('A2_COMPLETED_RUN_REQUIRED')
    if manifest['exact_historical_control_bytes']!='UNRESOLVED_R4_R5':raise ValueError('HISTORICAL_BYTE_CLAIM_DRIFT')
    out.mkdir(parents=True,exist_ok=False)
    report={'schema':'FP_SC_E0_A2_SEPARATE_RESULT_REVIEW_V1','study_id':'FP-SC-001','stage':'E0_A2',
      'reviewer':'/root/design_audit','reviewer_provenance':'SAME_SESSION_SEPARATE_REVIEWER','external_independent_accept':False,
      'utc_start':dt.datetime.now(dt.timezone.utc).isoformat(),'checker_sha256':sha(__file__),
      'independent_arithmetic_module_sha256':sha(Path(arithmetic.__file__)),
      'implementation_commit':manifest['implementation_commit'],'execution_commit':manifest['execution_commit'],
      'execution_lock_sha256':manifest['execution_lock_sha256'],'code_lock_sha256':sha(a2/'CODE_LOCK.json'),
      'rematerialized_registry_sha256':sha(a2/'controls/REGISTRY.json'),'production_functions_imported':False,
      'original_RUN_E0_001_unchanged':True,'historical_control_byte_identity':'UNRESOLVED_R4_R5','next_stage_GO':False,
      'failures':[]}
    try:
        print('CHECK identities and controls',flush=True)
        identities=inputs_and_controls(repo,run,a2);report['identities_and_controls']=identities
        (out/'IDENTITIES_AND_CONTROLS.json').write_text(json.dumps(identities,indent=2)+'\n')
        print('CHECK12 baseline recursions and independent propagation/Joseph',flush=True)
        result=arithmetic.check_baseline(repo,run);report['baseline']=result
        (out/'BASELINE.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        complete=(result['status']=='PASS' and len(result['cells'])==12 and result['total_update_rows']==12544 and result['full_replay_compared_rows']==12544 and result['independent_prediction_rows']==12544)
        passed=identities['status']=='PASS' and complete
        report['verdict']='PASS_NUMERICAL_REPRODUCTION_WITH_REMATERIALIZED_CONTROLS' if passed else 'FAIL_OR_PARTIAL_A2_NUMERICAL_REPRODUCTION'
        report['qualified_functional_H0']='SUPPORTED_WITH_EXPLICIT_INPUT_IDENTITY_QUALIFICATION' if passed else 'HOLD'
    except Exception as exc:
        import traceback
        report['failures'].append({'error':str(exc),'traceback':traceback.format_exc()})
        report['verdict']='FAIL_OR_PARTIAL_A2_NUMERICAL_REPRODUCTION';passed=False
    report['utc_end']=dt.datetime.now(dt.timezone.utc).isoformat()
    report['claim_limits']=['Historical R4/R5 ds bytes were not recovered.','Original failed RUN_E0_001 remains unchanged.','A2 validates numerical reproduction under the original1e-10 criterion and exact discrete mask/time/pose agreement.','SourceFFD polarization and BASE shadow engine are source-reviewed and full-replay-compared, not independently reimplemented.','No FP selector, E1-E5, RF-noise robustness, performance improvement or realtime claim.']
    (out/'E0_A2_RESULT_REVIEW.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    (out/'ARTIFACT_HASHES.json').write_text(json.dumps({p.name:sha(p) for p in sorted(out.iterdir()) if p.is_file() and p.name!='ARTIFACT_HASHES.json'},indent=2)+'\n')
    print(json.dumps({'verdict':report['verdict'],'failures':len(report['failures'])}),flush=True)
    raise SystemExit(0 if passed else 2)


if __name__=='__main__':main()
