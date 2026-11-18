#!/bin/bash
# Generic sweep runner with verified resume, a request contract, and honest exit codes.
#   SCENARIO=office|corridor  PYTHON=<sionna python>  POSITIONS=<file: "x y" per line>  OUT=<dir>
#   optional: CORES (4) BIN_STRIDE (1) DEADLINE_MIN (no limit) ANCHOR_X ANCHOR_Y TAG_PREFIX ALLOW_RUNNER_CHANGE=1
# A position is skipped only if sweep_verify.py finds it fully valid under THIS request (not because a receipt exists). An invalid folder is
# moved to $OUT/_superseded/ (kept) and recomputed. The completion marker is written only after every requested position passes sweep_verify.py run.
# Exit codes: 0 complete and verified | 1 a position failed or verification failed | 2 request differs from the one this OUT was started with | 3 incomplete (deadline), no failure
cd "$(dirname "$0")/.."
V=${PYTHON:?set PYTHON to the python that has sionna-rt 2.0.1, mitsuba 3.8.0 and drjit 1.3.1}
VP=${VERIFY_PYTHON:-$V}   # python with numpy for the checks (default: the same as PYTHON)
SC=${SCENARIO:?set SCENARIO=office or corridor}
P=${POSITIONS:?set POSITIONS to a file with one "x y" per line}
O=${OUT:?set OUT to the output directory}
STRIDE=${BIN_STRIDE:-1}
PREFIX=${TAG_PREFIX-$([ "$SC" = office ] && echo office_ || echo "")}
EXTRA=""; VERX=""
[ -n "${ANCHOR_X:-}" ] && EXTRA="$EXTRA --anchor-x $ANCHOR_X" && VERX="$VERX --anchor-x $ANCHOR_X"
[ -n "${ANCHOR_Y:-}" ] && EXTRA="$EXTRA --anchor-y $ANCHOR_Y" && VERX="$VERX --anchor-y $ANCHOR_Y"
[ -n "${ALLOW_RUNNER_CHANGE:-}" ] && VERX="$VERX --allow-runner-change"
mkdir -p $O/logs $O/_superseded
rm -f $O/logs/OFFICE_RUN_COMPLETE $O/logs/SWEEP_COMPLETE $O/logs/FAILED
$VP scripts/sweep_verify.py request --scenario $SC --run-dir $O --positions $P --bin-stride $STRIDE --tag-prefix "$PREFIX" $VERX || exit $?
DEADLINE=$(( $(date +%s) + ${DEADLINE_MIN:-100000} * 60 ))
export V VP SC O STRIDE PREFIX EXTRA VERX DEADLINE
one() {
  [ "$(date +%s)" -gt "$DEADLINE" ] && return 0
  x=$1; y=$2; tag=${PREFIX}x${x}_y${y}
  if $VP scripts/sweep_verify.py position --scenario $SC --run-dir $O --x $x --y $y --bin-stride $STRIDE --tag-prefix "$PREFIX" $VERX > /dev/null 2>&1; then return 0; fi
  [ -d $O/$tag ] && mv $O/$tag $O/_superseded/${tag}_$(date +%s)
  mkdir -p $O/$tag
  if ! $V scripts/corridor_sionna_run.py --scenario $SC --out $O/$tag --xy $x $y --tag $tag --threads 1 --bin-stride $STRIDE $EXTRA > $O/logs/$tag.log 2>&1; then
    echo "FAILED $tag (runner exit)" >> $O/logs/FAILED; return 1; fi
  if ! $VP scripts/sweep_verify.py position --scenario $SC --run-dir $O --x $x --y $y --bin-stride $STRIDE --tag-prefix "$PREFIX" $VERX > $O/logs/$tag.verify.json 2>&1; then
    echo "FAILED $tag (output check)" >> $O/logs/FAILED; return 1; fi
}
export -f one
awk 'NF>=2 {print $1, $2}' $P | xargs -P ${CORES:-4} -L 1 bash -c 'one $0 $1'
XRC=$?
$VP scripts/sweep_verify.py run --scenario $SC --run-dir $O --positions $P --bin-stride $STRIDE --tag-prefix "$PREFIX" $VERX > $O/logs/verify_run.txt 2>&1
VRC=$?
NFAIL=$( [ -f $O/logs/FAILED ] && wc -l < $O/logs/FAILED || echo 0 )
STATUS=INCOMPLETE; RC=3
if [ $XRC -ne 0 ] || [ "$NFAIL" -gt 0 ]; then STATUS=FAILED; RC=1
elif [ $VRC -eq 0 ]; then STATUS=COMPLETE; RC=0
elif [ "$(date +%s)" -gt "$DEADLINE" ]; then STATUS=INCOMPLETE; RC=3
else STATUS=FAILED; RC=1; fi
printf '{"status":"%s","xargs_exit":%d,"failed_positions":%d,"verify_exit":%d,"exit_code":%d}\n' $STATUS $XRC $NFAIL $VRC $RC > $O/RUN_STATUS.json
cat $O/RUN_STATUS.json
[ $RC -eq 0 ] && echo "$STATUS" > $O/logs/SWEEP_COMPLETE
exit $RC
