#!/bin/bash
set -euo pipefail
dir=$(cd -- "$(dirname -- "$0")" && pwd)
cd "$dir"
base=/home/KMS/G1_RT_TB3_CORRIDOR_G3_20261113T073918Z
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
rt=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
date -u +%FT%TZ > STARTED_UTC.txt
cd "$base"
sha256sum --quiet -c INPUT_SHA256.txt
sha256sum --quiet -c EVALUATION_OUTPUT_SHA256.txt
cd "$dir"
cmd=(docker run --rm --pull=never --network none --cpus 5 --user "$(id -u):$(id -g)"
    --workdir /ref -e PYTHONPATH=/diag:/g3/input:/runtime_packages:/ref/src:/ref
    -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e OPENBLAS_NUM_THREADS=1
    -e MKL_NUM_THREADS=1 -e OMP_NUM_THREADS=1
    --mount "type=bind,src=$dir,dst=/diag"
    --mount "type=bind,src=$base,dst=/g3,readonly"
    --mount "type=bind,src=$ref,dst=/ref,readonly"
    --mount "type=bind,src=$rt,dst=/runtime_packages,readonly"
    --entrypoint /bin/bash "$image" /diag/run_workers.sh)
printf '%q ' "${cmd[@]}" > COMMAND.txt
printf '\n' >> COMMAND.txt
set +e
timeout 480s "${cmd[@]}" 2>&1 | tee run.log
rc=${PIPESTATUS[0]}
set -e
printf '%s\n' "$rc" > EXIT_CODE.txt
date -u +%FT%TZ > FINISHED_UTC.txt
find . -maxdepth 1 -type f ! -name SHA256SUMS.txt -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS.txt
exit "$rc"
