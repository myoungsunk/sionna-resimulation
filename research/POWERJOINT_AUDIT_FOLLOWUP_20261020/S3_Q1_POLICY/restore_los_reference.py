"""Restore all eight historical Native LoS POWER traces from durable v2 archive."""
import argparse,urllib.request,shutil,zipfile,json,hashlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 rec=next(x for x in json.loads((HERE.parent/'S0_CORRECTIONS/TRACE_RECEIPT.json').read_text())['artifacts'] if x['artifact_id']==12238630433);path=a.out/'artifact-12238630433.zip'
 with urllib.request.urlopen(rec['release_asset_url'],timeout=180) as r,path.open('wb') as w:shutil.copyfileobj(r,w)
 with path.open('rb') as f:got=hashlib.file_digest(f,'sha256').hexdigest()
 assert got==rec['downloaded_sha256']==rec['release_download_sha256'] and path.stat().st_size==rec['downloaded_bytes']
 members=[]
 with zipfile.ZipFile(path) as z:
  assert z.testzip() is None
  for name in z.namelist():
   if name.endswith('.npz') and '_los_' in name and name.endswith('_POWER1.npz'):
    rel=Path(name);assert not rel.is_absolute() and '..' not in rel.parts;raw=z.read(name);out=a.out/rel;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(raw);members.append(dict(member=name,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)))
 assert len(members)==8,('EIGHT_NATIVE_LOS_HISTORICAL_TRACES',len(members))
 (a.out/'S3_LOS_REFERENCE_RECEIPT.json').write_text(json.dumps(dict(artifact_id=12238630433,archive_sha256=got,archive_bytes=path.stat().st_size,release_url=rec['release_asset_url'],members=members),indent=2)+'\n')
if __name__=='__main__':main()
