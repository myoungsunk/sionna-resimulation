#!/usr/bin/env bash
set -eu
cd /home/KMS/RUN4_20261113T105130Z
test ! -e s2_out/START_sensitivity_UTC.txt
nohup bash -c 'while ! test -s s2_out/EXIT_primary.txt; do sleep 15; done; test "$(cat s2_out/EXIT_primary.txt)" = 0 || exit 5; exec bash run_s2_sigma.sh sensitivity 12' > SIGMA_DRIVER.log 2>&1 < /dev/null &

