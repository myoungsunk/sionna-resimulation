#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
umask 077
run=$(pwd -P)
test "$(id -un)" = KMS
test -f code_commit.txt
test -f release.json
test ! -e S1_STARTED_UTC.txt
original=/home/KMS/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa/results
banks=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
model=/home/KMS/RUN2_20261113T072631Z/inputs/results/DRIVE_SIM_20261007/CAUSE_CHECK_A23_EXECUTION_20261010/retrieved/source
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
mounts=(
  -v "$original/CASES.json:/results/CASES.json:ro"
  -v "$original/GENERATION_RESULT.json:/results/GENERATION_RESULT.json:ro"
)
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
  -v "$run/release.json:/release.json:ro" -v "$model:/model:ro" -v "$banks:/banks:ro"
  --entrypoint /opt/rt-env/bin/python "$image" -u /code/run_tb3_model003_s1.py
  --results-root /results --release-receipt /release.json --model-source /model
  --banks-dir /banks --out /output/S1)
printf '%q ' "${cmd[@]}" > S1_COMMAND.txt
printf '\n' >> S1_COMMAND.txt
date -u +%FT%TZ > S1_STARTED_UTC.txt
rc=0
"${cmd[@]}" > S1.log 2>&1 || rc=$?
date -u +%FT%TZ > S1_FINISHED_UTC.txt
printf '%s\n' "$rc" > S1_EXIT_CODE.txt
exit "$rc"
