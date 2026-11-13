set -eu
base=/home/KMS/G1_RT_TB3_CORRIDOR_G3_20261113T073918Z
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
rt=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
diag=/home/KMS/G1_RT_TB3_CORRIDOR_G3_CAUSE_20261113T082528Z
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
date -u
sha256sum "$diag/diagnose_tb3_g3_candidate.py" "$base/analysis/G3.json"
docker run --rm --network none --cpus 5 --user "$(id -u):$(id -g)" --workdir /ref --mount "type=bind,src=$base,dst=/g3,readonly" --mount "type=bind,src=$ref,dst=/ref,readonly" --mount "type=bind,src=$rt,dst=/runtime_packages,readonly" --mount "type=bind,src=$diag,dst=/diag" -e PYTHONPATH=/diag:/g3/input:/runtime_packages:/ref/src:/ref -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e OMP_NUM_THREADS=1 "$image" bash -c 'tags="x6.0000_y0.4700 x6.0000_y-0.3100 x6.0000_y-0.3300 x6.0003_y0.4698 x6.3521_y0.4684"; for tag in $tags; do python -u /diag/diagnose_tb3_g3_candidate.py "$tag" --out "/diag/$tag.json" || exit; done'
date -u
sha256sum "$diag/"*.json
