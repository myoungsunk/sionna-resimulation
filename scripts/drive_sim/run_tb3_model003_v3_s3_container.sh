#!/usr/bin/env bash
set -euo pipefail
python=/opt/rt-env/bin/python
args=(--frozen /frozen --manifest /frozen/INPUT_MANIFEST.json
      --results-root /results --model-source /model --banks-dir /banks --out /output)
if [[ $phase == range ]]; then
    runner=/code/run_tb3_model003_v3_s3_range.py
    "$python" -c 'import run_tb3_model003_v3_s3_range as r; print(*(f"--case {c} --path {p} --snr {q}" for q in (30,20) for c in r.CASES for p in r.PATHS), sep="\n")' |
        xargs -n 6 -P 36 "$python" -B -u "$runner" fold "${args[@]}"
    "$python" -B -u "$runner" close "${args[@]}"
    "$python" -B -u "$runner" close "${args[@]}" --chain O30
    "$python" -B -u "$runner" close "${args[@]}" --snr 20
else
    runner=/code/run_tb3_model003_v3_s3_joint.py
    read -r gate_sha _ < <(sha256sum /output/RANGE_STAGE.json)
    args+=(--range-stage /output/RANGE_STAGE.json --range-stage-sha256 "$gate_sha")
    "$python" - <<'PY' |
from run_tb3_model003_v3_s3_joint import CASES, PATHS, LEVELS, JOINT, DIAGNOSTIC
import json
gate = json.load(open("/output/RANGE_STAGE.json"))
arms = JOINT if gate["status"] == "PASS" else DIAGNOSTIC
for snr, chain in ((30, "OR"), (30, "O30"), (20, "OR")):
    for p in PATHS:
        for c in CASES:
            for level in (*LEVELS, "B0_ZERO"):
                for arm in arms:
                    print("--case", c, "--path", p, "--level", level, "--arm", arm, "--chain", chain, "--snr", snr)
PY
        xargs -n 12 -P 72 "$python" -B -u "$runner" fold "${args[@]}"
    "$python" -B -u "$runner" close "${args[@]}"
    "$python" -B -u "$runner" close "${args[@]}" --chain O30
    "$python" -B -u "$runner" close "${args[@]}" --snr 20
fi
