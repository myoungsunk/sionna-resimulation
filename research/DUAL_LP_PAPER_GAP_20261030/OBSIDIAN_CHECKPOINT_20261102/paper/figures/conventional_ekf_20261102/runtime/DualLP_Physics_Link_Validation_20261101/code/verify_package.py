"""Verify delivered file bytes; optional companion input verification."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--with-external',action='store_true');a=ap.parse_args()
    inv=json.loads((ROOT/'FILE_INVENTORY.json').read_text());failed=[]
    rows=inv['files']+(inv['external_inputs'] if a.with_external else [])
    for row in rows:
        path=ROOT/row['path']
        if not path.is_file():failed.append((row['path'],'MISSING'))
        elif digest(path)!=row['sha256']:failed.append((row['path'],'SHA256_MISMATCH'))
    if failed:raise RuntimeError(json.dumps(failed,indent=2))
    print(f'PASS: {len(rows)} files; external banks checked={a.with_external}.')
if __name__=='__main__':main()
