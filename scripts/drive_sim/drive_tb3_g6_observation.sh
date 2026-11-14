#!/usr/bin/env bash
set -euo pipefail
declare -a pids=()
for entry in G-T1_A:1 G-T1_B:1 G-T1_C:1 G-T2_A:2 G-T2_B:2 G-T2_C:6 G-V_A:1 G-V_B:1 G-V_C:1; do
  case_id=${entry%:*}
  count=${entry#*:}
  for ((index=0; index<count; index++)); do
    key="${case_id}_${index}"
    /opt/rt-env/bin/python -u /run/code/diagnose_tb3_g6_observation.py \
      --g6 /g6 --image-result /image.json --production-root /production --source /ref \
      --case "$case_id" --shard "$index/$count" --out "/run/parts/$key.json" > "/run/logs/$key.log" 2>&1 &
    pids+=("$!")
  done
done
rc=0
for pid in "${pids[@]}"; do wait "$pid" || rc=2; done
exit "$rc"
