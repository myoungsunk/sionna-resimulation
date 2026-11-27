"""Check a copied Sweep Extension run against its Snowball completion receipt."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


COUNTS = {"A": (125, 4500), "B": (192, 6912), "C": (9, 1296)}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(root, run_set):
    positions, poses = COUNTS[run_set]
    done = read(root / "RUN_SUCCESS.json")
    require(done["status"] == "PASS" and done["run_set"] == run_set, "Run receipt differs")
    result = root / "results"
    completion = read(result / "completion.json")
    require(completion["status"] == "PASS", "Completion gate differs")
    require((completion["trace_positions"], completion["poses"]) == (positions, poses), "Coverage differs")
    require(completion["shared_trace"] and completion["extra_export_solver_calls"] == 0, "Trace provenance differs")
    require(completion["raw_traces"] == positions, "Raw trace coverage differs")
    manifest = completion["output_sha256"]
    sizes = completion["output_bytes"]
    filenames = {path.relative_to(result).as_posix() for path in result.rglob("*") if path.is_file()}
    require(filenames == set(manifest) | {"completion.json"}, "Result file coverage differs")
    for name, digest in manifest.items():
        path = result / name
        require(path.stat().st_size == sizes[name] and sha256(path) == digest, f"Result file differs: {name}")
    require(sha256(root / "inputs/RUN_CONTRACT.json") == completion["run_contract_sha256"], "Input contract differs")
    require(sha256(root / "BASELINE_PASS.json") == completion["baseline_pass_sha256"], "G0 receipt differs")
    baseline = read(root / "BASELINE_PASS.json")
    rows = read(root / "BASELINE_BYTE_CHECK.json")
    require(baseline["status"] == rows["status"] == "PASS" and baseline["poses"] == 9
            and baseline["max_abs_delta_h"] == 0 and all(row["byte_equal"] for row in rows["checks"]), "G0 differs")
    for gate in ("G4", "G8"):
        require(read(result / f"{gate}.json")["status"] == "PASS", f"{gate} differs")
    if run_set == "C":
        gc = read(root / "GC.json")
        require(gc["status"] == "PASS" and gc["rows"] == 324, "GC differs")
    shape = (poses, 257, 2, 2)
    for channel in ("H_full.npy", "H_LoS.npy"):
        array = np.load(result / "H/BLOCKC_B" / channel, mmap_mode="r", allow_pickle=False)
        require(array.shape == shape and array.dtype == np.complex128, f"Channel shape differs: {channel}")
    return {"status": "PASS", "run_set": run_set, "run_id": root.name, "positions": positions, "poses": poses,
            "channel_shape": shape, "output_files_checked": len(manifest), "output_bytes": sum(sizes.values()),
            "wall_s": done["wall_s"], "production_wall_s": done["production_wall_s"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("run_set", choices=COUNTS)
    args = parser.parse_args()
    receipt = verify(args.root, args.run_set)
    output = args.root / "LOCAL_VERIFICATION.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
