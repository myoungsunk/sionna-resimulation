"""S2 restore: immutable S0 release archives, complete hash/CRC, selected references."""
from pathlib import Path
import argparse,hashlib,json,shutil,urllib.request,zipfile
HERE=Path(__file__).resolve().parent
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--route',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 root=HERE.parents[2];audit=root/'research/POWERJOINT_AUDIT_RERUN_20261020'
 receipt=json.loads((HERE.parent/'S0_CORRECTIONS/TRACE_RECEIPT.json').read_text())
 if a.route=='R2':aid=12237051901
 else:aid=next(x['artifact_id'] for x in json.loads((audit/'T2_NEW_ROUTE_BASELINE/MANIFEST.json').read_text())['routes'] if x['route']==a.route)
 item=next(x for x in receipt['artifacts'] if x['artifact_id']==aid)
 assert item['original_digest_verified'] and item['downloaded_sha256']==item['release_download_sha256']
 a.out.mkdir(parents=True,exist_ok=True);archive=a.out/f'artifact-{aid}.zip'
 if not archive.exists():
  with urllib.request.urlopen(item['release_asset_url'],timeout=120) as r,archive.open('wb') as w:shutil.copyfileobj(r,w)
 assert archive.stat().st_size==item['downloaded_bytes'] and sha(archive)==item['downloaded_sha256'],'REFERENCE_ARCHIVE_IDENTITY'
 selected=[]
 with zipfile.ZipFile(archive) as z:
  assert z.testzip() is None,'REFERENCE_ZIP_CRC'
  for member in z.namelist():
   take=member.endswith('.npz') and ('_los_' in member and member.endswith('_Q_POWER1.npz') if a.route=='R2' else True)
   if not take:continue
   rel=Path(member);assert not rel.is_absolute() and '..' not in rel.parts
   raw=z.read(member);dest=a.out/rel;dest.parent.mkdir(parents=True,exist_ok=True)
   if dest.exists():assert dest.read_bytes()==raw,'NO_OVERWRITE'
   else:dest.write_bytes(raw)
   selected.append(dict(member=member,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
 assert selected,'EMPTY_REFERENCE_RESTORE'
 record=dict(route=a.route,artifact_id=aid,source_run_id=item['run_id'],url=item['release_asset_url'],archive_sha256=sha(archive),archive_bytes=archive.stat().st_size,full_archive_hash_verified=True,all_member_crc_verified=True,selected=selected)
 (a.out/'S2_REFERENCE_RECEIPT.json').write_text(json.dumps(record,indent=2)+'\n')
 print('S2_REFERENCES_RESTORED',a.route,len(selected),flush=True)
if __name__=='__main__':main()
