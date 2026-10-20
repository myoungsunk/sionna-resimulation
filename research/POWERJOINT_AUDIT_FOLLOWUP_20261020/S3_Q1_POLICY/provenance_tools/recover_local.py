"""Read durable S3 summary bundle, verify full SHA/CRC and every extracted member."""
from pathlib import Path
import argparse,hashlib,json,os,sys,time,zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'S0_CORRECTIONS'))
from github_io import session,api,download
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
def main():
 p=argparse.ArgumentParser();p.add_argument('--preserve-run',type=int,required=True);p.add_argument('--expected-archives',type=int,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 rid=a.preserve_run;name=f'powerjoint-s3-results-{rid}.zip';s=session()
 s.mount('https://',HTTPAdapter(max_retries=Retry(total=3,connect=3,read=3,backoff_factor=1,status_forcelist=[502,503,504],allowed_methods=['GET','HEAD'])))
 deadline=time.monotonic()+7200
 while True:
  release=api(s,'releases/tags/audit-traces-20261020-r01');page=1;asset=None
  while True:
   rows=api(s,f"releases/{release['id']}/assets",params={'per_page':100,'page':page});asset=next((x for x in rows if x['name']==name),None)
   if asset or len(rows)<100:break
   page+=1
  if asset and asset.get('state')=='uploaded':break
  run=api(s,f'actions/runs/{rid}')
  if run['status']=='completed' and run['conclusion']!='success':raise RuntimeError('PRESERVATION_FAILED:'+str(run['conclusion']))
  assert time.monotonic()<deadline,'WAIT_TIMEOUT'
  if Path(os.environ['MANAGED_PROCESS_STOP_FILE']).exists():raise SystemExit('STOP_REQUESTED')
  time.sleep(30)
 archive=a.out/name;attempts=[]
 for attempt in range(1,4):
  try:digest,n=download(s,asset['browser_download_url'],archive);break
  except Exception as e:
   attempts.append(dict(attempt=attempt,error=str(e),retry=attempt<3));(a.out/'TRANSPORT_ATTEMPTS.json').write_text(json.dumps(attempts,indent=2))
   if attempt==3:raise
   time.sleep(15)
 assert digest==asset['digest'].removeprefix('sha256:') and n==asset['size'],'SUMMARY_BUNDLE_SHA'
 with zipfile.ZipFile(archive) as z:
  assert z.testzip() is None,'SUMMARY_BUNDLE_CRC'
  for info in z.infolist():
   if info.is_dir():continue
   rel=Path(info.filename);assert not rel.is_absolute() and '..' not in rel.parts
   target=a.out/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(info))
 receipt=json.loads((a.out/'RECOVERY_RECEIPT.json').read_text());assert receipt['complete'] and len(receipt['records'])==a.expected_archives
 verified=0
 for record in receipt['records']:
  root=a.out/f"run-{record['actions_run_id']}"/record['name'];assert record['archive_sha256']==record['release_readback_sha256'] and record['archive_bytes']==record['release_readback_bytes']
  for member in record['members']:
   if not member.get('summary_extracted'):continue
   b=(root/member['name']).read_bytes();assert len(b)==member['bytes'] and hashlib.sha256(b).hexdigest()==member['sha256'];verified+=1
 proof=dict(preservation_actions_run_id=rid,bundle_release_asset_id=asset['id'],bundle_release_url=asset['browser_download_url'],bundle_sha256=digest,bundle_bytes=n,full_public_bundle_SHA_CRC_verified=True,original_summary_members_verified=verified,original_archives=a.expected_archives)
 (a.out/'PUBLIC_BUNDLE_RECEIPT.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof),flush=True)
if __name__=='__main__':main()
