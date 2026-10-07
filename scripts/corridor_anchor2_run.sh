#!/bin/bash
# Anchor 2 = ceiling anchor at (4, -0.4); tag on its own y = -0.4 line at the x list of results/CORRIDOR_ANCHOR2_20261007/positions.txt.
# Four single-core PathSolver sweeps at a time; resumable (a position with a receipt is skipped); no new position starts after DEADLINE_MIN.
#   PYTHON=<sionna venv python> bash scripts/corridor_anchor2_run.sh
cd "$(dirname "$0")/.."
V=${PYTHON:?set PYTHON to the sionna venv python}
O=results/CORRIDOR_ANCHOR2_20261007
AX=4.0; AY=-0.4
DEADLINE=$(( $(date +%s) + ${DEADLINE_MIN:-90} * 60 ))
one() {
  [ "$(date +%s)" -gt "$DEADLINE" ] && return 0
  x=$1; y=$2; tag=a2_x${x}_y${y}
  [ -f $O/$tag/${tag}_receipt.json ] && return 0
  mkdir -p $O/$tag
  $V scripts/corridor_sionna_run.py --out $O/$tag --xy $x $y --tag $tag --threads 1 --anchor-x $AX --anchor-y $AY > $O/logs/$tag.log 2>&1 || echo "FAILED $tag" >> $O/logs/FAILED; }
export -f one; export V O AX AY DEADLINE
xargs -P 4 -L 1 bash -c 'one $0 $1' < $O/positions.txt
n=$(wc -l < $O/positions.txt); done_n=$(ls $O/*/*_receipt.json 2>/dev/null | wc -l)
echo "receipts $done_n of $n"
if [ "$done_n" -ge "$n" ]; then echo ANCHOR2_COMPLETE > $O/logs/ANCHOR2_COMPLETE; fi
