"""Revalidate retained capture under an explicit amendment, preserving old STOP."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from qa import evaluate_arrays

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from producer import validate_runtime, BLOCK


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):
            h.update(block)
    return h.hexdigest()


def main(capture,out,source):
    if out.exists():
        raise ValueError('preserve evidence; new output required')
    manifest = json.loads((capture/'MANIFEST.json').read_text())
    hashes = json.loads((capture/'ARTIFACT_HASHES.json').read_text())
    runtime = validate_runtime(manifest['lock'])
    for name, digest in hashes.items():
        p = (capture/name).resolve()
        if not p.is_relative_to(capture.resolve()) or sha(p) != digest:
            raise ValueError('capture artifact mismatch '+name)
    if sha(capture/'RAW.npz') != manifest['raw_sha256']:
        raise ValueError('raw manifest binding')
    for name, digest in manifest['lock']['source_sha256'].items():
        if sha(source/name) != digest:
            raise ValueError('source mismatch '+name)
    with np.load(capture/'RAW.npz',allow_pickle=False) as z:
        arrays = {k:z[k] for k in z.files}
    case = manifest['case']
    pid = manifest['pose']['pose_id']
    for key, path in (
        ('archive_full',source/BLOCK/'FULL_RF'/('H_'+case+'.npy')),
        ('archive_los',source/BLOCK/('H_LoS_'+case+'.npy'))):
        if not np.array_equal(arrays[key],np.load(path,mmap_mode='r')[pid,:,:,0]):
            raise ValueError('archived source slice '+key)
    if not np.array_equal(arrays['frequencies_hz'],np.load(source/BLOCK/'freqs_hz.npy')):
        raise ValueError('archive frequency grid')
    result, groups = evaluate_arrays(arrays)
    result.update(case=case,pose_id=pid,old_capture_status=manifest['status'],
        old_capture_status_unchanged=True,independent_audit='PENDING',
        new_pathsolver_calls=0,causal_analysis_run=False,remaining_poses_run=0,
        contract_timing='post-hoc amended revalidation of already observed canary',
        source_base_revision='5e13c6025074d74c90644412d5a006f6c2a20e13',
        command=sys.argv,timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        runtime=runtime,input_sha256={name:sha(capture/name) for name in ('RAW.npz','MANIFEST.json','ARTIFACT_HASHES.json')},
        source_sha256=manifest['lock']['source_sha256'],
        code_contract_sha256={p.name:sha(p) for p in sorted(HERE.iterdir()) if p.suffix in ('.py','.md')},
        governance_sha256={n:sha(Path('/mnt/c/Users/Myoungsun Kim/.codex/research-governance')/n) for n in ('COMMON_CONTRACT.md','ROLE_IMPLEMENTER.md')})
    out.mkdir(parents=True)
    np.savez_compressed(out/'LEGACY_ATTRIBUTION_FIELDS.npz',group_fields=groups,
        native_full=groups.sum(0),frequencies_hz=arrays['frequencies_hz'],
        group_labels=arrays['group_labels'],direct_group=arrays['direct_group'])
    result['output_sha256'] = {'LEGACY_ATTRIBUTION_FIELDS.npz':sha(out/'LEGACY_ATTRIBUTION_FIELDS.npz')}
    (out/'RESULT.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(status=result['status'],checks=result['checks'],old_status=manifest['status'])))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--capture',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True)
    args = p.parse_args()
    main(args.capture,args.out,args.source)
