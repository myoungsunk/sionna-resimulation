"""Check the mount +45 publication and its archived execution records."""

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RECEIPTS = (
    ("comparison/execution", "comparison/RUN_CONTRACT.json", "contract_sha256", "outputs_sha256"),
    *((
        f"diagnostics/{stage}",
        "diagnostics/RUN_CONTRACT.json",
        "run_contract_sha256",
        "outputs",
    ) for stage in ("d0", "d5", "d1", "d2", "d3")),
    *((
        f"{stage}/execution",
        f"{stage}/RUN_CONTRACT.json",
        "contract_sha256",
        "outputs",
    ) for stage in ("structure", "d4", "ks", "followup", "c7", "c8", "r2_r5", "anchor_a_final")),
    ("l2/comparison/execution", "l2/comparison/RUN_CONTRACT.json", "contract_sha256", "outputs_sha256"),
    ("l2/structure", "l2/RUN_CONTRACT.json", "contract_sha256", "outputs"),
)


def load(path):
    return json.loads(path.read_bytes())


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(condition, description):
    if not condition:
        raise ValueError(description)


def check_file(path, expected, size=None):
    if size is not None and path.stat().st_size != size:
        raise ValueError(f"Size mismatch for {path}. Hydrate Git LFS data before verification.")
    require(digest(path) == expected, f"SHA-256 mismatch: {path}")


def check_receipts():
    outputs_count = 0
    for directory, contract, contract_key, outputs_key in RECEIPTS:
        directory = ROOT / directory
        receipt = load(directory / "EXECUTION.json")
        require(
            receipt["exit_code"] == 0 and receipt["status"].startswith("PASS"),
            f"Execution failure: {directory}",
        )
        check_file(ROOT / contract, receipt[contract_key])
        for name, expected in receipt[outputs_key].items():
            check_file(directory / name, expected)
            outputs_count += 1
    for name in ("anchor_a", "anchor_a_retry"):
        directory = ROOT / name
        receipt = load(directory / "execution/EXECUTION.json")
        require(receipt["status"] == "FAIL_EXECUTION", f"Unexpected retry state: {name}")
        require(receipt["exit_code"] != 0, f"Unexpected retry exit code: {name}")
        check_file(directory / "RUN_CONTRACT.json", receipt["contract_sha256"])
        for path, expected in receipt["outputs"].items():
            check_file(directory / "execution" / path, expected)
    observer = load(ROOT / "OBSERVER_RESULTS.json")
    require(observer["status"] == "PASS", "Observer verification failed")
    check_file(ROOT / "OBSERVER_CONTRACT.json", observer["contract_sha256"])
    for route, result in observer["routes"].items():
        check_file(ROOT / f"{route}_observer_evidence.npz", result["evidence_sha256"])
    training = load(ROOT / "training/FIT_RECEIPT.json")
    require(training["status"] == "PASS", "Training verification failed")
    check_file(ROOT / "training/RUN_CONTRACT.json", training["contract_sha256"])
    for name, expected in training["outputs_sha256"].items():
        check_file(ROOT / "training" / name, expected)
    return outputs_count


def main():
    manifest = load(ROOT / "PUBLICATION_MANIFEST.json")
    for name, entry in manifest["files"].items():
        check_file(ROOT / name, entry["sha256"], entry["size_bytes"])
    report = (ROOT / "CHECKLIST_STATUS_KO.md").read_text(encoding="utf-8")
    links = re.findall(r"\[[^\]\n]+\]\(([^)]+)\)", report)
    for name in links:
        require((ROOT / name).is_file(), f"Missing report link: {name}")
    reference_index = load(ROOT / "FROZEN_INPUTS_INDEX.json")
    for entry in reference_index["frozen_references"]:
        if entry["kind"] == "bundled":
            name = entry["path"]
            expected = {"sha256": entry["sha256"], "size_bytes": entry["size_bytes"]}
            require(manifest["files"].get(name) == expected, f"Input index mismatch: {name}")
    output_count = check_receipts()
    print(f"PASS {len(manifest['files'])} files, {len(links)} report links")
    print(f"PASS {output_count} output hashes across {len(RECEIPTS)} successful executions")
    print("PASS observer, training, and the two recorded anchor-A failed attempts")


if __name__ == "__main__":
    main()
