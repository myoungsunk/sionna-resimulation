#!/usr/bin/env bash
set -euo pipefail
cd /run
umask 077
py=/opt/rt-env/bin/python
shards=10
cases=(G-T1_A G-T1_B G-T1_C G-T2_A G-T2_B G-T2_C G-V_A G-V_B G-V_C)
pids=()

run_worker() {
  local case_id=$1 shard=$2 key=$3 rc=0
  local -a cmd=("$py" -u /run/code/tb3_g6_revalidate.py
    --production /production --source /ref --original /original
    --case "$case_id" --shard "$shard/$shards" --out "/run/traces/$key.jsonl")
  printf '%q ' "${cmd[@]}" > "logs/$key.command.txt"
  printf '\n' >> "logs/$key.command.txt"
  date -u +%FT%TZ > "logs/$key.started.txt"
  "${cmd[@]}" > "logs/$key.log" 2>&1 || rc=$?
  date -u +%FT%TZ > "logs/$key.finished.txt"
  printf '%s\n' "$rc" > "logs/$key.exit.txt"
  return "$rc"
}

for ((shard=0; shard<shards; shard++)); do
  for case_id in "${cases[@]}"; do
    printf -v key '%s_%02d' "$case_id" "$shard"
    run_worker "$case_id" "$shard" "$key" &
    pids+=("$!")
  done
done
failed=0
for pid in "${pids[@]}"; do
  wait "$pid" || failed=$((failed+1))
done
printf '%s\n' "$failed" > receipts/TRACE_WORKERS_FAILED.txt
if ((failed)); then exit 3; fi
