#!/usr/bin/env bash
set -euo pipefail
cd /run
umask 077
if (($# != 1)) || ! [[ "$1" =~ ^[1-9][0-9]?$ ]] || (($1 > 90)); then
  printf 'Usage: %s MAX_WORKERS (1–90)\n' "$0" >&2
  exit 3
fi
max_workers=$1
py=/opt/rt-env/bin/python
shards=10
cases=(G-T1_A G-T1_B G-T1_C G-T2_A G-T2_B G-T2_C G-V_A G-V_B G-V_C)
pids=()

run_worker() {
  local case_id=$1 shard=$2 key=$3 output_dir=$4 shard_count=$5 rc=0
  shift 5
  local -a cmd=("$py" -u /run/code/tb3_g6_revalidate.py
    --production /production --source /ref --original /original --finite-face-prior /prior
    --case "$case_id" --shard "$shard/$shard_count" --out "/run/$output_dir/$key.jsonl" "$@")
  printf '%q ' "${cmd[@]}" > "logs/$key.command.txt"
  printf '\n' >> "logs/$key.command.txt"
  date -u +%FT%TZ > "logs/$key.started.txt"
  "${cmd[@]}" > "logs/$key.log" 2>&1 || rc=$?
  date -u +%FT%TZ > "logs/$key.finished.txt"
  printf '%s\n' "$rc" > "logs/$key.exit.txt"
  return "$rc"
}

# Exercise archived rejection and a retained seam before the 90-shard rollout.
mkdir -p smoke
run_worker G-T2_B 0 SMOKE_B smoke 1 --task-id 1708 --task-id 1731 &
smoke_b=$!
run_worker G-T2_C 0 SMOKE_C smoke 1 --task-id 1025 &
smoke_c=$!
smoke_failed=0
wait "$smoke_b" || smoke_failed=$((smoke_failed+1))
wait "$smoke_c" || smoke_failed=$((smoke_failed+1))
printf '%s\n' "$smoke_failed" > receipts/SMOKE_WORKERS_FAILED.txt
if ((smoke_failed)); then exit 3; fi

failed=0
for ((shard=0; shard<shards; shard++)); do
  for case_id in "${cases[@]}"; do
    if (("${#pids[@]}" == max_workers)); then
      wait "${pids[0]}" || failed=$((failed+1))
      pids=("${pids[@]:1}")
    fi
    printf -v key '%s_%02d' "$case_id" "$shard"
    run_worker "$case_id" "$shard" "$key" traces "$shards" &
    pids+=("$!")
  done
done
for pid in "${pids[@]}"; do
  wait "$pid" || failed=$((failed+1))
done
printf '%s\n' "$failed" > receipts/TRACE_WORKERS_FAILED.txt
if ((failed)); then exit 3; fi
