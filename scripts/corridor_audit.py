"""Retrospective audit of every corridor sweep output in the repository with the same checks used for the office run.

For each receipt found under results/CORRIDOR_*: files, receipt contract (yaws, 257 bins, solver config, adapter and bank hashes), H and sweep.npz consistency,
LoS present at every call (the corridor is always line-of-sight), the anchor in SETUP_SNAPSHOT.json versus the anchor implied by the directory, duplicate positions.
The runner hash is NOT compared (the runner evolved during the campaign); the distinct hashes are listed instead.   python scripts/corridor_audit.py
"""
import glob
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import sweep_verify as sv  # noqa: E402
from qclean_uwb.runcheck import Expect, check_position  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

# anchor implied by the directory
ANCHOR_BY_DIR = {"CORRIDOR_SWEEP_20261006": (4.0, 0.0), "CORRIDOR_SCAN_20261006": (4.0, 0.0), "CORRIDOR_SCAN2_20261007": (4.0, 0.0),
                 "CORRIDOR_ANCHOR2_20261007": (4.0, -0.4), "CORRIDOR_ANCHOR2B_20261007": (4.0, -0.4)}


def main():
    solver = json.loads(sv.SOLVER_SOURCE.read_text())["solver"]
    manifest = json.loads(sv.BANK_MANIFEST.read_text())["npz_sha256"]
    bank_sha = {f"{n}_bank.npz": manifest[f"{n}_bank.npz"] for n in sv.PORTS}
    adapter = sv.sha256_file(sv.ADAPTER)
    with np.load(ROOT / "LP_plus45_bank.npz") as z:
        freq = z["freqs_hz"]
    mats = [(n, *sv.CORRIDOR_MATERIALS[n]) for n in CorridorSetup().surfaces()]
    rows, seen = [], defaultdict(list)
    runner_hashes = defaultdict(Counter)
    for rec in sorted(glob.glob(str(ROOT / "results" / "CORRIDOR_*" / "**" / "*receipt*.json"), recursive=True)):
        rp = Path(rec)
        top = rp.relative_to(ROOT / "results").parts[0]
        if top not in ANCHOR_BY_DIR:
            continue
        d = json.loads(rp.read_text())
        tag = d.get("tag") or rp.stem.replace("_receipt", "")
        xy = tuple(d["robot_xy_m"])
        ax, ay = ANCHOR_BY_DIR[top]
        setup = CorridorSetup(anchor_x_m=ax, anchor_y_m=ay)
        exp = Expect(yaw_deg=list(setup.yaw_sweep_deg), bin_stride=1, freq_grid_hz=freq, solver=solver, adapter_sha256=adapter, bank_sha256=bank_sha, anchor_m=setup.anchor_position.tolist(),
                     setup_config_sha256=setup.snapshot()["config_sha256"], runner_sha256=None, materials=mats, los_expected=lambda x, y: True, require_scene_files=6, npz_optional=("objects_cat",) if top == "CORRIDOR_SWEEP_20261006" else ())
        issues = check_position(rp.parent, tag if (rp.parent / f"{tag}_H.npy").exists() else tag, xy, exp)
        issues = [i for i in issues if not (i.startswith("receipt lacks") and False)]
        rows.append(dict(dir=top, folder=str(rp.parent.relative_to(ROOT)), tag=tag, xy=list(xy), issues=issues))
        seen[(top, xy)].append(str(rp.parent.relative_to(ROOT)))
        runner_hashes[top][d.get("runner_sha256", "none")[:10]] += 1
    dup = {f"{k[0]} {k[1]}": v for k, v in seen.items() if len(v) > 1}
    by_dir = {}
    for r in rows:
        e = by_dir.setdefault(r["dir"], dict(n=0, valid=0, issue_kinds=Counter()))
        e["n"] += 1
        e["valid"] += not r["issues"]
        for i in r["issues"]:
            e["issue_kinds"][i.split(":")[0][:90]] += 1
    out = dict(by_dir={k: dict(n=v["n"], valid=v["valid"], issue_kinds=dict(v["issue_kinds"])) for k, v in by_dir.items()}, duplicates=dup,
               runner_hashes={k: dict(v) for k, v in runner_hashes.items()}, invalid=[r for r in rows if r["issues"]])
    (ROOT / "results" / "CORRIDOR_AUDIT_20261008.json").write_text(json.dumps(out, indent=1))
    for k, v in out["by_dir"].items():
        print(f"{k:28s} positions {v['n']:3d} valid {v['valid']:3d}  issues {v['issue_kinds']}")
    print("duplicates:", dup or "none")
    print("runner hashes:", out["runner_hashes"])
    for r in out["invalid"][:12]:
        print("  INVALID", r["folder"], r["issues"][:3])


if __name__ == "__main__":
    main()
