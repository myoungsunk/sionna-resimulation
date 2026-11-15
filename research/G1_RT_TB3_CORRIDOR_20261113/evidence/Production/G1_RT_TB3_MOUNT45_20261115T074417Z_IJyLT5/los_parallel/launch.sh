#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
umask 077
run=$(dirname "$(pwd -P)")
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
legacy=/home/KMS/G1_RT_TB3_CORRIDOR_PILOT_20261113T070808Z/output
runtime=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
test "$(id -un)" = KMS
set -o noclobber
date -u +%FT%TZ > START_UTC.txt
set +o noclobber
rc=0
docker run --rm --pull=never --network none --name "los_$(basename "$run")" \
  --cpus 6 --cpu-shares 64 --user "$(id -u):$(id -g)" --workdir /ref \
  -e HOME=/run/cache -e TMPDIR=/run/scratch -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/run/code:/runtime_packages:/ref:/ref/src \
  -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 \
  -v "$run:/run:ro" -v "$run/cache:/run/cache" -v "$run/scratch:/run/scratch" \
  -v "$run/los_parallel:/run/los_parallel" \
  -v "$ref:/ref:ro" -v "$runtime:/runtime_packages:ro" -v "$legacy:/legacy:ro" \
  --entrypoint /usr/bin/nice "$image" -n 18 /run/los_parallel/eval.sh > trace.log 2>&1 || rc=$?
printf '%s\n' "$rc" > EXIT_CODE.txt
date -u +%FT%TZ > FINISH_UTC.txt
exit "$rc"
