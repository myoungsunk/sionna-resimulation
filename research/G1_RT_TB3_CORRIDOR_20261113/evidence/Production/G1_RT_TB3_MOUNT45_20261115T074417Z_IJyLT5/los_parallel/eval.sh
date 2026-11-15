#!/usr/bin/env bash
set -euo pipefail
cd /run/los_parallel
py=/opt/rt-env/bin/python
"$py" run.py stage
seq 0 5 | xargs -n1 -P6 bash -ec '/opt/rt-env/bin/python -u run.py trace "$1" > "bins_$1.log" 2>&1' _
"$py" run.py merge
