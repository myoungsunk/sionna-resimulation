#!/usr/bin/env bash
set -euo pipefail
umask 077
if (($# != 2)); then
  printf 'Usage: %s RUN_DIR PRODUCTION_CODE_COMMIT\n' "$0" >&2
  exit 3
fi
test "$(id -un)" = KMS
cd "$1"
run=$(pwd -P)
code_commit=$2
[[ "$run" == /home/KMS/G1_RT_TB3_FINITE_FACE_PRODUCTION_* ]]
[[ "$code_commit" =~ ^[a-f0-9]{40}$ ]]
test "$(cat PRODUCTION_EXIT.txt)" = 0
test ! -e G4_STARTED_UTC.txt

old=/home/KMS/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
out="$run/post_generation"
mkdir -m 700 "$out"
date -u +%FT%TZ > "$out/STARTED_UTC.txt"
sha256sum "$(realpath "$0")" "$run/code/verify_tb3_finite_face_production.py" > "$out/CODE.sha256"
finish() {
  local rc=$?
  trap - EXIT
  if ! sha256sum -c PINNED_INPUTS.sha256 HISTORICAL_SEALS.sha256 > "$out/HISTORICAL_VERIFY.log"; then
    rc=3
  fi
  if ! sha256sum -c RUN_INPUTS.sha256 > "$out/RUN_INPUTS_VERIFY.log"; then
    rc=3
  fi
  date -u +%FT%TZ > "$out/FINISHED_UTC.txt"
  printf '%s\n' "$rc" > "$out/EXIT_CODE.txt"
  exit "$rc"
}
trap finish EXIT

case_ids=(G-T1_{A,B,C} G-T2_{A,B,C} G-V_{A,B,C} G-T1_{A,B}_P-F)
metadata=(CASES.json GENERATION_RESULT.json)
current=(seal/SEAL_MANIFEST.json)
for case_id in "${case_ids[@]}"; do
  metadata+=("H/$case_id/MANIFEST.json" "paths/$case_id/TRACE_RECEIPTS.json")
done
cmd=(docker run --rm --pull=never --network none --name "pre_g4_$(basename "$run")"
  --cpus 2 --cpu-shares 128 --user "$(id -u):$(id -g)"
  -e PYTHONDONTWRITEBYTECODE=1
  -v "$run/code:/code:ro" -v "$out:/receipt")
for file in "${metadata[@]}"; do
  test -f "$old/results/$file"
  cmd+=(-v "$old/results/$file:/previous/results/$file:ro")
done
for file in "${metadata[@]}" "${current[@]}"; do
  test -f "$run/results/$file"
  cmd+=(-v "$run/results/$file:/run/results/$file:ro")
done
test ! -e results/seal/UNSEAL.json
cmd+=(--entrypoint /opt/rt-env/bin/python "$image" -u
  /code/verify_tb3_finite_face_production.py --run /run --previous /previous
  --code-commit "$code_commit" --out /receipt/GENERATION_CHECK.json)
printf '%q ' "${cmd[@]}" > "$out/COMMAND.txt"
printf '\n' >> "$out/COMMAND.txt"
"${cmd[@]}" > "$out/VERIFY.log" 2>&1
sha256sum "$out/GENERATION_CHECK.json" > "$out/GENERATION_CHECK.sha256"
bash launch_tb3_g4_snowball.sh
test ! -e results/seal/UNSEAL.json
sha256sum results/gates/G4.json results/gates/SEAL_STORAGE_CHECK.json \
  results/seal/SEAL_MANIFEST.json results/seal/ACCESS_LOG.jsonl > "$out/OUTPUTS.sha256"
