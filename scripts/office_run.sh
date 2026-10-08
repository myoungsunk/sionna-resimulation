#!/bin/bash
# Run the office sweeps (one single-core PathSolver process per position, CORES at a time). Resumable: a position with a receipt is skipped.
#   PYTHON=<python with sionna-rt 2.0.1> bash scripts/office_run.sh                       # all 35 positions
#   PYTHON=... POSITIONS=results/OFFICE_RUN_PLAN_20261008/positions_pilot.txt OUT=results/OFFICE_RUN_PILOT bash scripts/office_run.sh
# Environment variables: PYTHON (required), POSITIONS, OUT, CORES (default 4), BIN_STRIDE (default 1 = all 257 bins), DEADLINE_MIN (no new position after this many minutes)
cd "$(dirname "$0")/.."
V=${PYTHON:?set PYTHON to the python that has sionna-rt 2.0.1, mitsuba 3.8.0 and drjit 1.3.1}
P=${POSITIONS:-results/OFFICE_RUN_PLAN_20261008/positions_all.txt}
O=${OUT:-results/OFFICE_RUN_20261008}
STRIDE=${BIN_STRIDE:-1}
mkdir -p $O/logs
DEADLINE=$(( $(date +%s) + ${DEADLINE_MIN:-100000} * 60 ))
one() {
  [ "$(date +%s)" -gt "$DEADLINE" ] && return 0
  x=$1; y=$2; tag=office_x${x}_y${y}
  [ -f $O/$tag/${tag}_receipt.json ] && return 0
  mkdir -p $O/$tag
  $V scripts/corridor_sionna_run.py --scenario office --out $O/$tag --xy $x $y --tag $tag --threads 1 --bin-stride $STRIDE > $O/logs/$tag.log 2>&1 || echo "FAILED $tag" >> $O/logs/FAILED; }
export -f one; export V O STRIDE DEADLINE
xargs -P ${CORES:-4} -L 1 bash -c 'one $0 $1' < $P
n=$(wc -l < $P); done_n=$(ls $O/*/*_receipt.json 2>/dev/null | wc -l)
echo "receipts $done_n of $n"
if [ "$done_n" -ge "$n" ]; then echo OFFICE_RUN_COMPLETE > $O/logs/OFFICE_RUN_COMPLETE; fi
