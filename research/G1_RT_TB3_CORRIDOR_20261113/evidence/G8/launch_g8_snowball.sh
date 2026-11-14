#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
run="$(pwd -P)"
pilot=/home/KMS/G1_RT_TB3_CORRIDOR_PILOT_20261113T070808Z
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
rt=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
date -u +%FT%TZ > STARTED_UTC.txt
cmd=(docker run --rm --pull=never --network none --name "$(basename "$run")" --cpus 2
     --user "$(id -u):$(id -g)" --workdir /ref
     -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/input:/runtime_packages:/ref:/ref/src
     -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1
     -v "$pilot/input:/input:ro" -v "$pilot/output:/g1_out:ro" -v "$run:/run_g8"
     -v "$ref:/ref:ro" -v "$rt:/runtime_packages:ro"
     --entrypoint /opt/rt-env/bin/python "$image" -u /run_g8/run_tb3_g8_pilot.py
     --inputs /input --source /ref --out /run_g8/output --legacy-output /g1_out
     --production /run_g8/PRODUCTION_F1.json --code-commit "$1" --diagnostic-spec-sha "$2")
printf '%q ' "${cmd[@]}" > COMMAND.txt
printf '\n' >> COMMAND.txt
rc=0
"${cmd[@]}" > run.log 2>&1 || rc=$?
date -u +%FT%TZ > FINISHED_UTC.txt
printf '%s\n' "$rc" > EXIT_CODE.txt
find . -type f ! -name SHA256.txt ! -name nohup.log -print0 | sort -z | xargs -0 sha256sum > SHA256.txt
exit "$rc"
