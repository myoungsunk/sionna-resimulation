#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
run="$(pwd -P)"
base=/home/KMS/G1_RT_TB3_CORRIDOR_G3_20261113T073918Z
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
rt=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
baseline=/home/KMS/G1_RT_TB3_G3A_20261114T065509Z_qJRtuw
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
cores=72
date -u +%FT%TZ > STARTED_UTC.txt
cmd=(docker run --rm --pull=never --network none --name "$(basename "$run")" --cpus "$cores"
     --cpu-shares 256 --user "$(id -u):$(id -g)" --workdir /ref
     -v "$base:/g3:ro" -v "$ref:/ref:ro" -v "$rt:/runtime_packages:ro" -v "$baseline:/g3a:ro" -v "$run:/run_g3c"
     -e PYTHONPATH=/g3a:/g3/input:/runtime_packages:/ref/src -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1
     -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1
     --entrypoint /bin/bash "$image" -c '
set -euo pipefail
root=/run_g3c
py=/opt/rt-env/bin/python
mkdir -p "$root/logs"
"$py" "$root/run_g3c_trace.py" preflight "$1" > "$root/jobs.txt"
date -u +%FT%TZ > "$root/TRACE_START_UTC.txt"
start=$SECONDS
xargs -r -n 2 -P "$1" bash -c '"'"'
  export HOME="/tmp/g3c_$1_$2"
  mkdir -p "$HOME"
  nice -n 5 /opt/rt-env/bin/python -u /run_g3c/run_g3c_trace.py trace "$1" "$2" >"/run_g3c/logs/$1_$2.log" 2>&1
'"'"' _ < "$root/jobs.txt"
printf "%s\n" "$((SECONDS-start))" > "$root/TRACE_WALL_S.txt"
date -u +%FT%TZ > "$root/TRACE_FINISH_UTC.txt"
' _ "$cores")
printf '%q ' "${cmd[@]}" > TRACE_COMMAND.txt
printf '\n' >> TRACE_COMMAND.txt
rc=0
"${cmd[@]}" > trace.log 2>&1 || rc=$?
if [[ -d raw ]]; then
  find raw -type f -print0 | sort -z | xargs -0 -r sha256sum > RAW_SHA256.txt
fi
printf '%s\n' "$rc" > TRACE_EXIT_CODE.txt
exit "$rc"
