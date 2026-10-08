"""Verify sweep outputs against the REQUESTED contract (office strict, corridor audit).

  request   create or compare RUN_REQUEST.json (the contract of one output directory; a different request on the same directory is refused)
  position  exit 0 only if one position folder is fully valid under the request
  run       all requested positions valid, none missing/duplicated/unexpected; writes VERIFY.json

Examples:
  python3 scripts/sweep_verify.py run --scenario office --run-dir results/OFFICE_RUN_20261008 --positions results/OFFICE_RUN_PLAN_20261008/positions_all.txt
  python3 scripts/sweep_verify.py position --scenario office --run-dir DIR --x 5.0 --y 0.75
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.runcheck import Expect, check_position, check_run, sha256_file  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402
from qclean_uwb.scenarios.office import OfficeSetup  # noqa: E402

SOLVER_SOURCE = ROOT / "results" / "SIONNA_NATIVE41_REFRESH_20260925_01a0d84e" / "CONFIG.json"
BANK_MANIFEST = ROOT / "results" / "SIONNA_G2_FFD_NOFLIP_20260924_01a0d30b" / "bank" / "BANK_MANIFEST.json"
RUNNER = ROOT / "scripts" / "corridor_sionna_run.py"
ADAPTER = ROOT / "scripts" / "g2_completion" / "sionna_native_runtime.py"
PORTS = ("LP_plus45", "LP_minus45")
CORRIDOR_MATERIALS = {"floor": ("concrete", 0.2), "ceiling": ("concrete", 0.2), "end_x_min": ("concrete", 0.2), "end_x_max": ("concrete", 0.2),
                      "wall_y_neg": ("plasterboard", 0.0125), "wall_y_pos": ("plasterboard", 0.0125)}  # same table as scripts/corridor_sionna_run.py


def read_positions(path: Path) -> list:
    return [(float(t[0]), float(t[1])) for t in (ln.split() for ln in Path(path).read_text().splitlines()) if len(t) >= 2]


def build_expect(args) -> tuple:
    solver = json.loads(SOLVER_SOURCE.read_text())["solver"]
    manifest = json.loads(BANK_MANIFEST.read_text())["npz_sha256"]
    bank_sha = {f"{n}_bank.npz": manifest[f"{n}_bank.npz"] for n in PORTS}
    with np.load(ROOT / "LP_plus45_bank.npz") as z:
        freq = z["freqs_hz"]
    over = {k: v for k, v in (("anchor_x_m", args.anchor_x), ("anchor_y_m", args.anchor_y)) if v is not None}
    if args.scenario == "office":
        setup = OfficeSetup(**over)
        mats = [(o["name"], o["material"], o["thickness_m"]) for o in setup.objects()]
        los = lambda x, y: setup.los_status(x, y)["clear"]
        n_scene = len(mats)
    else:
        setup = CorridorSetup(**over)
        mats = [(n, *CORRIDOR_MATERIALS[n]) for n in setup.surfaces()]
        los = lambda x, y: True
        n_scene = len(mats)
    yaws = list(setup.yaw_sweep_deg)
    exp = Expect(yaw_deg=yaws, bin_stride=args.bin_stride, freq_grid_hz=freq, solver=solver, adapter_sha256=sha256_file(ADAPTER), bank_sha256=bank_sha,
                 anchor_m=setup.anchor_position.tolist(), robot_position=setup.robot_position, setup_config_sha256=setup.snapshot()["config_sha256"],
                 runner_sha256=None if args.allow_runner_change else sha256_file(RUNNER), materials=mats, los_expected=los, require_scene_files=n_scene, scenario=args.scenario)
    return setup, exp


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=("request", "position", "run"))
    ap.add_argument("--scenario", choices=("office", "corridor"), required=True)
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--positions", type=Path)
    ap.add_argument("--tag-prefix", default=None, help="default: 'office_' for the office, 'x' for the corridor (tag = prefix + x{x}_y{y})")
    ap.add_argument("--bin-stride", type=int, default=1)
    ap.add_argument("--anchor-x", type=float, default=None)
    ap.add_argument("--anchor-y", type=float, default=None)
    ap.add_argument("--allow-runner-change", action="store_true", help="do not compare the runner hash (results made by an older runner)")
    ap.add_argument("--x", type=float)
    ap.add_argument("--y", type=float)
    ap.add_argument("--expect-n", type=int, default=None)
    args = ap.parse_args()
    prefix = args.tag_prefix if args.tag_prefix is not None else ("office_" if args.scenario == "office" else "")
    tag_fn = lambda x, y: f"{prefix}x{x}_y{y}" if args.scenario == "office" else f"{prefix}x{x}_y{y}"
    setup, exp = build_expect(args)
    if args.mode == "request":
        pos = read_positions(args.positions)
        req = dict(scenario=args.scenario, positions=pos, positions_file_sha256=sha256_file(args.positions), bin_stride=args.bin_stride, yaw_deg=exp.yaw_deg, solver=exp.solver,
                   setup_config_sha256=exp.setup_config_sha256, runner_sha256=exp.runner_sha256, adapter_sha256=exp.adapter_sha256, bank_sha256=exp.bank_sha256, tag_prefix=prefix)
        path = args.run_dir / "RUN_REQUEST.json"
        args.run_dir.mkdir(parents=True, exist_ok=True)
        if path.exists():
            old = json.loads(path.read_text())
            diff = [k for k in req if old.get(k) != json.loads(json.dumps(req[k]))]
            if diff:
                print(f"REQUEST_MISMATCH: {args.run_dir} was started with a different request ({diff}); existing results are kept, use another --run-dir or restore the original settings", file=sys.stderr)
                raise SystemExit(2)
            print("request matches the existing RUN_REQUEST.json")
        else:
            req["created_unix"] = int(time.time())
            path.write_text(json.dumps(req, indent=1))
            print("RUN_REQUEST.json written")
        return
    if args.mode == "position":
        tag = tag_fn(args.x, args.y)
        folder = args.run_dir / tag
        issues = ["missing folder"] if not folder.exists() else check_position(folder, tag, (args.x, args.y), exp)
        print(json.dumps(dict(tag=tag, valid=not issues, issues=issues)))
        raise SystemExit(0 if not issues else 1)
    pos = read_positions(args.positions)
    res = check_run(args.run_dir, pos, tag_fn, exp)
    res["expected_n"] = args.expect_n
    bad = {k: v for k, v in res["positions"].items() if v}
    (args.run_dir / "VERIFY.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(dict(ok=res["ok"] and (args.expect_n in (None, res["n_requested"])), requested=res["n_requested"], valid=res["n_valid"], invalid=len(bad), duplicates=res["duplicates"], unexpected=res["unexpected"]), indent=1))
    for k, v in list(bad.items())[:10]:
        print("  ", k, "->", "; ".join(v[:3]))
    if not res["ok"] or (args.expect_n is not None and res["n_requested"] != args.expect_n):
        raise SystemExit("SWEEP_OUTPUT_CHECK_FAILED")


if __name__ == "__main__":
    main()
