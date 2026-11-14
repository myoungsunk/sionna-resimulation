#!/usr/bin/env bash
set -euo pipefail
cd '/home/KMS/G1_RT_TB3_G8_REVALIDATE_20261114_xUMt2d'
date -u +%FT%TZ > STARTED_UTC.txt
cmd=(docker run --rm --pull=never --network none --name "$(basename "$PWD")" --cpus 2
  --user "$(id -u):$(id -g)" --workdir /ref
  -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/run:/input:/runtime_packages:/ref:/ref/src
  -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1
  -v '/home/KMS/G1_RT_TB3_CORRIDOR_PILOT_20261113T070808Z/input:/input:ro' -v '/home/KMS/G1_RT_TB3_CORRIDOR_PILOT_20261113T070808Z/output:/g1:ro'
  -v '/home/KMS/G1_RT_TB3_G8_REVALIDATE_20261114_xUMt2d:/run' -v '/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source:/ref:ro' -v '/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages:/runtime_packages:ro'
  --entrypoint /opt/rt-env/bin/python 'sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f' -u /run/run_tb3_g8_pilot.py
  --inputs /input --source /ref --out /run/output --legacy-output /g1 --production /run/PRODUCTION_F1.json
  --code-commit d9701160ffc498af7c73a3d02c2600613d82629b --diagnostic-spec-sha 98a32c8129c32eb229505f0cb15b6e2f5624e0637a0f36b0771f231f3b051ac7 --native-direct-revalidation)
printf '%q ' "${cmd[@]}" > COMMAND.txt
printf '\n' >> COMMAND.txt
rc=0
"${cmd[@]}" > run.log 2>&1 || rc=$?
printf '%s\n' "$rc" > EXIT_CODE.txt
date -u +%FT%TZ > FINISHED_UTC.txt
{ find output -type f -print0; printf '%s\0' COMMAND.txt EXIT_CODE.txt STARTED_UTC.txt FINISHED_UTC.txt run.log launch.sh PRODUCTION_F1.json run_tb3_g8_pilot.py tb3_paths_near.py tb3_native_los.py; } | sort -z | xargs -0 sha256sum > SHA256.txt
exit "$rc"
