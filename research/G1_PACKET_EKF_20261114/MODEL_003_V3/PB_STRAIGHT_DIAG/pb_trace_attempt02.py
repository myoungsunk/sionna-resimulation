"""Observe production P-B replay with unchanged update/DR code (DIAGNOSTIC_ONLY)."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

import run_tb3_model003_v3_s3_joint as joint
from run_tb3_model003_v3_s3_range import rows_and_contributions

PATH = "P-B"
LEVELS = ("B0", "TB3_r2.1.0")
ARMS = ("S-V", "S-C")


def capture(args):
    frozen = args.frozen
    observed_dir = args.out
    gate_file = args.range_stage
    docs = joint.ready(frozen, joint.read(args.manifest))
    gate = joint.load_gate(gate_file, args.range_stage_sha256, args.manifest)
    assert gate["status"] == "DEV_FAIL_RANGE"
    case, level, arm = args.case, args.level, args.arm
    job_key = f"{case}_{PATH}_{level}_{arm}"
    archived_file = observed_dir / "joint" / "OR" / "30" / f"{job_key}.json"
    dr_file = observed_dir / "OR" / "30" / f"{case}_{PATH}_{level}_DR.json"
    archived = joint.read(archived_file)
    dr_archived = joint.read(dr_file)
    assert archived["status"] == dr_archived["status"] == "PASS"
    assert archived["phase"] == "DIAGNOSTIC_ONLY"
    assert archived["runner_sha256"] == joint.sha(Path(joint.__file__))
    assert archived["paired_dr_sha256"] == joint.sha(dr_file)
    assert archived["range_stage_sha256"] == joint.sha(gate_file)
    original_track = joint.track_fold
    original_eval = joint.m1r_clipped
    original_update = joint.update_joint
    original_write = joint.write
    capture_data = {}
    receipt = {}

    def intercept_track(inp, case, path, arm, level, state, measured, model, dr, data, rf, sites):
        rows = inp["rows"]
        assert len(rows) > 1
        assert not model.range_options and model.base in ARMS
        assert not ({"sweep", "in_place", "turn", "restart"} & {row["motion"] for row in rows})
        np.testing.assert_allclose(joint.wrap_rad(inp["truth"][:, 2]-inp["truth"][0, 2]), 0., atol=1.e-12)
        signs = tuple(state["signs"])
        dr_state = joint.start_level(inp, path, level, False, None)
        for key in ("wheel", "gyro", "signs", "bg"):
            np.testing.assert_array_equal(state[key], dr_state[key])
        np.testing.assert_array_equal(state["mean"][:, :state["md"]], dr_state["mean"])
        np.testing.assert_array_equal(state["cov"][:, :state["md"], :state["md"]], dr_state["cov"])
        full = inp | {"cp": np.arange(len(rows))}
        dr_rows, _ = rows_and_contributions(full, path, case, "DR", level, dr_state, None, None)
        dr_lookup = {}
        for row in dr_rows:
            key = row["checkpoint_order"], row["seed"], row["sign"]
            assert key not in dr_lookup
            dr_lookup[key] = row
        for row in dr_archived["rows"]:
            key = row["checkpoint_order"], row["seed"], row["sign"]
            replay = dr_lookup[key]
            for metric in ("heading_error_rad", "xy_error_m", "nees_heading", "nees_xy_normalized", "nees_bg"):
                assert row[metric] == replay[metric], (job_key, key, metric)
        seeds = joint.SEEDS
        capture_data.update(
            dr_error_rad=np.array([[dr_lookup[i, seed, sign]["heading_error_rad"]
                                    for seed in seeds for sign in signs] for i in range(len(rows))]),
            seed=np.repeat(seeds, len(signs)),
            sign=np.tile(signs, len(seeds)),
            truth_yaw_rad=inp["truth"][:, 2].copy(),
            distance_m=np.cumsum([float(row["distance_increment_m"]) for row in rows]),
            elapsed_s=np.cumsum(inp["dt"]),
            motion=np.array([row["motion"] for row in rows]),
            packet=np.array([int(row["sequence"]) for row in rows]),
            official_checkpoint=np.asarray(inp["cp"], dtype=int),
        )
        prior, slope, post, available, accepted, nis = [], [], [], [], [], []

        def observe_eval(*a, **kw):
            result = original_eval(*a, **kw)
            prior.append(a[3][:, 2].copy())
            slope.append(result[1][:, 2].copy())
            return result

        def observe_update(*a, **kw):
            result = original_update(*a, **kw)
            mean, _, event = result
            assert not event["r_accepted"].any()
            post.append(mean[:, 2].copy())
            available.append(event["s_available"].copy())
            accepted.append(event["s_accepted"].copy())
            nis.append(event["nis_s"].copy())
            return result

        joint.m1r_clipped = observe_eval
        joint.update_joint = observe_update
        try:
            result = original_track(inp, case, path, arm, level, state, measured, model, dr, data, rf, sites)
        finally:
            joint.m1r_clipped = original_eval
            joint.update_joint = original_update
        assert len(prior) == len(post) == len(slope) == len(rows)
        yaw = capture_data["truth_yaw_rad"][:, None]
        capture_data.update(prior_error_rad=joint.wrap_rad(np.asarray(prior)-yaw),
                            post_error_rad=joint.wrap_rad(np.asarray(post)-yaw),
                            jac_s_per_rad=np.asarray(slope), available=np.asarray(available),
                            accepted=np.asarray(accepted), marginal_nis_s=np.asarray(nis))
        assert np.isfinite(capture_data["post_error_rad"]).all()
        assert np.isfinite(capture_data["dr_error_rad"]).all()
        assert np.all(np.isfinite(capture_data["jac_s_per_rad"])[capture_data["available"]])
        assert np.all(~capture_data["accepted"] | capture_data["available"])
        np.testing.assert_array_equal(capture_data["post_error_rad"][~capture_data["accepted"]],
                                      capture_data["prior_error_rad"][~capture_data["accepted"]])
        return result

    def capture_write(path, doc):
        assert path == archived_file
        receipt.update(doc)

    joint.track_fold = intercept_track
    joint.write = capture_write
    try:
        joint.fold(args, docs, gate)
    finally:
        joint.track_fold = original_track
        joint.write = original_write
    assert receipt["status"] == "PASS"
    assert receipt["rows"] == archived["rows"], "Frozen S-arm checkpoint parity failed"
    assert receipt["contributions"] == archived["contributions"], "Frozen S-arm contribution parity failed"
    for key in ("rf_observations_sha256", "paired_dr_sha256", "runner_sha256", "source_sha256",
                "bank_sha256", "range_stage_sha256", "input_manifest_sha256"):
        assert receipt[key] == archived[key], (job_key, key)
    path = args.capture_dir / f"{job_key}.npz"
    np.savez_compressed(path, **capture_data)
    meta = {key: value for key, value in receipt.items() if key not in ("rows", "contributions", "student_weights")}
    meta.update(classification="DIAGNOSTIC_ONLY", archived_s_sha256=joint.sha(archived_file),
                archived_dr_sha256=joint.sha(dr_file), output_sha256=joint.sha(path),
                archived_s_checkpoint_rows=len(receipt["rows"]), archived_dr_checkpoint_rows=len(dr_archived["rows"]),
                checkpoint_match="EXACT", contributions_match="EXACT",
                n_packet=len(capture_data["packet"]), n_unique_runs=len(capture_data["seed"]),
                python=sys.version.split()[0], numpy=np.__version__)
    (args.capture_dir / f"{job_key}.json").write_text(json.dumps(meta, indent=2)+"\n", encoding="utf-8")
    print(f"{job_key}: {meta['n_packet']} packets x {meta['n_unique_runs']} paired runs, exact parity", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True, choices=joint.CASES)
    parser.add_argument("--arm", required=True, choices=ARMS)
    parser.add_argument("--level", required=True, choices=LEVELS)
    for name in ("frozen", "manifest", "range-stage", "results-root", "model-source", "banks-dir", "out", "capture-dir"):
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--range-stage-sha256", required=True)
    args = parser.parse_args()
    args.path, args.snr, args.chain = PATH, 30, "OR"
    capture(args)


if __name__ == "__main__":
    main()

