#!/bin/bash
# Anchor 2 = ceiling anchor (4, -0.4); tag on its own y = -0.4 line (positions.txt). Wrapper of scripts/sweep_run.sh (see there for the exit codes).
#   PYTHON=<sionna python> bash scripts/corridor_anchor2_run.sh
cd "$(dirname "$0")/.."
export SCENARIO=corridor OUT=results/CORRIDOR_ANCHOR2_20261007 TAG_PREFIX=a2_ ANCHOR_X=4.0 ANCHOR_Y=-0.4 ALLOW_RUNNER_CHANGE=1
export POSITIONS=$OUT/positions.txt
exec bash scripts/sweep_run.sh
