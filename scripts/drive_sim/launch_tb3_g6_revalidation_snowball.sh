#!/usr/bin/env bash
set -euo pipefail
umask 077
if (($# != 2)); then
  printf 'Usage: %s RUN_DIR CODE_COMMIT\n' "$0" >&2
  exit 3
fi
test "$(id -un)" = KMS
cd "$1"
r=$(pwd -P)
code_commit=$2
[[ "$r" == /home/KMS/G1_RT_TB3_G6_REVALIDATION_* && "$code_commit" =~ ^[0-9a-f]{40}$ ]]
p=/home/KMS/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa
original=/home/KMS/G1_RT_TB3_G6_20261114T124634Z_9ElGTD
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
runtime=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
img=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
g6_sha=b0da8458aacdcffc9800f413d65ed6da25a0a911190d818d862280c81e12fdef
seal="$p/results/seal"
cases=(G-T1_A G-T1_B G-T1_C G-T2_A G-T2_B G-T2_C G-V_A G-V_B G-V_C)
mkdir -p cache scratch receipts logs traces
shopt -s nullglob
existing_traces=(traces/*)
test "${#existing_traces[@]}" -eq 0
test ! -e receipts/STARTED_UTC.txt
test ! -e "$seal/UNSEAL.json"
test ! -e G6_REVALIDATION.json
for file in launch_tb3_g6_revalidation_snowball.sh drive_tb3_g6_revalidation.sh \
    tb3_g6_revalidate.py assess_tb3_g6_revalidation.py; do
  test -f "code/$file"
done
printf '%s  %s\n' "$g6_sha" "$original/G6.json" | sha256sum -c

record_command() {
  local target=$1
  shift
  printf '%q ' "$@" > "$target"
  printf '\n' >> "$target"
}

common=(docker run --rm --pull=never --network none --cpu-shares 192
  --user "$(id -u):$(id -g)" --workdir /ref
  -e HOME=/run/cache -e TMPDIR=/run/scratch -e PYTHONDONTWRITEBYTECODE=1
  -e PYTHONPATH=/run/code:/original/code:/production/code:/runtime_packages:/ref:/ref/src
  -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1
  -v "$r:/run" -v "$r/code:/run/code:ro" -v "$ref:/ref:ro" -v "$runtime:/runtime_packages:ro"
  -v "$original/G6.json:/original/G6.json:ro" -v "$original/code:/original/code:ro"
  -v "$original/selected:/original/selected:ro" -v "$original/traces:/original/traces:ro")
trace=("${common[@]}" --name "$(basename "$r")_trace" --cpus 96
  -v "$p/g0:/production/g0:ro" -v "$p/g7:/production/g7:ro" -v "$p/code:/production/code:ro"
  -v "$p/config:/production/config:ro" -v "$p/frozen:/production/frozen:ro"
  -v "$p/results/GENERATION_RESULT.json:/production/results/GENERATION_RESULT.json:ro"
  -v "$p/results/CASES.json:/production/results/CASES.json:ro")
trace_inputs=()
for case_id in "${cases[@]}"; do
  manifest="results/H/$case_id/MANIFEST.json"
  receipt="results/paths/$case_id/TRACE_RECEIPTS.json"
  test -f "$p/$manifest"
  test -f "$p/$receipt"
  trace+=(-v "$p/$manifest:/production/$manifest:ro" -v "$p/$receipt:/production/$receipt:ro")
  trace_inputs+=("$p/$manifest" "$p/$receipt")
done
trace+=(--entrypoint /usr/bin/nice "$img" -n 12 /bin/bash /run/code/drive_tb3_g6_revalidation.sh)
assess=("${common[@]}" --name "$(basename "$r")_assess" --cpus 1
  --entrypoint /opt/rt-env/bin/python "$img" -u /run/code/assess_tb3_g6_revalidation.py
  --original /original --traces /run/traces --out /run/G6_REVALIDATION.json --code-commit "$code_commit")

storage_check() {
  local phase=$1
  local case_id file
  local -a check=(docker run --rm --pull=never --network none --cpu-shares 128 --cpus 1
    --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1
    -v "$p/code/seal_tb3_production.py:/code/seal_tb3_production.py:ro"
    -v "$r/receipts:/receipts" -v "$seal/SEAL_MANIFEST.json:/results/seal/SEAL_MANIFEST.json:ro"
    -v "$seal/ACCESS_LOG.jsonl:/results/seal/ACCESS_LOG.jsonl")
  for case_id in G-T2_{A,B,C} G-V_{A,B,C}; do
    for file in "H/$case_id/"{MANIFEST.json,H_full.npy,H_LoS.npy} "paths/$case_id/PATHS_NEAR.npz"; do
      test -f "$p/results/$file" || return 3
      check+=(-v "$p/results/$file:/results/$file:ro")
    done
  done
  check+=(--entrypoint /usr/bin/nice "$img" -n 12 /opt/rt-env/bin/python
    /code/seal_tb3_production.py --root /results --verify "/receipts/SEAL_STORAGE_${phase}.json")
  record_command "receipts/SEAL_STORAGE_${phase}_COMMAND.txt" "${check[@]}"
  "${check[@]}" > "logs/SEAL_STORAGE_${phase}.log" 2>&1
}

seal_digests() {
  sha256sum "$seal/SEAL_MANIFEST.json" "$seal/ACCESS_LOG.jsonl"
}

record_command receipts/TRACE_COMMAND.txt "${trace[@]}"
record_command receipts/ASSESS_COMMAND.txt "${assess[@]}"
sha256sum code/*.py code/*.sh "$original/G6.json" "$original/selected/SELECTION.json" \
  "$original"/code/*.py "$p"/code/*.py "$p/results/GENERATION_RESULT.json" \
  "$p/results/CASES.json" "${trace_inputs[@]}" > receipts/RUN_INPUTS.sha256
date -u +%FT%TZ > receipts/STARTED_UTC.txt
seal_digests > receipts/SEAL_BEFORE.sha256
cp "$seal/ACCESS_LOG.jsonl" receipts/ACCESS_BEFORE.jsonl

rc=3
if storage_check BEFORE; then
  trc=0
  date -u +%FT%TZ > receipts/TRACE_STARTED_UTC.txt
  "${trace[@]}" > logs/TRACE.log 2>&1 || trc=$?
  date -u +%FT%TZ > receipts/TRACE_FINISHED_UTC.txt
  printf '%s\n' "$trc" > receipts/TRACE_EXIT.txt
  if ((trc == 0)); then
    rc=0
    date -u +%FT%TZ > receipts/ASSESS_STARTED_UTC.txt
    "${assess[@]}" > logs/ASSESS.log 2>&1 || rc=$?
    date -u +%FT%TZ > receipts/ASSESS_FINISHED_UTC.txt
    printf '%s\n' "$rc" > receipts/ASSESS_EXIT.txt
    case "$rc" in 0|2|3) ;; *) rc=3 ;; esac
    if [[ ! -s G6_REVALIDATION.json ]]; then rc=3; fi
  fi
fi

storage_check AFTER || rc=3
seal_digests > receipts/SEAL_AFTER.sha256
test ! -e "$seal/UNSEAL.json" || rc=3
cmp <(head -1 receipts/SEAL_BEFORE.sha256) <(head -1 receipts/SEAL_AFTER.sha256) || rc=3
python3 - "$seal/ACCESS_LOG.jsonl" <<'PY' || rc=3
from pathlib import Path
import sys

before = Path("receipts/ACCESS_BEFORE.jsonl").read_bytes()
after = Path(sys.argv[1]).read_bytes()
if not after.startswith(before):
    raise SystemExit("Production seal access log changed before the append boundary")
with Path("receipts/ACCESS_APPEND.jsonl").open("xb") as stream:
    stream.write(after[len(before):])
PY
sha256sum -c receipts/RUN_INPUTS.sha256 > receipts/RUN_INPUTS_VERIFY.log || rc=3
if [[ -f G6_REVALIDATION.json ]]; then sha256sum G6_REVALIDATION.json > receipts/RESULT.sha256; fi
trace_outputs=(traces/*.json traces/*.jsonl)
if ((${#trace_outputs[@]})); then sha256sum "${trace_outputs[@]}" > receipts/TRACE_OUTPUTS.sha256; fi
date -u +%FT%TZ > receipts/FINISHED_UTC.txt
printf '%s\n' "$rc" > receipts/EXIT_CODE.txt
exit "$rc"
