"""Dedicated Anchor-B input lock; never changes the historical P3 archive lock."""
import hashlib, json, zipfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
LOCK=ROOT.parent/'EXECUTION_LOCK.json'

def sha_file(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def read_lock(path=LOCK):
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('question_id')!='DLP-ANCHORB-8ARM-20261102':
        raise RuntimeError('WRONG_QUESTION_ID')
    digest=data.get('archive_sha256')
    if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
        raise RuntimeError('ARCHIVE_HASH_NOT_FROZEN')
    return data

def open_verified_archive(archive):
    if sha_file(archive)!=read_lock()['archive_sha256']:
        raise RuntimeError('ANCHORB_ARCHIVE_HASH_MISMATCH')
    z=zipfile.ZipFile(archive)
    if len(z.namelist())!=len(set(z.namelist())) or z.testzip() is not None:
        z.close()
        raise RuntimeError('DUPLICATE_OR_CORRUPT_ARCHIVE_MEMBER')
    return z
