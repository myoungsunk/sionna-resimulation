#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
umask 077
run=$(pwd -P)
test "$(id -un)" = KMS
test "$#" = 2
s0_sha=$1
origin_sha=$2
for digest in "$s0_sha" "$origin_sha"; do
  [[ $digest =~ ^[[:xdigit:]]{64}$ ]]
done
commit=$(cat code_commit.txt)
[[ $commit =~ ^[[:xdigit:]]{40}$ ]]
test -f REGRESSION_V3.json
test -f DELAY_ORIGIN.json
test ! -e S1_STARTED_UTC.txt
original=/home/KMS/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa/results
regen=/home/KMS/G1_MODEL003_G6_REGEN_okSskppe/results
banks=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
model=/home/KMS/RUN2_20261113T072631Z/inputs/results/DRIVE_SIM_20261007/CAUSE_CHECK_A23_EXECUTION_20261010/retrieved/source
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f

verify_seal() {
  local name=$1
  sha256sum -c > "S1_SEAL_${name}.txt" <<EOF
4d755c9a016275f2ba51fee02e9908fe8cb2a27f32c187192f00bc957c45ee4a  $original/seal/SEAL_MANIFEST.json
8f418d4fb6e073c0eb0edd5668d01b625eba11e61fa9d7f1865d2488ef5d9539  $original/seal/ACCESS_LOG.jsonl
63d535964a68a0ccf74ff7d3eaeff2c02a4f929122532eb05b1526a265187f33  $regen/seal/ACCESS_LOG.jsonl
EOF
}
verify_seal BEFORE

mounts=(-v "$original/CASES.json:/results/CASES.json:ro")
for case in G-T1_A G-T1_B G-T1_C; do
  mounts+=(-v "$original/H/$case:/results/H/$case:ro")
  mounts+=(-v "$original/poses/$case:/results/poses/$case:ro")
done
mkdir "$run/output"
cmd=(docker run --rm --pull=never --network none
  --name "$(basename "$run")" --cpus 6 --user "$(id -u):$(id -g)"
  -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=1
  -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1
  "${mounts[@]}" -v "$run/code:/code:ro" -v "$run/output:/output"
  -v "$run/REGRESSION_V3.json:/s0.json:ro" -v "$run/DELAY_ORIGIN.json:/origin.json:ro"
  -v "$model:/model:ro" -v "$banks:/banks:ro"
  --entrypoint /opt/rt-env/bin/python "$image" -u /code/run_tb3_model003_v3_s1.py
  --results-root /results --model-source /model --banks-dir /banks
  --s0-report /s0.json --s0-sha256 "$s0_sha" --delay-origin /origin.json
  --delay-origin-sha256 "$origin_sha" --code-commit "$commit" --out /output/S1)
printf '%q ' "${cmd[@]}" > S1_COMMAND.txt
printf '\n' >> S1_COMMAND.txt
date -u +%FT%TZ > S1_STARTED_UTC.txt
rc=0
"${cmd[@]}" > S1.log 2>&1 || rc=$?
verify_seal AFTER || rc=3
date -u +%FT%TZ > S1_FINISHED_UTC.txt
printf '%s\n' "$rc" > S1_EXIT_CODE.txt
exit "$rc"
