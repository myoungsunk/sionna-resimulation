#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")"
run=$(pwd -P)
[[ "$run" == /home/KMS/G1_RT_TB3_FINITE_FACE_MOUNT45_* ]]
test "$(id -un)" = KMS
test ! -e STARTED_UTC.txt
test ! -e results
test ! -e shards
workers=84
code_commit=a2dff24f603c2460fcf7cabf5597cbf0da7ad551
base=$(cat MOUNT0_REFERENCE_RUN.txt)
old45=$(cat MOUNT45_UNGUARDED_RUN.txt)
old0=$(cat MOUNT0_UNGUARDED_RUN.txt)
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
runtime=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
g1=/home/KMS/G1_RT_TB3_CORRIDOR_PILOT_20261113T070808Z/output
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
sha256sum -c HISTORICAL_INPUTS.sha256 RUN_INPUTS.sha256 > PRELAUNCH_VERIFY.log
for prior in "$base" "$old45" "$old0"; do test ! -e "$prior/results/seal/UNSEAL.json"; done

date -u +%FT%TZ > STARTED_UTC.txt
finish() {
  local rc=$?
  trap - EXIT
  sha256sum -c HISTORICAL_INPUTS.sha256 RUN_INPUTS.sha256 > RUN_INPUTS_VERIFY.log || rc=3
  for prior in "$base" "$old45" "$old0"; do test ! -e "$prior/results/seal/UNSEAL.json" || rc=3; done
  if ((rc == 0)); then
    test ! -e results/seal/UNSEAL.json || rc=3
    sha256sum canary01/CANARY.json results/GENERATION_RESULT.json post_generation/{GENERATION_CHECK,CROSS_MOUNT_CHECK}.json \
      results/gates/{G4,SEAL_STORAGE_CHECK}.json results/seal/{SEAL_MANIFEST.json,ACCESS_LOG.jsonl} > RESULT_RECEIPTS.sha256 || rc=3
  fi
  date -u +%FT%TZ > FINISHED_UTC.txt
  printf '%s\n' "$rc" > EXIT_CODE.txt
  exit "$rc"
}
trap finish EXIT

canary=(docker run --rm --pull=never --network none --name "canary_$(basename "$run")"
  --cpus 2 --cpu-shares 128 --user "$(id -u):$(id -g)" --workdir /ref
  -e HOME=/run/cache -e TMPDIR=/run/scratch -e PYTHONDONTWRITEBYTECODE=1
  -e PYTHONPATH=/run/code:/runtime_packages:/ref:/ref/src
  -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1
  -v "$run:/run" -v "$ref:/ref:ro" -v "$runtime:/runtime_packages:ro" -v "$g1:/g1:ro"
  -v "$run/code:/run/code:ro" -v "$run/g0:/run/g0:ro" -v "$run/g7:/run/g7:ro"
  -v "$run/config:/run/config:ro" -v "$run/frozen:/run/frozen:ro"
  -v "$run/los_reference:/run/los_reference:ro"
  --entrypoint /usr/bin/nice "$image" -n 15 /opt/rt-env/bin/python -u /run/code/run_tb3_production.py
  --inputs /run/g0 --g7 /run/g7 --source /ref --reference /run/frozen/REFERENCE.json
  --ffd-manifest /run/frozen/FFD_RESTORE_MANIFEST.json --production /run/config/PRODUCTION_F1.json
  --case G-T1_A --out /run/canary01 --g8-canary /g1 --canary-los-reference /run/los_reference
  --code-commit "$code_commit" --finite-face-guard)
printf '%q ' "${canary[@]}" > CANARY_COMMAND.txt
printf '\n' >> CANARY_COMMAND.txt
date -u +%FT%TZ > CANARY_START_UTC.txt
rc=0
"${canary[@]}" > canary.log 2>&1 || rc=$?
date -u +%FT%TZ > CANARY_FINISH_UTC.txt
printf '%s\n' "$rc" > CANARY_EXIT.txt
((rc == 0)) || exit "$rc"

bash launch_tb3_production.sh "$workers" "$code_commit" canary01 --finite-face-guard
post=(docker run --rm --pull=never --network none --name "verify_$(basename "$run")"
  --cpus 2 --cpu-shares 128 --user "$(id -u):$(id -g)"
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/run/code
  -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1
  -v "$run:/run:ro" -v "$run/post_generation:/post" -v "$old45:/previous:ro" -v "$base:/mount0:ro"
  --entrypoint /bin/bash "$image" -eu -c
  'py=/opt/rt-env/bin/python
   nice -n 15 "$py" /run/code/verify_tb3_finite_face_production.py --run /run --previous /previous --code-commit "$1" --out /post/GENERATION_CHECK.json
   nice -n 15 "$py" /run/code/compare_tb3_guarded_mounts.py --current /run --mount0 /mount0 --out /post/CROSS_MOUNT_CHECK.json' check "$code_commit")
printf '%q ' "${post[@]}" > post_generation/COMMAND.txt
printf '\n' >> post_generation/COMMAND.txt
"${post[@]}" > post_generation/VERIFY.log 2>&1
bash launch_tb3_g4_snowball.sh
