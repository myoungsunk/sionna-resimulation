#!/usr/bin/env bash
set -euo pipefail
umask 077
test "$(id -un)" = KMS
cd "$1"
r=$(pwd -P)
code_commit=$2
[[ "$r" == /home/KMS/G1_RT_TB3_G6_BOUNDARY_* && "$code_commit" =~ ^[0-9a-f]{40}$ ]]
test ! -e STARTED_UTC.txt
p=/home/KMS/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa
old=/home/KMS/G1_RT_TB3_G6_20261114T124634Z_9ElGTD
prior=/home/KMS/G1_RT_TB3_G6_REVALIDATION_20261114T144337Z_gPzl3x
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
runtime=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
seal="$p/results/seal"
test ! -e "$seal/UNSEAL.json"
mkdir -p cache scratch out
inputs=(code/*.py code/*.sh "$old/G6.json" "$prior/G6_REVALIDATION.json" \
  "$prior/diagnostics/FINITE_FACE_DIAGNOSTICS.json" "$p/config/PRODUCTION_F1.json" \
  "$p/g0/RUN_MANIFEST.json" "$p/g7/RUN_MANIFEST.json" "$ref/LP_plus45_bank.npz" \
  "$prior/code/tb3_g6_face_match.py" "$prior/code/tb3_g6_revalidate.py")
sha256sum "${inputs[@]}" > INPUTS.sha256
sha256sum "$seal/SEAL_MANIFEST.json" "$seal/ACCESS_LOG.jsonl" > SEAL_BEFORE.sha256
cmd=(docker run --rm --pull=never --network none --cpus 2 --cpu-shares 128
  --user "$(id -u):$(id -g)" --workdir /ref
  -e HOME=/run/cache -e TMPDIR=/run/scratch -e PYTHONDONTWRITEBYTECODE=1
  -e PYTHONPATH=/code:/revalidation:/original/code:/production/code:/runtime_packages:/ref:/ref/src
  -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1
  -v "$r/out:/run" -v "$r/cache:/run/cache" -v "$r/scratch:/run/scratch"
  -v "$r/code:/code:ro" -v "$ref:/ref:ro" -v "$runtime:/runtime_packages:ro"
  -v "$prior/code:/revalidation:ro" -v "$old/code:/original/code:ro"
  -v "$old/G6.json:/original/G6.json:ro" -v "$old/traces:/original/traces:ro"
  -v "$prior/G6_REVALIDATION.json:/evidence/G6_REVALIDATION.json:ro"
  -v "$prior/diagnostics/FINITE_FACE_DIAGNOSTICS.json:/evidence/FINITE_FACE_DIAGNOSTICS.json:ro"
  -v "$p/code:/production/code:ro" -v "$p/config:/production/config:ro"
  -v "$p/g0:/production/g0:ro" -v "$p/g7:/production/g7:ro"
  --entrypoint /usr/bin/nice "$image" -n 12 /opt/rt-env/bin/python
  -u /code/diagnose_tb3_g6_boundary.py "$code_commit")
printf '%q ' "${cmd[@]}" > COMMAND.txt
printf '\n' >> COMMAND.txt
date -u +%FT%TZ > STARTED_UTC.txt
rc=0
"${cmd[@]}" > EXECUTION.log 2>&1 || rc=$?
date -u +%FT%TZ > FINISHED_UTC.txt
printf '%s\n' "$rc" > EXIT_CODE.txt
sha256sum "$seal/SEAL_MANIFEST.json" "$seal/ACCESS_LOG.jsonl" > SEAL_AFTER.sha256
cmp SEAL_BEFORE.sha256 SEAL_AFTER.sha256
test ! -e "$seal/UNSEAL.json"
sha256sum -c INPUTS.sha256 > INPUTS_VERIFY.log
if ((rc == 0)); then
  sha256sum out/BOUNDARY_STAGES.json > OUTPUTS.sha256
else
  tail -40 EXECUTION.log
fi
exit "$rc"
