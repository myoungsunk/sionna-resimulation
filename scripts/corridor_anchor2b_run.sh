#!/bin/bash
# Anchor 2B = ceiling anchor (4, -0.4); tag on the y = 0 line at x chosen to keep theta (positions.txt). Wrapper of scripts/sweep_run.sh.
#   PYTHON=<sionna python> bash scripts/corridor_anchor2b_run.sh
cd "$(dirname "$0")/.."
export SCENARIO=corridor OUT=results/CORRIDOR_ANCHOR2B_20261007 TAG_PREFIX=a2b_ ANCHOR_X=4.0 ANCHOR_Y=-0.4 ALLOW_RUNNER_CHANGE=1
export POSITIONS=$OUT/positions.txt
exec bash scripts/sweep_run.sh
