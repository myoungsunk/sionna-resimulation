#!/usr/bin/env bash
set -euo pipefail
umask 077
base=/home/KMS/RUN3_20261113T085001Z
prior=/home/KMS/RUN2_20261113T072631Z
banks=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
workers=12
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
sha256sum -c code/INHERITED_SHA256.txt > outputs/INHERITED_CHECK.log
for item in LP_plus45_bank LP_minus45_bank; do
  test -f "$banks/$item.npz"
done
{
  printf '%s  %s\n' b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b "$banks/LP_plus45_bank.npz"
  printf '%s  %s\n' 39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9 "$banks/LP_minus45_bank.npz"
} | sha256sum -c >> outputs/INHERITED_CHECK.log
phase verify -c 'from pathlib import Path; from run_step1 import verify; import platform,sys,numpy,scipy; verify(Path("/inputs"), Path("/run/code/INPUTS_CHECK_1ce68f3.json")); print(sys.version); print(numpy.__version__,scipy.__version__); print(platform.platform()); print("Frozen input hashes passed")'
args=(--inputs /inputs --banks /banks --out /run/outputs --grid /run/grid --workers "$workers")
phase prep /run/code/v33_run.py prep "${args[@]}"
phase e2e /run/code/v33_run.py e2e "${args[@]}"
