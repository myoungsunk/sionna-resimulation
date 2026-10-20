"""Verified immutable route-release snapshot; no RF regeneration."""
from pathlib import Path
import argparse,hashlib,json,shutil,tarfile,urllib.request
HERE=Path(__file__).resolve().parent
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--route',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 tag='route-rf-'+a.route.lower()+'-20261019-r01'
 lock=json.loads((HERE/'RELEASE_INPUTS.json').read_text())[tag]
 asset=next(x for x in lock if x['name'].endswith('.tar.gz'))
 archive=a.out/asset['name']
 with urllib.request.urlopen(asset['browser_download_url'],timeout=180) as src,archive.open('wb') as dst:shutil.copyfileobj(src,dst)
 digest=sha(archive)
 if archive.stat().st_size!=asset['size'] or 'sha256:'+digest!=asset['digest']:raise RuntimeError('ROUTE_ARCHIVE_SHA')
 kept=[]
 with tarfile.open(archive,'r:gz') as tar:
  for member in tar:
   if not member.isfile():continue
   name=Path(member.name)
   if name.is_absolute() or '..' in name.parts:raise RuntimeError('UNSAFE_ROUTE_PATH')
   # Preserve all machine-readable route/case/batch input arrays, including visibility flags.
   if name.suffix.lower() not in ['.json','.csv','.txt','.npy','.npz'] or 'raw_paths' in name.parts:continue
   target=a.out/'data'/name;target.parent.mkdir(parents=True,exist_ok=True)
   with tar.extractfile(member) as src,target.open('wb') as dst:shutil.copyfileobj(src,dst)
   kept.append(dict(name=member.name,bytes=target.stat().st_size,sha256=sha(target)))
 (a.out/'ARCHIVE_CONTENTS_AND_SHA.json').write_text(json.dumps(dict(tag=tag,asset=asset,archive_sha256=digest,extracted=kept),indent=2))
 print('ROUTE_RESTORED',tag,len(kept),flush=True)
 print('KEY_MEMBERS',json.dumps([x['name'] for x in kept if any(k in x['name'] for k in ['CASES/','ROUTE_POSE','LOS_EXISTS','los_exists'])])[:6000],flush=True)
if __name__=='__main__':main()
