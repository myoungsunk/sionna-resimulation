set -euo pipefail
base=/home/KMS/G1_RT_TB3_CORRIDOR_G3_20261113T073918Z
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
rt=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
audit=/home/KMS/G1_RT_TB3_CORRIDOR_G3_AUDIT_20261113T084005Z
image=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
cd "$audit"
python3 -c 'import json; from pathlib import Path; base=Path("/home/KMS/G1_RT_TB3_CORRIDOR_G3_20261113T073918Z"); bad={r["tag"] for r in json.loads((base/"analysis/G3.json").read_text())["pooled"]["unusable"]}; tasks=json.loads((base/"input/cases/G-T2_A.json").read_text()); selected=[t for t in tasks if t["tag"] in bad]; assert len(selected)==5; Path("known_failures.json").write_text(json.dumps(selected))'
date -u +%FT%TZ
docker run --rm --pull=never --network none --cpus 1 --user "$(id -u):$(id -g)" --workdir /ref --mount "type=bind,src=$base,dst=/g3,readonly" --mount "type=bind,src=$ref,dst=/ref,readonly" --mount "type=bind,src=$rt,dst=/runtime_packages,readonly" --mount "type=bind,src=$audit,dst=/audit" -e PYTHONPATH=/g3/input:/runtime_packages:/ref/src -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e OMP_NUM_THREADS=1 "$image" bash -eu -c '
python -u /audit/check_tb3_production_bins.py --source /ref --inputs /g3/input --case G-T2_A --tasks /audit/known_failures.json --traces /g3/output/G-T2_A/node_interpolation --out /audit/targeted.json --bins 139 143
python -u /audit/check_tb3_production_bins.py --source /ref --inputs /g3/input --case G-T2_A --tasks /g3/input/cases/G-T2_A.json --traces /g3/output/G-T2_A/node_interpolation --out /audit/seeded.json
'
date -u +%FT%TZ
sha256sum check_tb3_production_bins.py known_failures.json targeted.json seeded.json
