#!/usr/bin/env bash
set -euo pipefail
umask 077
if (($# != 3)); then
  printf 'Usage: %s RUN_DIR WORKERS CODE_COMMIT\n' "$0" >&2
  exit 3
fi
test "$(id -un)" = KMS
cd "$1"
run=$(pwd -P)
workers=$2
code_commit=$3
[[ "$run" == /home/KMS/G1_RT_TB3_FINITE_FACE_PRODUCTION_* ]]
[[ "$workers" =~ ^[1-9][0-9]?$ && "$code_commit" =~ ^[a-f0-9]{40}$ ]]
test ! -e STARTED_UTC.txt
test ! -e results
test ! -e shards

old=/home/KMS/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa
mount45=/home/KMS/G1_RT_TB3_MOUNT45_20261115T074417Z_IJyLT5
original_fail=/home/KMS/G1_RT_TB3_G6_20261114T124634Z_9ElGTD/G6.json
revalidation_fail=/home/KMS/G1_RT_TB3_G6_REVALIDATION_20261114T144337Z_gPzl3x/G6_REVALIDATION.json
g6=/home/KMS/G1_RT_TB3_G6_FINITE_FACE_REVALIDATION_20261115T111337Z_a465Ta
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
runtime=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
g1=/home/KMS/G1_RT_TB3_CORRIDOR_PILOT_20261113T070808Z/output
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f

printf '%s  %s\n' \
  b0da8458aacdcffc9800f413d65ed6da25a0a911190d818d862280c81e12fdef "$original_fail" \
  e17723bbd0b5cb835a396b89fa72def3c590359f86e6f427d08180e64affb767 "$revalidation_fail" \
  e97a4d41378d4de96f58c377622861f4c72d649c8ae12c33571c3928bdf9f8df "$g6/G6_FINITE_FACE.json" \
  fcd3ee9448640bcd29e0f031d06243a7cd5d8c6d7f80b1db49485ed7904017d8 "$old/config/PRODUCTION_F1.json" \
  48ebdcdde68f3d62ec1b00c3061440f9363313ef35577f409eb5b5c0b75c13b6 "$old/g0/RUN_MANIFEST.json" \
  a1542122461b919f55ad2ce43314ba0a3732e0611a574fd51fa692e6b03e9830 "$old/g7/RUN_MANIFEST.json" \
  b05cae3dc9c26a62714e93931c1621c5c195844830b942b6bc738834b72e7c28 "$old/results/GENERATION_RESULT.json" \
  eebc54523655cc7eeacbd3e8a48c2a0700fb12a67653b6c801da35737d43cdb0 "$old/results/gates/G4.json" \
  4d755c9a016275f2ba51fee02e9908fe8cb2a27f32c187192f00bc957c45ee4a "$old/results/seal/SEAL_MANIFEST.json" \
  > PINNED_INPUTS.sha256
sha256sum -c PINNED_INPUTS.sha256
test ! -e "$old/results/seal/UNSEAL.json"
test ! -e "$mount45/results/seal/UNSEAL.json"
sha256sum "$mount45/results/seal/SEAL_MANIFEST.json" \
  "$old/results/seal/ACCESS_LOG.jsonl" "$mount45/results/seal/ACCESS_LOG.jsonl" > HISTORICAL_SEALS.sha256

mkdir -m 700 cache scratch logs
cp -a "$old/g0" "$old/g7" "$old/config" "$old/frozen" .
cp "$g6/G6_FINITE_FACE.json" config/
if grep -Fq "$image" "$g6/receipts/TRACE_COMMAND.txt" && test -d "$g6/cache/.drjit"; then
  cp -a "$g6/cache/.drjit" cache/
  printf 'source=%s\nimage=%s\nfiles=%s\n' "$g6/cache/.drjit" "$image" "$(find cache/.drjit -type f | wc -l)" > CACHE_SEED.txt
fi
find code config frozen g0 g7 -type f -print0 | sort -z | xargs -0 sha256sum > RUN_INPUTS.sha256
sha256sum launch_tb3_production.sh launch_tb3_g4_snowball.sh "${0##*/}" >> RUN_INPUTS.sha256
date -u +%FT%TZ > STARTED_UTC.txt

finish() {
  local rc=$?
  trap - EXIT
  if ! sha256sum -c PINNED_INPUTS.sha256 HISTORICAL_SEALS.sha256 > HISTORICAL_VERIFY.log; then
    rc=3
  fi
  if ! sha256sum -c RUN_INPUTS.sha256 > RUN_INPUTS_VERIFY.log; then
    rc=3
  fi
  if [[ -e "$old/results/seal/UNSEAL.json" || -e "$mount45/results/seal/UNSEAL.json" ]]; then
    rc=3
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
  --entrypoint /usr/bin/nice "$image" -n 15 /opt/rt-env/bin/python -u /run/code/run_tb3_production.py
  --inputs /run/g0 --g7 /run/g7 --source /ref --reference /run/frozen/REFERENCE.json
  --ffd-manifest /run/frozen/FFD_RESTORE_MANIFEST.json --production /run/config/PRODUCTION_F1.json
  --case G-T1_A --out /run/canary01 --g8-canary /g1 --code-commit "$code_commit" --finite-face-guard)
printf '%q ' "${canary[@]}" > CANARY_COMMAND.txt
printf '\n' >> CANARY_COMMAND.txt
date -u +%FT%TZ > CANARY_START_UTC.txt
rc=0
"${canary[@]}" > canary.log 2>&1 || rc=$?
date -u +%FT%TZ > CANARY_FINISH_UTC.txt
printf '%s\n' "$rc" > CANARY_EXIT.txt
((rc == 0)) || exit "$rc"

bash launch_tb3_production.sh "$workers" "$code_commit" canary01 --finite-face-guard
bash code/finish_tb3_finite_face_production_snowball.sh "$run" "$code_commit"
