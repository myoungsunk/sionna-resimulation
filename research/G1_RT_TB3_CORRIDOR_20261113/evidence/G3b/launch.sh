#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
run="$(pwd -P)"
base=/home/KMS/G1_RT_TB3_CORRIDOR_G3_20261113T073918Z
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
rt=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
g3a=/home/KMS/G1_RT_TB3_G3A_20261114T065509Z_qJRtuw
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
cores=32
date -u +%FT%TZ > STARTED_UTC.txt
cmd=(docker run --rm --pull=never --network none --name "$(basename "$run")" --cpus "$cores"
     --cpu-shares 256 --user "$(id -u):$(id -g)" --workdir /ref
     -v "$base:/g3:ro" -v "$ref:/ref:ro" -v "$rt:/runtime_packages:ro" -v "$g3a:/g3a:ro" -v "$run:/run_g3b"
     -e PYTHONPATH=/run_g3b:/g3/input:/runtime_packages:/ref/src -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1
     -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1
     --entrypoint /bin/bash "$image" -c '
set -euo pipefail
root=/run_g3b
py=/opt/rt-env/bin/python
mkdir -p "$root/logs"
"$py" "$root/run_g3b.py" preflight > "$root/jobs.txt"
date -u +%FT%TZ > "$root/TRACE_START_UTC.txt"
start=$SECONDS
xargs -r -n 2 -P "$1" bash -c '"'"'
  export HOME="/tmp/g3b_$1_${2%/*}"
  mkdir -p "$HOME"
  nice -n 5 /opt/rt-env/bin/python -u /run_g3b/run_g3b.py trace "$1" "$2" >"/run_g3b/logs/$1_${2%/*}.log" 2>&1
'"'"' _ < "$root/jobs.txt"
printf "%s\n" "$((SECONDS-start))" > "$root/TRACE_WALL_S.txt"
date -u +%FT%TZ > "$root/TRACE_FINISH_UTC.txt"
"$py" "$root/run_g3b.py" evaluate
' _ "$cores")
printf '%q ' "${cmd[@]}" > COMMAND.txt
printf '\n' >> COMMAND.txt
rc=0
"${cmd[@]}" > run.log 2>&1 || rc=$?
printf '%s\n' "$rc" > EXIT_CODE.txt
date -u +%FT%TZ > FINISHED_UTC.txt
if [[ -d output ]]; then
  find output -type f -print0 | sort -z | xargs -0 -r sha256sum > OUTPUT_SHA256.txt
fi
find . -maxdepth 1 -type f ! -name SHA256.txt ! -name nohup.log -print0 | sort -z | xargs -0 sha256sum > SHA256.txt
exit "$rc"
