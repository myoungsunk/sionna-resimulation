#!/usr/bin/env bash
set -euo pipefail
umask 077
base=/home/KMS/RUN3_20261113T085001Z
prior=/home/KMS/RUN2_20261113T072631Z
banks=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
workers=6
cd "$base"
docker_args=(--rm --pull=never --network none --cpus "$workers"
  --user "$(id -u):$(id -g)" --workdir /run/code
  -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=1
  -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1
  --mount "type=bind,src=$base,dst=/run"
  --mount "type=bind,src=$prior/inputs,dst=/inputs,readonly"
  --mount "type=bind,src=$banks,dst=/banks,readonly"
  --entrypoint /opt/rt-env/bin/python "$image")
phase() {
  local label="$1" rc
  shift
  date -u +%FT%TZ > "outputs/START_${label}_UTC.txt"
  printf '%q ' docker run --name "g1-v33-${base##*RUN3_}-$label" "${docker_args[@]}" "$@" > "outputs/COMMAND_$label.txt"
  printf '\n' >> "outputs/COMMAND_$label.txt"
  if docker run --name "g1-v33-${base##*RUN3_}-$label" "${docker_args[@]}" "$@" > "outputs/$label.log" 2>&1; then
    rc=0
  else
    rc=$?
  fi
  date -u +%FT%TZ > "outputs/FINISH_${label}_UTC.txt"
  printf '%s\n' "$rc" > "outputs/EXIT_$label.txt"
  return "$rc"
}
test "$(cat outputs/EXIT_verify.txt)" = 0
args=(--inputs /inputs --banks /banks --out /run/outputs --workers "$workers")
phase bias /run/code/v33_bias.py "${args[@]}"
