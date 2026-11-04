#!/usr/bin/env bash
set -euo pipefail
export PYTHONHOME=/home/myoung-sun/.local/share/prr31117
export LD_LIBRARY_PATH=/home/myoung-sun/.local/share/prr31117/lib
export PYTHONPATH=/home/myoung-sun/.local/share/sm0_native_20261104/site-packages
export DRJIT_LIBLLVM_PATH=/lib/x86_64-linux-gnu/libLLVM.so.20.1
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
here=/mnt/d/codex/MBVAR_PRR_001_20261103/research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/NEW_RT_DATA/SM0/PRECISION_AMENDMENT_001
test ! -e "$here/CHECKS_002.log"
test ! -e "$here/REVALIDATION_002.log"
/home/myoung-sun/.local/share/prr31117/bin/python3 "$here/test_precision.py" 2>&1 | tee "$here/CHECKS_002.log"
/home/myoung-sun/.local/share/prr31117/bin/python3 "$here/revalidate.py" \
  --capture "$here/../CANARY_R4_194_001" \
  --source /mnt/d/codex/MBVAR_PRR_001_20261103_inputs/SM0/source \
  --out "$here/REVALIDATION_002" 2>&1 | tee "$here/REVALIDATION_002.log"
