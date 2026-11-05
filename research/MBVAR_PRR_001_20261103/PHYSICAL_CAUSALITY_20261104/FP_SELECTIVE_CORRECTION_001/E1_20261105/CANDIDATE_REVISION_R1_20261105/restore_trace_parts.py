"""Reassemble public trace chunks with exact byte/hash verification; no experiment."""
import pathlib,json,hashlib
root=pathlib.Path(__file__).resolve().parent
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
for arm,item in json.loads((root/'TRACE_PARTS.json').read_text()).items():
    dest=root/item['original']
    if dest.exists():
        assert sha(dest)==item['sha256'],arm
        continue
    for part in item['parts']:
        assert sha(root/part['path'])==part['sha256'],part['path']
    with dest.open('xb') as out:
        for part in item['parts']:
            with (root/part['path']).open('rb') as f:
                while chunk:=f.read(1024*1024):out.write(chunk)
    assert dest.stat().st_size==item['bytes'] and sha(dest)==item['sha256'],arm
    print(arm,'RESTORED_AND_VERIFIED')
