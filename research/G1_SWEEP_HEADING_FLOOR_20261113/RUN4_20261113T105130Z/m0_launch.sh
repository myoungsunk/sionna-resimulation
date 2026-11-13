#!/usr/bin/env bash
set -euo pipefail
umask 077
base=/home/KMS/RUN4_20261113T105130Z
run3=/home/KMS/RUN3_20261113T085001Z
inputs=/home/KMS/RUN2_20261113T072631Z/inputs
banks=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
workers=16
cd "$base"
date -u +%FT%TZ > M0_START_UTC.txt
{
 date -u +%FT%TZ
 uptime
 free -h
 df -h "$base"
 docker info --format 'Docker CPU: {{.NCPU}}'
 docker image inspect "$image" --format '{{.Id}}'
 printf 'workers=%s\n' "$workers"
} > M0_RESOURCES.txt
printf '%s  %s\n' 5f9732bf406fde2e0f6bb7f80ad3b04979ec4e84c3d4731ed980e7af7a235ef3 "$run3/outputs/MANIFEST.json" | sha256sum -c > M0_INHERITED_CHECK.log
sha256sum -c M0_GRID_STAGE_SHA256.txt > M0_CODE_CHECK.log
{
 printf '%s  %s\n' b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b "$banks/LP_plus45_bank.npz"
 printf '%s  %s\n' 39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9 "$banks/LP_minus45_bank.npz"
} | sha256sum -c >> M0_INHERITED_CHECK.log
docker_args=(--rm --pull=never --network none --cpus "$workers"
 --user "$(id -u):$(id -g)" --workdir /run/grid_code
 -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=1
 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1
 --mount "type=bind,src=$base,dst=/run"
 --mount "type=bind,src=$inputs,dst=/inputs,readonly"
 --mount "type=bind,src=$banks,dst=/banks,readonly"
 --entrypoint /opt/rt-env/bin/python "$image")
printf '%q ' docker run --name g1-s2p-m0-RUN4_20261113T105130Z "${docker_args[@]}" /run/grid_code/build_m0.py --root /inputs --banks /banks --grid /run/grid --receipt /run/M0_GRID_STAGE_RECEIPT.json --input-check /run/grid_code/INPUTS_CHECK_1ce68f3.json --workers "$workers" > M0_GRID_COMMAND.txt
printf '\n' >> M0_GRID_COMMAND.txt
docker run --name g1-s2p-m0-RUN4_20261113T105130Z "${docker_args[@]}" /run/grid_code/build_m0.py --root /inputs --banks /banks --grid /run/grid --receipt /run/M0_GRID_STAGE_RECEIPT.json --input-check /run/grid_code/INPUTS_CHECK_1ce68f3.json --workers "$workers" > M0_GRID_BUILD.log 2>&1
find grid -maxdepth 1 -type f -name 'S1P_*_M0_*' -print0 | sort -z | xargs -0 sha256sum > M0_GRID_SHA256.txt
date -u +%FT%TZ > M0_FINISH_UTC.txt
