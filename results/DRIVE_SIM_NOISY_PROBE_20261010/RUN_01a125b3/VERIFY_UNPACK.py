"""Verify joined shard bytes, safe tar members and file hashes; optional extraction to NEW directory only."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,tarfile,io,tempfile
p=argparse.ArgumentParser();p.add_argument('archive_dir',type=Path);p.add_argument('--extract',type=Path);a=p.parse_args()
m=json.loads((a.archive_dir/'PACKAGE_MANIFEST.json').read_text(encoding='utf-8-sig'))
e=json.loads((a.archive_dir/'OUTPUT_MANIFEST.json').read_text(encoding='utf-8-sig'))['entries'];e={x.get('archive_path',x.get('path')):x for x in e}
if a.extract:
 if a.extract.exists():raise FileExistsError('Extraction destination must be new')
 a.extract.mkdir(parents=True)
h=hashlib.sha256();n=0;seen=set()
with tempfile.TemporaryFile() as joined:
 for x in m['parts']:
  ph=hashlib.sha256();size=0
  with (a.archive_dir/x['file']).open('rb') as f:
   while b:=f.read(8*1024*1024):joined.write(b);h.update(b);ph.update(b);n+=len(b);size+=len(b)
  assert size==x['bytes'] and ph.hexdigest()==x['sha256'],x['file']
 assert n==m['archive_bytes'] and h.hexdigest()==m['archive_sha256']
 joined.seek(0)
 with tarfile.open(fileobj=joined,mode='r|gz') as t:
  for x in t:
   q=PurePosixPath(x.name)
   assert x.isfile() and not q.is_absolute() and '..' not in q.parts and ':' not in x.name and '\\' not in x.name,x.name
   assert x.name not in seen,x.name;seen.add(x.name)
   f=t.extractfile(x);data=f.read();digest=hashlib.sha256(data).hexdigest()
   if x.name in e:assert len(data)==e[x.name]['bytes'] and digest==e[x.name]['sha256'],x.name
   else:assert x.name=='OUTPUT_MANIFEST.json',x.name
   if a.extract:
    dest=a.extract.joinpath(*q.parts);dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open('xb') as out:out.write(data)
 assert set(e)<=seen
print(json.dumps({'passed':True,'archive_sha256':h.hexdigest(),'checked_files':len(e),'members':len(seen)}))
