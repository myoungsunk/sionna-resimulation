"""Recover input-receipt zips of an earlier MBVAR run from its aggregate artifact, verified against that run's MANIFEST.

  python mbvar_recover_receipts.py <results_dir_of_source_run> <dir_with_downloaded_artifact_files>

Copies every <PREFIX>_INPUTS_*.zip listed in MANIFEST.output_sha256 into the results dir, only if its sha256 matches.
Exits 1 if any listed receipt is missing or mismatched. Never overwrites an existing file with different content.
(AMENDMENT-009 run 40992623257: the publish step only matched S1V3_INPUTS_*.zip, so the S1V4 receipts were not committed.)
"""
import hashlib, json, shutil, sys
from pathlib import Path

res, art = Path(sys.argv[1]), Path(sys.argv[2])
want = {k: v for k, v in json.loads((res / "MANIFEST.json").read_text())["output_sha256"].items() if "_INPUTS_" in k and k.endswith(".zip")}
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
bad = []
for name, h in sorted(want.items()):
    dst = res / name
    if dst.exists():
        if sha(dst) != h:
            bad.append(f"{name}: existing file hash mismatch")
        continue
    src = next(art.rglob(name), None)
    if src is None or sha(src) != h:
        bad.append(f"{name}: {'missing' if src is None else 'artifact hash mismatch'}")
        continue
    shutil.copyfile(src, dst); print("recovered", name, h[:12])
print(f"{len(want)} receipts listed in MANIFEST; problems: {bad}")
sys.exit(1 if bad or not want else 0)
