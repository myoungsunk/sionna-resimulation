"""Restore the byte-identical expired Actions artifact without exposing RF."""
import hashlib
import os
from pathlib import Path
import sys
import zipfile

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

data = Path(sys.argv[1]).read_bytes()
key = bytes.fromhex(os.environ["R2_INPUT_KEY"])
plaintext = AESGCM(key).decrypt(data[:12], data[12:], b"G1-DIAG-003/S0/r2-11782748118")
digest = hashlib.sha256(plaintext).hexdigest()
if digest != "88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63":
    raise RuntimeError("R2_ARCHIVE_SHA256_MISMATCH")
path = Path(sys.argv[2])
path.write_bytes(plaintext)
with zipfile.ZipFile(path) as archive:
    if archive.testzip() is not None:
        raise RuntimeError("R2_ARCHIVE_CRC_MISMATCH")
print("R2_ARCHIVE_SHA256_CRC_PASS", digest)