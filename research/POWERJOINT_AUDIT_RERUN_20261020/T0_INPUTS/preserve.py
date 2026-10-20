"""Preserve exact Actions archives in an immutable research release.

Credential sources: GH_TOKEN in Actions; local Git credential helper otherwise.
Credentials remain in memory, never in arguments, files, or logs.
"""
from __future__ import annotations
import argparse,datetime,hashlib,json,os,pathlib,subprocess,zipfile,time
import requests
REPO='myoungsunk/sionna-resimulation'
HERE=pathlib.Path(__file__).resolve().parent
def session():
    token=os.environ.get('GH_TOKEN')
    if not token:
        p=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\n\n',text=True,capture_output=True,check=True)
        token=dict(x.split('=',1) for x in p.stdout.splitlines() if '=' in x)['password']
    s=requests.Session();s.headers.update({'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
    return s
def api(s,path,method='GET',**kw):
    r=s.request(method,'https://api.github.com/repos/'+REPO+'/'+path,timeout=120,**kw)
    if r.status_code>=400:raise RuntimeError(f'{path}: HTTP {r.status_code} {r.text[:300]}')
    return r.json() if r.content else None
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def download(s,url,p,headers=None):
    r=s.get(url+'?nonce='+str(time.time_ns()),headers=headers,allow_redirects=False,timeout=(15,30))
    if r.status_code in (301,302,303,307,308):
        r=requests.get(r.headers['Location'],stream=True,timeout=(15,60))
    r.raise_for_status()
    with p.open('wb') as f:
        for b in r.iter_content(2**20):f.write(b)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--cache',type=pathlib.Path,required=True);a=ap.parse_args()
    a.cache.mkdir(parents=True,exist_ok=True);lock=json.loads((HERE/'PROTOCOL_LOCK.json').read_text());s=session();records=[]
    rel=api(s,'releases/tags/'+lock['release']) if s.get('https://api.github.com/repos/'+REPO+'/releases/tags/'+lock['release'],timeout=60).status_code==200 else api(s,'releases','POST',json={'tag_name':lock['release'],'target_commitish':lock['base_commit'],'name':'POWERJOINT audit immutable input preservation 2026-10-20','body':'Original Actions archives preserved byte-for-byte. Scientific results and approvals are separate. See INPUT_RECEIPT.json on research/powerjoint-audit-rerun-20261020.','draft':False,'prerelease':False})
    for aid in lock['artifact_ids']:
        d=api(s,f'actions/artifacts/{aid}');p=a.cache/f'artifact-{aid}.zip';expected=d.get('digest','').removeprefix('sha256:')
        if not p.exists() or (expected and sha(p)!=expected):
            print('DOWNLOAD',aid,d['size_in_bytes'],flush=True);download(s,f'https://api.github.com/repos/{REPO}/actions/artifacts/{aid}/zip',p)
        digest=sha(p)
        if expected and expected!=digest:raise RuntimeError(f'Actions digest mismatch {aid}')
        assets=api(s,f"releases/{rel['id']}/assets");asset=next((x for x in assets if x['name']==p.name),None)
        if asset is None:
            print('UPLOAD',aid,p.stat().st_size,digest,flush=True)
            with p.open('rb') as f:
                r=s.post(rel['upload_url'].split('{')[0],params={'name':p.name},headers={'Content-Type':'application/zip'},data=f,timeout=(30,600));r.raise_for_status();asset=r.json()
        if asset['size']!=p.stat().st_size:raise RuntimeError(f'Release size mismatch {aid}')
        rd=asset.get('digest','').removeprefix('sha256:')
        if rd and rd!=digest:raise RuntimeError(f'Release digest mismatch {aid}')
        # Public download readback, independently hash streamed bytes without keeping a second archive.
        r=requests.get(asset['browser_download_url'],stream=True,timeout=(30,180));r.raise_for_status();h=hashlib.sha256();n=0
        for b in r.iter_content(2**20):h.update(b);n+=len(b)
        if h.hexdigest()!=digest or n!=p.stat().st_size:raise RuntimeError(f'Release readback mismatch {aid}')
        with zipfile.ZipFile(p) as z:members=[{'name':i.filename,'bytes':i.file_size,'crc':i.CRC} for i in z.infolist()]
        record={'artifact_id':aid,'actions_run_id':d['workflow_run']['id'],'actions_head_sha':d['workflow_run']['head_sha'],'original_name':d['name'],'release_asset_id':asset['id'],'release_asset_url':asset['browser_download_url'],'sha256':digest,'bytes':p.stat().st_size,'actions_digest_verified':bool(expected),'release_digest_verified':bool(rd),'release_download_readback_verified':True,'members':members}
        records.append(record);(HERE/'INPUT_RECEIPT.json').write_text(json.dumps({'release':lock['release'],'release_url':rel['html_url'],'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'TECHNICAL_PASS' if len(records)==5 else 'IN_PROGRESS','inputs':records},indent=2)+'\n')
        print('PRESERVED',aid,digest,flush=True)
    (HERE/'MANIFEST.json').write_text(json.dumps({'task':'T0_INPUTS','protocol_sha256':sha(HERE/'PROTOCOL_LOCK.json'),'script_sha256':sha(pathlib.Path(__file__)),'receipt_sha256':sha(HERE/'INPUT_RECEIPT.json'),'command':subprocess.list2cmdline(['python',str(pathlib.Path(__file__).name),'--cache','<external-cache>']),'inputs':records},indent=2)+'\n')
if __name__=='__main__':
    try:main()
    except Exception as exc:
        p=HERE/'ERRORS.json';old=json.loads(p.read_text()) if p.exists() else []
        old.append({'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'error':str(exc),'retry':'not automatic; preserve completed assets and diagnose'});p.write_text(json.dumps(old,indent=2)+'\n');raise
