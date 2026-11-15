#!/usr/bin/env bash
set -euo pipefail
cd /run_m45
py=/opt/rt-env/bin/python
"$py" replay.py prepare
"$py" -u replay.py g3b > b.log 2>&1 &
bpid=$!
"$py" -u replay.py g3c > c.log 2>&1 &
cpid=$!
brc=0
crc=0
wait "$bpid" || brc=$?
wait "$cpid" || crc=$?
printf 'G3b %s\nG3c %s\n' "$brc" "$crc" > ARMS_EXIT.txt
test "$brc" = 0 && test "$crc" = 0
