#!/bin/bash
# Corridor scan 2 (anchor (4, 0), tag on the listed positions). Wrapper of scripts/sweep_run.sh: verified resume, request contract, honest exit codes.
# ALLOW_RUNNER_CHANGE=1 because the 61 existing results were made by an earlier runner version (audited in results/CORRIDOR_AUDIT_20261008.json).
#   PYTHON=<sionna python> bash scripts/corridor_scan2_run.sh
cd "$(dirname "$0")/.."
export SCENARIO=corridor OUT=results/CORRIDOR_SCAN2_20261007 TAG_PREFIX="" ALLOW_RUNNER_CHANGE=1
export POSITIONS=$OUT/positions.txt
exec bash scripts/sweep_run.sh
