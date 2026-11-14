#!/usr/bin/env bash
set -euo pipefail
phase="$1"
root="$(cd -- "$(dirname -- "$0")" && pwd -P)"
base=/home/KMS/RUN4_20261113T105130Z
entry=/home/KMS/RUN4_20261113T094312Z
inputs=/home/KMS/RUN2_20261113T072631Z/inputs
banks=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
case "$root" in /home/KMS/G1_DIAG_002_*) ;; *) exit 64;; esac
mkdir -p "$root/out"
if [[ "$phase" == k0 ]]; then
    (cd -- "$base"; python3 - <<'PY'
import hashlib, json
from pathlib import Path
manifest = Path("MANIFEST.json").read_bytes()
assert hashlib.sha256(manifest).hexdigest() == "3ecd384152e2c4b8af209ed7e54ff71a3acfd49eebeb539ef9fdfaab0a1877ce"
source = json.loads(manifest)
for key in ("code_sha256",):
    for path, digest in source[key].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest, path
        print(path, "OK")
PY
    ) >"$root/CODE_SEALED_CHECK.log"
fi
driver=/diag/k0_k1_k2.py
if [[ "$phase" == k1_k2 ]]; then driver=/diag/k1_k2.py; fi
cmd=(docker run --rm --pull=never --network none --cpus 4 --user 1001:1001
     --workdir /run/s2_code
     -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=1
     -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1
     --mount "type=bind,src=$base,dst=/run,readonly"
     --mount "type=bind,src=$entry,dst=/entry,readonly"
     --mount "type=bind,src=$inputs,dst=/inputs,readonly"
     --mount "type=bind,src=$banks,dst=/banks,readonly"
     --mount "type=bind,src=$root,dst=/diag"
     --entrypoint /opt/rt-env/bin/python "$image"
     "$driver" "$phase"
     --code /run/s2_code --inputs /inputs --banks /banks --grid /run/grid
     --entry /entry --frozen /run/s2_out --out /diag/out)
printf '%q ' "${cmd[@]}" >"$root/COMMAND_$phase.txt"
printf '\n' >>"$root/COMMAND_$phase.txt"
date -u +%FT%TZ >"$root/START_$phase.txt"
set +e
"${cmd[@]}" 2>&1 | tee "$root/$phase.log"
rc=${PIPESTATUS[0]}
set -e
date -u +%FT%TZ >"$root/FINISH_$phase.txt"
printf '%s\n' "$rc" >"$root/EXIT_$phase.txt"
exit "$rc"
