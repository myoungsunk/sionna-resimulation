#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
run="$(pwd -P)"
base=/home/KMS/G1_RT_TB3_CORRIDOR_G3_20261113T073918Z
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
rt=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
baseline=/home/KMS/G1_RT_TB3_G3A_20261114T065509Z_qJRtuw
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
date -u +%FT%TZ > EVALUATION_START_UTC.txt
cmd=(docker run --rm --pull=never --network none --name "$(basename "$run")_eval" --cpus 9
     --cpu-shares 256 --user "$(id -u):$(id -g)" --workdir /ref
     -v "$base:/g3:ro" -v "$ref:/ref:ro" -v "$rt:/runtime_packages:ro" -v "$baseline:/g3a:ro" -v "$run:/run_g3c"
     -e PYTHONPATH=/g3a:/run_g3c:/g3/input:/runtime_packages:/ref/src -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1
     -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1
     --entrypoint /bin/bash "$image" -c '
set -euo pipefail
root=/run_g3c
py=/opt/rt-env/bin/python
for ((i=0; i<240; i++)); do
  test ! -s "$root/TRACE_EXIT_CODE.txt" || break
  sleep 5
done
"$py" "$root/run_g3c_evaluation.py" preflight > "$root/evaluation_jobs.txt"
xargs -r -n 1 -P 9 bash -c '"'"'
  nice -n 5 /opt/rt-env/bin/python -u /run_g3c/run_g3c_evaluation.py case "$1" >"/run_g3c/logs/eval_$1.log" 2>&1
'"'"' _ < "$root/evaluation_jobs.txt"
"$py" "$root/run_g3c_evaluation.py" summarize
')
printf '%q ' "${cmd[@]}" > EVALUATION_COMMAND.txt
printf '\n' >> EVALUATION_COMMAND.txt
rc=0
"${cmd[@]}" > evaluation.log 2>&1 || rc=$?
date -u +%FT%TZ > FINISHED_UTC.txt
printf '%s\n' "$rc" > EXIT_CODE.txt
if [[ -d analysis ]]; then
  find analysis -type f -print0 | sort -z | xargs -0 -r sha256sum > ANALYSIS_SHA256.txt
fi
find . -maxdepth 1 -type f ! -name SHA256.txt ! -name 'nohup*' -print0 | sort -z | xargs -0 sha256sum > SHA256.txt
exit "$rc"
