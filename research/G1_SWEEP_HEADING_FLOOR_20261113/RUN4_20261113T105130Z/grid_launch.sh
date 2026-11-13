#!/usr/bin/env bash
set -euo pipefail
umask 077
base=/home/KMS/RUN4_20261113T105130Z
run3=/home/KMS/RUN3_20261113T085001Z
inputs=/home/KMS/RUN2_20261113T072631Z/inputs
banks=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
workers=24
cd "$base"
date -u +%FT%TZ > GRID_START_UTC.txt
{
  date -u +%FT%TZ
  uptime
  free -h
  df -h "$base"
  docker info --format 'Docker CPU: {{.NCPU}}'
  docker image inspect "$image" --format '{{.Id}}'
  printf 'workers=%s\n' "$workers"
} > GRID_RESOURCES.txt
printf '%s  %s\n' 5f9732bf406fde2e0f6bb7f80ad3b04979ec4e84c3d4731ed980e7af7a235ef3 "$run3/outputs/MANIFEST.json" | sha256sum -c > GRID_INHERITED_CHECK.log
sha256sum -c GRID_STAGE_SHA256.txt > GRID_CODE_CHECK.log
{
  printf '%s  %s\n' b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b "$banks/LP_plus45_bank.npz"
  printf '%s  %s\n' 39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9 "$banks/LP_minus45_bank.npz"
} | sha256sum -c >> GRID_INHERITED_CHECK.log
test -z "$(find grid -mindepth 1 -maxdepth 1 -type f -print -quit)"
docker_args=(--rm --pull=never --network none --cpus "$workers"
  --user "$(id -u):$(id -g)" --workdir /run/grid_code
  -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=1
  -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1
  --mount "type=bind,src=$base,dst=/run"
  --mount "type=bind,src=$inputs,dst=/inputs,readonly"
  --mount "type=bind,src=$banks,dst=/banks,readonly"
  --mount "type=bind,src=$run3/grid,dst=/prior_grid,readonly"
  --entrypoint /opt/rt-env/bin/python "$image")
printf '%q ' docker run --name g1-s2p-joint-RUN4_20261113T105130Z "${docker_args[@]}" /run/grid_code/build_m1_joint.py --root /inputs --banks /banks --grid /run/grid --prior-grid /prior_grid --receipt /run/GRID_STAGE_RECEIPT.json --input-check /run/grid_code/INPUTS_CHECK_1ce68f3.json --workers "$workers" > GRID_COMMAND.txt
printf '\n' >> GRID_COMMAND.txt
docker run --name g1-s2p-joint-RUN4_20261113T105130Z "${docker_args[@]}" /run/grid_code/build_m1_joint.py --root /inputs --banks /banks --grid /run/grid --prior-grid /prior_grid --receipt /run/GRID_STAGE_RECEIPT.json --input-check /run/grid_code/INPUTS_CHECK_1ce68f3.json --workers "$workers" > GRID_BUILD.log 2>&1
find grid -maxdepth 1 -type f -print0 | sort -z | xargs -0 sha256sum > GRID_SHA256.txt
date -u +%FT%TZ > GRID_FINISH_UTC.txt
