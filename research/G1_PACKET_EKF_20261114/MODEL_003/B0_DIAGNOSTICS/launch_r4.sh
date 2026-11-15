#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ${1-} == container ]]; then
    export PYTHONPATH=/code
    python=/opt/rt-env/bin/python
    "$python" -B -c 'import run_tb3_model003_s3 as s; [print(c, p) for c in s.CASES for p in s.PATHS]' |
        xargs -P 12 -n 2 "$python" -B -u /analysis/replay_r4.py
    exit
fi

test "$(id -un)" = KMS
old=/home/KMS/G1_MODEL003_S3_QH7zq5Jn
original=/home/KMS/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa/results
model=/home/KMS/RUN2_20261113T072631Z/inputs/results/DRIVE_SIM_20261007/CAUSE_CHECK_A23_EXECUTION_20261010/retrieved/source
banks=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
mounts=(-v "$original/CASES.json:/results/CASES.json:ro")
for case in G-T1_A G-T1_B G-T1_C; do
    mounts+=(-v "$original/H/$case:/results/H/$case:ro" -v "$original/poses/$case:/results/poses/$case:ro")
done
sha256sum replay_r4.py launch_r4.sh "$old/code/run_tb3_model003_s3.py" "$old/output/LOAO_RESULTS.json" "$old/frozen/RANGING_RULE_SELECTION.json"
command=(docker run --rm --pull=never --network none --name "$(basename "$PWD")" --cpus 12 --user "$(id -u):$(id -g)" -e HOME=/tmp -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1
    "${mounts[@]}" -v "$old/code:/code:ro" -v "$old/output/folds/30:/folds/30:ro" -v "$old/output/LOAO_RESULTS.json:/published/LOAO_RESULTS.json:ro" -v "$old/frozen:/frozen:ro" -v "$model:/model:ro" -v "$banks:/banks:ro" -v "$PWD:/analysis" --entrypoint /bin/bash "$image" /analysis/launch_r4.sh container)
printf '%q ' "${command[@]}"
printf '\n'
date -u +%FT%TZ
rc=0
"${command[@]}" || rc=$?
date -u +%FT%TZ
printf 'exit=%s\n' "$rc"
exit "$rc"
