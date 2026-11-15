#!/usr/bin/env bash
set -euo pipefail
if [[ ${1-} == container ]]; then
    export PYTHONPATH=/v3:/v2_r4
    python=/opt/rt-env/bin/python
    runner=/v3/run_tb3_model003_v3_s0.py
    "$python" -B "$runner" checks
    if [[ ${2-} == checks ]]; then
        exit
    fi
    "$python" -B -c 'import run_tb3_model003_s3 as m; [print(c,p,a) for c in m.CASES for p in m.PATHS for a in ("R4","J4")]' |
        xargs -n 3 -P 36 bash -c '
            export PYTHONPATH=/v3:/v2_r4
            if [[ $3 == J4 ]]; then export PYTHONPATH=/v3:/v2_j4; fi
            /opt/rt-env/bin/python -B -u /v3/run_tb3_model003_v3_s0.py fold "$@"
        ' regression
    "$python" -B "$runner" close
    exit
fi

cd "$(dirname "$0")/.."
test "$(id -un)" = KMS
mode=${1:-full}
[[ $mode == full || $mode == checks ]]
old=/home/KMS/G1_MODEL003_S3_QH7zq5Jn
origin=/home/KMS/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa/results
regen=/home/KMS/G1_MODEL003_G6_REGEN_okSskppe/results
model=/home/KMS/RUN2_20261113T072631Z/inputs/results/DRIVE_SIM_20261007/CAUSE_CHECK_A23_EXECUTION_20261010/retrieved/source
banks=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f

printf '%s\n' \
    "4d591aa6b0bd2955b3e61cbda8fcba8eab8aafe431caed1a94f3c7c85f3d4cfd  $old/frozen/TIMELINE_PACKETS.csv" \
    "27e55af01e63d677ebd06b123b5e3316adbe45a5710278d2645313cdff1b6d71  $old/output/LOAO_RESULTS.json" \
    "b48d664ab41d780ea2e255c06e980db055d977bfaf4cd2e8ce851685a8b189e1  $old/code/run_tb3_model003_s3.py" \
    "4c5d260c4af2fb4418c6aef51ab7935dd79356b8e9bb7e352924306e7aac5426  $old/code_joint/run_tb3_model003_s3.py" \
    "4d755c9a016275f2ba51fee02e9908fe8cb2a27f32c187192f00bc957c45ee4a  $origin/seal/SEAL_MANIFEST.json" \
    "8f418d4fb6e073c0eb0edd5668d01b625eba11e61fa9d7f1865d2488ef5d9539  $origin/seal/ACCESS_LOG.jsonl" \
    "63d535964a68a0ccf74ff7d3eaeff2c02a4f929122532eb05b1526a265187f33  $regen/seal/ACCESS_LOG.jsonl" |
    sha256sum -c
cat v3_commit.txt
sha256sum code/*.py code/*.sh provenance/*

mounts=(-v "$origin/CASES.json:/results/CASES.json:ro")
for case in G-T1_A G-T1_B G-T1_C; do
    mounts+=(-v "$origin/H/$case:/results/H/$case:ro" -v "$origin/poses/$case:/results/poses/$case:ro")
done
mkdir -p output
command=(docker run --rm --pull=never --network none --name "$(basename "$PWD")-$mode" --cpus 36
    --user "$(id -u):$(id -g)" -e HOME=/tmp -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1
    "${mounts[@]}" -v "$old/code:/v2_r4:ro" -v "$old/code_joint:/v2_j4:ro" -v "$old/frozen:/frozen:ro"
    -v "$old/output/folds/30:/folds/30:ro" -v "$old/output/LOAO_RESULTS.json:/provenance/LOAO_RESULTS.json:ro"
    -v "$PWD/provenance/TIMELINE_READBACK.json:/provenance/TIMELINE_READBACK.json:ro"
    -v "$PWD/provenance/REPORT_KO.md:/provenance/REPORT_KO.md:ro"
    -v "$model:/model:ro" -v "$banks:/banks:ro" -v "$PWD/code:/v3:ro" -v "$PWD/output:/work"
    --entrypoint /bin/bash "$image" /v3/launch_tb3_model003_v3_s0.sh container "$mode")
printf '%q ' "${command[@]}"
printf '\n'
date -u +%FT%TZ
result=0
"${command[@]}" || result=$?
date -u +%FT%TZ
printf 'exit=%s\n' "$result"
exit "$result"
