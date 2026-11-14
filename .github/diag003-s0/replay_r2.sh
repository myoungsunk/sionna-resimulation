set -euo pipefail
frozen="$1"
helper="$2"
archive="$3"
out="$4"
cd "$frozen"
export GITHUB_SHA
GITHUB_SHA="$(git rev-parse HEAD)"
test "$GITHUB_SHA" = 81cdffbdedf43b318ebf8eddb4fcbac1fd30d878
ns=research/EKF4_RANGE_S_STAGED_20261014
sensor=results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src
export PYTHONPATH="$PWD/$ns:$PWD/$sensor"
mkdir -p "$out"
{
    printf '%s\n' 'DIAGNOSTIC_ONLY' "host run $GITHUB_RUN_ID"
    printf '%s\n' '20261012.334.1 historical runner image, CPU unrecorded'
    env | grep -E '^(ImageOS|ImageVersion|RUNNER_OS|RUNNER_ARCH|OPENBLAS_NUM_THREADS|OPENBLAS_CORETYPE|OMP_NUM_THREADS|MKL_NUM_THREADS|PYTHONHASHSEED)='
    cat /etc/os-release
    lscpu
    python -VV
    python -m pip freeze
    python -c 'import numpy as np; np.show_config(); np.show_runtime()'
    sha256sum "$archive"
    git rev-parse HEAD
} | tee "$out/ENVIRONMENT.log"
python "$ns/r2_bias_audit.py" --out "$out/r2_bias_audit" | tee "$out/r2_bias_audit.log"
mkdir "$out/r2_bias_tests"
python -m pytest --noconftest -q -s -c "$ns/pytest.ini" "$ns/test_r2_bias.py" --junitxml="$out/r2_bias_tests/TESTS.xml" | tee "$out/r2_bias_tests.log"
for repeat in r2_01 r2_02; do
    path="$out/$repeat"
    audit="$out/r2_bias_audit/AUDIT.json"
    mkdir "$path"
    python "$helper/strict_gate.py" "$path/replay.log" python "$ns/r2_bias_replay.py" --archive "$archive" --audit "$audit" --out "$path/replay"
    python "$ns/r2_bias_score.py" --archive "$archive" --root "$path/replay" --audit "$audit" --out "$path/score" > "$path/score.log" 2>&1
    grep R2_BIAS_SCORE_FINAL "$path/score.log"
done
python "$helper/verify_r2.py" "$out" "$archive"