"""S0 regression using the frozen v2 inputs, RF runner, and checkpoint receipts."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import run_tb3_model003_s3 as v2
from run_tb3_g1_pilot import read, sha
from tb3_model003_v3_filter import (
    colored_transition, joseph_update, regression_rf_update, student_noise, white_boundary_variance,
)


FROZEN = Path("/frozen")
PROVENANCE = Path("/provenance")
RECEIPTS = Path("/folds/30")
WORK = Path("/work")
RELATIVE_TOLERANCE = 1e-9


def regression_difference(actual, expected):
    actual, expected = np.asarray(actual), np.asarray(expected)
    if actual.shape != expected.shape or not np.array_equal(np.isnan(actual), np.isnan(expected)):
        raise AssertionError("Regression shape or NaN mask differs")
    finite = np.isfinite(expected)
    if not np.array_equal(finite, np.isfinite(actual)):
        raise AssertionError("Regression finite mask differs")
    difference = np.abs(actual[finite] - expected[finite])
    if np.any(difference > RELATIVE_TOLERANCE * np.abs(expected[finite])):
        at = np.argmax(np.divide(difference, np.maximum(np.abs(expected[finite]), 1e-300)))
        raise AssertionError(f"Relative S0 difference {difference[at]} for reference {expected[finite][at]}")
    return float(np.max(difference, initial=0.0))


def checks():
    mean = np.array([[7.1, 2.0, 0.1, 0.0]])
    prior = np.diag([0.03, 0.02, 0.01, 0.001])[None]
    jac = np.array([[[1.0, 0.0, 0.0, 0.0], [0.0, 0.1, 0.5, 0.0]]])
    thermal, independent = np.array([0.006]), np.array([0.04])
    white = np.array([[[0.01, 0.0], [0.0, white_boundary_variance(thermal, independent).item()]]])
    gaussian_noise = np.array([[[0.01, 0.0], [0.0, thermal.item()]]])
    residual = np.array([[0.12, 0.7]])
    xv, pv = joseph_update(mean, prior, jac, white, residual, 4)

    # Independent colored state when the persisted C3 decision is white has
    # the same marginalized active update as a white measurement variance.
    colored_jac = np.concatenate((jac, np.array([[[0.0], [1.0]]])), axis=-1)
    colored_prior = np.zeros((1, 5, 5))
    colored_prior[:, :4, :4] = prior
    colored_prior[:, 4, 4] = independent
    xc, pc = joseph_update(np.column_stack((mean, np.zeros(1))), colored_prior,
                          colored_jac, gaussian_noise, residual, 5)
    white_mean_diff = regression_difference(xv, xc[:, :4])
    white_cov_diff = regression_difference(pv, pc[:, :4, :4])
    phi_hold, q_hold = colored_transition(0.0, 0.0, 0.016, np.deg2rad(2.5), 0.04)
    phi_move, q_move = colored_transition(0.016, 0.0, 0.016, np.deg2rad(2.5), 0.04)
    assert phi_hold == 1 and q_hold == 0
    assert np.isclose(phi_move, np.exp(-1.0)) and q_move > 0

    # Compare update kernels on the same accepted observations, as +T and
    # standard Gaussian production runs use different s gate policies.
    t_noise, weight = student_noise(prior, jac, white, residual, np.inf)
    xt, pt = joseph_update(mean, prior, jac, t_noise, residual, 4)
    assert weight.item() == 1
    finite_noise, finite_weight = student_noise(prior, jac, white, residual, 4)
    assert finite_weight.item() < 1 and finite_noise[..., 1, 1] > white[..., 1, 1]
    return dict(status="PASS", lower_bound_keeps_hold_phi=phi_hold, lower_bound_hold_q=q_hold,
                phi_positive_step_at_lower_bound=phi_move,
                white_boundary_max_mean_difference=white_mean_diff,
                white_boundary_max_covariance_difference=white_cov_diff,
                student_gaussian_max_mean_difference=regression_difference(xt, xv),
                student_gaussian_max_covariance_difference=regression_difference(pt, pv),
                finite_df_weight=float(finite_weight.item()))


def compare_rows(actual, expected):
    if len(actual) != len(expected):
        raise AssertionError("Checkpoint row count changed")
    max_error = 0.
    for current, saved in zip(actual, expected, strict=True):
        if current.keys() != saved.keys():
            raise AssertionError("Checkpoint row fields changed")
        floating = [key for key, value in saved.items() if type(value) is float]
        if any(current[key] != saved[key] for key in saved.keys() - set(floating)):
            raise AssertionError("Checkpoint row ID, status or count changed")
        max_error = max(max_error, regression_difference(
            [current[key] for key in floating], [saved[key] for key in floating]))
    return max_error


def run_fold(flags):
    gate = read(PROVENANCE/"LOAO_RESULTS.json")
    source = gate["source"]
    name = f"{flags.case}_{flags.path}_B0"
    archived = RECEIPTS/f"{name}_{flags.arm}.json"
    dr = RECEIPTS/f"{name}_DR.json"
    for file in (archived, dr):
        if sha(file) != gate["receipt_sha256"][f"30/{file.name}"]:
            raise ValueError(f"Damaged archived receipt: {file.name}")
    before = read(archived)
    if sha(Path(v2.__file__)) != before["source_file_sha256"]:
        raise ValueError("Runner hash does not match archived fold")
    original = v2.update_rf
    packet_count = 0
    max_differences = dict(mean=0., covariance=0., nis=0., innovation=0.)

    def check_update(*arguments, **options):
        nonlocal packet_count
        expected_mean, expected_cov, expected_event = original(*arguments, **options)
        new_mean, new_cov, event = regression_rf_update(*arguments, **options)
        for key in ("available", "accepted", "rejected"):
            np.testing.assert_array_equal(event[key], expected_event[key], err_msg=key)
        comparison = dict(mean=(new_mean, expected_mean), covariance=(new_cov, expected_cov),
                          nis=(event["nis"], expected_event["nis"]),
                          innovation=(event["innovation"], expected_event["innovation"]))
        for key, (actual, expected) in comparison.items():
            max_differences[key] = max(max_differences[key], regression_difference(actual, expected))
        packet_count += 1
        return new_mean, new_cov, event

    replay = WORK/"receipts"/archived.name
    args = SimpleNamespace(case=flags.case, path=flags.path, arm=flags.arm, level="B0", snr=30,
                           dr=dr, results_root=Path("/results"), model_source=Path("/model"),
                           banks_dir=Path("/banks"), out=replay)
    for arg, file, ident in (("timeline", "TIMELINE_PACKETS.csv", "timeline"),
                             ("s2", "CHARACTERIZATION_003.json", "s2"),
                             ("selection", "RANGING_RULE_SELECTION.json", "s1"),
                             ("parity", "PARITY.json", "parity")):
        setattr(args, arg, FROZEN/file)
        setattr(args, f"{arg}_sha256", source[f"{ident}_sha256"])
    v2.update_rf = check_update
    try:
        v2.run_fold(args)
    finally:
        v2.update_rf = original

    after = read(replay)
    rows = before["receipt_rows"]
    checkpoint_diff = compare_rows(after["receipt_rows"], rows)
    evidence = dict(status="PASS", case=flags.case, path=flags.path, arm=flags.arm,
                    original_sha256=sha(archived), paired_dr_sha256=sha(dr), replay_sha256=sha(replay),
                    v2_runner_sha256=sha(Path(v2.__file__)), packets=packet_count, checkpoint_rows=len(rows),
                    max_difference=max_differences, max_checkpoint_difference=checkpoint_diff)
    out = WORK/"checks"/archived.name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, indent=2)+"\n", encoding="utf-8")
    print(f"{flags.case} {flags.path} {flags.arm}: {len(rows)} checkpoints, {packet_count} packets", flush=True)


def close():
    files = sorted((WORK/"checks").glob("*.json"))
    folds = [read(file) for file in files]
    observed = {(r["case"], r["path"], r["arm"]) for r in folds if r["status"] == "PASS"}
    expected = {(c, p, a) for c in v2.CASES for p in v2.PATHS for a in ("R4", "J4")}
    if len(files) != len(expected) or observed != expected:
        raise ValueError("Missing, duplicate, or failed S0 fold")
    timeline_manifest = read(PROVENANCE/"TIMELINE_READBACK.json")
    timeline = sha(FROZEN/"TIMELINE_PACKETS.csv")
    if timeline_manifest["status"] != "PASS" or timeline != timeline_manifest["timeline_sha256"]:
        raise ValueError("S0 frozen timeline differs")
    report = dict(question_id="G1-MODEL-003", version=3, status="PASS", stage="S0",
                  finished_utc=datetime.now(timezone.utc).isoformat(), method="v2_compatibility",
                  v2_archive="/home/KMS/G1_MODEL003_S3_QH7zq5Jn", relative_tolerance=RELATIVE_TOLERANCE,
                  note="V2 30 dB B0 first 20 sensor seeds; R4 and J4. Unchanged v2 motion and nominal observation evaluation.",
                  timeline_sha256=timeline, timeline_packets=timeline_manifest["rows"],
                  v2_timeline_readback_sha256=sha(PROVENANCE/"TIMELINE_READBACK.json"),
                  v2_s0_report_sha256=sha(PROVENANCE/"REPORT_KO.md"),
                  v2_loao_results_sha256=sha(PROVENANCE/"LOAO_RESULTS.json"),
                  v3_runner_sha256=sha(Path(__file__)),
                  v3_filter_sha256=sha(Path(__file__).with_name("tb3_model003_v3_filter.py")),
                  synthetic=checks(), folds=folds)
    (WORK/"REGRESSION_V3.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("checks")
    fold = sub.add_parser("fold")
    fold.add_argument("case", choices=v2.CASES)
    fold.add_argument("path", choices=v2.PATHS)
    fold.add_argument("arm", choices=("R4", "J4"))
    sub.add_parser("close")
    flags = parser.parse_args()
    if flags.mode == "checks":
        print(json.dumps(checks(), indent=2))
    elif flags.mode == "fold":
        run_fold(flags)
    else:
        close()


if __name__ == "__main__":
    main()
