#!/bin/bash
# Run every position of results/CORRIDOR_SCAN2_20261007/positions.txt (tier A, then B), four single-core PathSolver sweeps at a time.
# Resumable: a position whose receipt exists is skipped.   PYTHON=<sionna venv python> bash scripts/corridor_scan2_run.sh
cd "$(dirname "$0")/.."
V=${PYTHON:?set PYTHON to the sionna venv python}
O=results/CORRIDOR_SCAN2_20261007
one() { x=$1; y=$2; tier=$3; tag=x${x}_y${y}
  [ -f $O/$tag/${tag}_receipt.json ] && return 0
  mkdir -p $O/$tag
  $V scripts/corridor_sionna_run.py --out $O/$tag --xy $x $y --tag $tag --threads 1 > $O/logs/$tag.log 2>&1 || echo "FAILED $tag" >> $O/logs/FAILED; }
export -f one; export V O
xargs -P 4 -L 1 bash -c 'one $0 $1 $2' < $O/positions.txt
echo SCAN2_COMPLETE > $O/logs/SCAN2_COMPLETE
