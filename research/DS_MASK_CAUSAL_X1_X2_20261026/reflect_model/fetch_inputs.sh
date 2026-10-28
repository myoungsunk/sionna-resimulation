#!/usr/bin/env bash
# Fetch every input of the reflection-model experiments into REFLECT_ROOT (default: this folder).
# All files come from one commit of myoungsunk/sionna-resimulation; LFS objects via media.githubusercontent.com.
set -euo pipefail
ROOT="${REFLECT_ROOT:-$(cd "$(dirname "$0")" && pwd)}"
COMMIT=9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13
REPO_URL=https://github.com/myoungsunk/sionna-resimulation.git
MEDIA=https://media.githubusercontent.com/media/myoungsunk/sionna-resimulation/$COMMIT
CASES="R2_aA_m0 R2_aB_m0 R2_aA_m45 R4_aA_m0 R4_aB_m0 R5_aA_m0 R5_aB_m0"
mkdir -p "$ROOT"/{repo,banks,rf,traces,out}

# 1) code: blob-less bare clone, then extract only the needed files (no LFS)
BARE="$ROOT/.src.git"
if [ ! -d "$BARE" ]; then
  git clone --bare --filter=blob:none --depth=1 --no-tags -b research/ds-x1-x2-results-20261026 "$REPO_URL" "$BARE"
fi
git -C "$BARE" fetch --depth=1 --filter=blob:none origin "$COMMIT" || true
take() { mkdir -p "$ROOT/repo/$(dirname "$1")"; git -C "$BARE" show "$COMMIT:$1" > "$ROOT/repo/$1"; }
for f in research/FFD_P0P3_20261016/source_model.py research/FFD_P0P3_20261016/p0_initial.py \
         research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py research/EKF4_RANGE_S_STAGED_20261014/core.py; do take "$f"; done
SRC=results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src/qclean_uwb
for f in $(git -C "$BARE" ls-tree -r --name-only "$COMMIT" -- "$SRC"); do take "$f"; done

# 2) FFD banks (LFS) + sha256 check
for f in LP_plus45_bank.npz LP_minus45_bank.npz; do
  [ -s "$ROOT/banks/$f" ] || curl -fsSL -o "$ROOT/banks/$f" "$MEDIA/$f"
done
( cd "$ROOT/banks" && sha256sum -c - <<'EOF'
b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b  LP_plus45_bank.npz
39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9  LP_minus45_bank.npz
EOF
)

# 3) ray-traced channels (plain git blobs, ~15-30 MB each) and pose lists
BLK=results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C
for c in $CASES; do
  [ -s "$ROOT/rf/H_$c.npy" ]     || git -C "$BARE" cat-file -p "$COMMIT:$BLK/FULL_RF/H_$c.npy" > "$ROOT/rf/H_$c.npy"
  [ -s "$ROOT/rf/H_LoS_$c.npy" ] || git -C "$BARE" cat-file -p "$COMMIT:$BLK/H_LoS_$c.npy"     > "$ROOT/rf/H_LoS_$c.npy"
  [ -s "$ROOT/rf/SAMPLES_$c.json" ] || git -C "$BARE" cat-file -p "$COMMIT:$BLK/$c/SAMPLES.json" > "$ROOT/rf/SAMPLES_$c.json"
done

# 4) E1 control traces (LFS), B0 and L2
WDW=research/DS_MASK_CAUSAL_X1_X2_20261026/why_ds_worse/CONTROL
for c in $CASES; do for b in B0 L2; do
  o="$ROOT/traces/${c}_${b}_CONTROL.npz"
  [ -s "$o" ] || curl -fsSL -o "$o" "$MEDIA/$WDW/${c}_${b}.npz"
done; done

# 5) record what was fetched
( cd "$ROOT" && find banks rf traces -type f -print0 | sort -z | xargs -0 sha256sum ) > "$ROOT/out/INPUT_LOCK.sha256"
echo "inputs ready in $ROOT"
