#!/usr/bin/env bash
set -eu
base=/home/KMS/RUN2_20261113T072631Z
start=$(date -u +%FT%TZ)
printf '%s\n' "$start" > "$base/outputs/START_PREFLIGHT_UTC.txt"
set +e
docker run --rm --pull=never --name g1-model-v32-preflight-20261113t072631z --network none --cpus 8 --user "$(id -u):$(id -g)" --workdir /run/code -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 --mount "type=bind,src=$base,dst=/run" --mount "type=bind,src=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source,dst=/banks,readonly" --entrypoint /opt/rt-env/bin/python sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f /run/code/v32_preflight.py --inputs /run/inputs --banks /banks --out /run/outputs --workers 8
rc=$?
date -u +%FT%TZ > "$base/outputs/FINISH_PREFLIGHT_UTC.txt"
printf '%s\n' "$rc" > "$base/outputs/EXIT_PREFLIGHT.txt"
exit "$rc"
