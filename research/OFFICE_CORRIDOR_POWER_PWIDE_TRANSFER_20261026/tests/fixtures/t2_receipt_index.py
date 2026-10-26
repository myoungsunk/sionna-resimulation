# Verbatim functions from prepare_inputs.py at 034e57a7209a3bd1bb8857b24fd85c64942e1258
# research/POWERJOINT_AUDIT_RERUN_20261020/T2_NEW_ROUTE_BASELINE/prepare_inputs.py
from pathlib import Path
import hashlib
import json

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def receipt_index(root):
    records, receipts = {}, []
    for name, key in [('ARCHIVE_CONTENTS_AND_SHA.json', 'extracted'),
                      ('SOURCE_RELEASE_SUBSET_RECEIPT.json', 'kept')]:
        for path in root.rglob(name):
            data = json.loads(path.read_text()); receipts.append(dict(path=str(path), sha256=sha(path)))
            for row in data.get(key, []):
                dest = (path.parent/'data'/row['name']).resolve()
                expected = row['sha256'].lower()
                if dest in records and records[dest] != expected:
                    raise ValueError('CONFLICTING_RECEIPT:'+str(dest))
                records[dest] = expected
    if not receipts: raise ValueError('BLOCKED_INPUT:NO_SOURCE_EXTRACTION_SHA_RECEIPT')
    return records, receipts
