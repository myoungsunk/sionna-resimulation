"""Check the published M5 receipts and evidence bytes from any checkout."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STAGE_OUTPUTS = (13, 1, 44, 23)
STAGE_NPZ = (12, 0, 41, 20)
LOCKED_SOURCE_NAMES = {"run_hfki.py", "hfki_replay.py", "hfki_predict.py"}
LOCAL_STAGE3_SOURCE = "run_stage3.py"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def compare(path, expected):
    require(digest(path) == expected, f"SHA-256 differs: {path}")


def check_sources(records, source_dir):
    originals = {Path(record["path"].replace("\\", "/")).name: record["sha256"]
                 for record in records}
    for name in sorted(LOCKED_SOURCE_NAMES):
        compare(source_dir / name, originals[name])


def check_stage(index, directory, plan_sha):
    contract_path = directory / "RUN_CONTRACT.json"
    execution_path = directory / "EXECUTION.json"
    contract, execution = read(contract_path), read(execution_path)
    verification = read(directory / "VERIFICATION.json")
    require(contract["stage"] == execution["stage"] == verification["stage"] == index,
            f"Stage identity differs: {directory}")
    require(contract["plan"]["sha256"] == plan_sha, f"Plan identity differs: {directory}")
    require(execution["status"] == "PASS_EXECUTION" and execution["exit_code"] == 0
            and verification["status"] == "PASS_VERIFICATION",
            f"Unsuccessful stage receipts: {directory}")
    compare(contract_path, execution["contract_sha256"])
    for name, expected in verification["inputs_and_execution"].items():
        compare(directory / name, expected)
    expected = execution["outputs"]
    require(len(expected) == verification["output_hashes"] == STAGE_OUTPUTS[index],
            f"Output count differs: {directory}")
    npz = {path.relative_to(directory).as_posix() for path in directory.rglob("*.npz")}
    require(npz == {name for name in expected if name.endswith(".npz")}
            and len(npz) == STAGE_NPZ[index], f"NPZ inventory differs: {directory}")
    for name, expected_sha in expected.items():
        compare(directory / name, expected_sha)
    if index < 3:
        check_sources(contract["sources"], ROOT)
    else:
        compare(ROOT / LOCAL_STAGE3_SOURCE, contract["source"]["sha256"])
        for stage, parent in contract["parents"].items():
            for name, expected_record in parent.items():
                compare(directory.parent / f"stage{stage}" / name, expected_record["sha256"])
        for records in contract["online_packets"].values():
            for record in records.values():
                name = Path(record["path"].replace("\\", "/")).name
                compare(directory.parent / "stage0" / name, record["sha256"])
    print(f"Stage {index}: {len(expected)} output hashes, {len(npz)} NPZ")


def main():
    manifest = ROOT / "SHA256SUMS"
    declared = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        expected, name = line.split("  ", maxsplit=1)
        compare(ROOT / name, expected)
        declared.add(name)
    actual = {path.relative_to(ROOT).as_posix() for path in ROOT.rglob("*")
              if path.is_file() and path != manifest}
    require(actual == declared, "Published file inventory differs")
    plan_sha = digest(ROOT.parent / "PLAN_M5_HFKI_STAGED_KO.md")
    for index in range(4):
        check_stage(index, ROOT / "attempt_02" / f"stage{index}", plan_sha)
    failed = ROOT / "stage0"
    contract = read(failed / "RUN_CONTRACT.json")
    execution = read(failed / "EXECUTION.json")
    require(execution["status"] == "FAIL_EXECUTION", "First Stage 0 receipt identity differs")
    compare(failed / "RUN_CONTRACT.json", execution["contract_sha256"])
    check_sources(contract["sources"], failed / "failed_sources")
    readiness = ROOT / "seed_readiness"
    receipt = read(readiness / "SEED_DATA_READINESS.json")
    compare(readiness / "check_seed_data.py", receipt["script_sha256"])
    print(f"Publication integrity passed: {len(declared)} files plus manifest")


if __name__ == "__main__":
    main()
