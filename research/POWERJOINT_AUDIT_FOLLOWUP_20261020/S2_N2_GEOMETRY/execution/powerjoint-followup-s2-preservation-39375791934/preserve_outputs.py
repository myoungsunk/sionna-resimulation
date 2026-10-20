"""Preserve every original S2 archive, including failures. No filter execution."""
from pathlib import Path
import argparse,hashlib,json,os,sys,time,zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'S0_CORRECTIONS'))
from github_io import session,api,download,sha
import requests
def dump(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def upload(s,release,assets,path,name,digest):
 if name in assets:
  asset=assets[name];assert asset['size']==path.stat().st_size and asset.get('digest')=='sha256:'+digest,'EXISTING_ASSET_DIFFERS'
 else:
  with path.open('rb') as f:r=s.post(release['upload_url'].split('{')[0],params={'name':name},headers={'Content-Type':'application/zip'},data=f,timeout=(30,600))
  r.raise_for_status();asset=r.json();assets[name]=asset;assert asset['size']==path.stat().st_size and asset.get('digest')=='sha256:'+digest
 r=requests.get(asset['browser_download_url']+'?nonce='+str(time.time_ns()),stream=True,timeout=(30,180));r.raise_for_status();h=hashlib.sha256();n=0
 for b in r.iter_content(2**20):h.update(b);n+=len(b)
 assert h.hexdigest()==digest and n==path.stat().st_size,'RELEASE_READBACK_DIFFERS'
 return dict(release_asset_id=asset['id'],release_asset_url=asset['browser_download_url'],release_readback_sha256=h.hexdigest(),release_readback_bytes=n)
def main():
 p=argparse.ArgumentParser();p.add_argument('--cache',type=Path,required=True);p.add_argument('--runs',type=int,nargs='+',required=True);a=p.parse_args();a.cache.mkdir(parents=True,exist_ok=True)
 s=session();deadline=time.monotonic()+7200
 while True:
  runs=[api(s,f'actions/runs/{rid}') for rid in a.runs]
  if all(r['status']=='completed' for r in runs):break
  assert time.monotonic()<deadline,'WAIT_FOR_EXISTING_S2_RUN_TIMEOUT';time.sleep(30)
 release=api(s,'releases/tags/audit-traces-20261020-r01');assets={};page=1
 while True:
  rows=api(s,f"releases/{release['id']}/assets",params={'per_page':100,'page':page});assets.update({x['name']:x for x in rows})
  if len(rows)<100:break
  page+=1
 bundle=a.cache/'summaries';bundle.mkdir(exist_ok=True);records=[]
 for run in runs:
  rid=run['id'];metas=api(s,f'actions/runs/{rid}/artifacts',params={'per_page':100})['artifacts'];assert metas
  dump(bundle/f'RUN_{rid}.json',{k:run.get(k) for k in ['id','status','conclusion','head_sha','html_url','created_at','updated_at']})
  # Failure logs remain in the durable summary as well as GitHub Actions.
  jobs=api(s,f'actions/runs/{rid}/jobs',params={'per_page':100})['jobs']
  dump(bundle/f'JOBS_{rid}.json',jobs)
  for job in jobs:
   if job['conclusion']!='failure':continue
   r=s.get('https://api.github.com/repos/myoungsunk/sionna-resimulation/actions/jobs/'+str(job['id'])+'/logs',timeout=90);r.raise_for_status()
   dest=bundle/'failure_logs'/f"{rid}-{job['id']}.log";dest.parent.mkdir(exist_ok=True);dest.write_bytes(r.content)
  for meta in metas:
   aid=meta['id'];archive=a.cache/f'artifact-{aid}.zip';dg,n=download(s,meta['archive_download_url'],archive)
   assert meta['digest']=='sha256:'+dg and meta['size_in_bytes']==n,'ORIGINAL_ARCHIVE_SHA'
   dest=bundle/f'run-{rid}'/meta['name'];members=[]
   with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None,'ORIGINAL_ARCHIVE_CRC'
    for info in z.infolist():
     if info.is_dir():continue
     rel=Path(info.filename);assert not rel.is_absolute() and '..' not in rel.parts
     b=z.read(info);member=dict(name=info.filename,bytes=len(b),CRC32=info.CRC,sha256=hashlib.sha256(b).hexdigest());members.append(member)
     if rel.suffix.lower() not in ['.csv','.json','.md','.py']:continue
     target=dest/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b);member['summary_extracted']=True
   mirror=upload(s,release,assets,archive,archive.name,dg)
   record=dict(artifact_id=aid,name=meta['name'],actions_run_id=rid,source_commit=run['head_sha'],archive_sha256=dg,archive_bytes=n,expires_at=meta['expires_at'],expired=meta['expired'],full_archive_download_verified=True,all_member_CRC_verified=True,members=members,**mirror)
   dump(dest/'OUTPUT_ARCHIVE_RECEIPT.json',record);records.append(record);print('PRESERVED_S2_ORIGINAL',rid,aid,n,flush=True)
 assert len(records)>=16,'EXPECTED_TRAIN_PLUS_FIRST9_PLUS_RETRY6'
 dump(bundle/'RECOVERY_RECEIPT.json',dict(complete=True,records=records,preservation_actions_run_id=os.environ['GITHUB_RUN_ID'],mode='full original SHA/CRC/member SHA plus public release full readback; summaries copied byte-for-byte'))
 summary=a.cache/('powerjoint-s2-results-'+os.environ['GITHUB_RUN_ID']+'.zip')
 with zipfile.ZipFile(summary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for path in sorted(bundle.rglob('*')):
   if path.is_file():z.write(path,path.relative_to(bundle).as_posix())
 receipt=dict(summary_bundle_sha256=sha(summary),summary_bundle_bytes=summary.stat().st_size,**upload(s,release,assets,summary,summary.name,sha(summary)))
 dump(Path(__file__).resolve().parent/'OUTPUT_PRESERVATION_RECEIPT.json',receipt);print(json.dumps(receipt),flush=True)
if __name__=='__main__':main()
