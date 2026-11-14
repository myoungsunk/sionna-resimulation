#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")"
run=$(pwd -P)
test "$(id -un)" = KMS
test "$(cat S3_BASELINE_EXIT_CODE.txt)" = 0
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f

wait_b0() {
  while [[ ! -s S3_JOINT_B0_EXIT_CODE.txt ]]; do
    if ! docker inspect --format '{{.State.Running}}' "$(basename "$run")" 2>/dev/null | grep -qx true; then
      sleep 3
      test -s S3_JOINT_B0_EXIT_CODE.txt
    else
      sleep 15
    fi
  done
  test "$(cat S3_JOINT_B0_EXIT_CODE.txt)" = 0
}

summarize() {
  local outfile=$1
  shift
  docker run --rm --pull=never --network none --cpus 2 --user "$(id -u):$(id -g)" \
    -e HOME=/tmp -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1 \
    -v "$run/code_gate:/code:ro" -v "$run/output:/output" -v "$run/frozen:/frozen:ro" \
    --entrypoint /opt/rt-env/bin/python "$image" -B /code/summarize_tb3_model003_s3.py \
    --folds /output/folds --logs /output/logs --futility /frozen/FUTILITY.json --out "/output/$outfile" "$@"
}

wait_b0
test ! -e output/B0_STATUS.json
summarize B0_STATUS.json --partial > S3_B0_SUMMARY.log 2>&1
if python3 -c 'import json,sys; sys.exit(not json.load(open("output/B0_STATUS.json"))["early_b0"]["all_candidates_ineligible"])'; then
  summarize LOAO_RESULTS.json --stop-after-b0 > S3_FINAL_SUMMARY.log 2>&1
else
  bash launch_joint.sh joint
  summarize LOAO_RESULTS.json > S3_FINAL_SUMMARY.log 2>&1
  summarize SENSITIVITY_20DB.json --snr 20 > S3_SENSITIVITY.log 2>&1
fi
test -s output/LOAO_RESULTS.json
date -u +%FT%TZ > S3_GATE_FINISHED_UTC.txt
