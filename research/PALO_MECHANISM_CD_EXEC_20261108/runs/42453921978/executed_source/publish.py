"""Publish verified outputs into a NEW run folder; never force-update a ref."""
import argparse
import base64
import hashlib
import json
import os
import urllib.request
from pathlib import Path
from urllib.parse import quote
from common import REPO, dump, sha256, blob_sha


def api(method,path,payload=None):
    token=os.environ.get('GITHUB_TOKEN')
    if not token:raise RuntimeError('GITHUB_TOKEN unavailable; no publish attempted')
    req=urllib.request.Request('https://api.github.com/repos/'+REPO+'/'+path,method=method,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','Content-Type':'application/json','X-GitHub-Api-Version':'2022-11-28'})
    with urllib.request.urlopen(req,timeout=120) as r:
        return json.load(r)


def subtree(tree_sha,parts):
    for part in parts:
        obj=api('GET','git/trees/'+tree_sha)
        assert not obj.get('truncated',False)
        found=[x for x in obj['tree'] if x['path']==part and x['type']=='tree']
        if len(found)!=1:raise RuntimeError('Published path not found: '+part)
        tree_sha=found[0]['sha']
    return api('GET','git/trees/'+tree_sha+'?recursive=1')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    branch=os.environ['GITHUB_REF_NAME'];source=os.environ['GITHUB_SHA'];run=os.environ['GITHUB_RUN_ID']
    if not branch.startswith('analysis/palo-mechanism-cd-execution-'):raise RuntimeError('Ref outside authorized execution branch prefix')
    if json.loads((a.output/'VERIFY_RECEIPT.json').read_text())['status']!='PASS':raise RuntimeError('Verification did not pass')
    manifest=json.loads((a.output/'OUTPUT_SHA256.json').read_text())
    for rel,record in manifest.items():
        data=(a.output/rel).read_bytes();assert len(data)==record['bytes'] and sha256(data)==record['sha256']
    ref=api('GET','git/ref/heads/'+quote(branch,safe='/'))
    if ref['object']['sha']!=source:raise RuntimeError('Branch advanced: refusing stale publication')
    parent=api('GET','git/commits/'+source)
    prefix='research/PALO_MECHANISM_CD_EXEC_20261108/runs/'+run
    nodes=[];expected={}
    for file in sorted(a.output.rglob('*')):
        if not file.is_file():continue
        data=file.read_bytes()
        if len(data)>90_000_000:raise RuntimeError('Split oversized data file before publication: '+file.name)
        blob=api('POST','git/blobs',dict(encoding='base64',content=base64.b64encode(data).decode()))
        assert blob['sha']==blob_sha(data)
        rel=file.relative_to(a.output).as_posix();expected[rel]=blob['sha']
        nodes.append(dict(path=prefix+'/'+rel,mode='100644',type='blob',sha=blob['sha']))
    tree=api('POST','git/trees',dict(base_tree=parent['tree']['sha'],tree=nodes))
    verified=subtree(tree['sha'],prefix.split('/'))
    if verified.get('truncated'):raise RuntimeError('Cannot verify published subtree')
    actual={r['path']:r['sha'] for r in verified['tree'] if r['type']=='blob'}
    assert actual==expected
    commit=api('POST','git/commits',dict(message=f'Execute PALO mechanism C/D: run {run}; parity and arithmetic checks pass',tree=tree['sha'],parents=[source]))
    # GitHub rejects a non-fast-forward update; NEVER set force=True.
    api('PATCH','git/refs/heads/'+quote(branch,safe='/'),dict(sha=commit['sha'],force=False))
    check=api('GET','git/ref/heads/'+quote(branch,safe='/'))
    assert check['object']['sha']==commit['sha']
    receipt=dict(status='PUSH_VERIFIED',branch=branch,source_commit=source,result_commit=commit['sha'],run_id=run,files=len(expected),git_tree=tree['sha'],result_path=prefix)
    dump(Path('PUBLISH_RECEIPT.json'),receipt)
    print(json.dumps(receipt,indent=2),flush=True)

if __name__=='__main__':main()
