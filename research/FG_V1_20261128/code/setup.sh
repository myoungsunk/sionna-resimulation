#!/bin/bash
# FG-V1 setup: (1) native FFD model bundle, (2) LFS inputs used by FG-V1, (3) optional FFD grid.
# Run from anywhere inside this branch checkout (research/g1-sweep-heading-floor-spec-20261113 or a branch based on it).
set -e
FGV1="$(cd "$(dirname "$0")/.." && pwd)"; REPO="$(cd "$FGV1/../.." && pwd)"
BR="${FGV1_LFS_BRANCH:-research/g1-sweep-heading-floor-spec-20261113}"
MEDIA="https://media.githubusercontent.com/media/myoungsunk/sionna-resimulation/$BR"
I=research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001
fetch() {  # replace an LFS pointer in the working tree with the real object (git lfs pull also works if available)
  local p="$1" out="$REPO/$1"
  if [ -s "$out" ] && [ "$(stat -c %s "$out")" -gt 200 ]; then return; fi
  mkdir -p "$(dirname "$out")"; curl -sS -L --retry 3 -o "$out" "$MEDIA/$p"
}
# (1) native bundle = continuation_ks/replay_inputs/R45_sources + LP +-45 banks
NAT="$FGV1/native"; mkdir -p "$NAT"
cp -r "$REPO/$I/continuation_ks/replay_inputs/R45_sources/research" "$REPO/$I/continuation_ks/replay_inputs/R45_sources/src" "$NAT/"
for b in LP_plus45_bank.npz LP_minus45_bank.npz; do
  [ -s "$NAT/$b" ] && [ "$(stat -c %s "$NAT/$b")" -gt 200 ] || curl -sS -L --retry 3 -o "$NAT/$b" "$MEDIA/$b"
done
echo "{\"native\": \"$NAT\"}" > "$NAT/base.json"
# (2) inputs: M7 online packets (B0, L2_GYRO_ARW x seeds 10-29 x R2/R4/R5), evaluators, M7 H2 seed10 R2 traces for parity
M=$I/m7_final_model_stage1/attempt_02
list=()
for c in B0 L2_GYRO_ARW; do for s in $(seq 10 29); do for r in R2 R4 R5; do list+=("$M/input_generation/inputs/$c/seed$s/${r}_online.npz"); done; done; done
for r in R2 R4 R5; do list+=("$I/gm_theta_m6/inputs/${r}_evaluator.npz"); done
for c in B0 L2_GYRO_ARW; do list+=("$M/replay/cells/$c/own/seed10/R2/H2/trace.npz"); done
for p in "${list[@]}"; do fetch "$p" & while [ "$(jobs -r | wc -l)" -ge 8 ]; do sleep 0.2; done; done; wait
echo "native: $NAT"; echo "inputs fetched: ${#list[@]}"
echo "FFD grid: run 'python3 gen_grid.py 0 200; ... 600 761' in code/ (about 31 min on 2 cores) or copy sur/ffd_grid.npz"
