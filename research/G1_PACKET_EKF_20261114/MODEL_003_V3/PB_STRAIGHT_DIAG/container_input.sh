set -euo pipefail
for case in G-T1_A G-T1_B G-T1_C; do
    for level in B0 TB3_r2.1.0; do
        for arm in S-V S-C; do
            printf '%s\n' "--case $case --level $level --arm $arm"
        done
    done
done | xargs -n 6 -P 8 /opt/rt-env/bin/python -B -u /diagnostic/pb_trace.py \
  --frozen /frozen --manifest /frozen/INPUT_MANIFEST.json --range-stage /output/RANGE_STAGE.json \
  --results-root /results --model-source /model --banks-dir /banks --out /output --capture-dir /capture \
  --range-stage-sha256 02fdc559df446f638405becbc6365597a19fdc302a159a0cf0d64fd615f7fcf7
