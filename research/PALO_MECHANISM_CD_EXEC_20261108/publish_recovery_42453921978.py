"""Recover and publish an ALREADY VERIFIED C/D Action's artifact, without rerunning science.

Tree insertion uses small immutable subtrees to avoid GitHub's large-tree 502.
Only the original run 42453921978 is accepted. No data or scores are rewritten.
"""
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

REPO = 'myoungsunk/sionna-resimulation'
RUN = '42453921978'
SOURCE_SHA = 'd46a1fb924688284f780d3546288b2e0dba5b7d6'
BRANCH = 'analysis/palo-mechanism-cd-execution-20261108'
PREFIX = f'research/PALO_MECHANISM_CD_EXEC_20261108/runs/{RUN}'
REPORT = Path('PUBLISH_RECOVERY_RECEIPT.json')


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def blob_sha(b):
    return hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()


def api(method, endpoint, body=None):
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        raise RuntimeError('Missing GitHub token: no publication')
    uri=f'https://api.github.com/repos/{REPO}/{endpoint}'
    payload=None if body is None else json.dumps(body,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json',
             'Content-Type':'application/json','X-GitHub-Api-Version':'2022-11-28'}
    for attempt in range(8):
        req=urllib.request.Request(uri, method=method, data=payload, headers=headers)
        try:
            with urllib.request.urlopen(req,timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            error=e.read(3000).decode('utf-8',errors='replace')
            if e.code not in (429,500,502,503,504) or attempt>=7:
                raise RuntimeError(f'GitHub API {method} {endpoint} failed HTTP {e.code}: {error[:300]}') from e
            delay=min(2**attempt,40)
            print(f'TRANSIENT_API_RETRY {method} {endpoint} HTTP {e.code} after {delay}s',flush=True)
            time.sleep(delay)
    raise RuntimeError('Unreachable GitHub retry state')


def read_verified_output():
    candidates=[Path('restored/output'),Path('restored'),Path('output')]
    roots=[p for p in candidates if (p/'OUTPUT_SHA256.json').is_file()]
    if len(roots)!=1:
        raise RuntimeError(f'Cannot resolve one retained output root: {roots}')
    root=roots[0]
    verify=json.loads((root/'VERIFY_RECEIPT.json').read_text(encoding='utf-8'))
    complete=json.loads((root/'EXECUTION_COMPLETE.json').read_text(encoding='utf-8'))
    contract=json.loads((root/'EXECUTION_CONTRACT.json').read_text(encoding='utf-8'))
    if verify.get('status')!='PASS' or complete.get('status')!='COMPLETE_SELF_CHECK_PASS':
        raise RuntimeError('Original independent arithmetic verification did not pass')
    if (int(verify.get('factorial_rows',-1))!=74784 or
        int(verify.get('D_horizon_rows',-1))!=250200 or
        int(verify.get('raw_branch_steps',-1))!=4606240 or
        int(verify.get('scalar_source_spot_checks',-1))!=2352):
        raise RuntimeError('Original verified result counts differ from contract')
    if (str(complete.get('github_run_id'))!=RUN or
        str(complete.get('source_sha'))!=SOURCE_SHA or
        str(contract.get('github_run_id'))!=RUN or
        str(contract.get('source_sha'))!=SOURCE_SHA):
        raise RuntimeError('Source/run attribution mismatch')
    manifest=json.loads((root/'OUTPUT_SHA256.json').read_text(encoding='utf-8'))
    if len(manifest)<296:
        raise RuntimeError(f'Manifest unexpectedly short {len(manifest)}')
    actual={}
    total=0
    for name,meta in sorted(manifest.items()):
        # Manifest was generated on Windows; Actions artifact is recovered on Linux.
        # Normalize path separators only. Preserve the stored filename and SHA values.
        canonical=name.replace(chr(92),'/')
        if canonical in actual or canonical.startswith('/') or '..' in canonical.split('/'):
            raise RuntimeError('Ambiguous or unsafe manifest path '+name)
        f=root.joinpath(*canonical.split('/'))
        if not f.is_file() or f.is_symlink() or not f.resolve().is_relative_to(root.resolve()):
            raise RuntimeError('Invalid source file/path '+name)
        content=f.read_bytes()
        if len(content)!=meta['bytes'] or sha256(content)!=meta['sha256']:
            raise RuntimeError('SHA256 or byte count mismatch '+name)
        actual[canonical]=blob_sha(content)
        total+=len(content)
    # The producer checks every payload except its own manifest; include that immutable manifest.
    manifest_content=(root/'OUTPUT_SHA256.json').read_bytes()
    actual['OUTPUT_SHA256.json']=blob_sha(manifest_content)
    total+=len(manifest_content)
    observed={f.relative_to(root).as_posix() for f in root.rglob('*') if f.is_file()}
    if observed!=set(actual):
        raise RuntimeError(f'Unmanifested/missing files: {sorted(observed^set(actual))[:10]}')
    print('RECOVERY_SHA_VERIFIED',len(actual),'files',total,'bytes',flush=True)
    return root,actual,verify,total


def tree_for_entries(items):
    # Repeated small Git tree updates, preserving previously-created immutable entries.
    if not items:
        return api('POST','git/trees',{'tree':[]})['sha']
    tree=None
    for start in range(0,len(items),16):
        part=items[start:start+16]
        payload={'tree':part}
        if tree:
            payload['base_tree']=tree
        tree=api('POST','git/trees',payload)['sha']
        print('TREE_CHUNK_PASS',min(start+len(part),len(items)),'/',len(items),flush=True)
    return tree


def build_nested(files):
    here=[]
    folders=defaultdict(dict)
    for rel,sha in sorted(files.items()):
        prefix,sep,remain=rel.partition('/')
        if sep:
            folders[prefix][remain]=sha
        else:
            here.append({'path':prefix,'mode':'100644','type':'blob','sha':sha})
    for name,child in sorted(folders.items()):
        t=build_nested(child)
        here.append({'path':name,'mode':'040000','type':'tree','sha':t})
    return tree_for_entries(here)


def verify_tree(root_sha,expected):
    current=root_sha
    for part in PREFIX.split('/'):
        d=api('GET',f'git/trees/{current}')
        if d.get('truncated'):
            raise RuntimeError('Tree listing truncated on path '+part)
        match=[z['sha'] for z in d['tree'] if z['path']==part and z['type']=='tree']
        if len(match)!=1:
            raise RuntimeError('Published directory missing '+part)
        current=match[0]
    d=api('GET',f'git/trees/{current}?recursive=1')
    if d.get('truncated'):
        raise RuntimeError('Recursive verified tree truncated')
    got={z['path']:z['sha'] for z in d['tree'] if z['type']=='blob'}
    if got!=expected:
        missing=set(expected)-set(got);extra=set(got)-set(expected)
        wrong=[n for n in set(expected)&set(got) if got[n]!=expected[n]]
        raise RuntimeError(f'Tree mismatch missing={len(missing)} extra={len(extra)} wrong={len(wrong)}')
    return current


def main():
    if os.environ.get('GITHUB_REF_NAME')!=BRANCH:
        raise RuntimeError('Publishing outside fixed branch is prohibited')
    head=os.environ.get('GITHUB_SHA')
    if not head or len(head)!=40:
        raise RuntimeError('No verified current workflow commit')
    root,hashes,verification,total=read_verified_output()
    remote=api('GET','git/ref/heads/'+quote(BRANCH,safe='/'))
    if remote['object']['sha']!=head:
        raise RuntimeError('Branch advanced; refusing stale push')
    tree_data=build_nested(hashes)
    parent=api('GET','git/commits/'+head)
    # Atomically add a single validated subtree to the original root.
    added=api('POST','git/trees',{'base_tree':parent['tree']['sha'],
        'tree':[{'path':PREFIX,'mode':'040000','type':'tree','sha':tree_data}]})
    found=verify_tree(added['sha'],hashes)
    if found!=tree_data:
        raise RuntimeError('Submitted and retrieved immutable result trees differ')
    commit=api('POST','git/commits',{'message':f'Recover verified PALO C/D outputs from Actions run {RUN}',
        'tree':added['sha'],'parents':[head]})
    api('PATCH','git/refs/heads/'+quote(BRANCH,safe='/'),{'sha':commit['sha'],'force':False})
    now=api('GET','git/ref/heads/'+quote(BRANCH,safe='/'))
    if now['object']['sha']!=commit['sha']:
        raise RuntimeError('Remote ref mismatch after publication')
    receipt={'status':'PUBLISHED_VERIFIED','original_science_run_id':RUN,
        'source_commit':SOURCE_SHA,'recovery_commit':head,'result_commit':commit['sha'],
        'result_path':PREFIX,'files':len(hashes),'bytes':total,
        'root_tree_sha':added['sha'],'results_tree_sha':tree_data,
        'verification':verification,'independent_science_audit':False}
    REPORT.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('RECOVERY_PUBLISH_PASS',json.dumps(receipt,ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
