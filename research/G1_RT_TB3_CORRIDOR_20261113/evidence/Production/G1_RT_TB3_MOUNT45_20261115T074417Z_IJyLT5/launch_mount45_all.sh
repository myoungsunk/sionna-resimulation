#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
umask 077
test "$(id -un)" = KMS
set -o noclobber
date -u +%FT%TZ > FULL_SCHEDULED_UTC.txt
set +o noclobber
finish() {
  rc=$?
  date -u +%FT%TZ > FULL_FINISHED_UTC.txt
  printf '%s\n' "$rc" > FULL_EXIT.txt
}
trap finish EXIT
until test -s CANARY_EXIT.txt; do
    test ! -s CANARY_LAUNCH_PID.txt || kill -0 "$(cat CANARY_LAUNCH_PID.txt)"
    sleep 15
done
test "$(cat CANARY_EXIT.txt)" = 0
sha256sum -c MOUNT45_INPUTS.sha256
sha256sum -c MOUNT0_SEAL_BEFORE.sha256
test ! -e "$(cat MOUNT0_RUN.txt)/results/seal/UNSEAL.json"
bash launch_tb3_production.sh 48 6242fb99f67df17c4b686eca14380ebd471491b6 canary01
g4_rc=0
bash launch_tb3_g4_snowball.sh || g4_rc=$?
sha256sum -c MOUNT0_SEAL_BEFORE.sha256
test ! -e "$(cat MOUNT0_RUN.txt)/results/seal/UNSEAL.json"
python3 verify_mount45.py
exit "$g4_rc"
