#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
test "$(id -un)" = KMS
max_wait=$((SECONDS + 5400))
while [[ ! -s los_parallel/EXIT_CODE.txt ]]; do
  if [[ -s CANARY_EXIT.txt && "$(cat CANARY_EXIT.txt)" = 0 ]] ||
     [[ -s los_reference/REFERENCE_RESULT.json ]]; then
    printf '%s original_reference_available\n' "$(date -u +%FT%TZ)" > los_parallel/SELECTION.txt
    exit 0
  fi
  (( SECONDS < max_wait ))
  sleep 15
done
test "$(cat los_parallel/EXIT_CODE.txt)" = 0
if [[ -s CANARY_EXIT.txt && "$(cat CANARY_EXIT.txt)" = 0 ]] ||
   [[ -s los_reference/REFERENCE_RESULT.json ]]; then
  printf '%s original_reference_available\n' "$(date -u +%FT%TZ)" > los_parallel/SELECTION.txt
  exit 0
fi
test -s los_parallel/reference/PATHS_LoS.npz
test -s los_parallel/reference/REFERENCE_RESULT.json
sha256sum -c los_parallel/INPUTS.sha256
sha256sum -c MOUNT45_INPUTS.sha256
container="canary_$(basename "$PWD")"
if [[ ! -s CANARY_EXIT.txt ]]; then
  docker stop --time 12 "$container"
fi
deadline=$((SECONDS + 120))
until [[ -s CANARY_EXIT.txt && -s FULL_EXIT.txt ]]; do
  (( SECONDS < deadline ))
  sleep 2
done
if [[ "$(cat CANARY_EXIT.txt)" = 0 ]]; then
  printf '%s original_reference_available\n' "$(date -u +%FT%TZ)" > los_parallel/SELECTION.txt
  exit 0
fi
test ! -e PRODUCTION_START_UTC.txt
archive=los_parallel/original_attempt
mkdir "$archive"
for path in CANARY_*.txt FULL_*.txt logs/canary.log logs/canary_launcher.log \
    logs/full_launcher.log los_reference canary01; do
    if [[ -e "$path" ]]; then mv -- "$path" "$archive/"; fi
done
cp -a -- los_parallel/reference los_reference
printf '%s independent_ranges_selected\n' "$(date -u +%FT%TZ)" > los_parallel/SELECTION.txt
nohup bash launch_mount45_canary_precomputed.sh > logs/canary_launcher.log 2>&1 </dev/null &
printf '%s\n' "$!" > CANARY_LAUNCH_PID.txt
nohup bash launch_mount45_all.sh > logs/full_launcher.log 2>&1 </dev/null &
printf '%s\n' "$!" > FULL_LAUNCH_PID.txt
