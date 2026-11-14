#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
umask 077
run=$(pwd -P)
s1=$(realpath "$1")
test "$(id -un)" = KMS
test "$(cat "$s1/S1_EXIT_CODE.txt")" = 0
test ! -e S2_STARTED_UTC.txt
commit=$(cat plan_commit.txt)
[[ "$commit" =~ ^[0-9a-f]{40}$ ]]
plan_sha=$(sha256sum frozen/CHARACTERIZATION_PLAN_003.json)
plan_sha=${plan_sha%% *}
original=/home/KMS/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa/results
banks=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
model=/home/KMS/RUN2_20261113T072631Z/inputs/results/DRIVE_SIM_20261007/CAUSE_CHECK_A23_EXECUTION_20261010/retrieved/source
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
mounts=(
  -v "$original/CASES.json:/results/CASES.json:ro"
  -v "$original/GENERATION_RESULT.json:/results/GENERATION_RESULT.json:ro"
)
for case in G-T1_A G-T1_B G-T1_C G-T1_A_P-F G-T1_B_P-F; do
  mounts+=(-v "$original/H/$case:/results/H/$case:ro")
  mounts+=(-v "$original/poses/$case:/results/poses/$case:ro")
done
mkdir "$run/output"
cmd=(docker run --rm --pull=never --network none
  --name "$(basename "$run")" --cpus 6 --user "$(id -u):$(id -g)"
  -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=1
  -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1
  "${mounts[@]}" -v "$run/code:/code:ro" -v "$run/output:/output" -v "$run/frozen:/frozen:ro"
  -v "$s1/output/S1:/s1:ro" -v "$model:/model:ro" -v "$banks:/banks:ro"
  --entrypoint /opt/rt-env/bin/python "$image" -u /code/run_tb3_model003_s2.py
  --results-root /results --s1-dir /s1 --model-source /model --banks-dir /banks
  --plan /frozen/CHARACTERIZATION_PLAN_003.json --plan-commit "$commit" --plan-sha256 "$plan_sha"
  --synthetic-receipt /frozen/FUTILITY_SYNTHETIC.json --timeline /frozen/TIMELINE_PACKETS.csv
  --out /output/S2)
printf '%q ' "${cmd[@]}" > S2_COMMAND.txt
printf '\n' >> S2_COMMAND.txt
date -u +%FT%TZ > S2_STARTED_UTC.txt
rc=0
"${cmd[@]}" > S2.log 2>&1 || rc=$?
date -u +%FT%TZ > S2_FINISHED_UTC.txt
printf '%s\n' "$rc" > S2_EXIT_CODE.txt
exit "$rc"
