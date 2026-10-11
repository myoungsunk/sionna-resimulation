#!/usr/bin/env python3
"""Recover ORIGINAL byte-identical V01 files from actual repository paths/archives.
No RF regeneration or scientific substitution; missing SHA objects remain blocked.
"""
from __future__ import annotations
import argparse,hashlib,json,shutil,subprocess,sys,tarfile
from pathlib import Path
import V01_archive_family_parity as A
ROOT=A.ROOT;BASE=A.BASE

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',required=True,type=Path);arg=ap.parse_args();out=arg.out;out.mkdir(parents=True,exist_ok=True)
 matrix=json.loads((BASE/'SUMMARY_CURRENT/MOUNT_CASE_MATRIX.json').read_text())
 expected=json.loads((BASE/'SUMMARY_FINAL/NATIVE_FULL_EFFECTIVE_STATUS_FREQUENCY.json').read_text())['cases']
 targets={c['full_sha256']:(c['case'],'legacy') for c in matrix};targets.update({c['H_sha256']:(c['case'],'native') for c in expected})
 names={'H_'+c['case']+'.npy' for c in matrix};tree=subprocess.check_output(['git','ls-tree','-r','--name-only','HEAD'],cwd=ROOT,text=True).splitlines()
 paths=[p for p in tree if Path(p).name in names]
 (out/'REPOSITORY_RF_PATH_DISCOVERY.json').write_text(json.dumps(dict(paths=paths,legacy_manifests_contain_historical_absolute_paths=True),indent=2))
 if paths:subprocess.run(['git','checkout','HEAD','--',*paths],cwd=ROOT,check=True)
 found={};metadata=[];archives=[];recover=out/'recovered';recover.mkdir(exist_ok=True)
 def accept(data,path_note):
  digest=hashlib.sha256(data).hexdigest()
  if digest not in targets:return
  case,kind=targets[digest];p=recover/(kind+'_'+case+'.npy');p.write_bytes(data)
  found[(case,kind)]=dict(path=str(p),member=path_note,sha256=digest)
 for p in paths:
  q=ROOT/p
  if q.exists():accept(q.read_bytes(),p)
 for folder in sorted(BASE.glob('*_ARCHIVE')):
  mf=folder/'PACKAGE_MANIFEST.json'
  if not mf.exists():continue
  m=json.loads(mf.read_text());combined=out/(folder.name+'.tar.gz');hs=hashlib.sha256();size=0
  with combined.open('wb') as w:
   for part in m['parts']:
    p=folder/part['file'];assert p.is_file() and p.stat().st_size==part['bytes'] and A.sha(p)==part['sha256'],str(p)
    with p.open('rb') as f:
     for data in iter(lambda:f.read(4194304),b''):w.write(data);hs.update(data);size+=len(data)
  assert hs.hexdigest()==m['archive_sha256'] and size==m['archive_bytes']
  n=0
  with tarfile.open(combined,'r:gz') as t:
   for p in t:
    if not p.isfile():continue
    if p.name.endswith('.npy') and (Path(p.name).name in names or 'H_full' in p.name or 'H_PARTIAL' in p.name):
     accept(t.extractfile(p).read(),folder.name+'/'+p.name);n+=1
    elif p.name.endswith('.json') and p.size<400000 and any(s in p.name.upper() for s in ('NATIVE_FULL','NATIVE_LOS','MANIFEST','COMPLETION')):
     try:metadata.append(dict(archive=folder.name,path=p.name,content=json.load(t.extractfile(p))))
     except (ValueError,TypeError):pass
  archives.append(dict(name=folder.name,archive_SHA_PASS=True,bytes=size,candidate_H_count=n));combined.unlink()
  print('V01_RECOVER',folder.name,len(found),len(targets),flush=True)
 A.LEGACY.mkdir(parents=True,exist_ok=True)
 for (case,kind),obj in found.items():
  if kind=='legacy':
   dest=A.LEGACY/('H_'+case+'.npy')
   if dest.resolve()!=Path(obj['path']).resolve():shutil.copyfile(obj['path'],dest)
 native={case:obj for (case,kind),obj in found.items() if kind=='native'}
 (out/'ORIGINAL_BYTE_RECOVERY_RECEIPT.json').write_text(json.dumps(dict(expected17_hashes=targets,recovered=[dict(case=c,kind=k,**v) for (c,k),v in found.items()],archives=archives,metadata=metadata),indent=2))
 # Reuse verified archive recovery, without scanning twice. No numeric model changes.
 A.unpack_needed=lambda _o,_e:(native,metadata)
 sys.argv=[str(Path(A.__file__)),'--out',str(out)];A.main()
 # Always save original numerical sources even if an input gate blocked.
 for p in list((ROOT/'src/qclean_uwb/drivesim').glob('*.py'))+list((ROOT/'research/P0_RESTORE_20261011').glob('*.py'))+list(Path(__file__).parent.glob('*.py')):
  q=out/'source_snapshot'/p.relative_to(ROOT);q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(p.read_bytes())
 for p in recover.glob('*.npy'):p.unlink()
if __name__=='__main__':main()
