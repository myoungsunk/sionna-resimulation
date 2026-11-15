#!/usr/bin/env bash
set -euo pipefail
umask 077
if (($# != 4)); then
  printf 'Usage: %s RUN_DIR CODE_COMMIT CPU_QUOTA MAX_WORKERS\n' "$0" >&2
  exit 3
fi
test "$(id -un)" = KMS
cd "$1"
r=$(pwd -P)
code_commit=$2
cpu_quota=$3
max_workers=$4
[[ "$r" == /home/KMS/G1_RT_TB3_G6_FINITE_FACE_* && "$code_commit" =~ ^[0-9a-f]{40}$ ]]
[[ "$cpu_quota" =~ ^[1-9][0-9]{0,2}$ && "$max_workers" =~ ^[1-9][0-9]?$ ]]
((cpu_quota <= 128 && max_workers <= 90))

p=/home/KMS/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa
original=/home/KMS/G1_RT_TB3_G6_20261114T124634Z_9ElGTD
prior=/home/KMS/G1_RT_TB3_G6_REVALIDATION_20261114T144337Z_gPzl3x
boundary=/home/KMS/G1_RT_TB3_G6_BOUNDARY_20261114T155612Z_kgdRjU/out/BOUNDARY_STAGES.json
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
runtime=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
img=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
seal="$p/results/seal"
cases=(G-T1_A G-T1_B G-T1_C G-T2_A G-T2_B G-T2_C G-V_A G-V_B G-V_C)
mkdir -p cache scratch receipts logs traces
shopt -s nullglob
existing_traces=(traces/*)
test "${#existing_traces[@]}" -eq 0
test ! -e receipts/STARTED_UTC.txt
test ! -e "$seal/UNSEAL.json"
test ! -e G6_FINITE_FACE.json
for file in launch_tb3_g6_finite_face_snowball.sh drive_tb3_g6_finite_face.sh \
    tb3_finite_face_guard.py tb3_g6_guard_replay.py tb3_g6_revalidate.py assess_tb3_g6_revalidation.py; do
  test -f "code/$file"
done
prior_traces=("$prior"/traces/*.jsonl)
test "${#prior_traces[@]}" -eq 90
printf '%s  %s\n' \
  b0da8458aacdcffc9800f413d65ed6da25a0a911190d818d862280c81e12fdef "$original/G6.json" \
  e17723bbd0b5cb835a396b89fa72def3c590359f86e6f427d08180e64affb767 "$prior/G6_REVALIDATION.json" \
  f678574ea2818f0ba10d0467f737b1af272027928ce1bc28aef134d83c2f4a2c "$boundary" | sha256sum -c

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
  -v "$original/selected:/original/selected:ro" -v "$original/traces:/original/traces:ro"
  -v "$prior/G6_REVALIDATION.json:/prior/G6_REVALIDATION.json:ro"
  -v "$prior/traces:/prior/traces:ro" -v "$boundary:/prior/BOUNDARY_STAGES.json:ro")
trace=("${common[@]}" --name "$(basename "$r")_trace" --cpus "$cpu_quota"
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
trace+=(--entrypoint /usr/bin/nice "$img" -n 12 /bin/bash /run/code/drive_tb3_g6_finite_face.sh "$max_workers")
assess=("${common[@]}" --name "$(basename "$r")_assess" --cpus 1
  -v "$p/code:/production/code:ro"
  --entrypoint /opt/rt-env/bin/python "$img" -u /run/code/assess_tb3_g6_revalidation.py
  --original /original --finite-face-prior /prior --traces /run/traces
  --out /run/G6_FINITE_FACE.json --code-commit "$code_commit")

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
sha256sum code/*.py code/*.sh "$original/G6.json" "$original"/selected/*.json \
  "$original"/code/*.py "$original"/traces/*.jsonl "$p"/code/*.py \
  "$p/config/PRODUCTION_F1.json" "$p/results/GENERATION_RESULT.json" "$p/results/CASES.json" \
  "$prior/G6_REVALIDATION.json" "$boundary" "${prior_traces[@]}" "${trace_inputs[@]}" > receipts/RUN_INPUTS.sha256
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
    if [[ ! -s G6_FINITE_FACE.json ]]; then rc=3; fi
  fi
fi

storage_check AFTER || rc=3
seal_digests > receipts/SEAL_AFTER.sha256
test ! -e "$seal/UNSEAL.json" || rc=3
cmp <(head -1 receipts/SEAL_BEFORE.sha256) <(head -1 receipts/SEAL_AFTER.sha256) || rc=3
python3 - "$seal/ACCESS_LOG.jsonl" "$seal/SEAL_MANIFEST.json" > receipts/SEAL_APPEND_VERIFY.txt <<'PY' || rc=3
import hashlib
import json
from pathlib import Path
import sys

receipts = Path("receipts")
before = (receipts / "ACCESS_BEFORE.jsonl").read_bytes()
after = Path(sys.argv[1]).read_bytes()
if not after.startswith(before):
    raise SystemExit("Production seal access log changed before the append boundary")
append = after[len(before):]
with (receipts / "ACCESS_APPEND.jsonl").open("xb") as stream:
    stream.write(append)
seal_file = Path(sys.argv[2])
seal_bytes = seal_file.read_bytes()
seal = json.loads(seal_bytes.decode("utf-8"))
expected_paths = sorted(name for case in seal["cases"].values() for name in case["files"])
if len(expected_paths) != 18 or not append.endswith(b"\n"):
    raise SystemExit("Unexpected seal storage or access-log coverage")
prefix = hashlib.sha256(before)
previous_hashes = {}
for i, line in enumerate(append.splitlines(keepends=True)):
    entry = json.loads(line.decode("utf-8"))
    if (entry.get("operation") != "STORAGE_HASH_CHECK" or entry.get("actor") != "KMS"
            or entry.get("paths") != expected_paths):
        raise SystemExit("Unexpected operation in seal access log")
    prefix.update(line)
    previous_hashes[prefix.hexdigest()] = i
last_index = -1
for phase in ("BEFORE", "AFTER"):
    report = json.loads((receipts / ("SEAL_STORAGE_" + phase + ".json")).read_text(encoding="utf-8"))
    index = previous_hashes.get(report["access_log_sha256"], -1)
    if (report.get("status") != "PASS" or report.get("files") != 18
            or report.get("seal_manifest_sha256") != hashlib.sha256(seal_bytes).hexdigest()
            or index <= last_index):
        raise SystemExit("Seal storage verification is not covered by the allowed log append")
    last_index = index
print("PASS: seal log prefix preserved and only the allowed 18-file storage checks appended")
PY
sha256sum -c receipts/RUN_INPUTS.sha256 > receipts/RUN_INPUTS_VERIFY.log || rc=3
if [[ -f G6_FINITE_FACE.json ]]; then sha256sum G6_FINITE_FACE.json > receipts/RESULT.sha256; fi
trace_outputs=(traces/*.json traces/*.jsonl smoke/*.json smoke/*.jsonl)
if ((${#trace_outputs[@]})); then sha256sum "${trace_outputs[@]}" > receipts/TRACE_OUTPUTS.sha256; fi
date -u +%FT%TZ > receipts/FINISHED_UTC.txt
printf '%s\n' "$rc" > receipts/EXIT_CODE.txt
exit "$rc"
