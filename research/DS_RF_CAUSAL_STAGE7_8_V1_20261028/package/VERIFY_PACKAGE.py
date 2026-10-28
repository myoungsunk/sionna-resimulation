#!/usr/bin/env python3
"""Validate local patch payload by SHA256 before any local write."""
from pathlib import Path
import hashlib,json

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for c in iter(lambda:f.read(1<<20),b''):h.update(c)
    return h.hexdigest()

def main():
    here=Path(__file__).resolve().parent
    manifest=json.loads((here/'PACKAGE_SHA256.json').read_text('utf-8'))
    for p,h in manifest['files'].items():
        target=here/p
        if not target.is_file() or sha(target)!=h:
            raise RuntimeError(f'PATCH_INTEGRITY_FAILURE: {p}')
    print('PACKAGE_VERIFY_PASS',len(manifest['files']),'files; exact 4d2414a additive overlay')

if __name__=='__main__':main()
