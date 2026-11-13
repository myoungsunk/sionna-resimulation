#!/usr/bin/env bash
set -euo pipefail
remote=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$remote"
[[ -s OUTPUT_SHA256.txt && -s output/SHARD_EXIT.json ]]
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
rt=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
find recovery -type f -print0 | sort -z | xargs -0 sha256sum > EVALUATION_INPUT_SHA256.txt
cmd=(docker run --rm --pull=never --network none --cpus 4 --name "$(basename "$remote")_eval"
     --user "$(id -u):$(id -g)" --workdir /ref
     -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/runtime_packages:/ref/src
     -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1
     --mount "type=bind,src=$remote/input,dst=/input,readonly"
     --mount "type=bind,src=$remote/recovery,dst=/recovery,readonly"
     --mount "type=bind,src=$remote,dst=/run-g3"
     --mount "type=bind,src=$ref,dst=/ref,readonly"
     --mount "type=bind,src=$rt,dst=/runtime_packages,readonly"
     --entrypoint /opt/rt-env/bin/python "$image" -u /recovery/run_tb3_g3.py evaluate-only)
printf '%q ' "${cmd[@]}" > EVALUATION_COMMAND.txt
printf '\n' >> EVALUATION_COMMAND.txt
set +e
"${cmd[@]}" 2>&1 | tee evaluation.log
rc=${PIPESTATUS[0]}
set -e
printf '%s\n' "$rc" > EVALUATION_EXIT_CODE.txt
if [[ -d analysis ]]; then
    find analysis -type f -print0 | sort -z | xargs -0 -r sha256sum > EVALUATION_OUTPUT_SHA256.txt
fi
exit "$rc"
