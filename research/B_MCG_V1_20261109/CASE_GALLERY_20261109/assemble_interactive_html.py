#!/usr/bin/env python3
"""Reconstruct the exact 506-case interactive HTML from SHA-checked UTF-8 parts."""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parent
PARTS=ROOT/"INTERACTIVE_HTML_PARTS"
OUTPUT=ROOT/"B_MCG_506_CASES_INTERACTIVE_20261109.html"
EXPECTED_SHA256="e707f55e879a8054c9df1a57fa50554eb1edbfad306039958554589bd6904c0f"
EXPECTED_SIZE=13488962
data=b"".join((PARTS/f"part_{i:02d}.txt").read_bytes() for i in range(20))
assert len(data)==EXPECTED_SIZE,(len(data),EXPECTED_SIZE)
assert hashlib.sha256(data).hexdigest()==EXPECTED_SHA256,"SOURCE_SHA256_MISMATCH"
if OUTPUT.exists():
    assert OUTPUT.read_bytes()==data,"OUTPUT_ALREADY_EXISTS_DIFFERENT"
else: OUTPUT.write_bytes(data)
print(f"VERIFIED {OUTPUT} SHA256={EXPECTED_SHA256}")
