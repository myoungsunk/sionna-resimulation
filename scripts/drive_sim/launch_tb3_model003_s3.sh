#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")"
run=$(pwd -P)
if [[ ${1-} == container ]]; then
  mode=$2
  export PYTHONPATH=/code
  common=(--results-root /results --model-source /model --banks-dir /banks)
  inputs=(timeline s2 selection parity)
  files=(TIMELINE_PACKETS.csv CHARACTERIZATION_003.json RANGING_RULE_SELECTION.json PARITY.json)
  for index in "${!inputs[@]}"; do
    file=/frozen/${files[$index]}
    digest=$(sha256sum "$file")
    common+=("--${inputs[$index]}" "$file" "--${inputs[$index]}-sha256" "${digest%% *}")
  done
  function run_fold() {
    local case="$1" path="$2" level="$3" arm="$4" snr="$5"
    local leaf="${snr}/${case}_${path}_${level}_${arm}"
    local dr="${snr}/${case}_${path}_${level}_DR"
    local extra=()
    [[ "$arm" == DR ]] || extra=(--dr "/output/folds/$dr.json")
    /opt/rt-env/bin/python -B -u /code/run_tb3_model003_s3.py \
      --case "$case" --path "$path" --level "$level" --arm "$arm" --snr "$snr" \
      --out "/output/folds/$leaf.json" "${common[@]}" "${extra[@]}" > "/output/logs/$leaf.log" 2>&1
  }
  cases=(G-T1_A G-T1_B G-T1_C)
  paths=(TEACH_REPEAT P-B C1 C2 C3 C4)
  levels=(B0 L0 L1 L2 TB3_r1.3.1 TB3_r2.1.0)
  arms=(R4 J4 J-V J-C J-CS J-CI J4+K J-V+K J-C+K J-CS+K J-CI+K)
  mkdir -p /output/{folds,logs}/{30,20}
  for snr in 30 20; do
    for level in "${levels[@]}"; do
      for arm in DR "${arms[@]}"; do
      for path in "${paths[@]}"; do
          for case in "${cases[@]}"; do
            printf '%s\n' "$case $path $level $arm $snr"
          done
      done
      done
    done > "/output/jobs_$snr.txt"
  done
  # RF children consume the matched receipts from the completed DR wave.
  export -f run_fold
  printf '%q ' "${common[@]}" > /output/common_args.txt
  for snr in 30 20; do
    if [[ "$mode" == baseline ]]; then
      for arm in DR R4; do
        awk -v arm="$arm" '$4==arm' "/output/jobs_$snr.txt" |
          xargs -P 36 -n 5 bash -c 'eval "common=($(cat /output/common_args.txt))"; run_fold "$@"' _
      done
    else
      awk '$4!="DR" && $4!="R4"' "/output/jobs_$snr.txt" |
        xargs -P 54 -n 5 bash -c 'eval "common=($(cat /output/common_args.txt))"; run_fold "$@"' _
    fi
  done
  exit
fi
test "$(id -un)" = KMS
mode=$1
case "$mode" in
  baseline) start=S3_BASELINE ;;
  joint) start=S3_JOINT; test "$(cat S3_BASELINE_EXIT_CODE.txt)" = 0 ;;
  *) exit 2 ;;
esac
test ! -e "${start}_STARTED_UTC.txt"
original=/home/KMS/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa/results
banks=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
model=/home/KMS/RUN2_20261113T072631Z/inputs/results/DRIVE_SIM_20261007/CAUSE_CHECK_A23_EXECUTION_20261010/retrieved/source
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
mounts=(-v "$original/CASES.json:/results/CASES.json:ro")
for case in G-T1_A G-T1_B G-T1_C; do
  mounts+=(-v "$original/H/$case:/results/H/$case:ro")
  mounts+=(-v "$original/poses/$case:/results/poses/$case:ro")
done
mkdir -p output
cmd=(docker run --rm --pull=never --network none
  --name "$(basename "$run")" --cpus 54 --user "$(id -u):$(id -g)"
  -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=1
  -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1
  "${mounts[@]}" -v "$run/code:/code:ro" -v "$run/output:/output" -v "$run/frozen:/frozen:ro"
  -v "$model:/model:ro" -v "$banks:/banks:ro"
  --entrypoint /bin/bash "$image" /code/launch_tb3_model003_s3.sh container "$mode")
printf '%q ' "${cmd[@]}" > "${start}_COMMAND.txt"
printf '\n' >> "${start}_COMMAND.txt"
date -u +%FT%TZ > "${start}_STARTED_UTC.txt"
rc=0
"${cmd[@]}" > "$start.log" 2>&1 || rc=$?
date -u +%FT%TZ > "${start}_FINISHED_UTC.txt"
printf '%s\n' "$rc" > "${start}_EXIT_CODE.txt"
exit "$rc"
