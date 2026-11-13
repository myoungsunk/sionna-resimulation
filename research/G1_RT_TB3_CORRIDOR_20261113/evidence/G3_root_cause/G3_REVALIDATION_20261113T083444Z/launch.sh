set -euo pipefail
base=/home/KMS/G1_RT_TB3_CORRIDOR_G3_20261113T073918Z
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
rt=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
run=/home/KMS/G1_RT_TB3_CORRIDOR_G3_REVALIDATION_20261113T083444Z
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
cd "$run"
date -u +%FT%TZ > STARTED_UTC.txt
cmd=(docker run --rm --pull=never --network none --name "$(basename "$run")" --cpus 48 --user "$(id -u):$(id -g)" --workdir /ref
     --mount "type=bind,src=$base,dst=/g3,readonly" --mount "type=bind,src=$ref,dst=/ref,readonly"
     --mount "type=bind,src=$rt,dst=/runtime_packages,readonly" --mount "type=bind,src=$run,dst=/revalidation"
     -e PYTHONPATH=/runtime_packages:/ref/src -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1
     -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e OMP_NUM_THREADS=1
     --entrypoint /opt/rt-env/bin/python "$image" -u /revalidation/revalidate_tb3_g3_reference.py run)
printf '%q ' "${cmd[@]}" > COMMAND.txt
printf '\n' >> COMMAND.txt
set +e
"${cmd[@]}" 2>&1 | tee run.log
rc=${PIPESTATUS[0]}
set -e
printf '%s\n' "$rc" > EXIT_CODE.txt
date -u +%FT%TZ > FINISHED_UTC.txt
find . -maxdepth 1 -type f ! -name SHA256.txt -print0 | sort -z | xargs -0 sha256sum > SHA256.txt
if [[ -d analysis ]]; then
    find analysis -type f -print0 | sort -z | xargs -0 sha256sum >> SHA256.txt
fi
if [[ -d output ]]; then
    find output -type f -print0 | sort -z | xargs -0 sha256sum > TRACE_SHA256.txt
fi
exit "$rc"
