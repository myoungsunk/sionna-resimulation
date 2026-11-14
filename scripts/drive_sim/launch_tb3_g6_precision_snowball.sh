#!/usr/bin/env bash
set -euo pipefail
umask 077
r=/home/KMS/G1_RT_TB3_G6_CAUSE_20261114T135903Z_BcThNX
p=/home/KMS/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa
g6=/home/KMS/G1_RT_TB3_G6_20261114T124634Z_9ElGTD
image=/home/KMS/G1_RT_TB3_G6_IMAGE_20261114T135937Z_yqvk1k/G6_IMAGE_DIAGNOSTIC.json
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
runtime=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
img=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
test "$(id -un)" = KMS
cd "$r"
test ! -e "$p/results/seal/UNSEAL.json"
test ! -e G6_PRECISION_DIAGNOSTIC.json
sha256sum "$p/results/seal/SEAL_MANIFEST.json" "$p/results/seal/ACCESS_LOG.jsonl" > SEAL_BEFORE.sha256
cmp SEAL_BEFORE.sha256 "$g6/receipts/SEAL_AFTER.sha256"
cmd=(docker run --rm --pull=never --network none --cpus 1 --cpu-shares 192
  --name "$(basename "$r")_precision" --user "$(id -u):$(id -g)" --workdir /ref
  -e HOME=/run/cache -e TMPDIR=/run/scratch -e PYTHONDONTWRITEBYTECODE=1
  -e PYTHONPATH=/run/code:/g6code:/production/code:/runtime_packages:/ref:/ref/src
  -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1
  -v "$r:/run" -v "$ref:/ref:ro" -v "$runtime:/runtime_packages:ro"
  -v "$g6/code:/g6code:ro" -v "$g6/selected:/g6/selected:ro" -v "$g6/traces:/g6/traces:ro"
  -v "$g6/G6.json:/g6/G6.json:ro" -v "$image:/image.json:ro"
  -v "$p/code:/production/code:ro" -v "$p/g0:/production/g0:ro" -v "$p/g7:/production/g7:ro"
  -v "$p/config:/production/config:ro" -v "$p/frozen:/production/frozen:ro"
  --entrypoint /opt/rt-env/bin/python "$img" -u /run/code/diagnose_tb3_g6_precision.py
  --g6 /g6 --image-result /image.json --production-root /production --source /ref
  --out /run/G6_PRECISION_DIAGNOSTIC.json)
printf '%q ' "${cmd[@]}" > COMMAND.txt
printf '\n' >> COMMAND.txt
date -u +%FT%TZ > STARTED_UTC.txt
rc=0
"${cmd[@]}" > logs/PRECISION.log 2>&1 || rc=$?
date -u +%FT%TZ > FINISHED_UTC.txt
printf '%s\n' "$rc" > EXIT_CODE.txt
test ! -e "$p/results/seal/UNSEAL.json"
sha256sum "$p/results/seal/SEAL_MANIFEST.json" "$p/results/seal/ACCESS_LOG.jsonl" > SEAL_AFTER.sha256
cmp SEAL_BEFORE.sha256 SEAL_AFTER.sha256
sha256sum code/*.py code/*.sh "$image" > RUN_INPUTS.sha256
if ((rc == 0)); then
  sha256sum G6_PRECISION_DIAGNOSTIC.json > RESULT.sha256
fi
exit "$rc"
