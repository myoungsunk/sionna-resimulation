"""Immutable release-only restore. Never consumes expiring Actions inputs."""
from pathlib import Path
import hashlib,json,shutil,urllib.request,zipfile
ROOT=Path.cwd();SOURCE=ROOT/'source'
HERE=Path(__file__).resolve().parent
def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def extract(z,destination):
 for i in z.infolist():
  p=Path(i.filename)
  if p.is_absolute() or '..' in p.parts:raise RuntimeError('unsafe archive path')
  if i.is_dir():continue
  target=destination/p;target.parent.mkdir(parents=True,exist_ok=True)
  if target.exists():continue
  with z.open(i) as a,target.open('wb') as b:shutil.copyfileobj(a,b)
def main():
 receipt=json.loads((HERE/'T0_INPUTS/INPUT_RECEIPT.json').read_text())
 names={11782748118:'rf_frozen.zip',11948391783:'physics_rs_inputs.zip',12034154094:'ffd_original.zip',12188081569:'reference_ae.zip',12188722472:'reference_f.zip'}
 checks=[]
 for r in receipt['inputs']:
  p=ROOT/names[r['artifact_id']]
  if not p.exists():
   with urllib.request.urlopen(r['release_asset_url'],timeout=180) as a,p.open('wb') as b:shutil.copyfileobj(a,b)
  if p.stat().st_size!=r['bytes'] or digest(p)!=r['sha256']:raise RuntimeError('RELEASE_INPUT_IDENTITY:'+p.name)
  checks.append(dict(file=p.name,sha256=digest(p),url=r['release_asset_url']))
  with zipfile.ZipFile(p) as z:
   if r['artifact_id']==11948391783:extract(z,SOURCE)
   if r['artifact_id'] in [12188081569,12188722472]:extract(z,ROOT/('reference_ae' if r['artifact_id']==12188081569 else 'reference_f'))
   if r['artifact_id']==12034154094:
    for name in ['LP_plus45_bank.npz','LP_minus45_bank.npz']:
     match=[n for n in z.namelist() if n.endswith(name)]
     if len(match)!=1:raise RuntimeError('bank identity not unique')
     with z.open(match[0]) as a,(ROOT/name).open('wb') as b:shutil.copyfileobj(a,b)
 banks={n:digest(ROOT/n) for n in ['LP_plus45_bank.npz','LP_minus45_bank.npz']}
 expected=['b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b','39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9']
 if list(banks.values())!=expected:raise RuntimeError('BANK_SHA_MISMATCH')
 (ROOT/'BANK_MANIFEST.json').write_text(json.dumps({'npz_sha256':banks}))
 (ROOT/'ffd_p0p3/out').mkdir(parents=True,exist_ok=True)
 (ROOT/'RESTORE_RECEIPT.json').write_text(json.dumps(checks,indent=2))
 print('RELEASE_RESTORE_PASS',flush=True)
if __name__=='__main__':main()
