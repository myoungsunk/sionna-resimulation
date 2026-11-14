#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "$0")" && pwd -P)"
base=/home/KMS/RUN4_20261113T105130Z
entry=/home/KMS/RUN4_20261113T094312Z
inputs=/home/KMS/RUN2_20261113T072631Z/inputs
banks=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
prior=/home/KMS/G1_DIAG_002_20261114T073741Z_Nr6pdY
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
case "$root" in /home/KMS/G1_DIAG_002_K910_*) ;; *) exit 64;; esac
[[ "$(cat "$prior/EXIT_k0.txt")" == 0 ]]
[[ "$(cat "$prior/EXIT_k3_k6.txt")" == 0 ]]
mkdir -p "$root/out" "$root/records"
(
  cd -- "$base"
  python3 - <<'PY'
import hashlib, json
from pathlib import Path
data = Path("MANIFEST.json").read_bytes()
assert hashlib.sha256(data).hexdigest() == "3ecd384152e2c4b8af209ed7e54ff71a3acfd49eebeb539ef9fdfaab0a1877ce"
for name, digest in json.loads(data)["code_sha256"].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
    print(f"{name}: OK")
PY
) > "$root/records/CODE_HASH_CHECK.log"
cmd=(docker run --rm --pull=never --network none --cpus 4 --user 1001:1001
     --workdir /run/s2_code -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1
     -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1
     --mount "type=bind,src=$base,dst=/run,readonly"
     --mount "type=bind,src=$entry,dst=/entry,readonly"
     --mount "type=bind,src=$inputs,dst=/inputs,readonly"
     --mount "type=bind,src=$banks,dst=/banks,readonly"
     --mount "type=bind,src=$prior,dst=/prior,readonly"
     --mount "type=bind,src=$root,dst=/diag"
     --entrypoint /opt/rt-env/bin/python "$image")
run_phase() {
  local phase="$1" rc
  shift
  printf '%q ' "${cmd[@]}" "$@" > "$root/records/COMMAND_$phase.txt"
  printf '\n' >> "$root/records/COMMAND_$phase.txt"
  date -u +%FT%TZ > "$root/records/START_$phase.txt"
  set +e
  "${cmd[@]}" "$@" 2>&1 | tee "$root/records/$phase.log"
  rc=${PIPESTATUS[0]}
  set -e
  date -u +%FT%TZ > "$root/records/FINISH_$phase.txt"
  printf '%s\n' "$rc" > "$root/records/EXIT_$phase.txt"
  return "$rc"
}
run_phase k9 /diag/k9.py --code /run/s2_code --inputs /inputs --banks /banks \
  --grid /run/grid --entry /entry --frozen /run/s2_out --prior /prior --out /diag/out
run_phase k10 /diag/k10.py --q1 /prior/q1_sweep_rows.csv --k4 /prior/out/K4_ORACLE_SCALE.json \
  --out /diag/out/K10_KAPPA_CONVERGENCE.json
