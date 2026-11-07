#!/usr/bin/env bash
# Explicit execution entry point. Preparation never invokes this script.
set -euo pipefail
WORKDIR="$(cd "${1:?WORKDIR required}" && pwd)"
test "$(id -un)" = KMS || { echo 'KMS account required'; exit 2; }
test -f "$WORKDIR/EXECUTION_LOCK.json"
test -f "$WORKDIR/FROZEN_BASE.json"
test -f "$WORKDIR/input/anchor_b_frozen.zip"
mkdir "$WORKDIR/out" # Refuse overwriting an existing run.
docker run --rm -u "$(id -u):$(id -g)" -v "$WORKDIR:/w" -w /w/repo \
  -e GITHUB_SHA=81cdffbdedf43b318ebf8eddb4fcbac1fd30d878 \
  -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 \
  -e PYTHONHASHSEED=0 -e PYTHONUNBUFFERED=1 \
  python:3.11.11 bash -euo pipefail -c '
    python -m venv /w/venv
    export PATH="/w/venv/bin:$PATH"
    python -m pip install --disable-pip-version-check numpy==1.26.4 scipy==1.13.1 pytest==8.3.5
    STAGE=research/EKF4_RANGE_S_STAGED_20261014
    export PYTHONPATH="/w/repo/$STAGE:/w/repo/results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src"
    python -c "import sys,numpy,scipy;print(sys.version,numpy.__version__,scipy.__version__)" | tee /w/out/environment.txt
    python "$STAGE/r2_bias_audit.py" --out /w/out/audit | tee /w/out/audit.log
    python -m pytest --noconftest -q -c "$STAGE/pytest.ini" "$STAGE/test_r2_bias.py" "$STAGE/test_anchor_b.py" --junitxml=/w/out/TESTS.xml | tee /w/out/tests.log
    python "$STAGE/preflight_anchor_b.py" --archive /w/input/anchor_b_frozen.zip --out /w/out/PREFLIGHT.json | tee /w/out/preflight.log
    python "$STAGE/r2_bias_replay.py" --archive /w/input/anchor_b_frozen.zip --audit /w/out/audit/AUDIT.json --out /w/out/replay | tee /w/out/replay.log
    python "$STAGE/r2_bias_score.py" --archive /w/input/anchor_b_frozen.zip --audit /w/out/audit/AUDIT.json --root /w/out/replay --out /w/out/score | tee /w/out/score.log
    sha256sum /w/out/score/*.csv /w/out/score/FINAL.json > /w/out/OUTPUT_SHA256.txt
  '
