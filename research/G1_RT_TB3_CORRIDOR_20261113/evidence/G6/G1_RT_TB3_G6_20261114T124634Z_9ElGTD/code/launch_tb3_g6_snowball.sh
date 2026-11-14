#!/usr/bin/env bash
set -euo pipefail
umask 077
r=/home/KMS/G1_RT_TB3_G6_20261114T124634Z_9ElGTD
p=/home/KMS/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa
g5=/home/KMS/G1_RT_TB3_G5_20261114T122910Z_94D6ow
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
runtime=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
img=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
code_commit=c0d764f3a9c46867745e88e4b7add2cb3bd266ba
cd "$r"
test "$(id -un)" = KMS
test "$(cat receipts/SMOKE_EXIT.txt)" = 0
test "$(cat "$g5/EXIT_CODE.txt")" = 0
test ! -e receipts/STARTED_UTC.txt
test ! -e "$p/results/seal/UNSEAL.json"
sha256sum -c receipts/SEAL_BEFORE.sha256
sha256sum -c "$g5/SEAL_AFTER.sha256"
sha256sum code/*.py code/*.sh selected/*.json > receipts/RUN_INPUTS.sha256
cases=(G-T1_A G-T1_B G-T1_C G-T2_A G-T2_B G-T2_C G-V_A G-V_B G-V_C)
common=(docker run --rm --pull=never --network none --cpu-shares 192 --user "$(id -u):$(id -g)" --workdir /ref
  -e HOME=/run/cache -e TMPDIR=/run/scratch -e PYTHONDONTWRITEBYTECODE=1
  -e PYTHONPATH=/run/code:/production/code:/runtime_packages:/ref:/ref/src
  -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1
  -v "$r:/run" -v "$ref:/ref:ro" -v "$runtime:/runtime_packages:ro"
  -v "$p/g0:/production/g0:ro" -v "$p/g7:/production/g7:ro" -v "$p/code:/production/code:ro"
  -v "$p/config:/production/config:ro" -v "$p/frozen:/production/frozen:ro"
  -v "$p/results/GENERATION_RESULT.json:/production/results/GENERATION_RESULT.json:ro"
  -v "$p/results/CASES.json:/production/results/CASES.json:ro")
trace=("${common[@]}" --name "$(basename "$r")_trace" --cpus 56)
for case in "${cases[@]}"; do
  trace+=(-v "$p/results/H/$case/MANIFEST.json:/production/results/H/$case/MANIFEST.json:ro"
          -v "$p/results/paths/$case/TRACE_RECEIPTS.json:/production/results/paths/$case/TRACE_RECEIPTS.json:ro")
done
trace+=(--entrypoint /usr/bin/nice "$img" -n 12 /bin/bash /run/code/drive_g6_shards.sh 7)
assess=("${common[@]}" --cpus 1 -v "$g5/G5.json:/g5.json:ro" --entrypoint /opt/rt-env/bin/python
  "$img" -u /run/code/validate_tb3_g6.py --production /production assess --source /ref
  --selection /run/selected --traces /run/traces --g5 /g5.json --out /run/G6.json --code-commit "$code_commit")
printf '%q ' "${trace[@]}" > receipts/TRACE_COMMAND.txt
printf '\n' >> receipts/TRACE_COMMAND.txt
printf '%q ' "${assess[@]}" > receipts/ASSESS_COMMAND.txt
printf '\n' >> receipts/ASSESS_COMMAND.txt
date -u +%FT%TZ > receipts/STARTED_UTC.txt
trc=0
"${trace[@]}" > logs/TRACE.log 2>&1 || trc=$?
date -u +%FT%TZ > receipts/TRACE_FINISHED_UTC.txt
printf '%s\n' "$trc" > receipts/TRACE_EXIT.txt
rc=0
"${assess[@]}" > logs/ASSESS.log 2>&1 || rc=$?
date -u +%FT%TZ > receipts/FINISHED_UTC.txt
printf '%s\n' "$rc" > receipts/ASSESS_EXIT.txt
test ! -e "$p/results/seal/UNSEAL.json"
sha256sum "$p/results/seal/SEAL_MANIFEST.json" "$p/results/seal/ACCESS_LOG.jsonl" > receipts/SEAL_AFTER.sha256
cmp receipts/SEAL_BEFORE.sha256 receipts/SEAL_AFTER.sha256
sha256sum -c receipts/RUN_INPUTS.sha256 > receipts/RUN_INPUTS_VERIFY.log
[[ ! -e G6.json ]] || sha256sum G6.json > receipts/G6.sha256
if ((trc != 0)); then rc=3; fi
printf '%s\n' "$rc" > receipts/EXIT_CODE.txt
exit "$rc"

