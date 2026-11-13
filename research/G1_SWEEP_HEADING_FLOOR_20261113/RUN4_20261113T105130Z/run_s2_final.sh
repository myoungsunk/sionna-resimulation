#!/usr/bin/env bash
set -euo pipefail
umask 077
base=/home/KMS/RUN4_20261113T105130Z
run3=/home/KMS/RUN3_20261113T085001Z
entry=/home/KMS/RUN4_20261113T094312Z
inputs=/home/KMS/RUN2_20261113T072631Z/inputs
banks=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
phase="${1:?phase required}"
workers="${2:?worker count required}"
cd "$base"
mkdir -p s2_out
finish() {
  local rc=$?
  trap - EXIT
  date -u +%FT%TZ > "s2_out/FINISH_${phase}_UTC.txt"
  printf '%s\n' "$rc" > "s2_out/EXIT_${phase}.txt"
  exit "$rc"
}
trap finish EXIT
date -u +%FT%TZ > "s2_out/START_${phase}_UTC.txt"
if [[ "$phase" = calibrate || "$phase" = calibrate_retry ]]; then
  (cd "$run3" && sha256sum -c) > s2_out/INHERITED_CODE_CHECK.log <<'HASHES'
c9a8d4a9c5fcc922211ee2f4365eb5d97c45576207ab4247e02f29c0a4ad1c64  code/INPUTS_CHECK_1ce68f3.json
dc94968ce4187eb8c451ef7e87669d37b59d5b9faf93f240d4dd7cbc6af46f62  code/run_step1.py
287c0a655dae0f660854133697bac10825ea0fe832c8793dec801a83a80afe89  code/run_step2.py
ef731cea0af12f409ccf962ee66b29d04a7905184cbdb246850fb0dec76c0edc  code/s1_analysis.py
8e96859156ffc110b02131619799d367a39f54f7e50c5a9b2998e9c6adb85b33  code/v32_filter.py
592906c20bac232139776ce7ca706ff7017da6439ff932a86b98c5f58edbcd4d  code/v32_observation.py
4ceeadf71e2cd77127e7ed84bbf05563165ca56d0e030126d1dc28043c5b7270  code/v32_preflight.py
8848890ef3f8d4e02d000e0b04cc5610793fd2892f553c8012386e096a138f64  code/v33_observation.py
13b907a73367263c446c23578d83eb94e7b47dca736721c8b78999da70f6f701  code/v33_filter.py
a097dde87b1ab3322e96ae5627a2b38a5d7b54f4cc2387810c53798d2342b0ec  code/v33_baseline.py
HASHES
  for f in INPUTS_CHECK_1ce68f3.json run_step1.py run_step2.py s1_analysis.py v32_filter.py v32_observation.py v32_preflight.py v33_observation.py v33_filter.py v33_baseline.py; do
    cp "$run3/code/$f" "s2_code/$f"
  done
fi
printf '%s  %s\n' 18d1a312da1e870746b4569658da8a98ffa46601af4dc9040be5d084eac7e299 "$entry/MANIFEST.json" | sha256sum -c
sha256sum -c >> "s2_out/${phase}_HASH_CHECK.log" <<'HASHES'
b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b  /home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source/LP_plus45_bank.npz
39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9  /home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source/LP_minus45_bank.npz
HASHES
sha256sum s2_code/* run_s2.sh run_s2_final.sh > "s2_out/CODE_${phase}_SHA256.txt"
{
  date -u +%FT%TZ
  uptime
  free -h
  df -h "$base"
  printf 'workers=%s\n' "$workers"
  docker image inspect "$image" --format '{{.Id}}'
} > "s2_out/RESOURCES_${phase}.txt"
docker_args=(--rm --pull=never --network none --cpus "$workers"
  --user "$(id -u):$(id -g)" --workdir /run/s2_code
  -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=1
  -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1
  --mount "type=bind,src=$base,dst=/run"
  --mount "type=bind,src=$entry,dst=/entry,readonly"
  --mount "type=bind,src=$inputs,dst=/inputs,readonly"
  --mount "type=bind,src=$banks,dst=/banks,readonly"
  --entrypoint /opt/rt-env/bin/python "$image")
name="g1-s2-${base##*RUN4_}-$phase"
python_phase="${phase%_retry}"
args=(/run/s2_code/s2_primary_final.py "$python_phase" --inputs /inputs --banks /banks --grid /run/grid --entry /entry --out /run/s2_out --workers "$workers")
printf '%q ' docker run --name "$name" "${docker_args[@]}" "${args[@]}" > "s2_out/COMMAND_$phase.txt"
printf '\n' >> "s2_out/COMMAND_$phase.txt"
if [[ "$phase" = calibrate || "$phase" = calibrate_retry ]]; then
  docker run --name "$name-verify" "${docker_args[@]}" -c 'from pathlib import Path; from run_step1 import verify; import sys,numpy,scipy; verify(Path("/inputs"), Path("/run/s2_code/INPUTS_CHECK_1ce68f3.json")); print(sys.version); print(numpy.__version__,scipy.__version__); print("Frozen input hashes passed")' > s2_out/VERIFY_INPUTS.log
fi
docker run --name "$name" "${docker_args[@]}" "${args[@]}" > "s2_out/$phase.log" 2>&1
