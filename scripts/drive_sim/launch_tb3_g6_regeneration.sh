#!/usr/bin/env bash
set -euo pipefail
umask 077
run=$1
commit=$2
if [[ ${3-} == container ]]; then
  cd /run
  py=/opt/rt-env/bin/python
  args=(--inputs /inputs/g0 --g7 /inputs/g7)
  cases=(G-T2_B G-T2_C)
  pids=()
  for case_id in "${cases[@]}"; do
    for ((i=0; i<18; i++)); do
      printf -v label '%03d' "$i"
      "$py" -u code/run_tb3_production.py "${args[@]}" --source /ref \
        --production /inputs/config/PRODUCTION_F1.json --reference /inputs/frozen/REFERENCE.json \
        --ffd-manifest /inputs/frozen/FFD_RESTORE_MANIFEST.json --code-commit "$commit" \
        --g6-regenerate --case "$case_id" --shard-index "$i" --shard-count 18 \
        --out "shards/$case_id/$label" > "logs/${case_id}_$label.log" 2>&1 &
      pids+=("$!")
    done
  done
  errors=0
  for pid in "${pids[@]}"; do
    wait "$pid" || errors=$((errors+1))
  done
  printf '%s\n' "$errors" > SHARD_FAILURES.txt
  ((errors == 0)) || exit 3
  for case_id in "${cases[@]}"; do
    "$py" -u code/merge_tb3_production.py "${args[@]}" --case "$case_id" \
      --shards "shards/$case_id" --out results > "logs/${case_id}_merge.log" 2>&1
    "$py" code/seal_tb3_production.py --root results --case "$case_id"
  done
  exit
fi

test "$(id -un)" = KMS
run=$(cd "$run" && pwd -P)
[[ "$run" == /home/KMS/G1_MODEL003_G6_REGEN_* && "$commit" =~ ^[0-9a-f]{40}$ ]]
cd "$run"
original=/home/KMS/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
runtime=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
img=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
test ! -e "$original/results/seal/UNSEAL.json"
mkdir cache scratch logs shards results
sha256sum code/*.py code/*.sh > CODE.sha256
cmd=(docker run --rm --pull=never --network none --cpus 36 --cpu-shares 192
  --name "$(basename "$run")" --user "$(id -u):$(id -g)" --workdir /ref
  -e PYTHONDONTWRITEBYTECODE=1 -e HOME=/run/cache -e TMPDIR=/run/scratch
  -e PYTHONPATH=/run/code:/runtime_packages:/ref:/ref/src
  -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1
  -v "$run:/run" -v "$run/code:/run/code:ro" -v "$ref:/ref:ro" -v "$runtime:/runtime_packages:ro"
  -v "$original/g0:/inputs/g0:ro" -v "$original/g7:/inputs/g7:ro"
  -v "$original/config:/inputs/config:ro" -v "$original/frozen:/inputs/frozen:ro"
  --entrypoint /usr/bin/nice "$img" -n 12 /bin/bash /run/code/launch_tb3_g6_regeneration.sh
  /run "$commit" container)
printf '%q ' "${cmd[@]}" > COMMAND.txt
printf '\n' >> COMMAND.txt
date -u +%FT%TZ > STARTED_UTC.txt
rc=0
"${cmd[@]}" > execution.log 2>&1 || rc=$?
date -u +%FT%TZ > FINISHED_UTC.txt
printf '%s\n' "$rc" > EXIT_CODE.txt
exit "$rc"
