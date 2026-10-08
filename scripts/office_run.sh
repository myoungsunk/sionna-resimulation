#!/bin/bash
# Office sweeps (single-core PathSolver processes, CORES at a time). Thin wrapper of scripts/sweep_run.sh with the office scenario.
#   PYTHON=<python with sionna-rt 2.0.1> bash scripts/office_run.sh                       # all 35 positions
#   PYTHON=... POSITIONS=results/OFFICE_RUN_PLAN_20261008/positions_pilot.txt OUT=results/OFFICE_RUN_PILOT bash scripts/office_run.sh
# Environment: PYTHON (required), POSITIONS, OUT, CORES (4), BIN_STRIDE (1 = all 257 bins), DEADLINE_MIN. Exit codes: see scripts/sweep_run.sh.
cd "$(dirname "$0")/.."
export SCENARIO=office
export POSITIONS=${POSITIONS:-results/OFFICE_RUN_PLAN_20261008/positions_all.txt}
export OUT=${OUT:-results/OFFICE_RUN_20261008}
exec bash scripts/sweep_run.sh
