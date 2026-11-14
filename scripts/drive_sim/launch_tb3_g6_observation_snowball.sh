#!/usr/bin/env bash
set -euo pipefail
umask 077
r=/home/KMS/G1_RT_TB3_G6_OBSERVATION_20261114T231100KST_nKAcNg
p=/home/KMS/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa
g6=/home/KMS/G1_RT_TB3_G6_20261114T124634Z_9ElGTD
image=/home/KMS/G1_RT_TB3_G6_IMAGE_20261114T135937Z_yqvk1k/G6_IMAGE_DIAGNOSTIC.json
ref=/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source
runtime=/home/KMS/COOL_DIJKSTRA_20261007_01a11582/runtime_packages
img=sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f
cases=(G-T1_A G-T1_B G-T1_C G-T2_A G-T2_B G-T2_C G-V_A G-V_B G-V_C)
cd "$r"
test "$(id -un)" = KMS
test ! -e "$p/results/seal/UNSEAL.json"
test ! -e receipts/STARTED_UTC.txt
sha256sum "$p/results/seal/SEAL_MANIFEST.json" "$p/results/seal/ACCESS_LOG.jsonl" > receipts/SEAL_BEFORE.sha256
sha256sum code/*.py code/*.sh "$image" > receipts/RUN_INPUTS.sha256
cp "$p/results/seal/ACCESS_LOG.jsonl" receipts/ACCESS_BEFORE.jsonl
cmd=(docker run --rm --pull=never --network none --cpus 12 --cpu-shares 192
  --name "$(basename "$r")" --user "$(id -u):$(id -g)" --workdir /ref
  -e HOME=/run/cache -e TMPDIR=/run/scratch -e PYTHONDONTWRITEBYTECODE=1
  -e PYTHONPATH=/run/code:/g6code:/production/code:/runtime_packages:/ref:/ref/src
  -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1
  -v "$r:/run" -v "$ref:/ref:ro" -v "$runtime:/runtime_packages:ro"
  -v "$g6/code:/g6code:ro" -v "$g6/selected:/g6/selected:ro" -v "$g6/traces:/g6/traces:ro"
  -v "$g6/G6.json:/g6/G6.json:ro" -v "$image:/image.json:ro"
  -v "$p/code:/production/code:ro" -v "$p/g0:/production/g0:ro" -v "$p/g7:/production/g7:ro"
  -v "$p/config:/production/config:ro" -v "$p/frozen:/production/frozen:ro"
  -v "$p/results/GENERATION_RESULT.json:/production/results/GENERATION_RESULT.json:ro"
  -v "$p/results/CASES.json:/production/results/CASES.json:ro"
  -v "$p/results/seal/SEAL_MANIFEST.json:/production/results/seal/SEAL_MANIFEST.json:ro")
for c in "${cases[@]}"; do
  cmd+=(-v "$p/results/H/$c/H_full.npy:/production/results/H/$c/H_full.npy:ro"
        -v "$p/results/H/$c/MANIFEST.json:/production/results/H/$c/MANIFEST.json:ro"
        -v "$p/results/paths/$c/TRACE_RECEIPTS.json:/production/results/paths/$c/TRACE_RECEIPTS.json:ro")
done
cmd+=(--entrypoint /usr/bin/nice "$img" -n 12 /bin/bash /run/code/drive_tb3_g6_observation.sh)
printf '%q ' "${cmd[@]}" > receipts/COMMAND.txt
printf '\n' >> receipts/COMMAND.txt
record() {
  python3 - "$p" "$r" "$1" "$2" <<'PY'
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
import sys
from pathlib import Path
p, r = map(Path, sys.argv[1:3])
root = p / "results"
status = int(sys.argv[4])
sealed = [f"H/{g}_{a}/H_full.npy" for g in ("G-T2", "G-V") for a in "ABC"]
report = r / "G6_OBSERVATION_DIAGNOSTIC.json"
assert not (root / "seal/UNSEAL.json").exists()
def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

entry = dict(utc=datetime.now(timezone.utc).isoformat(), actor="KMS",
    operation="G6_OBSERVATION_" + sys.argv[3], gate="G6", run_id=r.name,
    script="diagnose_tb3_g6_observation.py", script_sha256=sha256(r / "code/diagnose_tb3_g6_observation.py"),
    purpose="paired noise-free signed s sensitivity to exact image-law delays at original failing XY; no heading-error calculation",
    paths=sealed, scope="read-only H_full, original failing XY and all associated production pose IDs",
    seal_manifest_sha256=sha256(root / "seal/SEAL_MANIFEST.json"), seal_status="SEALED",
    exit_code=None if sys.argv[3] == "START" else status, report_sha256=sha256(report) if report.is_file() else None)
with (root / "seal/ACCESS_LOG.jsonl").open("a", encoding="utf-8") as stream:
    fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
    stream.write(json.dumps(entry) + "\n")
    stream.flush()
    os.fsync(stream.fileno())
PY
}
record START 0
date -u +%FT%TZ > receipts/STARTED_UTC.txt
rc=0
"${cmd[@]}" > logs/EXECUTION.log 2>&1 || rc=$?
if ((rc == 0)); then
  python3 code/summarize_tb3_g6_observation.py "$image" parts G6_OBSERVATION_DIAGNOSTIC.json >> logs/EXECUTION.log 2>&1 || rc=$?
fi
date -u +%FT%TZ > receipts/FINISHED_UTC.txt
printf '%s\n' "$rc" > receipts/EXIT_CODE.txt
record FINISH "$rc"
test ! -e "$p/results/seal/UNSEAL.json"
sha256sum "$p/results/seal/SEAL_MANIFEST.json" "$p/results/seal/ACCESS_LOG.jsonl" > receipts/SEAL_AFTER.sha256
cmp <(head -1 receipts/SEAL_BEFORE.sha256) <(head -1 receipts/SEAL_AFTER.sha256)
python3 - "$p" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
old = Path("receipts/ACCESS_BEFORE.jsonl").read_bytes()
new = (p / "results/seal/ACCESS_LOG.jsonl").read_bytes()
assert new.startswith(old)
add = new[len(old):]
entries = [json.loads(line) for line in add.splitlines()]
assert [e["operation"] for e in entries if e.get("run_id") == Path.cwd().name] == [
    "G6_OBSERVATION_START", "G6_OBSERVATION_FINISH"]
with Path("receipts/ACCESS_APPEND.jsonl").open("xb") as stream:
    stream.write(add)
PY
if ((rc == 0)); then
  sha256sum G6_OBSERVATION_DIAGNOSTIC.json > receipts/RESULT.sha256
fi
exit "$rc"
