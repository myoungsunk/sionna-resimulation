from pathlib import Path
import json,hashlib,argparse,os
root=Path(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path);args=ap.parse_args()
m=json.loads((root/'H4_PARTS.json').read_text());dest=args.output or root/m['original_path']
assert not dest.exists(),'Destination exists; refusing overwrite'
temp=dest.with_name(dest.name+'.partial');whole=hashlib.sha256();total=0
with temp.open('xb') as out:
 for part in m['parts']:
  h=hashlib.sha256();count=0
  with (root/part['path']).open('rb') as f:
   for data in iter(lambda:f.read(1048576),b''):
    h.update(data);whole.update(data);out.write(data);count+=len(data)
  assert count==part['bytes'] and h.hexdigest()==part['sha256'],part['path']
  total+=count
assert total==m['bytes'] and whole.hexdigest()==m['sha256'],'Whole-file integrity failure'
# On Windows rename refuses an existing destination, preserving the no-overwrite rule.
temp.rename(dest)
print('RESTORE PASS',whole.hexdigest())
