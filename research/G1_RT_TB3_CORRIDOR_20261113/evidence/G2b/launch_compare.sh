#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
run="$(pwd -P)"
trace="$1"
g2=/home/KMS/G1_RT_TB3_CORRIDOR_G2_20261113T073116Z
g3c=/home/KMS/G1_RT_TB3_G3C_20261114T073923Z_hfLYcu
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
rt=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
date -u +%FT%TZ > STARTED_UTC.txt
cmd=(docker run --rm --pull=never --network none --name "$(basename "$run")" --cpus 1
     --user "$(id -u):$(id -g)" --workdir /ref
     -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/input:/trace-run:/runtime_packages:/ref:/ref/src
     -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1
     -v "$g2/input:/input:ro" -v "$g3c:/g3c:ro" -v "$trace:/trace-run:ro"
     -v "$run:/evaluation" -v "$ref:/ref:ro" -v "$rt:/runtime_packages:ro"
     --entrypoint /opt/rt-env/bin/python "$image" -u /evaluation/compare_g2b.py)
printf '%q ' "${cmd[@]}" > COMMAND.txt
printf '\n' >> COMMAND.txt
rc=0
"${cmd[@]}" > run.log 2>&1 || rc=$?
printf '%s\n' "$rc" > EXIT_CODE.txt
date -u +%FT%TZ > FINISHED_UTC.txt
find . -type f ! -name SHA256.txt -print0 | sort -z | xargs -0 sha256sum > SHA256.txt
exit "$rc"
