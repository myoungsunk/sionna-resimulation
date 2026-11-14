"""Supplement the frozen G3 checks at four G6 regeneration locations."""

import argparse
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from run_tb3_g1_pilot import load_runtime, sha, write
from run_tb3_production import case_inputs, frozen_settings, utc_now
from tb3_g6_face_match import load_faces
from tb3_g6_revalidate import finite_face_trace
from validate_tb3_production_g3 import frozen_tools, scene_runtime


TARGETS = {"G-T2_B": (1708,), "G-T2_C": (1025, 1840, 2477)}


def compare_energy(core, low, high, tools):
    low_dirs = core.P.path_directions(*low["ang"])
    high_dirs = core.P.path_directions(*high["ang"])
    low_chain = np.concatenate((low["interactions"], low["objects"]), axis=1)
    high_chain = np.concatenate((high["interactions"], high["objects"]), axis=1)
    match = tools["g3c_evaluation"]
    # The rotated 3x3 Jones tensors preserve the Frobenius norm of the ISO 2x2 matrices.
    pair = match.match_matrix(low["tau"], low_dirs, low_chain, high["tau"], high_dirs, high_chain)
    return [match.energy_metrics(pair, np.sum(abs(a)**2, axis=(1, 2)), np.sum(abs(b)**2, axis=(1, 2)))
            for a, b in zip(low["jones"], high["jones"], strict=True)]


def evaluate(core, case, task, entry, anchor, setup, scene, solver, faces, freq, banks, poses, settings,
             tools, thresholds):
    tx = tuple(entry["anchors_xyz_m"][anchor])
    rx = task["x"], task["y"], entry["rx_z_m"]
    recorded = tuple(np.asarray(scene.transmitters["tx"].position).reshape(3).astype(float))
    full = np.arange(len(freq))
    nodes17 = core.node_bins(len(freq), "17")
    traces = {}
    for name, bins, config in (("nominal257", full, settings), ("nominal17", nodes17, settings),
                               ("high257", full, settings | {"samples_per_src": 400_000})):
        trace, nodes, report = finite_face_trace(core, scene, solver, config, freq, bins, task, setup, faces,
                                                 tx, rx, recorded)
        if (nodes != list(bins) or not trace["present"].all() or
                (name.startswith("nominal") and len(report["rejected"]) != 1)):
            raise ValueError(f"Unexpected path coverage at {case}/{task['task_id']}/{name}")
        traces[name] = (trace, report)
    low, sparse, high = (traces[name][0] for name in ("nominal257", "nominal17", "high257"))
    for key in ("tau", "ang", "interactions", "objects"):
        if not np.array_equal(low[key], sparse[key]):
            raise ValueError(f"Nominal trace differs at {case}/{task['task_id']}/{key}")
    energy = compare_energy(core, low, high, tools)
    parity = tools["parity"]
    yaws = [poses[i]["yaw_body_deg"] for i in task["pose_ids"]]
    h0, h17, hh = (parity.h_for_antenna_yaws(t, banks, yaws) for t in (low, sparse, high))
    b = [parity.compare(h, ref, freq) for h, ref in zip(h17, h0, strict=True)]
    c = [parity.compare(h, ref, freq) for h, ref in zip(hh, h0, strict=True)]
    passed = (max(row["abs_ds"] for row in b) <= thresholds["abs_ds_max"]
              and np.mean([row["fp_index_match"] for row in b]) >= thresholds["fp_index_match_min"]
              and max(row["range_diff_m"] for row in b) <= thresholds["range_diff_max_m"]
              and max(row[2] for row in energy) < 0.01
              and max(row["abs_ds"] for row in c) <= 0.002)
    return dict(case=case, task_id=task["task_id"], pose_ids=task["pose_ids"], status="PASS" if passed else "FAIL",
                trace_receipts={name: v[1] for name, v in traces.items()},
                g3a_bins=len(full), g3b_by_pose=b, g3c_by_pose=c, g3c_energy_by_bin=energy)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "source", "tools", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--case", choices=TARGETS, required=True)
    parser.add_argument("--task-id", type=int, required=True)
    args = parser.parse_args()
    if args.task_id not in TARGETS[args.case]:
        parser.error("Unknown regeneration location")
    started = utc_now()
    root = args.root
    args.production = root / "config/PRODUCTION_F1.json"
    args.reference = root / "frozen/REFERENCE.json"
    args.ffd_manifest = root / "frozen/FFD_RESTORE_MANIFEST.json"
    production, _ = frozen_settings(args)
    tools, thresholds = frozen_tools(SimpleNamespace(
        source=args.source, g3a=args.tools / "run_g3a.py", g3c_trace=args.tools / "run_g3c_trace.py",
        g3c_evaluation=args.tools / "run_g3c_evaluation.py", parity=args.tools / "parity_gate.py",
    ))
    core, _, runtime = load_runtime(args.source)
    banks = [core.P.Bank(b) for b in core.C.load_banks()]
    freq = banks[0].freqs_hz
    entry, anchor, poses, tasks, *_ = case_inputs(root / "g0", root / "g7", args.case)
    scene_root = root / "g0" / "scene"
    scene, solver, setup = scene_runtime(core, entry, anchor, scene_root)
    result = evaluate(core, args.case, tasks[args.task_id], entry, anchor, setup, scene, solver,
                      load_faces(scene, entry, scene_root), freq, banks, poses, production["solver"],
                      tools, thresholds)
    write(args.out, result | dict(question_id="G1-MODEL-003", role="IMPLEMENTER", started_utc=started,
                                  finished_utc=utc_now(), runtime=runtime, thresholds=thresholds,
                                  input_sha256={p.name: sha(p) for p in (args.production, args.reference,
                                      args.ffd_manifest, root / "g0/RUN_MANIFEST.json", root / "g7/RUN_MANIFEST.json",
                                      *[Path(module.__file__) for module in tools.values()])},
                                  code_sha256={name: sha(Path(__file__).with_name(name)) for name in
                                      (Path(__file__).name, "tb3_g6_face_match.py", "tb3_g6_revalidate.py")}))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
