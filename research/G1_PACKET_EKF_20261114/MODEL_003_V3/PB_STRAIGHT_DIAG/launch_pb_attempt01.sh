#!/usr/bin/env bash
set -euo pipefail
umask 077
test "$(id -un)" = KMS
cd -- "$(dirname "$0")"
run=$PWD
job=/home/KMS/G1_MODEL003_V3_S3_xoTFSqB8
origin=/home/KMS/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa/results
regen=/home/KMS/G1_MODEL003_G6_REGEN_okSskppe/results
v2=/home/KMS/G1_MODEL003_S3_QH7zq5Jn
banks=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
model=/home/KMS/RUN2_20261113T072631Z/inputs/results/DRIVE_SIM_20261007/CAUSE_CHECK_A23_EXECUTION_20261010/retrieved/source
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
test ! -e STARTED_UTC
mkdir capture
date -u +%FT%TZ > STARTED_UTC
finish() {
    rc=$?
    trap - EXIT
    date -u +%FT%TZ > FINISHED_UTC
    printf '%s\n' "$rc" > EXIT_CODE
    exit "$rc"
}
trap finish EXIT
check_seal() {
    sha256sum -c <<EOF
4d755c9a016275f2ba51fee02e9908fe8cb2a27f32c187192f00bc957c45ee4a  $origin/seal/SEAL_MANIFEST.json
8f418d4fb6e073c0eb0edd5668d01b625eba11e61fa9d7f1865d2488ef5d9539  $origin/seal/ACCESS_LOG.jsonl
63d535964a68a0ccf74ff7d3eaeff2c02a4f929122532eb05b1526a265187f33  $regen/seal/ACCESS_LOG.jsonl
EOF
}
check_seal > SEAL_BEFORE.log
sha256sum -c <<EOF > INPUT_CHECK.log
32a67a150f43f4cb31d103c1af52a3bc39f0c7e8797e9f97c29876893a19a5a3  $job/code.tar
02fdc559df446f638405becbc6365597a19fdc302a159a0cf0d64fd615f7fcf7  $job/output/RANGE_STAGE.json
EOF
sha256sum pb_trace.py PLAN.md launch_pb.sh >> INPUT_CHECK.log
mounts=(-v "$origin/CASES.json:/results/CASES.json:ro")
for case in G-T1_A G-T1_B G-T1_C; do
    mounts+=(-v "$origin/H/$case:/results/H/$case:ro" -v "$origin/poses/$case:/results/poses/$case:ro")
done
cmd=(docker run --rm --pull=never --network none --cpus 8 --name "$(basename "$run")"
     --user "$(id -u):$(id -g)" -e HOME=/tmp -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1
     -e MKL_NUM_THREADS=1 -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/code
     "${mounts[@]}" -v "$model:/model:ro" -v "$banks:/banks:ro" -v "$job/code:/code:ro"
     -v "$job/frozen:/frozen:ro" -v "$v2/frozen/TIMELINE_PACKETS.csv:/frozen/TIMELINE_PACKETS.csv:ro"
     -v "$job/output:/output:ro" -v "$run/pb_trace.py:/diagnostic/pb_trace.py:ro"
     -v "$run/capture:/capture" --entrypoint /bin/bash "$image" -s)
printf '%q ' "${cmd[@]}" > COMMAND.txt
printf '\n' >> COMMAND.txt
cat > container_input.sh <<'EOF'
set -euo pipefail
for case in G-T1_A G-T1_B G-T1_C; do
    for level in B0 TB3_r2.1.0; do
        for arm in S-V S-C; do
            printf '%s\n' "--case $case --level $level --arm $arm"
        done
    done
done | xargs -n 6 -P 8 /opt/rt-env/bin/python -B -u /diagnostic/pb_trace.py \
  --frozen /frozen --manifest /frozen/INPUT_MANIFEST.json --range-stage /output/RANGE_STAGE.json \
  --results-root /results --model-source /model --banks-dir /banks --out /output --capture-dir /capture \
  --range-stage-sha256 02fdc559df446f638405becbc6365597a19fdc302a159a0cf0d64fd615f7fcf7
EOF
rc=0
"${cmd[@]}" < container_input.sh > execution.log 2>&1 || rc=$?
check_seal > SEAL_AFTER.log
if [[ "$rc" == 0 ]]; then
    [[ "$(find capture -name '*.npz' -type f | wc -l)" == 12 ]]
    sha256sum capture/* > CAPTURE_SHA256SUMS
fi
exit "$rc"
