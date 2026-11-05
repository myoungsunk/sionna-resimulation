import csv,hashlib,json,tarfile
from pathlib import Path
p=Path(__file__).resolve().parent
expected_archive=(p/'ARCHIVE_SHA256.txt').read_text().split()[0]
assert hashlib.sha256((p/'evidence.tar.gz').read_bytes()).hexdigest()==expected_archive
actual={}
with tarfile.open(p/'evidence.tar.gz','r|gz') as archive:
 for member in archive:
  if not member.isfile():continue
  data=archive.extractfile(member).read()
  if member.name.startswith('out/'):actual[member.name]=hashlib.sha256(data).hexdigest()
  if member.name=='SHA256SUMS.txt':
   expected={name:h for h,name in (line.split(None,1) for line in data.decode().splitlines())}
  if member.name in ['out/QA.json','out/FAILED_KEYS.csv','out/INPUT_LOCK.json','out/APPROVAL.json','run.log','runtime.txt','SHA256SUMS.txt']:
   (p/Path(member.name).name).write_bytes(data)
assert actual==expected
qa=json.loads((p/'QA.json').read_text())
previous=json.loads((p.parent/'SM0B/B1/QA.json').read_text())
for r in previous:
 if r['route']=='R4' and r['pose']==168:
  qa.append(dict(r,yaw=-31.700092,range_m=r['tap']*0.14955225880474907,source='B1'))
rows=[]
for yaw in [-35.7,0.,35.7,180.,-31.700092]:
 pair=[next((r for r in qa if r['yaw']==yaw and r['mode']==mode),None) for mode in ['Full','LoS']]
 if not all(r and r['status']=='PASS_TECHNICAL' for r in pair):continue
 full,los=pair
 rows.append(dict(yaw=yaw,source=full.get('source','NEW'),full_tap=full['tap'],los_tap=los['tap'],delta_range_m=full['range_m']-los['range_m'],full_s=full['signed_s'],los_s=los['signed_s'],delta_s=full['signed_s']-los['signed_s']))
with (p/'PAIRED_YAW.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
print('verified files',len(actual),'pairs',len(rows))
