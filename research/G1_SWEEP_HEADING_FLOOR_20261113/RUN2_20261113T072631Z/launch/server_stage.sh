#!/usr/bin/env bash
set -eu
stage=$1
script=$2
shift 2
base=/home/KMS/RUN2_20261113T072631Z
date -u +%FT%TZ > "$base/outputs/START_${stage}_UTC.txt"
set +e
set -x
docker run --rm --pull=never --name "g1-model-v32-${stage,,}-20261113t072631z" --network none --cpus 24 --user "$(id -u):$(id -g)" --workdir /run/code -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 --mount "type=bind,src=$base,dst=/run" --mount "type=bind,src=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source,dst=/banks,readonly" --entrypoint /opt/rt-env/bin/python sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f "/run/code/$script" --inputs /run/inputs --banks /banks --out /run/outputs "$@"
rc=$?
set +x
date -u +%FT%TZ > "$base/outputs/FINISH_${stage}_UTC.txt"
printf '%s\n' "$rc" > "$base/outputs/EXIT_${stage}.txt"
exit "$rc"
