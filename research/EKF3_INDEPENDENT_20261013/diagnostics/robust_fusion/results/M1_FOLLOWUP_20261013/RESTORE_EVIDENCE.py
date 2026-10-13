"""Concatenate verified archive parts next to this script; do not overwrite."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
metadata = json.loads((root/'EVIDENCE_ARCHIVE.json').read_text())
digest = hashlib.sha256()
size = 0
with (root/'EVIDENCE.zip').open('xb') as target:
    for name in metadata['parts']:
        if Path(name).name != name:
            raise ValueError('Archive parts must be sibling files')
        with (root/name).open('rb') as source:
            while data := source.read(1024*1024):
                target.write(data); digest.update(data); size += len(data)
if digest.hexdigest() != metadata['sha256'] or size != metadata['bytes']:
    raise RuntimeError('Archive integrity failed; do not extract the output')
print('Verified EVIDENCE.zip; extract with any standard ZIP reader.')
