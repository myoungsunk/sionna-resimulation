"""Restore the published static canonical archive without replacing any file."""
import hashlib,json,tarfile
from pathlib import Path
root=Path(__file__).resolve().parent
receipt=json.loads((root/'STATIC48/STATIC_PREPARATION.json').read_text())
with tarfile.open(root/'STATIC48_PAYLOADS.tar.gz','r:gz') as tar:
    for member in tar:
        target=(root/member.name).resolve()
        if not target.is_relative_to((root/'STATIC48').resolve()) or not member.isfile():
            raise ValueError('INVALID_ARCHIVE_MEMBER')
        relative=target.relative_to(root/'STATIC48').as_posix()
        expected=receipt['files'][relative]
        content=tar.extractfile(member).read()
        if hashlib.sha256(content).hexdigest()!=expected:raise ValueError('ARCHIVE_SHA_MISMATCH')
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest()!=expected:raise ValueError('EXISTING_PAYLOAD_DIFFERS')
        else:
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as f:f.write(content)
print('STATIC48_PAYLOADS_VERIFIED')
