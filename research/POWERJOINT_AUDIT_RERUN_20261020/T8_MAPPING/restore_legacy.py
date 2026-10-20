"""Preserve part and reconstructed archive hashes; extract only frozen inputs."""
from pathlib import Path
import hashlib,json,tarfile,urllib.request,shutil,sys
HERE=Path(__file__).resolve().parent;AUDIT=HERE.parent;SOURCE=AUDIT.parents[1]
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def download(asset):
 with urllib.request.urlopen(asset['browser_download_url'],timeout=180) as f:b=f.read()
 if len(b)!=asset['size'] or 'sha256:'+hashlib.sha256(b).hexdigest()!=asset['digest']:raise RuntimeError('METADATA_ASSET_SHA')
 return b
def main():
 root=Path('legacy_snapshot');root.mkdir(exist_ok=True);locks=json.loads((AUDIT/'RELEASE_INPUTS.json').read_text());cases=[]
 for route in ['R4','R5']:
  assets=locks['legacy-rf-'+route.lower()+'-20261019-r02'];meta=json.loads(download(next(a for a in assets if a['name'].endswith('SHA256.json'))));receipt=download(next(a for a in assets if a['name'].endswith('ROUTE_RECEIPT.json')))
  out=root/route;out.mkdir(exist_ok=True);(out/'ORIGINAL_ROUTE_RECEIPT.json').write_bytes(receipt);archive=out/meta['archive'];parts=[];total=hashlib.sha256()
  with archive.open('wb') as dst:
   for asset in sorted([a for a in assets if '.part' in a['name']],key=lambda a:a['name']):
    h=hashlib.sha256();n=0
    with urllib.request.urlopen(asset['browser_download_url'],timeout=180) as src:
     while b:=src.read(8*1024*1024):h.update(b);total.update(b);dst.write(b);n+=len(b)
    if n!=asset['size'] or 'sha256:'+h.hexdigest()!=asset['digest']:raise RuntimeError('LEGACY_PART_SHA:'+asset['name'])
    parts.append(dict(asset=asset,verified_sha256=h.hexdigest()));print('PART_VERIFIED',route,asset['name'],flush=True)
  if archive.stat().st_size!=meta['archive_bytes'] or total.hexdigest()!=meta['archive_sha256']:raise RuntimeError('RECONSTRUCTED_ARCHIVE_SHA')
  kept=[]
  with tarfile.open(archive,'r:gz') as tar:
   for member in tar:
    name=Path(member.name)
    if not member.isfile():continue
    if name.is_absolute() or '..' in name.parts:raise RuntimeError('UNSAFE_ARCHIVE')
    if 'raw_paths' in name.parts or 'BATCHES' in name.parts:continue
    if name.suffix.lower() not in ['.json','.csv','.txt','.npy','.npz']:continue
    dst=out/'data'/name;dst.parent.mkdir(parents=True,exist_ok=True)
    with tar.extractfile(member) as src,dst.open('wb') as f:shutil.copyfileobj(src,f)
    kept.append(dict(name=member.name,sha256=sha(dst),bytes=dst.stat().st_size))
  certificate=out/'RESTORE_RECEIPT.json';certificate.write_text(json.dumps(dict(parts=parts,archive_sha256=total.hexdigest(),kept=kept),indent=2))
  for anchor in ['A','B']:
   folder=next(out.rglob(route+'_'+anchor+'_M45_FULL'))
   cases.append(dict(reference_case=route+'_a'+anchor+'_m0',radio_pose=str((folder/'RADIO_POSE.csv').resolve()),full_h=str((folder/'H_FULL.npy').resolve()),los_h=str((folder/'H_DIRECT_LOS.npy').resolve()),source_receipt=str(certificate.resolve())))
  # The verified archive is temporary transport in an ephemeral Actions runner;
  # retain its signed identity, all original release assets remain immutable.
  archive.unlink()
 Path('T8_INPUTS.json').write_text(json.dumps(dict(cases=cases),indent=2));print('T8_INPUTS_READY',flush=True)
if __name__=='__main__':main()
