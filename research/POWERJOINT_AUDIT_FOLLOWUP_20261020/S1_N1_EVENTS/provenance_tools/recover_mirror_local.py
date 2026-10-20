from pathlib import Path
import hashlib,json,sys,time,zipfile,os
sys.path.insert(0,r'D:/tmp/sionna-powerjoint-followup-20261020/research/POWERJOINT_AUDIT_FOLLOWUP_20261020/S0_CORRECTIONS')
from github_io import session,api,download
ROOT=Path(r'D:/tmp/pj_s1_release_recovery');ROOT.mkdir(exist_ok=True)
rid=39371510111;name=f'powerjoint-s1-results-{rid}.zip';s=session()
deadline=time.monotonic()+7200
while True:
    rel=api(s,'releases/tags/audit-traces-20261020-r01');page=1;asset=None
    while True:
        rows=api(s,f"releases/{rel['id']}/assets",params={'per_page':100,'page':page})
        asset=next((x for x in rows if x['name']==name),None)
        if asset or len(rows)<100:break
        page+=1
    if asset and asset.get('state')=='uploaded':break
    r=api(s,f'actions/runs/{rid}')
    if r['status']=='completed' and r['conclusion']!='success':raise RuntimeError('OUTPUT_PRESERVATION_FAILED:'+str(r['conclusion']))
    assert time.monotonic()<deadline,'WAIT_TIMEOUT'
    if Path(os.environ['MANAGED_PROCESS_STOP_FILE']).exists():raise SystemExit('STOP_REQUESTED')
    time.sleep(30)
archive=ROOT/name
transport_errors=[]
for attempt in range(1,4):
    try:
        digest,n=download(s,asset['browser_download_url'],archive);break
    except Exception as exc:
        transport_errors.append(dict(attempt=attempt,error=str(exc),retry=attempt<3))
        (ROOT/'PUBLIC_TRANSPORT_ATTEMPTS.json').write_text(json.dumps(transport_errors,indent=2))
        if attempt==3:raise
        time.sleep(15)
assert digest==asset['digest'].removeprefix('sha256:') and n==asset['size'],'SUMMARY_BUNDLE_SHA'
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None,'SUMMARY_BUNDLE_CRC'
    for info in z.infolist():
        if info.is_dir():continue
        rel=Path(info.filename);assert not rel.is_absolute() and '..' not in rel.parts
        target=ROOT/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(info))
receipt=json.loads((ROOT/'RECOVERY_RECEIPT.json').read_text())
assert receipt['complete'] and len(receipt['records'])==10
members_verified=0
for record in receipt['records']:
    root=ROOT/f"run-{record['actions_run_id']}"/record['name']
    assert record['archive_sha256']==record['release_readback_sha256']
    for member in record['members']:
        if not member.get('summary_extracted'):continue
        data=(root/member['name']).read_bytes()
        assert len(data)==member['bytes'] and hashlib.sha256(data).hexdigest()==member['sha256']
        members_verified+=1
proof={'preservation_actions_run_id':rid,'bundle_release_asset_id':asset['id'],'bundle_release_url':asset['browser_download_url'],'bundle_sha256':digest,'bundle_bytes':n,'full_bundle_SHA_CRC_verified':True,'original_member_hashes_verified':members_verified}
(ROOT/'PUBLIC_BUNDLE_RECEIPT.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof),flush=True)
