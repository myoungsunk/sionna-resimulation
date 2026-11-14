"""Reuse the verified exact-zero R2 result for the Anchor B gate correction."""
import json
from pathlib import Path
import sys


record = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
checks = record["checks"]
files = record["per_file_sha256_first_second"]
required = {
    "s0_r2": "REPORT_LEVEL_PASS",
    "source_commit": "81cdffbdedf43b318ebf8eddb4fcbac1fd30d878",
    "verified_input_zip_sha256": "88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63",
    "check_count": 657,
    "failures": [],
}
if any(record[key] != expected for key, expected in required.items()):
    raise SystemExit("Frozen R2 S0 receipt failed identity or verdict verification")
if len(checks) != 657 or len(files) != 34 or any(a != b for a, b in files.values()):
    raise SystemExit("Frozen R2 S0 receipt failed repeated replay verification")
print("R2 REPORT_LEVEL_PASS reused from hosted Actions 43606841242. Exact-zero gate retained.")
