"""Run the frozen direct-path reference over independent frequency ranges."""
import ast
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path("/run")
OUT = ROOT / "los_parallel"
RANGES = [(0, 43), (43, 86), (86, 129), (129, 172), (172, 215), (215, 257)]


def stage():
    frozen = ROOT / "code/run_tb3_g1_pilot.py"
    source = frozen.read_text()
    node, = [node for node in ast.parse(source).body if getattr(node, "name", None) == "run_los"]
    text = "\n".join(source.splitlines()[node.lineno - 1:node.end_lineno])
    for a, b in (
        ("out):", "out, start, stop):"),
        ('freqs = banks[0]["freqs_hz"]', 'freqs = banks[0]["freqs_hz"][start:stop]'),
        ("C.set_bin(scene, banks, txp, rxp, fi, f)", "C.set_bin(scene, banks, txp, rxp, start + fi, f)"),
        ("fi % 64 == 0", "fi % 8 == 0 or fi + 1 == len(freqs)"),
    ):
        if text.count(a) != 1:
            raise ValueError(f"Unexpected reference source for {a}")
        text = text.replace(a, b)
    with (OUT / "ranged_los.py").open("x") as out:
        out.write("import time\nimport numpy as np\n" + text + "\n")


def trace_part(index):
    from ranged_los import run_los
    from run_tb3_g1_pilot import geometry_adapter, load_runtime, write
    from run_tb3_production import canary_selection, case_inputs, read

    mount = read(ROOT / "config/PRODUCTION_F1.json")["mount_deg"]
    if mount != 45:
        raise ValueError("Wrong RX mount")
    scene, anchor, poses, tasks, base, _, _ = case_inputs(ROOT / "g0", ROOT / "g7", "G-T1_A")
    _, ids = canary_selection(Path("/legacy"), base, tasks)
    if len(ids) != 332 or anchor != "A":
        raise ValueError("Wrong pilot cases")
    rotated = [poses[i] | {"yaw_body_deg": poses[i]["yaw_body_deg"] + mount} for i in sorted(ids)]
    trace, np, versions = load_runtime(Path("/ref"))
    factory, loader = geometry_adapter(trace, scene, ROOT / "g0/scene")
    begin, end = RANGES[index]
    directory = OUT / f"bins_{index}"
    directory.mkdir()
    receipt = run_los(trace, np, factory(anchor_x_m=scene["anchors_xyz_m"][anchor][0]),
                      loader, rotated, directory, begin, end)
    write(directory / "REFERENCE_RESULT.json", dict(
        receipt, mount_deg=mount, pose_ids=sorted(ids), start=begin, stop=end, versions=versions))


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def merge():
    import numpy as np

    directories = [OUT / f"bins_{i}" for i in range(len(RANGES))]
    recs = [json.loads((d / "REFERENCE_RESULT.json").read_text()) for d in directories]
    assert [(r["start"], r["stop"]) for r in recs] == RANGES
    assert len(recs[0]["pose_ids"]) == 332
    assert all(r["pose_ids"] == recs[0]["pose_ids"] and r["mount_deg"] == 45 for r in recs)
    assert all(r["solver"] == recs[0]["solver"] and r["versions"] == recs[0]["versions"] for r in recs)
    pieces = []
    for d, (start, stop) in zip(directories, RANGES, strict=True):
        with np.load(d / "PATHS_LoS.npz", allow_pickle=False) as arr:
            assert arr["a"].shape == (332, stop - start, 2, 2)
            pieces.append(dict(arr))
    arrays = {key: np.concatenate([p[key] for p in pieces], axis=int(key != "freqs_hz"))
              for key in pieces[0]}
    assert arrays["a"].shape == (332, 257, 2, 2)
    assert np.all(np.diff(arrays["freqs_hz"]) > 0) and np.all(arrays["counts"] == 1)
    reference = OUT / "reference"
    reference.mkdir()
    np.savez_compressed(reference / "PATHS_LoS.npz", **arrays)
    np.save(reference / "H_LoS.npy", np.concatenate(
        [np.load(d / "H_LoS.npy", allow_pickle=False) for d in directories], axis=1))
    record = dict(mount_deg=45, poses=332, bins=257, pose_ids=recs[0]["pose_ids"],
                  solver=recs[0]["solver"], versions=recs[0]["versions"], shards=[
                      dict(start=r["start"], stop=r["stop"], wall_s=r["wall_s"],
                           sha256=sha(d / "PATHS_LoS.npz"))
                      for d, r in zip(directories, recs, strict=True)],
                  original_los_sha256=sha(ROOT / "code/run_tb3_g1_pilot.py"),
                  ranged_los_sha256=sha(OUT / "ranged_los.py"),
                  output_sha256=sha(reference / "PATHS_LoS.npz"))
    with (reference / "REFERENCE_RESULT.json").open("x") as f:
        json.dump(record, f, indent=2)
        f.write("\n")


if __name__ == "__main__":
    action, *args = sys.argv[1:]
    if action == "stage":
        stage()
    elif action == "trace":
        trace_part(int(args[0]))
    elif action == "merge":
        merge()
    else:
        raise ValueError(action)
