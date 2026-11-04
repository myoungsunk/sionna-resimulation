#!/usr/bin/env bash
set -euo pipefail
export PYTHONHOME=/home/myoung-sun/.local/share/prr31117
export LD_LIBRARY_PATH=/home/myoung-sun/.local/share/prr31117/lib
export PYTHONPATH=/home/myoung-sun/.local/share/sm0_native_20261104/site-packages
export DRJIT_LIBLLVM_PATH=/lib/x86_64-linux-gnu/libLLVM.so.20.1
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
here=/mnt/d/codex/MBVAR_PRR_001_20261103/research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/NEW_RT_DATA/SM0
mkdir -p "$here/logs"
# A new GO_SM0_V2_CANARY.json must be issued after independent V2 code audit.
test -f "$here/audit/GO_SM0_V2_CANARY.json" || { echo "HOLD: independent V2 GO missing" >&2; exit 3; }
test ! -e "$here/logs/CANARY_R4_194_V2_001.log"
/home/myoung-sun/.local/share/prr31117/bin/python3 -u "$here/producer.py" \
  --source /mnt/d/codex/MBVAR_PRR_001_20261103_inputs/SM0/source \
  --bank /mnt/d/codex/MBVAR_PRR_001_20261103_inputs \
  --case R4_aB_m0 --pose-id 194 --go "$here/audit/GO_SM0_V2_CANARY.json" \
  --out "$here/CANARY_R4_194_V2_001" 2>&1 | tee "$here/logs/CANARY_R4_194_V2_001.log"
