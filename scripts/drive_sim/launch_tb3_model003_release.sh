#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
umask 077
run=$(pwd -P)
test "$(id -un)" = KMS
test ! -e STARTED_UTC.txt
new=/home/KMS/G1_MODEL003_G6_REGEN_okSskppe
banks=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
model=/home/KMS/RUN2_20261113T072631Z/inputs/results/DRIVE_SIM_20261007/CAUSE_CHECK_A23_EXECUTION_20261010/retrieved/source
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
test "$(cat "$new/EXIT_CODE.txt")" = 0
test -f "$run/old/G6_REVALIDATION.json"
test -f "$run/old/G9.json"
mkdir "$run/output"
cmd=(docker run --rm --pull=never --network none
  --name "$(basename "$run")" --cpus 6 --user "$(id -u):$(id -g)"
  -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=1
  -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1
  -v "$run/old:/old:ro" -v "$new/results:/new/results:ro" -v "$new/g3_retry:/g3:ro"
  -v "$run/code:/code:ro" -v "$run/output:/output"
  -v "$model:/model:ro" -v "$banks:/banks:ro"
  --entrypoint /opt/rt-env/bin/python "$image" -u /code/validate_tb3_g6_regenerated_release.py
  --old-results-root /old/results --old-seal-root /old
  --new-results-root /new/results --new-seal-root /new/results
  --g6 /old/G6_REVALIDATION.json --g9 /old/G9.json
  --supplemental-g3 /g3/G-T2_B_1708.json /g3/G-T2_C_1025.json /g3/G-T2_C_1840.json /g3/G-T2_C_2477.json
  --model-source /model --banks-dir /banks --out /output/REGENERATED_RELEASE.json)
printf '%q ' "${cmd[@]}" > COMMAND.txt
printf '\n' >> COMMAND.txt
date -u +%FT%TZ > STARTED_UTC.txt
rc=0
"${cmd[@]}" > execution.log 2>&1 || rc=$?
date -u +%FT%TZ > FINISHED_UTC.txt
printf '%s\n' "$rc" > EXIT_CODE.txt
exit "$rc"
