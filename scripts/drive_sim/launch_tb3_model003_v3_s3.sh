#!/usr/bin/env bash
set -euo pipefail
test "$(id -un)" = KMS
cd "$(dirname "$0")/.."
umask 077
phase=${1:-range}
[[ $phase == range || $phase == joint ]]
test ! -e "S3_${phase}_STARTED_UTC.txt"
origin=/home/KMS/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa/results
regen=/home/KMS/G1_MODEL003_G6_REGEN_okSskppe/results
v2=/home/KMS/G1_MODEL003_S3_QH7zq5Jn
banks=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
model=/home/KMS/RUN2_20261113T072631Z/inputs/results/DRIVE_SIM_20261007/CAUSE_CHECK_A23_EXECUTION_20261010/retrieved/source
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
export phase

check_seal() {
    sha256sum -c <<EOF
4d755c9a016275f2ba51fee02e9908fe8cb2a27f32c187192f00bc957c45ee4a  $origin/seal/SEAL_MANIFEST.json
8f418d4fb6e073c0eb0edd5668d01b625eba11e61fa9d7f1865d2488ef5d9539  $origin/seal/ACCESS_LOG.jsonl
63d535964a68a0ccf74ff7d3eaeff2c02a4f929122532eb05b1526a265187f33  $regen/seal/ACCESS_LOG.jsonl
EOF
}
check_seal
mounts=(-v "$origin/CASES.json:/results/CASES.json:ro")
for case in G-T1_A G-T1_B G-T1_C; do
    mounts+=(-v "$origin/H/$case:/results/H/$case:ro" -v "$origin/poses/$case:/results/poses/$case:ro")
done

if [[ $phase == joint ]]; then
    [[ $(cat S3_range_EXIT_CODE.txt) == 0 ]]
    test -f output/RANGE_STAGE.json
fi
mkdir -p output
cmd=(docker run --rm --pull=never --network none --name "$(basename "$PWD")-$phase" --cpus 72
    --user "$(id -u):$(id -g)" -e HOME=/tmp -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1
    -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/code -e phase="$phase"
    "${mounts[@]}" -v "$model:/model:ro" -v "$banks:/banks:ro" -v "$PWD/code:/code:ro"
    -v "$PWD/frozen:/frozen:ro" -v "$v2/frozen/TIMELINE_PACKETS.csv:/frozen/TIMELINE_PACKETS.csv:ro"
    -v "$PWD/output:/output" --entrypoint /bin/bash "$image" /code/run_tb3_model003_v3_s3_container.sh)
printf '%q ' "${cmd[@]}" > "S3_${phase}_COMMAND.txt"
printf '\n' >> "S3_${phase}_COMMAND.txt"
date -u +%FT%TZ > "S3_${phase}_STARTED_UTC.txt"
rc=0
"${cmd[@]}" > "S3_$phase.log" 2>&1 || rc=$?
check_seal > "S3_${phase}_SEAL_AFTER.txt" || rc=3
date -u +%FT%TZ > "S3_${phase}_FINISHED_UTC.txt"
printf '%s\n' "$rc" > "S3_${phase}_EXIT_CODE.txt"
exit "$rc"
