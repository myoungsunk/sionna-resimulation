"""Read archived M6 traces to analyze R5 passage bias and local information."""

import ast
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parent
STUDY = ROOT.parent
ART = STUDY.parent
M6 = ART / "G1_GM_THETA_M6_20261116"
PUB = Path("D:/SLAM_bot/g1_m5_pub_20261116/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001")
EVALUATOR = PUB / "gm_theta_m6/inputs/R5_evaluator.npz"
CROSSING_SOURCE = ART / "G1_EXPOSURE_M1_M4_20261116/exposure_score.py"
SEEDS = tuple(range(10, 15))
ARMS = ("G1_LORO", "G1_KI")
WINDOWS = {"approach": (-20., -10.), "pre": (-10., 0.), "post": (0., 10.),
           "passage": (-10., 10.)}
POSE_BIAS = [0, 1, 2, 4]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    with np.load(path, allow_pickle=False) as packed:
        return {key: packed[key] for key in packed.files}


def trace_path(seed, arm):
    if arm == "G0":
        return M6 / "attempt_02/implementation" / f"seed{seed}/R5_G0.npz"
    stage = "seed10" if seed == 10 else "seed11_14"
    return M6 / "attempt_02" / stage / f"seed{seed}/R5_{arm}.npz"


def write_json(path, payload):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


def write_csv(path, rows):
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def crossings_function():
    tree = ast.parse(CROSSING_SOURCE.read_text(encoding="utf-8"))
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "crossings")
    namespace = {"np": np}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(CROSSING_SOURCE), "exec"), namespace)
    return namespace["crossings"]


def rms(value):
    return float(np.sqrt(np.mean(np.square(value))))


def wrap(value):
    return (value + np.pi) % (2. * np.pi) - np.pi


def episode(near, t, passage):
    switches = np.flatnonzero(np.diff(np.r_[False, near, False])).reshape(-1, 2)
    index = passage["packet_index"]
    containing = [pair for pair in switches if pair[0] <= index < pair[1]]
    if containing:
        first, stop = containing[0]
        gap = 0.
    else:
        distance = [max(float(t[first] - passage["time_s"]),
                        float(passage["time_s"] - t[stop - 1]), 0.)
                    for first, stop in switches]
        winner = int(np.argmin(distance))
        first, stop = switches[winner]
        gap = distance[winner]
    return int(first), int(stop), gap


def local_information(trace):
    """Integrate the Gaussian bias conditional on pose in the archived prior."""
    count = len(trace["t"])
    values = {name: np.zeros(count) for name in (
        "conditional_bias_var_rad2", "delta_jyy", "nominal_jyy", "marginal_jyy",
        "local_y_loss_fraction", "conditional_s_y_loss_fraction", "physical_hy",
        "effective_hy", "prior_b_y_corr", "prior_b_heading_corr",
        "simple_no_cross_y_loss_fraction", "actual_y_var_reduction_fraction")}
    max_covariance_error = 0.
    max_woodbury_scaled_error = 0.
    for i in range(count):
        joint = trace["Pprior_aug"][i][np.ix_(POSE_BIAS, POSE_BIAS)]
        pose = joint[:3, :3]
        cross = joint[3, :3]
        regression = np.linalg.solve(pose, cross)
        variance = float(joint[3, 3] - cross @ regression)
        if variance <= 0.:
            raise ValueError("Conditional bias variance is nonpositive")
        H = trace["H_aug"][i][:, POSE_BIAS]
        loading = H[:, 3]
        effective = H[:, :3] + np.outer(loading, regression)
        R = trace["Reff"][i]
        effective_R = R + variance * np.outer(loading, loading)
        nominal_info = effective.T @ np.linalg.solve(R, effective)
        marginalized_info = effective.T @ np.linalg.solve(effective_R, effective)
        Rinv_a = np.linalg.solve(R, loading)
        vector = effective.T @ Rinv_a
        woodbury = np.outer(vector, vector) / (1. / variance + loading @ Rinv_a)
        difference = nominal_info - marginalized_info
        scale = max(1., float(np.max(np.abs(nominal_info))))
        max_woodbury_scaled_error = max(max_woodbury_scaled_error,
                                        float(np.max(np.abs(woodbury - difference))) / scale)
        nominal_y = float(nominal_info[1, 1])
        delta_y = float(woodbury[1, 1])
        conditional_h = effective[1] - R[1, 0] / R[0, 0] * effective[0]
        conditional_R = R[1, 1] - R[1, 0]**2 / R[0, 0]
        nominal_s_y = conditional_h[1]**2 / conditional_R
        simple_H = H[:, :3]
        simple_nominal = float(simple_H[:, 1] @ np.linalg.solve(R, simple_H[:, 1]))
        simple_vector = float(simple_H[:, 1] @ Rinv_a)
        stationary = float(trace["sigma_theta_rad"][i]**2)
        simple_delta = simple_vector**2 / (1. / stationary + loading @ Rinv_a)
        values["conditional_bias_var_rad2"][i] = variance
        values["delta_jyy"][i] = delta_y
        values["nominal_jyy"][i] = nominal_y
        values["marginal_jyy"][i] = float(marginalized_info[1, 1])
        values["local_y_loss_fraction"][i] = delta_y / nominal_y if nominal_y > 0. else 0.
        values["conditional_s_y_loss_fraction"][i] = delta_y / nominal_s_y if nominal_s_y > 0. else 0.
        values["physical_hy"][i] = H[1, 1]
        values["effective_hy"][i] = effective[1, 1]
        values["prior_b_y_corr"][i] = joint[3, 1] / np.sqrt(joint[3, 3] * pose[1, 1])
        values["prior_b_heading_corr"][i] = joint[3, 2] / np.sqrt(joint[3, 3] * pose[2, 2])
        values["simple_no_cross_y_loss_fraction"][i] = simple_delta / simple_nominal if simple_nominal > 0. else 0.
        values["actual_y_var_reduction_fraction"][i] = (
            trace["Pprior"][i, 1, 1] - trace["P"][i, 1, 1]) / trace["Pprior"][i, 1, 1]
        if trace["mask"][i]:
            projected = effective @ pose
            posterior = pose - projected.T @ np.linalg.solve(
                projected @ effective.T + effective_R, projected)
        else:
            posterior = pose
        max_covariance_error = max(max_covariance_error,
                                   float(np.max(np.abs(posterior - trace["P"][i, :3, :3]))))
    if max_covariance_error > 1e-10 or max_woodbury_scaled_error > 1e-10:
        raise ValueError("Bias marginalization calculation does not match archived covariance")
    return values, dict(max_pose_covariance_error=max_covariance_error,
                        max_woodbury_scaled_error=max_woodbury_scaled_error)


def derived_trace(trace, truth):
    b_previous = np.r_[0., trace["b_theta"][:-1]]
    decay = trace["b_theta_prior"] - b_previous
    ratio = trace["S"][:, 1, 0] / trace["S"][:, 0, 0]
    conditional_s = trace["nu"][:, 1] - ratio * trace["nu"][:, 0]
    K = trace["K_aug"][:, 4]
    update_r = (K[:, 0] + ratio * K[:, 1]) * trace["nu"][:, 0]
    update_s = K[:, 1] * conditional_s
    reconstructed = b_previous + decay + update_r + update_s
    errors = dict(
        bias_ledger=float(np.max(np.abs(reconstructed - trace["b_theta"]))),
        bias_transition=float(np.max(np.abs(trace["b_theta_prior"] - trace["alpha"] * b_previous))),
        bias_augmented=float(np.max(np.abs(trace["x_aug"][:, 4] - trace["b_theta"]))))
    if max(errors.values()) > 1e-10:
        raise ValueError("Archived bias transition or update ledger differs")
    information, information_checks = local_information(trace)
    errors.update(information_checks)
    return dict(heading_error_deg=np.rad2deg(wrap(trace["x"][:, 2] - truth[:, 2])),
                y_error_cm=100. * (trace["x"][:, 1] - truth[:, 1]),
                b_deg=np.rad2deg(trace["b_theta"]),
                b_prior_deg=np.rad2deg(trace["b_theta_prior"]),
                b_previous_deg=np.rad2deg(b_previous),
                b_decay_deg=np.rad2deg(decay),
                b_range_update_deg=np.rad2deg(update_r),
                b_s_update_deg=np.rad2deg(update_s),
                b_sd_deg=np.rad2deg(np.sqrt(trace["P_aug"][:, 4, 4])),
                **information), errors


def alignment(trace, select):
    select = select & trace["mask"]
    R = trace["Reff"][select]
    hy = trace["H"][select, 1, 1] - R[:, 1, 0] / R[:, 0, 0] * trace["H"][select, 0, 1]
    a = trace["a"][select]
    variance = R[:, 1, 1] - R[:, 1, 0]**2 / R[:, 0, 0]
    yy = float(np.sum(hy**2 / variance))
    aa = float(np.sum(a**2 / variance))
    ya = float(np.sum(hy * a / variance))
    return ya**2 / (yy * aa) if yy > 0. and aa > 0. else None


def window_row(seed, arm, passage, name, select, trace, values, near):
    accepted = select & trace["mask"]
    first, last = np.flatnonzero(select)[[0, -1]]
    row = dict(seed=seed, arm=arm, passage=passage, window=name,
               packets=int(select.sum()), accepted=int(accepted.sum()),
               y_rmse_cm=rms(values["y_error_cm"][select]),
               heading_rmse_deg=rms(values["heading_error_deg"][select]),
               b_mean_deg=float(np.mean(values["b_deg"][select])),
               b_rms_deg=rms(values["b_deg"][select]),
               b_start_previous_deg=float(values["b_previous_deg"][first]),
               b_end_deg=float(values["b_deg"][last]),
               b_decay_sum_deg=float(values["b_decay_deg"][select].sum()),
               b_range_update_sum_deg=float(values["b_range_update_deg"][select].sum()),
               b_s_update_sum_deg=float(values["b_s_update_deg"][select].sum()),
               fixed_near_fraction=float(near[select].mean()),
               qs_positive_fraction=float(np.mean(trace["q_s"][select] > 0.)),
               inflation_median=float(np.median(trace["s_infl"][select])),
               loading_alignment_cos2=alignment(trace, select))
    for key in ("local_y_loss_fraction", "conditional_s_y_loss_fraction",
                "prior_b_y_corr", "prior_b_heading_corr", "actual_y_var_reduction_fraction",
                "simple_no_cross_y_loss_fraction"):
        row[key + "_median"] = float(np.median(values[key][accepted]))
    return row


def plot_seed10(t, truth, baseline, traces, derived, near, passages):
    colors = {"G1_LORO": "#2671b4", "G1_KI": "#d85c24"}
    fig, axes = plt.subplots(3, 3, figsize=(14., 9.), sharex="col")
    for column, passage in enumerate(passages):
        time = passage["time_s"]
        selected = (t >= time - 20.) & (t < time + 10.)
        x = t[selected] - time
        for arm in ARMS:
            d = derived[arm]
            color = colors[arm]
            axes[0, column].plot(x, d["b_deg"][selected], color=color, label=arm)
            axes[0, column].fill_between(x, d["b_deg"][selected] - d["b_sd_deg"][selected],
                                         d["b_deg"][selected] + d["b_sd_deg"][selected],
                                         color=color, alpha=.12)
            axes[1, column].plot(x, d["y_error_cm"][selected], color=color)
            axes[2, column].plot(x, d["heading_error_deg"][selected], color=color)
        axes[1, column].plot(x, 100. * (baseline["x"][selected, 1] - truth[selected, 1]),
                             color=".5", linestyle=":", label="G0")
        axes[2, column].plot(x, np.rad2deg(wrap(baseline["x"][selected, 2] - truth[selected, 2])),
                             color=".5", linestyle=":")
        for row in range(3):
            ax = axes[row, column]
            ax.axvline(0., color=".25", linestyle="--", linewidth=.8)
            ax.axhline(0., color=".7", linewidth=.6)
            ax.grid(alpha=.2)
            ax.fill_between(x, 0., 1., where=near[selected], color=".5", alpha=.08,
                            transform=ax.get_xaxis_transform())
        axes[0, column].set_title(f"R5 seed 10 passage {column + 1} ({time:.2f} s)")
        axes[2, column].set_xlabel("Time relative to passage [s]")
    axes[0, 0].set_ylabel("Estimated bias [deg], ±1 SD")
    axes[1, 0].set_ylabel("y error [cm]")
    axes[2, 0].set_ylabel("Heading error [deg]")
    axes[0, 0].legend(loc="best")
    axes[1, 0].legend(loc="best")
    fig.tight_layout()
    fig.savefig(ROOT / "R5_seed10_passage_timeline.png", dpi=180)
    plt.close(fig)


def execute():
    root_contract = STUDY / "RUN_CONTRACT.json"
    if not root_contract.exists():
        raise FileNotFoundError("Mother root RUN_CONTRACT.json must be frozen before analysis")
    if (ROOT / "EXECUTION.json").exists():
        raise FileExistsError("Existing completed execution evidence")
    receipt = dict(question_id="G1-FINAL-MODEL/STAGE0/R5-PASSAGE", role="IMPLEMENTER",
                   root_contract_sha256=sha(root_contract), started_utc=datetime.now(timezone.utc).isoformat(),
                   argv=sys.argv, python=sys.version, numpy=np.__version__, platform=platform.platform(),
                   sources={str(Path(__file__).resolve()): sha(__file__), str(CROSSING_SOURCE): sha(CROSSING_SOURCE)},
                   inputs={}, outputs={})
    try:
        evaluator = load(EVALUATOR)
        receipt["inputs"][str(EVALUATOR)] = sha(EVALUATOR)
        truth, t = evaluator["truth"], evaluator["t"]
        passages = crossings_function()(truth, t)
        if len(passages) != 3:
            raise ValueError("Expected exactly three R5 passages")
        all_rows, windows, entries, qs_rows = [], [], [], []
        checks = {}
        for seed in SEEDS:
            baseline_path = trace_path(seed, "G0")
            baseline = load(baseline_path)
            receipt["inputs"][str(baseline_path)] = sha(baseline_path)
            rho = np.linalg.norm(baseline["prior"][:, :2] - np.array([10., 0.]), axis=1)
            near = rho < 3.
            traces, derived = {}, {}
            for arm in ARMS:
                path = trace_path(seed, arm)
                trace = load(path)
                receipt["inputs"][str(path)] = sha(path)
                np.testing.assert_array_equal(trace["t"], t)
                np.testing.assert_array_equal(trace["pose_id"], evaluator["pose_id"])
                np.testing.assert_array_equal(trace["mask"], baseline["mask"])
                values, ledger_checks = derived_trace(trace, truth)
                checks[f"{seed}/{arm}"] = ledger_checks
                traces[arm], derived[arm] = trace, values
                for i, time in enumerate(t):
                    row = dict(seed=seed, arm=arm, t_s=float(time), accepted=int(trace["mask"][i]),
                               fixed_g0_near=int(near[i]), own_prior_rho_m=float(trace["distance"][i]),
                               q_s=float(trace["q_s"][i]), inflation=float(trace["s_infl"][i]))
                    row.update({key: float(value[i]) for key, value in values.items()})
                    all_rows.append(row)
                own_near = trace["distance"] < 3.
                qs_rows.append(dict(seed=seed, arm=arm,
                                    fixed_near_packets=int(near.sum()), own_near_packets=int(own_near.sum()),
                                    fixed_near_q_positive_fraction=float(np.mean(trace["q_s"][near] > 0.)),
                                    own_near_q_positive_fraction=float(np.mean(trace["q_s"][own_near] > 0.))))
                for passage_id, passage in enumerate(passages, 1):
                    time = passage["time_s"]
                    first, stop, gap = episode(near, t, passage)
                    entry = first + int(np.flatnonzero(trace["mask"][first:stop])[0])
                    entries.append(dict(seed=seed, arm=arm, passage=passage_id,
                                        passage_time_s=time, episode_start_s=float(t[first]),
                                        episode_end_s=float(t[stop-1]), selection_gap_s=gap,
                                        entry_time_s=float(t[entry]),
                                        entry_b_prior_deg=float(values["b_prior_deg"][entry]),
                                        entry_b_sd_deg=float(np.rad2deg(np.sqrt(trace["Pprior_aug"][entry, 4, 4]))),
                                        entry_prior_y_error_cm=float(100. * (trace["prior"][entry, 1] - truth[entry, 1])),
                                        entry_prior_heading_error_deg=float(np.rad2deg(wrap(trace["prior"][entry, 2] - truth[entry, 2]))),
                                        entry_q_s=float(trace["q_s"][entry]),
                                        entry_own_rho_m=float(trace["distance"][entry])))
                    for name, (start, end) in WINDOWS.items():
                        selected = (t >= time + start) & (t < time + end)
                        windows.append(window_row(seed, arm, passage_id, name, selected, trace, values, near))
            if seed == 10:
                plot_seed10(t, truth, baseline, traces, derived, near, passages)
        pairs = []
        for seed in SEEDS:
            for passage_id in range(1, 4):
                by_arm = {row["arm"]: row for row in windows
                          if row["seed"] == seed and row["passage"] == passage_id and row["window"] == "passage"}
                left, right = by_arm["G1_LORO"], by_arm["G1_KI"]
                pairs.append(dict(seed=seed, passage=passage_id,
                                  g1_y_rmse_cm=left["y_rmse_cm"], hybrid_y_rmse_cm=right["y_rmse_cm"],
                                  delta_y_rmse_cm=right["y_rmse_cm"]-left["y_rmse_cm"],
                                  g1_b_rms_deg=left["b_rms_deg"], hybrid_b_rms_deg=right["b_rms_deg"],
                                  g1_y_loss_median=left["local_y_loss_fraction_median"],
                                  hybrid_y_loss_median=right["local_y_loss_fraction_median"]))
        expected = {"G1_LORO": [2.89, 4.78, 4.82], "G1_KI": [3.35, 2.68, 2.67]}
        for arm, values in expected.items():
            actual = [row["y_rmse_cm"] for row in windows
                      if row["seed"] == 10 and row["arm"] == arm and row["window"] == "passage"]
            np.testing.assert_allclose(actual, values, atol=.011, rtol=0.)
        write_csv(ROOT / "R5_TIMELINE.csv", all_rows)
        write_csv(ROOT / "R5_PASSAGE_WINDOWS.csv", windows)
        write_csv(ROOT / "R5_NEAR_ENTRIES.csv", entries)
        write_csv(ROOT / "R5_QS_SUPPORT.csv", qs_rows)
        write_csv(ROOT / "R5_PAIRED_PASSAGES.csv", pairs)
        result = dict(question_id=receipt["question_id"], passages=passages,
                      checks=checks, windows=windows, near_entries=entries, q_support=qs_rows,
                      paired_passages=pairs,
                      boundaries=["All results describe archived traces, with no filter replay.",
                                  "b_theta is a latent heading-equivalent correction, with no separately observed ground truth.",
                                  "Local information loss conditions on the archived joint Gaussian prior and is not a causal allocation of trajectory RMSE.",
                                  "Loading alignment is a signed whitened geometric diagnostic, without an independent-packet or constant-bias claim."])
        write_json(ROOT / "RESULTS.json", result)
        receipt.update(status="PASS", exit_code=0)
    except BaseException as exc:
        receipt.update(status="FAIL", exit_code=1, error=str(exc))
        raise
    finally:
        receipt["finished_utc"] = datetime.now(timezone.utc).isoformat()
        for path in ROOT.iterdir():
            if path.is_file() and path.name not in ("analyze_r5.py", "EXECUTION.json"):
                receipt["outputs"][path.name] = sha(path)
        write_json(ROOT / "EXECUTION.json", receipt)


if __name__ == "__main__":
    execute()
