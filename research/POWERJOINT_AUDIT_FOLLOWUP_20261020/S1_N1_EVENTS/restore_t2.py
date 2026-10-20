"""Restore S1 historical T2 inputs only from S0 verified durable release assets."""
from pathlib import Path
import argparse,hashlib,json,shutil,sys,urllib.request,zipfile
HERE=Path(__file__).resolve().parent

def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def restore(route,out,receipt_path=None):
 source=HERE.parents[2];audit=source/'research/POWERJOINT_AUDIT_RERUN_20261020'
 manifest=json.loads((audit/'T2_NEW_ROUTE_BASELINE/MANIFEST.json').read_text())
 route_rec=next(x for x in manifest['routes'] if x['route']==route)
 receipt=json.loads((receipt_path or HERE.parent/'S0_CORRECTIONS/TRACE_RECEIPT.json').read_text())
 item=next(x for x in receipt['artifacts'] if x['artifact_id']==route_rec['artifact_id'])
 assert item['original_digest_verified'] and item['downloaded_sha256']==item['release_download_sha256']
 out.mkdir(parents=True,exist_ok=True);archive=out/f"artifact-{item['artifact_id']}.zip"
 if not archive.exists():
  with urllib.request.urlopen(item['release_asset_url'],timeout=120) as r,archive.open('wb') as w:shutil.copyfileobj(r,w)
 assert archive.stat().st_size==item['downloaded_bytes'] and sha(archive)==item['downloaded_sha256'],'ARCHIVE_IDENTITY'
 selected=[]
 with zipfile.ZipFile(archive) as z:
  assert z.testzip() is None,'ZIP_CRC'
  for member in z.namelist():
   if not(member.endswith(('_B0.npz','_L2.npz')) or member.endswith('.json')):continue
   rel=Path(member);assert not rel.is_absolute() and '..' not in rel.parts
   raw=z.read(member);dest=out/rel;dest.parent.mkdir(parents=True,exist_ok=True)
   if dest.exists():assert dest.read_bytes()==raw,'NO_OVERWRITE'
   else:dest.write_bytes(raw)
   selected.append({'member':member,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
 record={'route':route,'artifact_id':item['artifact_id'],'source_run_id':item['run_id'],'source_commit':route_rec['source_commit'],'url':item['release_asset_url'],'archive_sha256':item['downloaded_sha256'],'archive_bytes':item['downloaded_bytes'],'full_archive_hash_verified_this_restore':True,'all_member_crc_verified':True,'selected':selected}
 (out/'S1_RESTORE_RECEIPT.json').write_text(json.dumps(record,indent=2)+'\n')
 print('RESTORED',route,len(selected),flush=True);return record
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--route',choices=['ALL','C01','C02','C03','O01','O02','O03'],required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 for route in (['C01','C02','C03','O01','O02','O03'] if a.route=='ALL' else [a.route]):restore(route,a.out/route)
