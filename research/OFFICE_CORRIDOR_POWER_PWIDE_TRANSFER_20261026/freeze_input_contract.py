"""Pre-freeze immutable P2 manifests and verify held-route control provenance.

The freeze command only hashes existing inputs. It never downloads, trains,
modifies a dataset, or evaluates RF. Run it as a separate, auditable step.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from office_transfer_core import load_lock, sha256
from runtime_contract import verify_checkout

CASES = ('R2_aA_m0','R2_aA_m45','R2_aB_m0',
         'R4_aA_m0','R4_aB_m0','R5_aA_m0','R5_aB_m0')


def _safe(repo: Path, relative: str) -> Path:
    path = (repo / relative).resolve()
    if not path.is_relative_to(repo):
        raise ValueError('FROZEN_PATH_ESCAPE:' + relative)
    if not path.is_file():
        raise FileNotFoundError('FROZEN_SOURCE_MISSING:' + relative)
    return path


def _unique(artifacts: Path, filename: str) -> Path:
    matches = [p.resolve() for p in artifacts.rglob(filename)
               if p.name == filename and p.is_file()]
    if len(matches) != 1 or not matches[0].is_relative_to(artifacts):
        raise ValueError('FROZEN_ARTIFACT_NOT_UNIQUE:' + filename)
    return matches[0]


def _cases(repo: Path):
    origin = _safe(repo, 'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json')
    records = json.loads(origin.read_text(encoding='utf-8'))['cases']
    if {r['id'] for r in records} != set(CASES) or len(records) != len(CASES):
        raise ValueError('FROZEN_CASE_SET_CHANGED')
    if any(r['id'].split('_', 1)[0] != r['route'] for r in records):
        raise ValueError('FROZEN_CASE_ROUTE_MISMATCH')
    return origin, {r['id']:r for r in records}


def control_files(repo: Path, artifacts: Path) -> dict[str,Path]:
    repo, artifacts = repo.resolve(), artifacts.resolve()
    origin, cases = _cases(repo)
    files = {
        'observations': _unique(artifacts, 'OBSERVATION_FEATURES_LABELS.csv.gz'),
        'packets': _safe(repo, 'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz'),
        'cases': origin,
    }
    for name, case in sorted(cases.items()):
        files[name+'/samples'] = _safe(repo, case['samples_path'])
    return files


def target_files(repo: Path, artifacts: Path, case_name: str, channel: str, bias: str):
    repo, artifacts = repo.resolve(), artifacts.resolve()
    _, cases = _cases(repo)
    if case_name not in cases or channel not in ('full','los') or bias not in ('B0','L2') or (channel=='los' and bias!='B0'):
        raise ValueError('FROZEN_TARGET_CONDITION_INVALID')
    meta = cases[case_name]
    stem = f'{case_name}_{channel}_{bias}'
    files = {name: _unique(artifacts, name) for name in
             (stem+'_TRACE.npz', 'OBSERVATION_FEATURES_LABELS.csv.gz', 'OOF_PARAMETERS.csv.gz')}
    files['HP_PACKETS.csv.gz'] = _safe(repo, 'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz')
    files['SB_SCORES.csv'] = _safe(repo, 'research/PJ_DS_GATED_20261021/results_strict/SB_SCORES.csv')
    if channel == 'los':
        files['los_path'] = _safe(repo, meta['los_path'])
        files['samples_path'] = _safe(repo, meta['samples_path'])
    return files


def _digests(files:dict[str,Path])->dict[str,str]:
    return {key: sha256(file) for key,file in files.items()}


def _write(path:Path, doc:dict)->str:
    # No re-use or overwrite of a frozen evidence file.
    with path.open('x', encoding='utf-8') as f:
        json.dump(doc, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write('\n')
    return sha256(path)


def freeze(repo:Path, artifacts:Path, out:Path, held:str, case:str, channel:str, bias:str, lock_path:Path):
    lock = load_lock(lock_path)
    repo, artifacts = repo.resolve(), artifacts.resolve()
    verify_checkout(repo, lock['corridor_p2_commit'], 'TARGET_P2')
    if not artifacts.is_dir() or repo == artifacts or artifacts.is_relative_to(repo) or repo.is_relative_to(artifacts):
        raise ValueError('FROZEN_ARTIFACT_ROOT_INVALID')
    if held not in ('R2','R4','R5') or case.split('_')[0] != held:
        raise ValueError('FROZEN_HELD_CASE_MISMATCH')
    cf = control_files(repo, artifacts)
    tf = target_files(repo, artifacts, case, channel, bias)
    out = out.resolve()
    if out.exists() or out.is_relative_to(repo) or out.is_relative_to(artifacts):
        raise ValueError('FROZEN_OUTPUT_NOT_FRESH_OR_OVERLAPS')
    out.mkdir(parents=True)
    pctrl = out / f'{held}_control_inputs.json'
    ptgt = out / f'{case}_{channel}_{bias}.json'
    ctrl_sha = _write(pctrl, {
        'schema':'CORRIDOR_CONTROL_INPUTS_V1',
        'held':held, 'target_commit':lock['corridor_p2_commit'], 'files':_digests(cf)})
    tgt_sha = _write(ptgt, {
        'schema':'TRANSFER_TARGET_INPUTS_V1',
        'target_commit':lock['corridor_p2_commit'],
        'condition':{'case':case, 'channel':channel, 'bias':bias}, 'files':_digests(tf)})
    receipts = {'technical':'FROZEN_MANIFESTS_CREATED_NO_RF_EXECUTION',
                'control_manifest':str(pctrl),'control_manifest_sha256':ctrl_sha,
                'target_manifest':str(ptgt),'target_manifest_sha256':tgt_sha,
                'held':held,'condition':{'case':case,'channel':channel,'bias':bias},
                'corridor_checkout':str(repo),'artifacts':str(artifacts),
                'training':'NOT_RUN','replay':'NOT_RUN'}
    _write(out/'FREEZE_RECEIPT.json',receipts)
    return receipts


def validate_control_origin(repo:Path, artifacts:Path, manifest:Path, control_qa:Path, held:str, lock_path:Path):
    """Re-verify the complete train-only input snapshot just before replay."""
    lock=load_lock(lock_path)
    qa=json.loads(Path(control_qa).read_text(encoding='utf-8'))
    identity=qa.get('identity',{})
    if (qa.get('status')!='CORRIDOR_CONTROL_TRAINED' or identity.get('held')!=held or
        identity.get('lock_sha256')!=sha256(lock_path) or
        identity.get('input_manifest_sha256')!=sha256(manifest)):
        raise ValueError('CONTROL_TRAINING_ORIGIN_SHA_MISMATCH')
    record=json.loads(Path(manifest).read_text(encoding='utf-8'))
    actual=control_files(repo, artifacts)
    if (record.get('schema')!='CORRIDOR_CONTROL_INPUTS_V1' or
        record.get('held')!=held or record.get('target_commit')!=lock['corridor_p2_commit'] or
        record.get('files')!=_digests(actual)):
        raise ValueError('CONTROL_TRAINING_INPUTS_CHANGED')
    return {'status':'PASS','input_manifest_sha256':sha256(manifest),
            'n_files':len(actual),'held':held}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--target-checkout',type=Path,required=True)
    p.add_argument('--target-artifacts',type=Path,required=True)
    p.add_argument('--lock',type=Path,default=Path(__file__).with_name('lock.json'))
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--held',choices=['R2','R4','R5'],required=True)
    p.add_argument('--case',choices=CASES,required=True)
    p.add_argument('--channel',choices=['full','los'],default='full')
    p.add_argument('--bias',choices=['B0','L2'],required=True)
    a=p.parse_args(argv)
    q=freeze(a.target_checkout,a.target_artifacts,a.out,a.held,a.case,a.channel,a.bias,a.lock)
    print('FROZEN_INPUT_MANIFESTS',json.dumps(q,ensure_ascii=False))


if __name__=='__main__':
    main()