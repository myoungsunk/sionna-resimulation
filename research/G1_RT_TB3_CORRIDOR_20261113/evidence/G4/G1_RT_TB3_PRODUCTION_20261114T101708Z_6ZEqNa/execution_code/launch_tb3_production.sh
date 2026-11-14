#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
umask 077
run=$(pwd -P)
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
runtime=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
workers=$1
code_ref=$2
driver=$3
test "$(id -un)" = KMS
test "$(cat CANARY_EXIT.txt)" = 0
test ! -e PRODUCTION_START_UTC.txt
date -u +%FT%TZ > PRODUCTION_START_UTC.txt
cmd=(docker run --rm --pull=never --network none --name "production_$(basename "$run")"
  --cpus "$workers" --cpu-shares 256 --user "$(id -u):$(id -g)" --workdir /ref
  -e HOME=/run/cache -e TMPDIR=/run/scratch -e PYTHONDONTWRITEBYTECODE=1
  -e PYTHONPATH=/run/code:/runtime_packages:/ref:/ref/src
  -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1
  -v "$run:/run" -v "$ref:/ref:ro" -v "$runtime:/runtime_packages:ro"
  --entrypoint /usr/bin/nice "$image" -n 15 /opt/rt-env/bin/python -u
  /run/code/run_tb3_production_batch.py --root /run --source /ref
  --workers "$workers" --code-commit "$code_ref" --driver "$driver")
mkdir -p cache scratch
printf '%q ' "${cmd[@]}" > PRODUCTION_COMMAND.txt
printf '\n' >> PRODUCTION_COMMAND.txt
rc=0
"${cmd[@]}" > production.log 2>&1 || rc=$?
date -u +%FT%TZ > PRODUCTION_FINISH_UTC.txt
printf '%s\n' "$rc" > PRODUCTION_EXIT.txt
exit "$rc"
