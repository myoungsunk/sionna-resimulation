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
[[ "$(cat "$root/EXIT_k0.txt")" == 0 ]]
python3 - "$root/out/K0_REPRODUCTION.json" <<'PY'
import json, sys
with open(sys.argv[1]) as stream:
    k0 = json.load(stream)
assert k0["status"] == "PASS"
assert all(all(model["array_equal_all_50_visits"].values()) for model in k0["models"].values())
PY
[[ "$(cat "$root/EXIT_k1_k2.txt")" == 0 ]]
case "$phase" in
  k7_k8)
    cpu=4
    args=(/diag/k7_k8.py --code /run/s2_code --inputs /inputs --banks /banks
          --loro /run/s2_out/S1P_ERR_MODEL_LORO.json --q1 /diag/q1_sweep_rows.csv
          --out /diag/observation --workers 4)
    ;;
  k3_k6)
    [[ "$(cat "$root/EXIT_k7_k8.txt")" == 0 ]]
    test -s "$root/observation/K7_LOS_ATTRIBUTION.json"
    test -s "$root/observation/K8_TAP_CONTAMINATION.json"
    cpu=24
    args=(/diag/k3_k6.py --code /run/s2_code --inputs /inputs --banks /banks
          --grid /run/grid --entry /entry --frozen /run/s2_out --q1 /diag/q1_sweep_rows.csv
          --out /diag/out --workers 24)
    ;;
  *) exit 64 ;;
esac
echo "ede1a041dc275a57ca49751257d5c264f861a147e58b42166e0d737902111c3e  q1_sweep_rows.csv" |
    (cd -- "$root"; sha256sum -c -)
cmd=(docker run --rm --pull=never --network none --cpus "$cpu" --user 1001:1001
     --workdir /run/s2_code -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1
     -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1
     --mount "type=bind,src=$base,dst=/run,readonly"
     --mount "type=bind,src=$entry,dst=/entry,readonly"
     --mount "type=bind,src=$inputs,dst=/inputs,readonly"
     --mount "type=bind,src=$banks,dst=/banks,readonly"
     --mount "type=bind,src=$root,dst=/diag"
     --entrypoint /opt/rt-env/bin/python "$image" "${args[@]}")
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
