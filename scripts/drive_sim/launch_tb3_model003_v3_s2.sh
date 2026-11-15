#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test "$(id -un)" = KMS
test "$#" = 2
s1run=$1
plan_commit=$2
[[ $s1run =~ ^/home/KMS/G1_MODEL003_V3_[[:alnum:]]+/s1$ && $plan_commit =~ ^[0-9a-f]{40}$ ]]
[[ $(cat "$s1run/S1_EXIT_CODE.txt") == 0 ]]
test ! -e S2_STARTED_UTC.txt
test "$(cat plan_commit.txt)" = "$plan_commit"
umask 077

origin=/home/KMS/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa/results
regen=/home/KMS/G1_MODEL003_G6_REGEN_okSskppe/results
v2=/home/KMS/G1_MODEL003_S3_QH7zq5Jn
banks=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
model=/home/KMS/RUN2_20261113T072631Z/inputs/results/DRIVE_SIM_20261007/CAUSE_CHECK_A23_EXECUTION_20261010/retrieved/source
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
timeline="$v2/frozen/TIMELINE_PACKETS.csv"
s1="$s1run/output/S1"
plan="$PWD/plan/CHARACTERIZATION_PLAN_003_V3.json"
synthetic="$PWD/plan/SYNTHETIC_V3.json"

check_seal() {
    sha256sum -c <<EOF
4d755c9a016275f2ba51fee02e9908fe8cb2a27f32c187192f00bc957c45ee4a  $origin/seal/SEAL_MANIFEST.json
8f418d4fb6e073c0eb0edd5668d01b625eba11e61fa9d7f1865d2488ef5d9539  $origin/seal/ACCESS_LOG.jsonl
63d535964a68a0ccf74ff7d3eaeff2c02a4f929122532eb05b1526a265187f33  $regen/seal/ACCESS_LOG.jsonl
EOF
}
check_seal > S2_SEAL_BEFORE.txt
mounts=(-v "$origin/CASES.json:/results/CASES.json:ro")
for case in G-T1_A G-T1_B G-T1_C; do
    mounts+=(-v "$origin/H/$case:/results/H/$case:ro" -v "$origin/poses/$case:/results/poses/$case:ro")
done
digest() { sha256sum "$1" | cut -d ' ' -f 1; }
mkdir output
command=(docker run --rm --pull=never --network none --name "$(basename "$PWD")"
    --cpus 8 --user "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1
    -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1
    "${mounts[@]}" -v "$model:/model:ro" -v "$banks:/banks:ro" -v "$PWD/code:/code:ro"
    -v "$PWD/plan:/plan:ro" -v "$PWD/output:/output" -v "$s1:/s1:ro"
    -v "$timeline:/timeline.csv:ro" -v "$s1run/REGRESSION_V3.json:/s0.json:ro"
    --entrypoint /opt/rt-env/bin/python "$image" -u /code/run_tb3_model003_v3_s2.py
    --results-root /results --s0-report /s0.json --s1-dir /s1 --model-source /model --banks-dir /banks
    --plan /plan/CHARACTERIZATION_PLAN_003_V3.json --synthetic-receipt /plan/SYNTHETIC_V3.json --timeline /timeline.csv
    --out /output/S2 --plan-commit "$plan_commit" --plan-sha256 "$(digest "$plan")"
    --s0-sha256 "$(digest "$s1run/REGRESSION_V3.json")" --selection-sha256 "$(digest "$s1/RANGING_RULE_SELECTION_V3.json")"
    --parity-sha256 "$(digest "$s1/PARITY_V3.json")")
printf '%q ' "${command[@]}" > S2_COMMAND.txt
printf '\n' >> S2_COMMAND.txt
date -u +%FT%TZ > S2_STARTED_UTC.txt
rc=0
"${command[@]}" > S2.log 2>&1 || rc=$?
check_seal > S2_SEAL_AFTER.txt || rc=3
date -u +%FT%TZ > S2_FINISHED_UTC.txt
printf '%s\n' "$rc" > S2_EXIT_CODE.txt
exit "$rc"
