#!/bin/bash
# NOTE (R2-1): copied verbatim from the session scratchpad for the record; S= is the scratchpad of the original session and job_p5 is a copy of the G7 job tree built by p5_build_harness.py. Not runnable as-is elsewhere.
# resumable confirmatory driver: 16 chunks of 8 seeds; a chunk is skipped when its CSV exists
S=/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad
mkdir -p $S/p5_out/confirm_chunks
cd $S/g7/job_p5
for i in $(seq 0 15); do
  lo=$((5100+i*8)); hi=$((lo+8)); f=$S/p5_out/confirm_chunks/chunk_${lo}_${hi}.csv
  [ -f $f ] && continue
  rm -f OUTPUT/09_V2_main.csv
  P5_SEEDS=confirm P5_LO=$lo P5_HI=$hi python3 -I simulate_p5.py main > $S/p5_confirm_chunk_${lo}.log 2>&1 && cp OUTPUT/09_V2_main.csv $f
done
echo done > $S/p5_confirm_done.flag
