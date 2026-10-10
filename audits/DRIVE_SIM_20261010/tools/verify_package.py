"""Verify published exact/decompressed bytes; never execute experiments."""
import pathlib,json,hashlib,gzip
ROOT=pathlib.Path(__file__).resolve().parents[3]
INDEX=ROOT/'audits/DRIVE_SIM_20261010/ARTIFACT_INDEX.json'
def digest(stream):
    h=hashlib.sha256()
    for b in iter(lambda:stream.read(1048576),b''):h.update(b)
    return h.hexdigest()
def verify():
    rows=json.loads(INDEX.read_text(encoding='utf-8'));n=0
    for r in rows:
        if not r['published_path']:continue
        p=ROOT/r['published_path']
        with (gzip.open(p,'rb') if r['storage']=='gzip_lossless' else p.open('rb')) as f:
            assert digest(f)==r['original_sha256'],r['published_path']
        n+=1
    print(json.dumps(dict(published_verified=n,external_not_checked=sum(not r['published_path'] for r in rows)),ensure_ascii=False))
if __name__=='__main__':verify()
