#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
run="$(pwd -P)"
base=/home/KMS/G1_RT_TB3_CORRIDOR_G3_20261113T073918Z
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
rt=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
cores="$1"
date -u +%FT%TZ > STARTED_UTC.txt
cmd=(docker run --rm --pull=never --network none --name "$(basename "$run")" --cpus "$cores"
     --cpu-shares 256 --user "$(id -u):$(id -g)" --workdir /ref
     -v "$base:/g3:ro" -v "$ref:/ref:ro" -v "$rt:/runtime_packages:ro" -v "$run:/run_g3a"
     -e PYTHONPATH=/g3/input:/runtime_packages:/ref/src -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1
     -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1
     --entrypoint /bin/bash "$image" -c '
set -euo pipefail
root=/run_g3a
py=/opt/rt-env/bin/python
mkdir -p "$root/logs"
"$py" "$root/run_g3a.py" preflight > "$root/jobs.txt"
date -u +%FT%TZ > "$root/TRACE_START_UTC.txt"
start=$SECONDS
export G3A_PY="$py"
xargs -r -n 2 -P "$1" bash -c '"'"'
  export HOME="/tmp/g3a_$1_$2"
  mkdir -p "$HOME"
  nice -n 5 "$G3A_PY" -u /run_g3a/run_g3a.py trace "$1" "$2" >"/run_g3a/logs/$1_$2.log" 2>&1
'"'"' _ < "$root/jobs.txt"
printf "%s\n" "$((SECONDS-start))" > "$root/TRACE_WALL_S.txt"
date -u +%FT%TZ > "$root/TRACE_FINISH_UTC.txt"
"$py" "$root/run_g3a.py" evaluate
' _ "$cores")
printf '%q ' "${cmd[@]}" > COMMAND.txt
printf '\n' >> COMMAND.txt
rc=0
"${cmd[@]}" > run.log 2>&1 || rc=$?
printf '%s\n' "$rc" > EXIT_CODE.txt
date -u +%FT%TZ > FINISHED_UTC.txt
if [[ -d raw ]]; then
  find raw -type f -print0 | sort -z | xargs -0 -r sha256sum > RAW_SHA256.txt
fi
find . -maxdepth 1 -type f ! -name SHA256.txt -print0 | sort -z | xargs -0 sha256sum > SHA256.txt
exit "$rc"
