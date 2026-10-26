from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parent
SRC=Path(r'D:\SLAM_bot\OFFICE_CORRIDOR_TRANSFER_FIX_20261026\execution_33e9849\p2')
lock=json.loads((ROOT/'source_blob_lock.json').read_text())
out=[]
for x in lock['files']+lock['reference_files']:
 p=SRC/x['path']; b=p.read_bytes() if p.exists() else None
 h=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest() if b is not None else None
 out.append(dict(**x,local_blob=h,match=h==x['sha']))
(ROOT/'SOURCE_IDENTITY_CHECK.json').write_text(json.dumps(out,indent=2))
print(json.dumps({'checked':len(out),'mismatches':[x for x in out if not x['match']]}))
