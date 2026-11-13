#!/usr/bin/env bash
set -eu
cd /home/KMS/RUN4_20261113T105130Z
test -s GRID_FINISH_UTC.txt && test -s GRID_SHA256.txt && test -s s2_out/S1P_ERR_MODEL_LORO.json
grep -q PASS_GRID_BUILD GRID_BUILD.log
test ! -e s2_out/START_primary_UTC.txt
if ps -p 353604 -o args= | grep -q 'while ! test -s GRID_EXIT.txt.*run_s2_final.sh primary 24'; then kill 353604; fi
nohup bash run_s2_final.sh primary 24 > PRIMARY_READY_DRIVER.log 2>&1 < /dev/null &
nohup bash -c 'while ! test -s M0_FINISH_UTC.txt || ! test -s s2_out/EXIT_primary.txt; do sleep 15; done; test "$(cat s2_out/EXIT_primary.txt)" = 0 && test -s M0_GRID_SHA256.txt && grep -q PASS_M0_GRID_BUILD M0_GRID_BUILD.log || exit 5; exec bash run_s2_final.sh b0 16' > B0_DRIVER.log 2>&1 < /dev/null &
printf '%s\n' 'Primary started, B0 queued'

