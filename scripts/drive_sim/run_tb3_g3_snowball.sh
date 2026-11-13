
#!/usr/bin/env bash
set -euo pipefail
remote=$(cd -- "$(dirname -- "$0")/.." && pwd)
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
rt=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
docker image inspect --format '{{.Id}}' "$image"
cd "$remote"
date -u +%FT%TZ | tee STARTED_UTC.txt
find input -type f -print0 | sort -z | xargs -0 sha256sum > INPUT_SHA256.txt
cmd=(docker run --rm --pull=never --network none --cpus 36 --name "$(basename "$remote")"
     --user "$(id -u):$(id -g)" --workdir /ref
     -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/runtime_packages:/ref/src
     -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1
     --mount "type=bind,src=$remote/input,dst=/input,readonly"
     --mount "type=bind,src=$remote,dst=/run-g3"
     --mount "type=bind,src=$ref,dst=/ref,readonly"
     --mount "type=bind,src=$rt,dst=/runtime_packages,readonly"
     --entrypoint /opt/rt-env/bin/python "$image" -u /input/run_tb3_g3.py)
printf '%q ' "${cmd[@]}" > COMMAND.txt
printf '\n' >> COMMAND.txt
set +e
"${cmd[@]}" 2>&1 | tee run.log
rc=${PIPESTATUS[0]}
set -e
printf '%s\n' "$rc" > EXIT_CODE.txt
date -u +%FT%TZ > FINISHED_UTC.txt
if [[ -d output ]]; then
    find output -type f -print0 | sort -z | xargs -0 -r sha256sum > OUTPUT_SHA256.txt
fi
exit "$rc"
