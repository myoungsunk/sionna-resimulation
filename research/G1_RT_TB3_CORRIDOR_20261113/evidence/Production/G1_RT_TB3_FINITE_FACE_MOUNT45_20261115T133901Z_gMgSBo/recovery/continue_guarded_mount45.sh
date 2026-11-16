#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
run=$(pwd -P)
[[ "$run" == /home/KMS/G1_RT_TB3_FINITE_FACE_MOUNT45_* ]]
test "$(id -un)" = KMS
test ! -e recovery/STARTED_UTC.txt
test "$(cat PRODUCTION_EXIT.txt)" = 1
sha256sum -c HISTORICAL_INPUTS.sha256 RUN_INPUTS.sha256 > recovery/PRELAUNCH_VERIFY.log
(cd recovery/initial_attempt; sha256sum -c ../INITIAL_ATTEMPT.sha256) >> recovery/PRELAUNCH_VERIFY.log
sha256sum recovery/{recover_guarded_mount45.py,continue_guarded_mount45.sh} > recovery/RECOVERY_CODE.sha256
date -u +%FT%TZ > recovery/STARTED_UTC.txt
finish() {
  local rc=$?
  trap - EXIT
  sha256sum -c HISTORICAL_INPUTS.sha256 RUN_INPUTS.sha256 recovery/RECOVERY_CODE.sha256 > recovery/INPUTS_VERIFY.log || rc=3
  (cd recovery/initial_attempt; sha256sum -c ../INITIAL_ATTEMPT.sha256) >> recovery/INPUTS_VERIFY.log || rc=3
  if ((rc == 0)); then
    for prior in "$(cat MOUNT0_REFERENCE_RUN.txt)" "$(cat MOUNT45_UNGUARDED_RUN.txt)" "$(cat MOUNT0_UNGUARDED_RUN.txt)" "$run"; do
      test ! -e "$prior/results/seal/UNSEAL.json" || rc=3
    done
    sha256sum canary01/CANARY.json results/GENERATION_RESULT.json post_generation/{GENERATION_CHECK,CROSS_MOUNT_CHECK}.json \
      results/gates/{G4,SEAL_STORAGE_CHECK}.json results/seal/{SEAL_MANIFEST.json,ACCESS_LOG.jsonl} > RESULT_RECEIPTS.sha256 || rc=3
  fi
  date -u +%FT%TZ > recovery/FINISHED_UTC.txt
  printf '%s\n' "$rc" > recovery/EXIT_CODE.txt
  exit "$rc"
}
trap finish EXIT

base=$(cat MOUNT0_REFERENCE_RUN.txt)
old45=$(cat MOUNT45_UNGUARDED_RUN.txt)
code_commit=a2dff24f603c2460fcf7cabf5597cbf0da7ad551
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
runtime=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f

retry=(docker run --rm --pull=never --network none --name "retry_$(basename "$run")"
  --cpus 10 --cpu-shares 256 --user "$(id -u):$(id -g)" --workdir /ref
  -e HOME=/run/cache -e TMPDIR=/run/scratch -e PYTHONDONTWRITEBYTECODE=1
  -e PYTHONPATH=/run/code:/runtime_packages:/ref:/ref/src
  -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1
  -v "$run:/run" -v "$ref:/ref:ro" -v "$runtime:/runtime_packages:ro"
  -v "$run/code:/run/code:ro" -v "$run/g0:/run/g0:ro" -v "$run/g7:/run/g7:ro"
  -v "$run/config:/run/config:ro" -v "$run/frozen:/run/frozen:ro"
  -v "$run/recovery/recover_guarded_mount45.py:/run/recovery/recover_guarded_mount45.py:ro"
  --entrypoint /usr/bin/nice "$image" -n 15 /opt/rt-env/bin/python -u /run/recovery/recover_guarded_mount45.py)
printf '%q ' "${retry[@]}" > recovery/RETRY_COMMAND.txt
printf '\n' >> recovery/RETRY_COMMAND.txt
"${retry[@]}" > recovery/retry.log 2>&1
printf '0\n' > recovery/PRODUCTION_EXIT.txt

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
cp recovery/PRODUCTION_EXIT.txt PRODUCTION_EXIT.txt
bash launch_tb3_g4_snowball.sh
