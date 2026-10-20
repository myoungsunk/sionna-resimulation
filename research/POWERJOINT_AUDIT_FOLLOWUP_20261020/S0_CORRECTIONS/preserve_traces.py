"""Preserve the complete base-audit Actions inventory, verify full readback."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import time
import zipfile
import requests
from github_io import REPO,api,download,session,sha

HERE=Path(__file__).resolve().parent
def stamp():return datetime.now(timezone.utc).isoformat()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--cache',type=Path,required=True);args=ap.parse_args();args.cache.mkdir(parents=True,exist_ok=True)
    lock=json.loads((HERE/'PROTOCOL_LOCK.json').read_text());inventory=json.loads((HERE/'TRACE_INVENTORY.json').read_text());s=session()
    release=lock['S0_5']['release'];records=[];errors=[]
    path='releases/tags/'+release
    try:rel=api(s,path)
    except RuntimeError as exc:
        if 'HTTP404' not in str(exc):raise
        rel=api(s,'releases','POST',json=dict(tag_name=release,target_commitish=lock['base_commit'],name='POWERJOINT audit trace preservation 2026-10-20',body='Byte-preserved original Actions archives referenced by audit commit034e57a. No new recursive experiment. See S0 TRACE_RECEIPT.json on research/powerjoint-audit-followup-20261020.',draft=False,prerelease=False))
    assets={};page=1
    while True:
        batch=api(s,f"releases/{rel['id']}/assets?per_page=100&page={page}")
        assets.update({a['name']:a for a in batch})
        if len(batch)<100:break
        page+=1
    def save():
        passed=[r for r in records if r['verification_status']=='VERIFIED_ORIGINAL_AND_RELEASE_READBACK']
        receipt=dict(stage='S0-5_TRACE_PRESERVATION',base_commit=lock['base_commit'],lock_commit='a37364c11587bae951955e1beb020261118310c1',
                     protocol_sha256=sha(HERE/'PROTOCOL_LOCK.json'),inventory_sha256=sha(HERE/'TRACE_INVENTORY.json'),release=release,release_url=rel['html_url'],
                     actions_run_id=os.getenv('GITHUB_RUN_ID'),execution_commit=os.getenv('GITHUB_SHA'),timestamp_utc=stamp(),
                     expected_artifact_count=inventory['artifact_count'],preserved_artifact_count=len(records),verified_artifact_count=len(passed),
                     total_preserved_bytes=sum(r['downloaded_bytes'] for r in records),
                     task_status='COMPLETE' if len(passed)==inventory['artifact_count'] else 'IN_PROGRESS_OR_UNVERIFIED',
                     scientific_verdict='NOT_APPLICABLE_PRESERVATION_ONLY',artifacts=records,
                     reconciliation=dict(expected_ids=[r['artifact_id'] for r in inventory['artifacts']],recorded_ids=[r['artifact_id'] for r in records]),
                     self_reference_exclusion='Followup receipt artifact created after this inventory is recorded separately; it is not a base-audit trace input.')
        (HERE/'TRACE_RECEIPT.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
        (HERE/'ERRORS_PRESERVATION.json').write_text(json.dumps(errors,indent=2),encoding='utf-8')
    for item in inventory['artifacts']:
        aid=item['artifact_id'];name=f'artifact-{aid}.zip';d=api(s,f'actions/artifacts/{aid}')
        expected=(d.get('digest') or '').removeprefix('sha256:');p=args.cache/name
        if item['original_digest']!=d.get('digest') or item['bytes']!=d['size_in_bytes']:raise RuntimeError('INVENTORY_DRIFT:'+str(aid))
        if not p.exists():
            for attempt in range(3):
                candidate=args.cache/f'artifact-{aid}-attempt{attempt}.zip'
                try:
                    digest,n=download(s,f'https://api.github.com/repos/{REPO}/actions/artifacts/{aid}/zip',candidate)
                    if n!=d['size_in_bytes'] or (expected and digest!=expected):raise RuntimeError('ORIGINAL_SHA_OR_SIZE_MISMATCH')
                    candidate.rename(p);break
                except Exception as exc:
                    errors.append(dict(timestamp_utc=stamp(),artifact_id=aid,operation='download_original',attempt=attempt,error=str(exc),retry=attempt<2));save()
                    if attempt==2:raise
                    time.sleep(2)
        digest=sha(p);n=p.stat().st_size
        if n!=d['size_in_bytes'] or (expected and digest!=expected):raise RuntimeError('CACHED_ORIGINAL_MISMATCH:'+str(aid))
        asset=assets.get(name);reused=asset is not None
        if asset is None:
            print('UPLOAD',aid,n,flush=True)
            with p.open('rb') as f:
                r=s.post(rel['upload_url'].split('{')[0],params={'name':name},headers={'Content-Type':'application/zip'},data=f,timeout=(30,600));r.raise_for_status();asset=r.json()
            assets[name]=asset
        if asset['size']!=n:raise RuntimeError('EXISTING_RELEASE_SIZE_MISMATCH:'+str(aid))
        asset_digest=(asset.get('digest') or '').removeprefix('sha256:')
        if asset_digest and asset_digest!=digest:raise RuntimeError('EXISTING_RELEASE_DIGEST_MISMATCH:'+str(aid))
        # Full public release readback, separately hash every byte, no second archive.
        r=requests.get(asset['browser_download_url']+'?nonce='+str(time.time_ns()),stream=True,timeout=(30,180));r.raise_for_status();h=hashlib.sha256();rn=0
        for b in r.iter_content(2**20):h.update(b);rn+=len(b)
        if h.hexdigest()!=digest or rn!=n:raise RuntimeError('RELEASE_READBACK_MISMATCH:'+str(aid))
        with zipfile.ZipFile(p) as z:
            members=z.infolist();npz_count=sum(x.filename.endswith('.npz') for x in members)
        record=dict(artifact_id=aid,run_id=d['workflow_run']['id'],source_commit=d['workflow_run']['head_sha'],original_name=d['name'],
                    original_digest=d.get('digest'),original_digest_present=bool(expected),original_digest_verified=bool(expected) and digest==expected,
                    downloaded_sha256=digest,downloaded_bytes=n,release_asset_id=asset['id'],release_asset_url=asset['browser_download_url'],
                    release_asset_digest=asset.get('digest'),release_download_sha256=h.hexdigest(),release_download_bytes=rn,
                    reused_existing_asset=reused,member_count=len(members),npz_member_count=npz_count,
                    verification_status='VERIFIED_ORIGINAL_AND_RELEASE_READBACK' if expected else 'PRESERVED_ORIGINAL_DIGEST_UNAVAILABLE')
        records.append(record);save();print('PRESERVED',aid,n,digest,flush=True)
    save()
    if len(records)!=inventory['artifact_count'] or any(not r['original_digest_verified'] for r in records):raise RuntimeError('PRESERVATION_GATE_NOT_VERIFIED')
    print(json.dumps(dict(task_status='COMPLETE',artifacts=len(records),bytes=sum(r['downloaded_bytes'] for r in records))),flush=True)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        path=HERE/'ERRORS_PRESERVATION_FATAL.json';prior=json.loads(path.read_text()) if path.exists() else []
        prior.append(dict(timestamp_utc=stamp(),error=str(exc),retry='No followup analysis; diagnose transport/input before a preserved retry.'))
        path.write_text(json.dumps(prior,indent=2),encoding='utf-8');raise
