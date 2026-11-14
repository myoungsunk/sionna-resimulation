#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
run="$(pwd -P)"
base=/home/KMS/G1_RT_TB3_CORRIDOR_G3_20261113T073918Z
revalidation=/home/KMS/G1_RT_TB3_CORRIDOR_G3_REVALIDATION_20261113T083444Z
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
rt=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
date -u +%FT%TZ > STARTED_UTC.txt
cmd=(docker run --rm --pull=never --network none --name "$(basename "$run")" --cpus 9
     --user "$(id -u):$(id -g)" --workdir /ref
     -v "$base:/g3:ro" -v "$revalidation:/revalidation:ro" -v "$ref:/ref:ro"
     -v "$rt:/runtime_packages:ro" -v "$run:/diag"
     -e PYTHONPATH=/g3/input:/runtime_packages:/ref/src -e HOME=/tmp
     -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 --entrypoint /bin/bash "$image" -c '
  pids=()
  for i in {0..8}; do
    /opt/rt-env/bin/python -u /diag/run_f1_pilot.py "$i" >"/diag/$i.log" 2>&1 &
    pids+=("$!")
  done
  rc=0
  for pid in "${pids[@]}"; do wait "$pid" || rc=1; done
  exit "$rc"')
printf '%q ' "${cmd[@]}" > COMMAND.txt
printf '\n' >> COMMAND.txt
rc=0
"${cmd[@]}" > run.log 2>&1 || rc=$?
printf '%s\n' "$rc" > EXIT_CODE.txt
date -u +%FT%TZ > FINISHED_UTC.txt
find . -maxdepth 1 -type f ! -name SHA256.txt -print0 | sort -z | xargs -0 sha256sum > SHA256.txt
exit "$rc"
