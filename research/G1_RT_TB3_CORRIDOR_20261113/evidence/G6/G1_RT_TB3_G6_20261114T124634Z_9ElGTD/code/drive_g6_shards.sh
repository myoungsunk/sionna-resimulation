#!/usr/bin/env bash
set -euo pipefail
cd /run
umask 077
shards=$1
py=/opt/rt-env/bin/python
cases=(G-T1_A G-T1_B G-T1_C G-T2_A G-T2_B G-T2_C G-V_A G-V_B G-V_C)
pids=()
for shard in $(seq 0 "$((shards-1))"); do
 for case in "${cases[@]}"; do
  prefix="${case}_$(printf '%02d' "$shard")"
  cmd=("$py" -u /run/code/tb3_g6_trace.py --production-root /production --source /ref
    --case "$case" --tasks "/run/selected/$case.json" --all-nodes --shard "$shard/$shards"
    --receipts "/production/results/paths/$case/TRACE_RECEIPTS.json" --out "/run/traces/$prefix.jsonl")
  printf '%q ' "${cmd[@]}" > "logs/$prefix.command.txt"
  printf '\n' >> "logs/$prefix.command.txt"
  "${cmd[@]}" > "logs/$prefix.log" 2>&1 &
  pids+=("$!")
 done
done
rc=0
for pid in "${pids[@]}"; do wait "$pid" || rc=1; done
printf '%s\n' "$rc" > receipts/TRACE_WORKERS_EXIT.txt
exit "$rc"

