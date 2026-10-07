#!/bin/bash
# DRIVE_SIM RF stages for Snowball (or any machine with sionna-rt 2.0.1 / mitsuba 3.8.0 / drjit 1.3.1 and the LP+-45 FFD banks).
# Four single-thread processes at a time; every stage is resumable (outputs that exist are skipped): if a job is stopped, rerun the same command.
#
#   PYTHON=<venv python> bash scripts/drive_sim/run_rf_snowball.sh <stage>
#
# stages (run in this order):
#   traj        S1 trajectories, pose sets, task lists                          (seconds, no Sionna)
#   parity      G2/G2'/G4 inputs: bin-by-bin + 17-node traces at the stored reference positions, method-A runs at out-of-range yaws
#   parity-report   compute PARITY_REPORT.json (gates G2, G2', G4 against the thresholds in S0/PREREG.json)
#   trace       production traces, 17 nodes, all positions of both laterals
#   continuity  G3 path continuity along both trajectories
#   apply       H stores for lateral x mount (needs the banks)                   (minutes, no Sionna)
set -u
cd "$(dirname "$0")/../.."
V=${PYTHON:?set PYTHON to the sionna venv python}
D=results/DRIVE_SIM_20261007
S1=$D/S1; S2=${S2_DIR:-$D/S2}; NP=${NPROC:-4}
shards() { # run "<cmd> --shard i/NP" in parallel
  local i
  for ((i=0;i<NP;i++)); do ( eval "$1 --shard $i/$NP" ) & done; wait
}
case "${1:?stage}" in
  traj)
    $V scripts/drive_sim/build_trajectories.py --out $S1 ;;
  parity)
    $V scripts/drive_sim/make_parity_tasks.py --out $S2
    mkdir -p $S2/logs
    shards "$V scripts/drive_sim/rf_b_trace.py --tasks $S2/ref_positions_tasks.json --out $S2/traces_ref_all --nodes all"
    shards "$V scripts/drive_sim/rf_b_trace.py --tasks $S2/ref_positions_tasks.json --out $S2/traces_ref_n17 --nodes 17"
    shards "$V scripts/drive_sim/rf_a_runner.py --tasks $S2/g4_a_tasks.json --out $S2/g4_a" ;;
  parity-report)
    $V scripts/drive_sim/parity_gate.py --traces-all $S2/traces_ref_all --traces-nodes $S2/traces_ref_n17 --g4-a-dir $S2/g4_a --out $S2/PARITY_REPORT.json ;;
  trace)
    for y in 0 0.35; do
      shards "$V scripts/drive_sim/rf_b_trace.py --tasks $S1/rf_tasks_y${y}_m0.json --out $S2/traces_y$y --nodes 17"
    done ;;
  continuity)
    for y in 0 0.35; do
      $V scripts/drive_sim/path_continuity.py --timeline $S1/timeline_y${y}_Tnone.csv --traces $S2/traces_y$y --out $S2/G3_continuity_y$y.json
    done ;;
  apply)
    for y in 0 0.35; do for m in 0 45; do
      $V scripts/drive_sim/rf_b_apply.py --poses $S1/rf_poses_y$y.json --traces $S2/traces_y$y --mount $m --out $S2/H_y${y}_m${m}.npy
    done; done ;;
  *) echo "unknown stage"; exit 2 ;;
esac
