"""Recover immutable Actions traces, verify archive SHA; RF comes from releases."""
from pathlib import Path
import argparse,json,hashlib,os,urllib.request,zipfile
REPO='myoungsunk/sionna-resimulation'
def main():
 p=argparse.ArgumentParser();p.add_argument('--run');p.add_argument('--route');p.add_argument('--artifact-id');p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 url=(f'https://api.github.com/repos/{REPO}/actions/artifacts/{a.artifact_id}' if a.artifact_id else f'https://api.github.com/repos/{REPO}/actions/runs/{a.run}/artifacts?per_page=100');req=urllib.request.Request(url,headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'})
 with urllib.request.urlopen(req,timeout=90) as src:meta=json.load(src)
 expected=f'powerjoint-audit-t2-{a.route}-{a.run}';asset=meta if a.artifact_id else next(x for x in meta['artifacts'] if x['name']==expected);req=urllib.request.Request(asset['archive_download_url'],headers={'Authorization':'Bearer '+os.environ['GH_TOKEN']})
 archive=a.out/'result.zip';digest=hashlib.sha256()
 with urllib.request.urlopen(req,timeout=180) as src,archive.open('wb') as dst:
  while b:=src.read(4*1024*1024):digest.update(b);dst.write(b)
 if 'sha256:'+digest.hexdigest()!=asset['digest'] or archive.stat().st_size!=asset['size_in_bytes']:raise RuntimeError('RESULT_ARTIFACT_SHA')
 with zipfile.ZipFile(archive) as z:
  for name in z.namelist():
   path=Path(name)
   if path.is_absolute() or '..' in path.parts:raise RuntimeError('UNSAFE_RESULT_ARCHIVE')
   if name.endswith('/'):continue
   dst=a.out/path;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(z.read(name))
 asset.update(verified_sha256=digest.hexdigest());(a.out/'ARTIFACT_RECEIPT.json').write_text(json.dumps(asset,indent=2))
 if a.artifact_id:print('RESULT_RESTORED',asset['id'],digest.hexdigest(),flush=True);return
 cases=[]
 for anchor in (['A','B'] if a.route.startswith('C') else ['O0']):
  cases.append(dict(case=dict(id=f'{a.route}_{anchor}_M45_FULL',anchor={'A':[4.,0.,2.65],'B':[10.,0.,2.65],'O0':[5.,2.2,2.65]}[anchor],mount_deg=45.,robot_z_m=.45),bias='B0',trace=f'{a.route}_{anchor}_M45_FULL_B0.npz'))
 (a.out/'CASES.json').write_text(json.dumps(dict(cases=cases),indent=2));print('RESULT_RESTORED',expected,asset['id'],digest.hexdigest(),flush=True)
if __name__=='__main__':main()
