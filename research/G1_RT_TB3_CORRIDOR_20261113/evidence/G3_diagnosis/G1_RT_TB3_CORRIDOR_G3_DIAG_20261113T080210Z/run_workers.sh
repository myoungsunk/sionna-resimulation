#!/bin/bash
set -euo pipefail
pids=()
for tag in x6.0000_y-0.3100 x6.0000_y-0.3300 x6.0000_y0.4700 x6.0003_y0.4698 x6.3521_y0.4684; do
    /opt/rt-env/bin/python -u /diag/diagnose_tb3_g3.py "$tag" --root /g3 --out "/diag/$tag.json" > "/diag/$tag.log" 2>&1 &
    pids+=($!)
done
rc=0
for pid in "${pids[@]}"; do wait "$pid" || rc=1; done
for log in /diag/x*.log; do tail -n 4 "$log"; done
exit "$rc"
