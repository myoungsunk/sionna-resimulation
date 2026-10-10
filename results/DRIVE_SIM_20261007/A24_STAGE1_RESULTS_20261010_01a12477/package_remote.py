from pathlib import Path
import json,tarfile,hashlib,sys
J=Path('/home/KMS/DRIVE_SIM_A24_STAGE1_20261010_01a12477');assert json.loads((J/'VERIFICATION.json').read_text())['state']=='completed'
selected=[]
for d in ['OUTPUT_GATE','OUTPUT_F2','OUTPUT_F1','OUTPUT_F3','OUTPUT_F2acf','OUTPUT_F1acf','INPUTS','FROZEN_SOURCE']:
 selected.extend(p for p in (J/d).rglob('*') if p.is_file())
for n in ['PLAN.json','SOURCE_REVISION.json','EXECUTION.json','STATUS.json','VERIFICATION.json','RUNTIME_INSPECT.json','LAUNCHES.json','freqs_hz.npy','launch.py','driver.py','collect_verify.py','package_remote.py','check-a0.log','F2.log','F1.log','F3.log','F2acf.log','F1acf.log']:
 p=J/n;assert p.exists(),p;selected.append(p)
records=[{'path':p.relative_to(J).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(selected)]
assert all(r['bytes']<40*1024**2 for r in records)
(J/'TRANSFER_MANIFEST.json').write_text(json.dumps({'files':records,'self_excluded':True,'total_bytes':sum(r['bytes'] for r in records)},indent=2))
archive=J.parent/'A24_STAGE1_01a12477.tar.gz'
with tarfile.open(archive,'w:gz') as tf:
 for p in selected+[J/'TRANSFER_MANIFEST.json']:tf.add(p,arcname=p.relative_to(J).as_posix())
print(json.dumps({'archive':str(archive),'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'files':len(records)+1,'total_bytes':sum(r['bytes'] for r in records)}))
