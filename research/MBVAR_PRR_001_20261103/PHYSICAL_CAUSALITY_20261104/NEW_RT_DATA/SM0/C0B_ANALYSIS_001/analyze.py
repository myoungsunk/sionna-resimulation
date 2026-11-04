"""Audited-data-only C0-B diagnostics, using amended legacy ray spectra."""
import argparse
import csv
import datetime
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

HERE = Path(__file__).resolve().parent
SM0 = HERE.parent
sys.path.insert(0,str(SM0))
sys.path.insert(0,str(SM0/'PRECISION_AMENDMENT_001'))
from qa import evaluate_arrays
from diagnostics_amended import evaluate
from producer import validate_runtime


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def put(p,obj):
    p.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n',encoding='utf8')


def main(out,acceptance,go_path):
    if sys.flags.optimize:
        raise ValueError('optimized Python disables required diagnostic assertions')
    accepted = json.loads(acceptance.read_text())
    go = json.loads(go_path.read_text())
    code = {str(p.relative_to(SM0)):sha(p) for p in (HERE/'analyze.py',HERE/'ANALYSIS_CONTRACT_KO.md',HERE/'diagnostics_amended.py',SM0/'PRECISION_AMENDMENT_001/qa.py',SM0/'producer.py',SM0/'PRECISION_AMENDMENT_001/producer.py',SM0/'native_math.py',SM0/'RUNTIME_LOCK.json')}
    if accepted.get('decision') != 'ACCEPT' or accepted.get('scope') != 'ALL_15_AMENDED_SM0_DATA':
        raise ValueError('independent complete-data acceptance required')
    if go.get('decision') != 'GO' or go.get('code_sha256') != code or go.get('data_acceptance_sha256') != sha(acceptance):
        raise ValueError('independent C0-B code/data GO binding')
    items = accepted['captures']
    expected = [('R4_aB_m0',194),*[("R4_aB_m0",i) for i in (168,172,173,234,500,525,729)],*[("R5_aB_m0",i) for i in (401,465,979,980,982,983)],('R2_aB_m0',525)]
    if [(i['case'],i['pose_id']) for i in items] != expected:
        raise ValueError('complete ordered 15-pose scope required')
    # Validate every input binding before generating any FFT result.
    for item in items:
        capture = (SM0/item['capture']).resolve()
        if not capture.is_relative_to(SM0.resolve()):
            raise ValueError('capture path outside SM0')
        if sha(capture/'RAW.npz') != item['raw_sha256'] or sha(capture/'MANIFEST.json') != item['manifest_sha256']:
            raise ValueError('audited capture hash')
        manifest = json.loads((capture/'MANIFEST.json').read_text())
        if manifest.get('case') != item['case'] or manifest.get('pose',{}).get('pose_id') != item['pose_id']:
            raise ValueError('audited capture pose identity')
    out.mkdir(parents=True,exist_ok=False)
    runtime = validate_runtime(dict(runtime_lock_sha256=sha(SM0/'RUNTIME_LOCK.json')))
    governance = Path('/mnt/c/Users/Myoungsun Kim/.codex/research-governance')
    receipt = dict(status='RUNNING',start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        command=sys.argv,data_acceptance_sha256=sha(acceptance),go_sha256=sha(go_path),code_sha256=code,
        captures=items,completed=[],validated_runtime=runtime,
        governance_sha256={n:sha(governance/n) for n in ('COMMON_CONTRACT.md','ROLE_IMPLEMENTER.md')})
    put(out/'MANIFEST.json',receipt)
    rows = []
    try:
        for item in items:
            capture = SM0/item['capture']
            with np.load(capture/'RAW.npz',allow_pickle=False) as z:
                a = {k:z[k] for k in z.files}
            qa, groups = evaluate_arrays(a)
            if 'legacy_group_fields' in a and not np.array_equal(a['legacy_group_fields'],groups):
                raise ValueError('stored legacy groups mismatch')
            name = item['case']+'_'+str(item['pose_id'])
            folder = out/name
            result = evaluate(folder,a['frequencies_hz'],groups,a['group_labels'].tolist(),int(a['direct_group']),groups.sum(0),a['archive_full'],a['archive_los'])
            for channel in ('full','los'):
                if result['native'][channel]['tap'] != result['archive'][channel]['tap']:
                    raise ValueError('native/archive detector tap mismatch '+name+' '+channel)
            native = result['native']
            with (folder/'surface_removal.csv').open() as f:
                surfaces = list(csv.DictReader(f))
            with (folder/'attribution.csv').open() as f:
                chains = list(csv.DictReader(f))
            valid = [r for r in surfaces if r['tap_ref']=='fpLoS' and r['delta_s_fixed']!='']
            top = max(valid,key=lambda r:abs(float(r['delta_s_fixed']))) if valid else None
            receipt['completed'].append(dict(case=item['case'],pose_id=item['pose_id'],qa_status=qa['status']))
            pose = json.loads((capture/'MANIFEST.json').read_text())['pose']
            rows.append(dict(case=item['case'],pose_id=item['pose_id'],time_s=pose['t'],yaw_deg=pose['yaw_body_deg'],
                fp_full=native['full']['tap'],fp_los=native['los']['tap'],tap_shift=native['delta_tap'],
                range_shift_m=native['delta_range_m'],s_full=native['full']['s'],s_los=native['los']['s'],
                e_mp=native['e_mp'],same_los_tap=native['same_los_tap'],detector_choice=native['detector_choice'],
                identity_error=native['identity_error'],archive_e_mp=result['archive']['e_mp'],
                native_archive_e_mp_difference=native['e_mp']-result['archive']['e_mp'],
                strongest_fixed_los_surface=None if top is None else top['surface'],
                strongest_fixed_los_surface_delta_s=None if top is None else float(top['delta_s_fixed']),
                undefined_surface_signed=sum(r['s_removed_fixed']=='' for r in surfaces),
                undefined_surface_redetected=sum(r['s_removed_redetected']=='' for r in surfaces),
                undefined_chain_signed=sum(r['removed_s_fixed']=='' for r in chains),
                undefined_chain_redetected=sum(r['removed_s_redetected']=='' for r in chains)))
            put(out/'MANIFEST.json',receipt)
        with (out/'SUMMARY.csv').open('w',newline='',encoding='utf8') as f:
            writer = csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        receipt['status'] = 'ANALYSIS_COMPLETE_PENDING_INDEPENDENT_AUDIT'
    except BaseException as exc:
        receipt['status'] = 'STOP';receipt['error'] = repr(exc)
        raise
    finally:
        receipt['end_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        put(out/'MANIFEST.json',receipt)
        put(out/'ARTIFACT_HASHES.json',{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='ARTIFACT_HASHES.json'})


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--acceptance',type=Path,required=True)
    p.add_argument('--go',type=Path,required=True)
    args = p.parse_args()
    main(args.out,args.acceptance,args.go)
