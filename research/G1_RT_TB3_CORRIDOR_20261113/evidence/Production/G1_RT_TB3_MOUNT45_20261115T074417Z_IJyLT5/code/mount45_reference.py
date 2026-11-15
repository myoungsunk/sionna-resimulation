"""Evaluate the G1 pilot LoS with mount-45 orientation and full 257 bins."""
import sys
from pathlib import Path

from run_tb3_g1_pilot import geometry_adapter, load_runtime, run_los, write
from run_tb3_production import canary_selection, case_inputs, read, sha

root, source, legacy = map(Path, sys.argv[1:])
mount = read(root / "config/PRODUCTION_F1.json")["mount_deg"]
assert mount == 45
scene, anchor, poses, tasks, base, _, _ = case_inputs(root / "g0", root / "g7", "G-T1_A")
_, ids = canary_selection(legacy, base, tasks)
assert len(ids) == 332 and anchor == "A"
rotated = [poses[i] | {"yaw_body_deg": poses[i]["yaw_body_deg"] + mount} for i in sorted(ids)]
trace, np, versions = load_runtime(source)
factory, loader = geometry_adapter(trace, scene, root / "g0/scene")
out = root / "los_reference"
out.mkdir()
receipt = run_los(trace, np, factory(anchor_x_m=scene["anchors_xyz_m"][anchor][0]), loader, rotated, out)
write(out / "REFERENCE_RESULT.json", dict(
    receipt, mount_deg=mount, poses=len(rotated), versions=versions, code_sha256=sha(Path(__file__)),
    pose_ids=sorted(ids), output_sha256=sha(out / "PATHS_LoS.npz"),
))
