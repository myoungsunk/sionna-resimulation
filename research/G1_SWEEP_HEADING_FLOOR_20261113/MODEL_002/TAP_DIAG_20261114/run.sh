#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "$0")" && pwd -P)"
base=/home/KMS/RUN4_20261113T105130Z
inputs=/home/KMS/RUN2_20261113T072631Z/inputs
banks=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
old=/home/KMS/G1_DIAG_002_20261114T073741Z_Nr6pdY
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
case "$root" in /home/KMS/G1_MODEL_002_TAP_*) ;; *) exit 64;; esac
[[ "$(id -un)" == KMS ]]
[[ ! -e "$root/out" && ! -e "$root/EXIT.txt" ]]
date -u +%FT%TZ > "$root/START.txt"
echo "faab61382dfa97d9cc7c14c1edb9b778fc142df7eb2c19726da2eb8ca2c10fe7  SPEC_KO.md" |
  (cd "$root"; sha256sum -c -)
cmd=(docker run --rm --pull=never --network none --cpus 12 --user 1001:1001
     --workdir /run/s2_code -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1
     -e PYTHONPATH=/old -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1
     --mount "type=bind,src=$base,dst=/run,readonly"
     --mount "type=bind,src=$inputs,dst=/inputs,readonly"
     --mount "type=bind,src=$banks,dst=/banks,readonly"
     --mount "type=bind,src=$old,dst=/old,readonly"
     --mount "type=bind,src=$root,dst=/diag"
     --entrypoint /opt/rt-env/bin/python "$image" /diag/tap_diagnostic.py
     --code /run/s2_code --inputs /inputs --banks /banks --loro /run/s2_out/S1P_ERR_MODEL_LORO.json
     --q1 /old/q1_sweep_rows.csv --spec /diag/SPEC_KO.md --out /diag/out --workers 12)
printf '%q ' "${cmd[@]}" > "$root/COMMAND.txt"
printf '\n' >> "$root/COMMAND.txt"
set +e
PYTHONPATH='' "${cmd[@]}" 2>&1 | tee "$root/run.log"
rc=${PIPESTATUS[0]}
set -e
date -u +%FT%TZ > "$root/FINISH.txt"
printf '%s\n' "$rc" > "$root/EXIT.txt"
if [[ "$rc" == 0 ]]; then
  (cd "$root"; sha256sum SPEC_KO.md tap_diagnostic.py run.sh COMMAND.txt START.txt FINISH.txt EXIT.txt run.log out/* > SHA256SUMS.txt)
fi
exit "$rc"
