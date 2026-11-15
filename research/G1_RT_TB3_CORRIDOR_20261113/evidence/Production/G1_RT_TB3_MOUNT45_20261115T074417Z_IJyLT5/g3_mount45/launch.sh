#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
umask 077
run=$(pwd -P)
a=/home/KMS/G1_RT_TB3_G3A_20261114T065509Z_qJRtuw
b=/home/KMS/G1_RT_TB3_G3B_20261114T072931Z_tUu1JZ
c=/home/KMS/G1_RT_TB3_G3C_20261114T073923Z_hfLYcu
prep=/home/KMS/G1_RT_TB3_CORRIDOR_G3_20261113T073918Z
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
rt=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
test "$(id -un)" = KMS
set -o noclobber
date -u +%FT%TZ > START_UTC.txt
set +o noclobber
rc=0
docker run --rm --pull=never --network none --name "g3_$(basename "$(dirname "$run")")" \
  --cpus 2 --cpu-shares 64 --user "$(id -u):$(id -g)" --workdir /ref \
  -v "$a:/g3a:ro" -v "$b:/g3b:ro" -v "$c:/g3c:ro" -v "$prep:/g3:ro" \
  -v "$run:/run_m45" -v "$ref:/ref:ro" -v "$rt:/runtime_packages:ro" \
  -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/g3a:/g3c:/g3/input:/runtime_packages:/ref/src \
  -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 \
  --entrypoint /usr/bin/nice "$image" -n 19 /run_m45/eval.sh > evaluate.log 2>&1 || rc=$?
printf '%s\n' "$rc" > EXIT_CODE.txt
date -u +%FT%TZ > FINISH_UTC.txt
exit "$rc"
