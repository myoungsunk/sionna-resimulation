#!/usr/bin/env python3
"""Transport-only bootstrap. No experiment code executes before all hashes match."""
import os,json,base64,gzip,hashlib,urllib.request,time,runpy
from pathlib import Path
REPO='myoungsunk/sionna-resimulation'
PREFIX='research/PALO_AUDITED_FIRST_TESTS_20261109'
REF=os.environ['GITHUB_SHA']
def get(ref,path):
    err=None
    for a in range(4):
        try:
            q=urllib.request.Request(f'https://raw.githubusercontent.com/{REPO}/{ref}/{path}',headers={'User-Agent':'PALO-audited-source'})
            with urllib.request.urlopen(q,timeout=90) as r:return r.read()
        except Exception as e:err=e;time.sleep(a+1)
    raise RuntimeError(f'FETCH_FAILED:{path}:{err}')
def digest(b):return hashlib.sha256(b).hexdigest()
m=json.loads(get(REF,PREFIX+'/source_bundle/MANIFEST.json'))
s=''.join(get(REF,f'{PREFIX}/source_bundle/part{k}.b64').decode().strip() for k in range(m['parts']))
b=gzip.decompress(base64.b64decode(s,validate=True))
assert digest(b)==m['sha256'],'DECODED_SOURCE_BUNDLE_HASH_MISMATCH'
files=json.loads(b)
assert set(files)==set(m['files'])
Path('src').mkdir(exist_ok=True)
for name,text in files.items():
    assert Path(name).name==name and name.endswith('.py'),'UNSAFE_SOURCE_PATH'
    v=text.encode();assert digest(v)==m['files'][name],('SOURCE_FILE_HASH_MISMATCH',name)
    Path('src',name).write_bytes(v)
route=get('151d1af2f30070780f43d94327e50c50d60c4103','research/PALO_NIS_ROUTE_TRANSFER_20261108/validate_routes.py')
blob=hashlib.sha1(b'blob '+str(len(route)).encode()+b'\0'+route).hexdigest()
assert blob=='d0ae06abeeba856a3f333d2b6e0b4d94dda5a805',('ROUTE_LOADER_BLOB_MISMATCH',blob)
Path('src/route_loader.py').write_bytes(route)
Path('repair_source.py').write_bytes(get(REF,PREFIX+'/repair_source.py'))
runpy.run_path('repair_source.py',run_name='__main__')
final={name:digest(Path('src',name).read_bytes()) for name in files}
Path('SOURCE_DECODE_RECEIPT.json').write_text(json.dumps({'source_commit':REF,'decoded_bundle_sha256':digest(b),'original_files':m['files'],'executed_files':final,'route_loader_git_blob':blob,'repair_receipt':json.loads(Path('REPAIR_SOURCE_RECEIPT.json').read_text())},indent=2))
print('SOURCE_DECODE_AND_REPAIR_PASS',REF,len(files),'FILES',flush=True)
