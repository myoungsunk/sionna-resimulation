"""Verify uploaded files and optionally restore complete results into a new folder."""
import argparse,hashlib,json,tarfile,tempfile
from pathlib import Path

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--extract',type=Path);a=ap.parse_args()
    root=Path(__file__).resolve().parent
    receipt=json.loads((root/'UPLOAD_VALIDATION.json').read_text())
    for name,digest in receipt['files'].items():assert sha(root/name)==digest,name
    h=hashlib.sha256()
    for name in receipt['archive_parts']:
        with (root/name).open('rb') as f:
            for b in iter(lambda:f.read(1048576),b''):h.update(b)
    assert h.hexdigest()==receipt['archive_sha256'],'ARCHIVE_SHA_MISMATCH'
    if a.extract:
        target=a.extract.resolve();assert not target.exists(),'EXTRACTION_TARGET_MUST_BE_NEW'
        # Assemble into a temporary file, leaving all delivered parts unchanged.
        with tempfile.TemporaryFile() as merged:
            for name in receipt['archive_parts']:
                with (root/name).open('rb') as f:
                    for b in iter(lambda:f.read(1048576),b''):merged.write(b)
            merged.seek(0)
            with tarfile.open(fileobj=merged,mode='r:gz') as t:t.extractall(target,filter='data')
        count=0
        for manifest in target.glob('0*/OUTPUT_SHA256.json'):
            for name,digest in json.loads(manifest.read_text()).items():
                assert sha(manifest.parent/name)==digest,name;count+=1
        assert count==receipt['output_hashes_verified']
        print('RESTORED_OUTPUT_SHA_PASS',count)
    print('DELIVERY_SHA_PASS',len(receipt['files']))

if __name__=='__main__':main()
