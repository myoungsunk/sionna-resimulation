#!/bin/bash
set -euo pipefail
cd /d7
export PYTHONPATH=/diag/diag003_work/code
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
python=/opt/rt-env/bin/python
"$python" - <<'PY'
import json
import platform
import sys
from pathlib import Path

import numpy
import scipy
import pandas

from diag_inputs import WORK, BASE, sha256
from check_d7_limits import d4_inputs

s0 = json.loads(Path("/d7/S0_REGRESSION.json").read_text(encoding="utf-8"))
assert s0["s0_overall"] == "REPORT_LEVEL_PASS"
record = json.loads((WORK/"MANIFEST.json").read_text(encoding="utf-8"))
for name, digest in record["code_sha256"].items():
    assert sha256(WORK/"code"/name) == digest, name
for path, digest in [
    (BASE/"original_RF_R2.zip", "88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63"),
    (BASE/"anchor_rf.zip", "9691d5b96141331734ac726b3b82c1b33f2d55e60721b64dd61080e399e8f36d"),
]:
    assert sha256(path) == digest, path
d4_inputs()
print("Inputs and frozen code verified.", sys.version, platform.platform(), numpy.__version__, scipy.__version__, pandas.__version__, flush=True)
PY
declare -a pids
for case in R2_aA_m0 R2_aB_m0 R4_aB_m0 R5_aB_m0; do
  "$python" -u /d7/check_d7_limits.py "$case" "GATE_$case.json" > "GATE_$case.log" 2>&1 &
  pids+=("$!")
done
failed=0
for pid in "${pids[@]}"; do
  wait "$pid" || failed=1
done
printf 'gate_exit=%s\n' "$failed"
exit "$failed"
