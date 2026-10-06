#!/bin/bash
# Two batches of four single-core PathSolver sweeps (about 16 min each).
cd /home/user/sionna-resimulation
V=${PYTHON:?set PYTHON to the sionna venv python}
O=results/CORRIDOR_SCAN_20261006
run() { x=$1; y=$2; tag=x${x}_y${y}; mkdir -p $O/$tag
  $V scripts/corridor_sionna_run.py --out $O/$tag --xy $x $y --tag $tag --threads 1 > $O/logs/$tag.log 2>&1 & }
run 5.5 0.0; run 7.0 0.0; run 9.0 0.0; run 11.0 0.0; wait
run 13.0 0.0; run 7.0 -0.7; run 7.0 -0.35; run 7.0 0.7; wait
echo SCAN_COMPLETE > $O/logs/SCAN_COMPLETE
