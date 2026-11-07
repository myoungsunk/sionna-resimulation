import json,hashlib,shutil
from pathlib import Path
B=Path(__file__).resolve().parent
provenance=json.loads((B/'results/EXECUTION_PROVENANCE.json').read_bytes())
for p,d in provenance['files'].items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==d
inputroot=Path('D:/codex/PALO_EXACT_ORACLE_20261107_01')
manifest=json.loads((inputroot/'INPUT_MANIFEST.json').read_bytes())
for r in manifest['files']:
 p=inputroot/'inputs'/r['path'].split('research/POL_HEADING_RESEARCH_20261107/',1)[1]
 assert hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256']
logs=B/'logs';logs.mkdir(exist_ok=False)
processes={'campaign':'dbd0e83e-6201-4924-a947-4a2b83e02cd9'}
extra=B/'EXTRA_PROCESSES.json'
if extra.exists():processes.update(json.loads(extra.read_bytes()))
for name,pid in processes.items():
 for f in ('stdout.log','stderr.log'):
  src=Path.home()/'.codex/managed-processes/runs'/pid/f
  shutil.copyfile(src,logs/f'{name}_{f}')
receipt=dict(status='SEALED_INPUT_SOURCE_HASHES_UNCHANGED',inputs=86,processes=processes,independent_audit=False)
(B/'SEAL_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
files={str(p.relative_to(B)).replace('\\','/'):{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in B.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='OUTPUT_MANIFEST.json'}
(B/'OUTPUT_MANIFEST.json').write_text(json.dumps(files,indent=2)+'\n')
print('SEALED',len(files),'files',sum(r['bytes'] for r in files.values()),'bytes')
