"""Read-only amended-math control on the original STOP canary.

Never opens a simulator or writes original evidence. A successful recheck is
NOT a new native canary PASS and does not approve the other 14 poses.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from precision_qa import evaluate_precision
from producer import THRESHOLDS


def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda:file.read(1048576),b""):
            h.update(block)
    return h.hexdigest()


def main(old, output):
    m=json.loads((old/"MANIFEST.json").read_text())
    if m["status"]!="STOP_MISMATCH":
        raise ValueError("not the preserved original STOP record")
    if m.get("case")!="R4_aB_m0" or m["pose"]["pose_id"]!=194:
        raise ValueError("not the frozen first canary")
    raw=old/"RAW.npz"
    if sha(raw)!=m["raw_sha256"]:
        raise ValueError("original raw SHA mismatch")
    old_errors=m["archive_los_error"]
    if not 2e-5 < old_errors["relative_l2"] < 3e-5:
        raise ValueError("different failure event: halt review")
    with np.load(raw,allow_pickle=False) as z:
        arrays={key:z[key] for key in z.files}
    result=evaluate_precision(arrays,THRESHOLDS)
    arr=result.pop("direct_legacy32")
    output.mkdir(parents=True,exist_ok=False)
    receipt=dict(mode="READ_ONLY_REEVALUATION_NO_SOLVER",
        original_status=m["status"], original_raw_sha256=m["raw_sha256"],
        original_manifest_sha256=sha(old/"MANIFEST.json"),
        amended_math_gate=result,
        preserved_original_stop=True,
        new_SM0_canary_executed=False,
        expansion_authorized=False,
        legacy_direct_shape=list(arr.shape))
    (output/"RECHECK_RESULT.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps(receipt,indent=2))
    if not result["pass_all"]:
        raise RuntimeError("Amended math FAIL on original raw; do not request new native canary")


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("old",type=Path,help="unmodified CANARY_R4_194_001")
    ap.add_argument("out",type=Path,help="new output folder only")
    a=ap.parse_args()
    main(a.old,a.out)
