#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
umask 077
run=$PWD
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
legacy=/home/KMS/G1_RT_TB3_CORRIDOR_PILOT_20261113T070808Z/output
runtime=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
test "$(id -un)" = KMS
test ! -e CANARY_START_UTC.txt
date -u +%FT%TZ > CANARY_START_UTC.txt
cmd=(docker run --rm --pull=never --network none --name "canary_$(basename "$run")"
  --cpus 1 --cpu-shares 64 --user "$(id -u):$(id -g)" --workdir /ref
  -e HOME=/run/cache -e TMPDIR=/run/scratch -e PYTHONDONTWRITEBYTECODE=1
  -e PYTHONPATH=/run/code:/runtime_packages:/ref:/ref/src
  -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1
  -v "$run:/run" -v "$ref:/ref:ro" -v "$runtime:/runtime_packages:ro" -v "$legacy:/legacy:ro"
  --entrypoint /usr/bin/nice "$image" -n 18 /bin/bash -ec '
py=/opt/rt-env/bin/python
"$py" -u /run/code/mount45_reference.py /run /ref /legacy
"$py" -u /run/code/run_tb3_production.py \
  --inputs /run/g0 --g7 /run/g7 --source /ref --production /run/config/PRODUCTION_F1.json \
  --reference /run/frozen/REFERENCE.json --ffd-manifest /run/frozen/FFD_RESTORE_MANIFEST.json \
  --case G-T1_A --g8-canary /legacy --canary-los-reference /run/los_reference \
  --code-commit 6242fb99f67df17c4b686eca14380ebd471491b6 --out /run/canary01
')
printf '%q ' "${cmd[@]}" > CANARY_COMMAND.txt
printf '\n' >> CANARY_COMMAND.txt
rc=0
"${cmd[@]}" > logs/canary.log 2>&1 || rc=$?
date -u +%FT%TZ > CANARY_FINISH_UTC.txt
printf '%s\n' "$rc" > CANARY_EXIT.txt
exit "$rc"
