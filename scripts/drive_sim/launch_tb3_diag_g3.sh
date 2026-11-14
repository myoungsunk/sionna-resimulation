#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
umask 077
test "$(id -un)" = KMS
run=$(pwd -P)
prod=/home/KMS/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
runtime=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
stage=$1
workers=$(if [[ $stage = plan ]]; then printf 2; else printf '%s' "$2"; fi)
branch=$3
case "$stage" in plan|g3a|g3b|g3c) ;; *) exit 64 ;; esac
case "$workers" in ''|*[!0-9]*) exit 64 ;; esac
cmd=(docker run --rm --pull=never --network none --name "diag_${stage}_$(basename "$run")"
  --cpus "$workers" --cpu-shares 256 --user "$(id -u):$(id -g)" --workdir /ref
  -e HOME=/run/cache -e TMPDIR=/run/scratch -e PYTHONDONTWRITEBYTECODE=1
  -e "DIAG_BRANCH=$branch" -e PYTHONPATH=/run/code:/runtime_packages:/ref:/ref/src
  -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1
  -v "$run:/run" -v "$run/code:/run/code:ro" -v "$ref:/ref:ro" -v "$runtime:/runtime_packages:ro"
  -v "$prod/g0:/production/g0:ro" -v "$prod/g7:/production/g7:ro"
  -v "$prod/config:/production/config:ro" -v "$prod/frozen:/production/frozen:ro"
  -v "$prod/code/run_tb3_g1_pilot.py:/run/code/run_tb3_g1_pilot.py:ro"
  -v "$prod/code/run_tb3_production.py:/run/code/run_tb3_production.py:ro"
  -v "$prod/code/run_tb3_g8_pilot.py:/run/code/run_tb3_g8_pilot.py:ro"
  --entrypoint /usr/bin/nice "$image" -n 15 /opt/rt-env/bin/python -u
  /run/code/run_tb3_diag_g3_batch.py "$stage")
if [[ "$stage" != plan ]]; then cmd+=("$workers"); fi
test ! -e "${stage}_COMMAND.txt"
printf '%q ' "${cmd[@]}" > "${stage}_COMMAND.txt"
printf '\n' >> "${stage}_COMMAND.txt"
rc=0
"${cmd[@]}" > "${stage}.log" 2>&1 || rc=$?
printf '%s\n' "$rc" > "${stage}_EXIT.txt"
exit "$rc"
