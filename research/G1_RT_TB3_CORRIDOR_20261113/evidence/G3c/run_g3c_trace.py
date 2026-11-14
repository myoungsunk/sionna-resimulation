"""G3c direct 400k trace. Calls the sealed G3a tracer with only ray count changed."""
import sys
from pathlib import Path

import run_g3a as g3a
from run_tb3_g1_pilot import load_runtime, read, write


RUN = Path("/run_g3c")
BASELINE = Path("/g3a")
BUNDLES = 8
BASELINE_DIGESTS = {
    "G3A.json": "c50f1d325f3387841d3bb2995a6bd33f99505fa8696fbccfcb360dad0a39f386",
    "MANIFEST.json": "5f0fd8052aee05ef3c5e05a56c270b5fc8d25935926d7b755a83dc797f4ba140",
    "PREFLIGHT.json": "13e004f7fa2ca3f894a723a8fb7589c689b27c54739926ce3b4d848008235d77",
    "RAW_SHA256.txt": "7095c7805061a33a4a20e825b27408b2bf3d5224e352a2190d9a1af29f47ba7a",
    "run_g3a.py": "6bde953ce7aa2c989484d2509461f50b3f39b983f09a8d707164a92755179880",
}


def verify(path, digest):
    if g3a.sha(path) != digest:
        raise ValueError(f"Input digest mismatch: {path}")


def preflight():
    for name, digest in BASELINE_DIGESTS.items():
        verify(BASELINE / name, digest)
    manifest = read(BASELINE / "MANIFEST.json")
    a = read(BASELINE / "G3A.json")
    if (a["status"], a["completed_positions"], a["compared_bins"], a["invalid_bins"], a["mismatched_bins"]) != (
            "PASS", 195, 50_115, 0, 0):
        raise ValueError("G3a baseline does not have full valid coverage")
    pre = read(BASELINE / "PREFLIGHT.json")
    for path, digest in manifest["input_sha256"].items():
        verify(g3a.INPUT / path, digest)
    reference = read(g3a.INPUT / "REFERENCE.json")
    contract = read(g3a.INPUT / "G3_CONTRACT.json")
    for path, digest in (reference["method_b_sha256"] | contract["source_sha256"]).items():
        verify(g3a.SOURCE / path, digest)
    verify(g3a.INPUT / "parity_gate.py", contract["parity_sha256"])
    for entry in read(g3a.INPUT / "scene/SCENE_MANIFEST.json")["geometries"].values():
        for item in entry["material_bindings"]:
            verify(g3a.INPUT / "scene" / item["ply"], item["ply_sha256"])
    for bank in read(g3a.INPUT / "FFD_RESTORE_MANIFEST.json")["banks"]:
        verify(g3a.SOURCE / bank["filename"], bank["sha256"])

    trace, np, versions = load_runtime(g3a.SOURCE)
    freq = trace.C.load_banks()[0]["freqs_hz"]
    if not np.array_equal(freq, pre["freqs_hz"]) or versions != pre["versions"]:
        raise ValueError("G3a runtime or frequency grid changed")
    if pre["solver"] != reference["block_c_solver"] | {"refraction": False}:
        raise ValueError("G3a did not use the frozen F1 configuration")
    if pre["solver"]["samples_per_src"] != 100_000 or reference["image"] != manifest["container_image"]:
        raise ValueError("Unexpected baseline sampling or image")
    tasks = g3a.task_table()
    if sum(len(task["sampled_yaws"]) for rows in tasks.values() for task in rows) != 5067:
        raise ValueError("Incomplete frozen location/yaw sample")
    expected = {f"raw/{case}/{task['tag']}.{ext}"
                for case, rows in tasks.items() for task in rows for ext in ("json", "npz")}
    actual = {}
    for line in (BASELINE / "RAW_SHA256.txt").read_text().splitlines():
        digest, rel = line.split(maxsplit=1)
        if rel in actual:
            raise ValueError(f"Duplicate checksum: {rel}")
        actual[rel] = digest
    if actual.keys() != expected:
        raise ValueError("G3a raw trace coverage mismatch")
    for rel, digest in actual.items():
        verify(BASELINE / rel, digest)

    solver = pre["solver"] | {"samples_per_src": 400_000}
    write(RUN / "PREFLIGHT.json", pre | {"solver": solver})
    write(RUN / "MANIFEST.json", dict(
        question_id="G1-RT-TB3-001", stage="G3c", role="IMPLEMENTER",
        execution_site="Snowball KMS", branch=manifest["branch"],
        frozen_spec_commit=manifest["frozen_spec_commit"], frozen_spec_blob=manifest["frozen_spec_blob"],
        governance=manifest["governance"], method_b_commit=reference["method_b_commit"],
        container_image=reference["image"], runtime_versions=versions, baseline_sha256=BASELINE_DIGESTS,
        run_input_sha256={name: g3a.sha(RUN / name) for name in ("launch_trace.sh", "run_g3c_trace.py")},
        contract_sha256=g3a.sha(g3a.INPUT / "G3_CONTRACT.json"),
        solver_100k=pre["solver"], solver_400k=solver, positions=195, bins=257, poses=5067,
        required_direct_trace_calls=50_115, workers=int(sys.argv[2]), bundles_per_case=BUNDLES,
        max_added_energy_fraction_exclusive=0.01, max_abs_delta_s_inclusive=0.002,
    ))
    for case in tasks:
        for shard in range(BUNDLES):
            print(case, shard)


if __name__ == "__main__":
    g3a.RUN, g3a.BUNDLES_PER_CASE = RUN, BUNDLES
    if sys.argv[1] == "preflight":
        preflight()
    elif sys.argv[1] == "trace":
        g3a.trace_case(sys.argv[2], int(sys.argv[3]))
    else:
        raise ValueError(f"Unexpected mode: {sys.argv[1]}")
