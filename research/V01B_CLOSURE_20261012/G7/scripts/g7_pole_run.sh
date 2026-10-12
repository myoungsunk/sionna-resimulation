#!/bin/bash
S=/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad
cd $S/g7/job_pole
export SCRATCH=$S POLE_SAFE=1
mkdir -p $S/div_PA $S/div_PB $S/div_PC
DIV_OUT=$S/div_PA python3 -I simulate_pole.py main > $S/div_PA.log 2>&1; cp OUTPUT/09_V2_main.csv $S/div_PA.csv
OPENBLAS_CORETYPE=HASWELL DIV_OUT=$S/div_PB python3 -I simulate_pole.py main > $S/div_PB.log 2>&1; cp OUTPUT/09_V2_main.csv $S/div_PB.csv
ULP_PERTURB=1 DIV_OUT=$S/div_PC python3 -I simulate_pole.py main > $S/div_PC.log 2>&1; cp OUTPUT/09_V2_main.csv $S/div_PC.csv
echo done > $S/pole_done.flag
