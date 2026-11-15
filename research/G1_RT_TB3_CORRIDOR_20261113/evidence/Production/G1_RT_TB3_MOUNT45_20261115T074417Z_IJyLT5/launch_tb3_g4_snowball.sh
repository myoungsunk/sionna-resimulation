#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
umask 077
run=$(pwd -P)
bank_root=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
model_root=/home/KMS/RUN2_20261113T072631Z/inputs/results/DRIVE_SIM_20261007/CAUSE_CHECK_A23_EXECUTION_20261010/retrieved/source
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
test "$(id -un)" = KMS
test "$(cat PRODUCTION_EXIT.txt)" = 0
test -f results/seal/SEAL_MANIFEST.json
test ! -e G4_STARTED_UTC.txt
date -u +%FT%TZ > G4_STARTED_UTC.txt
cmd=(docker run --rm --pull=never --network none --name "g4_$(basename "$run")"
  --cpus 6 --cpu-shares 128 --user "$(id -u):$(id -g)"
  -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/code
  -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1
  -v "$run/code:/code:ro" -v "$run/results:/results:ro"
  -v "$run/results/gates:/results/gates" -v "$run/results/seal:/results/seal"
  -v "$model_root:/model:ro" -v "$bank_root:/banks:ro"
  --entrypoint /bin/bash "$image" -c '
set -euo pipefail
py=/opt/rt-env/bin/python
gate=/results/gates/G4.json
tool=/code/validate_tb3_g4.py
seal=/code/seal_tb3_production.py
rc=0
"$py" "$seal" --root /results --g4-access START --g4-tool "$tool" --g4-report "$gate"
nice -n 15 "$py" -u "$tool" --results-root /results --model-source /model --banks-dir /banks --out "$gate" || rc=$?
"$py" "$seal" --root /results --g4-access FINISH --g4-tool "$tool" --g4-report "$gate"
"$py" "$seal" --root /results --verify /results/gates/SEAL_STORAGE_CHECK.json
exit "$rc"
')
printf '%q ' "${cmd[@]}" > G4_COMMAND.txt
printf '\n' >> G4_COMMAND.txt
rc=0
"${cmd[@]}" > g4.log 2>&1 || rc=$?
date -u +%FT%TZ > G4_FINISHED_UTC.txt
printf '%s\n' "$rc" > G4_EXIT.txt
exit "$rc"
