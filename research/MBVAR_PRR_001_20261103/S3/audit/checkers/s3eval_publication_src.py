import json,hashlib,subprocess
from pathlib import Path
import pandas as pd,numpy as np
root=Path('/mnt/d/codex/MBVAR_PRR_001_20261103');pkg=root/'research/MBVAR_PRR_001_20261103';s=pkg/'S3';r=s/'runs/EVAL_001';pub='a288f7e0ad17f2f763cf3db339231e124ac37723'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
files=sorted(p for p in r.iterdir() if p.is_file());paths=[pub+':'+p.relative_to(root).as_posix() for p in files]
raw=subprocess.check_output(['git','--git-dir='+str(root/'.git'),'cat-file','--batch'],input=('\n'.join(paths)+'\n').encode());cursor=0;nlfs=0;nmeta=0
for p in files:
 end=raw.index(b'\n',cursor);header=raw[cursor:end].decode().split();assert len(header)==3 and header[1]=='blob';size=int(header[2]);body=raw[end+1:end+1+size];cursor=end+1+size+1
 if body.startswith(b'version https://git-lfs.github.com/spec/v1'):
  fields=dict(a.split(' ',1) for a in body.decode().splitlines()[1:]);assert fields['oid']=='sha256:'+sha(p) and int(fields['size'])==p.stat().st_size;nlfs+=1
 else:assert body==p.read_bytes(),p.name;nmeta+=1
print(json.dumps(dict(publication='PASS',commit=pub,metadata_blobs=nmeta,LFS_pointer_local_payload_matches=nlfs,manifest_sha256=sha(r/'RUN_MANIFEST.json'),remote_LFS_redownload=False)),flush=True)
