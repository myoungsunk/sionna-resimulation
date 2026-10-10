from pathlib import Path
import json,hashlib,tarfile
J=Path('/job');D=J/'DELIVERY_C_CORRECTION';D.mkdir(exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
entries=[]
for p in (J/'BODY_CONTROLS_C_CORRECTED').rglob('*'):
 if p.is_file():entries.append({'source':str(p),'path':str(p.relative_to(J)),'bytes':p.stat().st_size,'sha256':sha(p)})
for p in J.iterdir():
 if p.is_file() and p.suffix in ['.json','.csv','.py','.md'] and p.name!='RF_PROGRESS.json':entries.append({'source':str(p),'path':'CORRECTED_SUMMARY_AND_HARNESS/'+p.name,'bytes':p.stat().st_size,'sha256':sha(p)})
(D/'OUTPUT_MANIFEST.json').write_text(json.dumps({'entries':entries,'correction':'Only C measurement routing, not sensor/filter or Q/R/gate/prior tuning. Original C retains original files and is not specification C.'},indent=2))
archive=D/'C_CORRECTED.tar.gz'
with tarfile.open(archive,'w:gz',compresslevel=1) as t:
 for x in entries:t.add(x['source'],arcname=x['path'],recursive=False)
 t.add(D/'OUTPUT_MANIFEST.json',arcname='OUTPUT_MANIFEST.json',recursive=False)
parts=[]
with archive.open('rb') as f:
 i=0
 while True:
  buf=f.read(32*1024*1024)
  if not buf:break
  p=D/f'C_CORRECTED.tar.gz.part-{i:03d}';p.write_bytes(buf);parts.append({'file':p.name,'bytes':len(buf),'sha256':sha(p)});i+=1
r={'archive_sha256':sha(archive),'archive_bytes':archive.stat().st_size,'parts':parts,'payload_bytes':sum(x['bytes'] for x in entries),'files':len(entries)};(D/'PACKAGE_MANIFEST.json').write_text(json.dumps(r,indent=2));print(json.dumps({k:v for k,v in r.items() if k!='parts'}),flush=True)
