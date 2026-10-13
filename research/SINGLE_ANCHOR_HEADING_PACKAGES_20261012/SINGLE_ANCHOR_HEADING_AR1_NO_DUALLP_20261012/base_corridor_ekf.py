#!/usr/bin/env python3
"""Single-anchor UWB range-only + DR EKF: reproducible corridor Monte Carlo.

Requires numpy, pandas and matplotlib. No ROS, Gazebo or RF hardware.
All measurements and ground truth are SYNTHETIC.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

CHI2_95_1 = 3.841458820694124
CHI2_95_2 = 5.991464547107979
CHI2_95_3 = 7.814727903251179


def wrap(a: np.ndarray) -> np.ndarray:
    return (a + np.pi) % (2.0 * np.pi) - np.pi


@dataclass(frozen=True)
class Config:
    runs: int = 500
    seed: int = 20261012
    n_steps: int = 100
    step_m: float = 0.1
    dt_s: float = 0.5
    # Geometry copied from GitHub CorridorSetup (defaults are placeholders, not measurements).
    corridor_length_m: float = 20.0
    corridor_width_m: float = 2.4
    corridor_height_m: float = 2.7
    anchor_x_m: float = 4.0
    anchor_y_m: float = 0.0
    anchor_z_m: float = 2.65  # ceiling height - 0.05 m standoff
    tag_z_m: float = 0.45  # tag xy is collocated with the robot centre
    robot_body_lwh_m: tuple[float, float, float] = (0.60, 0.40, 0.40)
    robot_clearance_m: float = 0.10
    robot_x_min_m: float = 1.0
    robot_x_max_m: float = 19.0
    start_x_m: float = 4.0   # first example_xy_m of GitHub CorridorSetup
    start_y_m: float = 0.0
    initial_xy_std_m: float = 0.10
    initial_yaw_std_deg: float = 3.0
    dr_step_std_m: float = 0.008
    dr_yaw_step_std_deg: float = 0.23
    range_std_m: float = 0.08
    range_bias_m: float = 0.20
    independent_calibration_samples: int = 1000

    @property
    def robot_y_limit_m(self) -> float:
        length, width, _ = self.robot_body_lwh_m
        return self.corridor_width_m/2 - self.robot_clearance_m - np.hypot(length, width)/2


def true_3d_range(config: Config, xy: np.ndarray) -> np.ndarray:
    """Euclidean anchor-to-tag distance; tag XY = robot centre XY, fixed tag Z."""
    dx = xy[..., 0] - config.anchor_x_m
    dy = xy[..., 1] - config.anchor_y_m
    dz = config.tag_z_m - config.anchor_z_m
    return np.sqrt(dx**2 + dy**2 + dz**2)


def range_jacobian(config: Config, pose: np.ndarray) -> np.ndarray:
    """Jacobian wrt (robot x, robot y, heading). Fixed-Z centred tag -> yaw term 0."""
    dr = true_3d_range(config, pose[..., :2])
    H = np.zeros((*pose.shape[:-1], 3))
    H[..., 0] = (pose[..., 0]-config.anchor_x_m)/dr
    H[..., 1] = (pose[..., 1]-config.anchor_y_m)/dr
    return H


def f_motion(x: np.ndarray, ds: np.ndarray, dpsi: np.ndarray) -> np.ndarray:
    phi = x[:, 2] + 0.5 * dpsi
    out = x.copy()
    out[:, 0] += ds * np.cos(phi)
    out[:, 1] += ds * np.sin(phi)
    out[:, 2] = wrap(out[:, 2] + dpsi)
    return out


def f_F_G(x: np.ndarray, ds: float, dpsi: float, dimension: int) -> tuple[np.ndarray, np.ndarray]:
    """Jacobian F = df/dx and G = df/d(ds,dpsi) at the prediction state."""
    n = x.shape[0]
    phi = x[:, 2] + 0.5 * dpsi
    s, c = np.sin(phi), np.cos(phi)
    F = np.broadcast_to(np.eye(dimension), (n, dimension, dimension)).copy()
    F[:, 0, 2] = -ds * s
    F[:, 1, 2] = ds * c
    G = np.zeros((n, dimension, 2))
    G[:, 0, 0] = c
    G[:, 1, 0] = s
    G[:, 0, 1] = -0.5 * ds * s
    G[:, 1, 1] = 0.5 * ds * c
    G[:, 2, 1] = 1.0
    return F, G


def generate(config: Config) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(config.seed)
    n, k = config.runs, config.n_steps
    sigma_psi = np.deg2rad(config.dr_yaw_step_std_deg)
    p0_diag = np.array([
        config.initial_xy_std_m**2,
        config.initial_xy_std_m**2,
        np.deg2rad(config.initial_yaw_std_deg)**2,
    ])
    true = np.zeros((n, k+1, 3))
    true[:, 0, 0] = config.start_x_m
    true[:, 0, 1] = config.start_y_m
    # DR reports nominal increments. Actual displacements differ by stochastic errors.
    # This is a *matched*, independent, zero-mean motion uncertainty model.
    ds_true = config.step_m + rng.normal(0, config.dr_step_std_m, (n, k))
    dpsi_true = rng.normal(0, sigma_psi, (n, k))
    for j in range(k):
        true[:, j+1, :] = f_motion(true[:, j, :], ds_true[:, j], dpsi_true[:, j])
    initial_est = true[:, 0, :] + rng.normal(0, np.sqrt(p0_diag), (n, 3))
    initial_est[:, 2] = wrap(initial_est[:, 2])
    r_true = true_3d_range(config, true[:, :, :2])
    rf_noise = rng.normal(0, config.range_std_m, (n, k))
    z_ideal = r_true[:, 1:] + rf_noise
    z_biased = z_ideal + config.range_bias_m
    # Different, independent calibration recording for each Monte Carlo run.
    # Sample mean estimates constant bias. Test RF data are never used for calibration.
    train_noise = rng.normal(0, config.range_std_m,
                             (n, config.independent_calibration_samples))
    b_hat = config.range_bias_m + train_noise.mean(axis=1)
    b_uncert_std = config.range_std_m / np.sqrt(config.independent_calibration_samples)
    return dict(true=true, initial_est=initial_est,
                z_ideal=z_ideal, z_biased=z_biased,
                r_true=r_true, b_hat=b_hat,
                b_uncert_std=np.array(b_uncert_std),
                p0_diag=p0_diag)


def apply_filter(config: Config, data: dict[str, np.ndarray], mode: str) -> dict[str, np.ndarray]:
    # modes: DR | EKF_IDEAL | EKF_BIASED | EKF_CALIBRATED
    if mode not in ('DR', 'EKF_IDEAL', 'EKF_BIASED', 'EKF_CALIBRATED'):
        raise ValueError(mode)
    n, steps = config.runs, config.n_steps
    # Calibrated variant augments 3D pose with one constant residual-range-bias
    # state. Its covariance represents the independent calibration's uncertainty.
    dim = 4 if mode == 'EKF_CALIBRATED' else 3
    est = np.zeros((n, dim))
    est[:, :3] = data['initial_est']
    P = np.zeros((n, dim, dim))
    for i, variance in enumerate(data['p0_diag']):
        P[:, i, i] = variance
    if dim == 4:
        P[:, 3, 3] = float(data['b_uncert_std'])**2
    mat = np.diag([config.dr_step_std_m**2,
                   np.deg2rad(config.dr_yaw_step_std_deg)**2])
    R = config.range_std_m**2
    eye = np.eye(dim)[None, :, :]
    trace = np.zeros((n, steps+1, dim))
    trace[:, 0, :] = est
    cov_trace = np.zeros((n, steps+1, 3, 3))
    cov_trace[:, 0] = P[:, :3, :3]
    nis = np.full((n, steps+1), np.nan)
    nees_xy = np.zeros((n, steps+1))
    nees_pose = np.zeros((n, steps+1))
    err = np.zeros((n, steps+1, 3))

    def store(j: int) -> None:
        trace[:, j] = est
        cov_trace[:, j] = P[:, :3, :3]
        err[:, j] = est[:, :3] - data['true'][:, j, :3]
        err[:, j, 2] = wrap(err[:, j, 2])
        P_xy = P[:, :2, :2]
        nees_xy[:, j] = np.einsum(
            'ni,ni->n', err[:, j, :2],
            np.linalg.solve(P_xy, err[:, j, :2, None])[:, :, 0])
        P_pose = P[:, :3, :3]
        nees_pose[:, j] = np.einsum(
            'ni,ni->n', err[:, j, :3],
            np.linalg.solve(P_pose, err[:, j, :3, None])[:, :, 0])

    store(0)
    for j in range(steps):
        F, G = f_F_G(est, config.step_m, 0.0, dim)
        P = F @ P @ np.swapaxes(F, 1, 2) + (G @ mat) @ np.swapaxes(G, 1, 2)
        est[:, :3] = f_motion(est[:, :3],
                              np.full(n, config.step_m), np.zeros(n))
        if mode != 'DR':
            dx = est[:, 0] - config.anchor_x_m
            dy = est[:, 1] - config.anchor_y_m
            expected_r = true_3d_range(config, est[:, :2])
            H = np.zeros((n, dim))
            H[:, :3] = range_jacobian(config, est[:, :3])
            if mode == 'EKF_CALIBRATED':
                observed_r = data['z_biased'][:, j] - data['b_hat']
                expected_r += est[:, 3]
                H[:, 3] = 1.0
            elif mode == 'EKF_BIASED':
                observed_r = data['z_biased'][:, j]
            else:
                observed_r = data['z_ideal'][:, j]
            nu = observed_r - expected_r
            PH = (P @ H[:, :, None])[:, :, 0]
            S = np.einsum('ni,ni->n', H, PH) + R
            nis[:, j+1] = nu**2 / S
            K = PH / S[:, None]
            est += K * nu[:, None]
            est[:, 2] = wrap(est[:, 2])
            # Numerically stable Joseph covariance update.
            A = eye - K[:, :, None] * H[:, None, :]
            P = A @ P @ np.swapaxes(A, 1, 2) + R * K[:, :, None] * K[:, None, :]
            P = 0.5 * (P + np.swapaxes(P, 1, 2))
        store(j+1)
    return dict(estimate=trace, cov=cov_trace, error=err,
                nis=nis, nees_xy=nees_xy, nees_pose=nees_pose)


def filter_metrics(out: dict[str, np.ndarray]) -> dict[str, float | None]:
    e = out['error'][:, 1:, :]
    err2d = np.linalg.norm(e[:, :, :2], axis=2)
    rmse = lambda val: float(np.sqrt(np.mean(val**2)))
    nees_xy = out['nees_xy'][:, 1:]
    nees_pose = out['nees_pose'][:, 1:]
    nis_values = out['nis'][:, 1:]
    is_ekf = np.isfinite(nis_values).any()
    return dict(
        rmse_x_m=rmse(e[:, :, 0]), rmse_y_m=rmse(e[:, :, 1]),
        rmse_2d_m=rmse(err2d), p95_2d_m=float(np.quantile(err2d, .95)),
        final_rmse_2d_m=rmse(err2d[:, -1]),
        final_p95_2d_m=float(np.quantile(err2d[:, -1], .95)),
        final_rmse_yaw_deg=float(np.rad2deg(rmse(e[:, -1, 2]))),
        nees_xy_mean=float(np.mean(nees_xy)),
        nees_pose_mean=float(np.mean(nees_pose)),
        coverage_xy_95_pct=float(100*np.mean(nees_xy <= CHI2_95_2)),
        coverage_pose_95_pct=float(100*np.mean(nees_pose <= CHI2_95_3)),
        final_coverage_xy_95_pct=float(100*np.mean(nees_xy[:, -1] <= CHI2_95_2)),
        nis_mean=float(np.mean(nis_values)) if is_ekf else None,
        nis_below_95_pct=float(100*np.mean(nis_values <= CHI2_95_1)) if is_ekf else None,
    )


def range_metrics(difference: np.ndarray) -> dict[str, float]:
    return dict(bias_m=float(np.mean(difference)),
                mae_m=float(np.mean(np.abs(difference))),
                rmse_m=float(np.sqrt(np.mean(difference**2))),
                p95_abs_m=float(np.quantile(np.abs(difference), .95)))


def report_plots(config: Config, data: dict, outs: dict, output_dir: Path) -> None:
    plt.rcParams.update({'font.size': 10, 'axes.grid': True, 'grid.alpha': .25})
    labels = {
        'DR': 'DR only',
        'EKF_IDEAL': 'EKF: unbiased range',
        'EKF_BIASED': 'EKF: biased range (uncorrected)',
        'EKF_CALIBRATED': 'EKF: independently calibrated',
    }
    keys = list(labels)
    dist = config.step_m * np.arange(config.n_steps+1)
    sample_i = 0  # first generated trial, no post-hoc best-trajectory selection
    fig, ax = plt.subplots(figsize=(13, 4.4), constrained_layout=True)
    ax.axhline(-config.corridor_width_m/2, linestyle='--', linewidth=1.5, label='Corridor walls')
    ax.axhline(config.corridor_width_m/2, linestyle='--', linewidth=1.5)
    ax.axvline(0, linestyle='--', linewidth=0.9, alpha=.4)
    ax.axvline(config.corridor_length_m, linestyle='--', linewidth=0.9, alpha=.4)
    ax.fill_between([config.robot_x_min_m, config.robot_x_max_m],
                    -config.robot_y_limit_m, config.robot_y_limit_m,
                    alpha=.07, label='GitHub robot allowed region')
    a = (config.anchor_x_m, config.anchor_y_m)
    ax.plot(*a, '*', markersize=14, label=f'Ceiling anchor (z={config.anchor_z_m:.2f} m)')
    ax.plot(data['true'][sample_i, :, 0], data['true'][sample_i, :, 1],
            linewidth=2.7, label='Ground truth')
    for key in keys:
        coords = outs[key]['estimate'][sample_i, :, :2]
        ax.plot(coords[:, 0], coords[:, 1], linewidth=1.5, label=labels[key])
    ax.set(xlabel='x (m), corridor longitudinal', ylabel='y (m), lateral',
           xlim=(-.4, config.corridor_length_m+.4), ylim=(-config.corridor_width_m/2-.24, config.corridor_width_m/2+.24),
           title='GitHub CorridorSetup geometry (top view) — reproducible run #0')
    ax.set_aspect('equal', adjustable='box')
    ax.legend(fontsize=8, ncol=3, loc='lower center', bbox_to_anchor=(.5, -0.42))
    fig.savefig(output_dir/'01_corridor_trajectory.png', dpi=170, bbox_inches='tight')
    plt.close(fig)

    # Side view makes the anchor-tag height difference unambiguous.
    fig, (top, side) = plt.subplots(2, 1, figsize=(12, 6.5), constrained_layout=True)
    top.add_patch(plt.Rectangle((0, -config.corridor_width_m/2), config.corridor_length_m,
                                config.corridor_width_m, fill=False, linewidth=2))
    top.plot([config.start_x_m, config.start_x_m+config.n_steps*config.step_m],
             [config.start_y_m]*2, color='#3983bd', linewidth=2, label='10 m robot path')
    top.scatter([config.anchor_x_m], [config.anchor_y_m], s=110, marker='*', color='#d28b22', label='Anchor XY')
    top.set(xlim=(-.4, config.corridor_length_m+.4), ylim=(-1.6, 1.6),
            xlabel='x (m)', ylabel='y (m)', title='Plan: 20 m x 2.4 m corridor')
    top.set_aspect('equal', adjustable='box'); top.legend(loc='upper right')
    side.add_patch(plt.Rectangle((0, 0), config.corridor_length_m, config.corridor_height_m,
                                 fill=False, linewidth=2))
    side.plot([config.start_x_m, config.start_x_m+config.n_steps*config.step_m],
              [config.tag_z_m]*2, color='#3983bd', linewidth=2, label=f'Tag z={config.tag_z_m:.2f} m')
    side.scatter([config.anchor_x_m], [config.anchor_z_m], s=120, marker='*', color='#d28b22',
                 label=f'Anchor z={config.anchor_z_m:.2f} m')
    side.plot([config.anchor_x_m,config.start_x_m],[config.anchor_z_m,config.tag_z_m],
              linestyle=':', color='#888888')
    side.set(xlim=(-.4, config.corridor_length_m+.4), ylim=(-.15, config.corridor_height_m+.3),
             xlabel='x (m)', ylabel='z (m)', title='Side: 2.20 m anchor-tag height difference')
    side.legend(loc='upper right')
    fig.savefig(output_dir/'00_github_geometry_top_side.png', dpi=160, bbox_inches='tight')
    plt.close(fig)

    fig, axs = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    for key in keys:
        e = outs[key]['error']
        curve = np.sqrt(np.mean(e[:, :, 0]**2+e[:, :, 1]**2, axis=0))
        axs[0,0].plot(dist, curve, label=labels[key])
    axs[0,0].set(title='Position RMSE vs. distance', ylabel='2D RMSE (m)')
    for key in ('DR', 'EKF_IDEAL'):
        e = outs[key]['error']
        axs[0,1].plot(dist, np.sqrt(np.mean(e[:, :, 0]**2, axis=0)),
                      label=labels[key]+' x')
        axs[0,1].plot(dist, np.sqrt(np.mean(e[:, :, 1]**2, axis=0)),
                      linestyle='--', label=labels[key]+' y')
    axs[0,1].set(title='Longitudinal vs. lateral RMSE', ylabel='RMSE (m)')
    for key in keys:
        axs[1,0].plot(dist, np.mean(outs[key]['nees_xy'], axis=0), label=labels[key])
    axs[1,0].axhline(2., linestyle=':', linewidth=2, label='Reference: E[NEES2D]=2')
    # Log scale keeps the biased (severely overconfident) and ideal NEES readable.
    axs[1,0].set_yscale('log')
    axs[1,0].set_ylim(0.8, 150.0)
    axs[1,0].set(title='Position NEES (log scale, averaged over runs)', ylabel='Mean NEES2D')
    for key in keys[1:]:
        axs[1,1].plot(dist[1:], np.mean(outs[key]['nis'][:, 1:], axis=0),
                      label=labels[key])
    axs[1,1].axhline(1., linestyle=':', linewidth=2, label='Reference: E[NIS]=1')
    axs[1,1].set(title='Range innovation NIS (averaged over runs)', ylabel='Mean NIS')
    for ax in axs.flat:
        ax.set_xlabel('Nominal travel distance (m)')
        ax.legend(fontsize=7)
    fig.savefig(output_dir/'02_accuracy_consistency.png', dpi=170, bbox_inches='tight')
    plt.close(fig)

    fig, axs = plt.subplots(1, 2, figsize=(11, 3.9), constrained_layout=True)
    noise = data['z_ideal']-data['r_true'][:, 1:]
    rf_err = {
        'Unbiased range': noise,
        'Biased range': data['z_biased']-data['r_true'][:, 1:],
        'Calibrated range': (data['z_biased']-data['b_hat'][:, None])-data['r_true'][:, 1:],
    }
    for label, e in rf_err.items():
        axs[0].hist(e.ravel(), bins=75, alpha=.48, density=True, label=label)
    axs[0].set(title='Simulated RF ranging error', xlabel='Measured - true 3D range (m)', ylabel='Density')
    axs[0].legend(fontsize=8)
    for key in keys:
        proportion = 100*np.mean(outs[key]['nees_xy'] <= CHI2_95_2, axis=0)
        axs[1].plot(dist, proportion, label=labels[key])
    axs[1].axhline(95., linestyle=':', linewidth=2, label='Nominal 95%')
    axs[1].set(title='2D position 95% ellipse coverage', xlabel='Nominal travel distance (m)',
               ylabel='Actual coverage (%)', ylim=(0, 102))
    axs[1].legend(fontsize=7)
    fig.savefig(output_dir/'03_ranging_coverage.png', dpi=170, bbox_inches='tight')
    plt.close(fig)


def run(config: Config, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    data = generate(config)
    keys = ('DR', 'EKF_IDEAL', 'EKF_BIASED', 'EKF_CALIBRATED')
    outputs = {key: apply_filter(config, data, key) for key in keys}
    results = {key: filter_metrics(outputs[key]) for key in keys}
    no_bias_error = data['z_ideal']-data['r_true'][:, 1:]
    biased_error = data['z_biased']-data['r_true'][:, 1:]
    corrected_error = (data['z_biased']-data['b_hat'][:, None])-data['r_true'][:, 1:]
    ranging = dict(ideal=range_metrics(no_bias_error),
                   biased=range_metrics(biased_error),
                   calibrated_independent=range_metrics(corrected_error))
    # Paired CI on *per-run mean squared* 2D error difference, not on correlated steps.
    mse_dr = np.mean(np.sum(outputs['DR']['error'][:, 1:, :2]**2, axis=-1), axis=1)
    mse_ideal = np.mean(np.sum(outputs['EKF_IDEAL']['error'][:, 1:, :2]**2, axis=-1), axis=1)
    paired_improvement = mse_dr-mse_ideal
    rng_boot = np.random.default_rng(config.seed+1)
    boot_idx = rng_boot.integers(0, config.runs, (1500, config.runs))
    boot_ci = np.quantile(paired_improvement[boot_idx].mean(axis=1), [.025, .975])
    meta = dict(
        config=asdict(config),
        ground_truth='fully synthetic, no real RF / ROS / map ground truth',
        range=ranging,
        methods=results,
        pairing=dict(
            paired_mse_gain_mean_m2=float(paired_improvement.mean()),
            paired_mse_gain_95pct_bootstrap_ci_m2=[float(x) for x in boot_ci],
            percent_runs_with_mse_improvement=float(100*np.mean(paired_improvement > 0)),
            ideal_2d_rmse_improvement_pct=float(
                100*(1-results['EKF_IDEAL']['rmse_2d_m']/results['DR']['rmse_2d_m']))),
        environment=dict(
            source_repo='myoungsunk/sionna-resimulation',
            source_branch='codex/range-only-bias-consistency-20261011',
            source_commit='cd8f3ef90b9307ee079b4ec7a0cef552b4644c10',
            source_file='src/qclean_uwb/scenarios/corridor.py',
            source_blob_sha='eba1ab64d5e2117bfd519ceb5cac077b24caf3f8',
            note='Github CorridorSetup values explicitly marked placeholders, not measured',
            anchor_xyz_m=[config.anchor_x_m,config.anchor_y_m,config.anchor_z_m],
            robot_tag_z_m=config.tag_z_m, robot_tag_horizontal_lever_arm_m=[0,0],
            robot_start_xy_m=[config.start_x_m,config.start_y_m],
            robot_y_limit_m=float(config.robot_y_limit_m),
            robot_x_range_m=[config.robot_x_min_m,config.robot_x_max_m],
            corridor_lwh_m=[config.corridor_length_m,config.corridor_width_m,config.corridor_height_m],
            nominal_path_end_xy_m=[config.start_x_m+config.n_steps*config.step_m,config.start_y_m],
            ),
        true_robot_wall_violations=dict(
            fraction_of_samples_pct=float(100*np.mean(
                (np.abs(data['true'][:, :, 1]) > config.robot_y_limit_m) |
                (data['true'][:, :, 0] < config.robot_x_min_m) |
                (data['true'][:, :, 0] > config.robot_x_max_m))),
            fraction_of_runs_pct=float(100*np.mean(np.any(
                (np.abs(data['true'][:, :, 1]) > config.robot_y_limit_m) |
                (data['true'][:, :, 0] < config.robot_x_min_m) |
                (data['true'][:, :, 0] > config.robot_x_max_m),axis=1))),
            criterion='github robot centre conservative allowed x and y envelope; NOT used as motion constraint',
        ),
        references=dict(nis_mean_expected=1., nees_xy_mean_expected=2.,
                        nees_pose_mean_expected=3., ellipse_2d_95_chisq=CHI2_95_2,
                        ellipsoid_pose_3d_95_chisq=CHI2_95_3, nis_scalar_95_chisq=CHI2_95_1),
    )
    (output_dir/'results.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    pd.DataFrame.from_dict(results, orient='index').rename_axis('method').to_csv(
        output_dir/'methods_summary.csv', float_format='%.7f')
    pd.DataFrame.from_dict(ranging, orient='index').rename_axis('ranging_condition').to_csv(
        output_dir/'ranging_summary.csv', float_format='%.7f')

    rows = []
    for key in keys:
        e = outputs[key]['error']
        for j in range(config.n_steps+1):
            rows.append(dict(method=key, step=j, nominal_distance_m=j*config.step_m,
                             rmse_x_m=float(np.sqrt(np.mean(e[:, j, 0]**2))),
                             rmse_y_m=float(np.sqrt(np.mean(e[:, j, 1]**2))),
                             rmse_2d_m=float(np.sqrt(np.mean(np.sum(e[:, j, :2]**2, axis=1)))),
                             nees_xy_mean=float(np.mean(outputs[key]['nees_xy'][:, j])),
                             coverage_xy_95_pct=float(100*np.mean(outputs[key]['nees_xy'][:, j] <= CHI2_95_2)),
                             nis_mean=float(np.mean(outputs[key]['nis'][:, j])) if j>0 and key != 'DR' else None))
    pd.DataFrame(rows).to_csv(output_dir/'time_series.csv', index=False, float_format='%.7f')
    trial0 = dict(step=np.arange(config.n_steps+1),
                  nominal_distance_m=config.step_m*np.arange(config.n_steps+1),
                  x_true_m=data['true'][0,:,0], y_true_m=data['true'][0,:,1],
                  r_true_3d_m=data['r_true'][0],
                  yaw_true_rad=data['true'][0,:,2])
    for key in keys:
        trial0[f'{key}_x_m'] = outputs[key]['estimate'][0,:,0]
        trial0[f'{key}_y_m'] = outputs[key]['estimate'][0,:,1]
        trial0[f'{key}_yaw_rad'] = outputs[key]['estimate'][0,:,2]
        trial0[f'{key}_nees_xy'] = outputs[key]['nees_xy'][0]
        trial0[f'{key}_nis'] = outputs[key]['nis'][0]
    trial0['ideal_range_m'] = np.r_[np.nan, data['z_ideal'][0]]
    trial0['biased_range_m'] = np.r_[np.nan, data['z_biased'][0]]
    pd.DataFrame(trial0).to_csv(output_dir/'sample_run_0.csv', index=False, float_format='%.7f')
    report_plots(config, data, outputs, output_dir)
    rmse_dr = results['DR']['rmse_2d_m']
    rmse_i = results['EKF_IDEAL']['rmse_2d_m']
    rmse_b = results['EKF_BIASED']['rmse_2d_m']
    rmse_c = results['EKF_CALIBRATED']['rmse_2d_m']
    readme = f'''# 단일 앵커 Range-only + DR/EKF 복도 시뮬레이션

**주의: 실제 RF·ROS·터틀봇 측정이 아닌 전부 합성(Synthetic) 데이터입니다.**

## 환경과 재현 방법

- 복도: 길이 {config.corridor_length_m:g} m × 폭 {config.corridor_width_m:g} m × 높이 {config.corridor_height_m:g} m (벽 y=±{config.corridor_width_m/2:g} m)
- 고정 단일 앵커: ({config.anchor_x_m}, {config.anchor_y_m}, {config.anchor_z_m}) m. 천장 마운트 및 0.05 m standoff.
- 로봇 태그: robot centre와 동일한 XY, z={config.tag_z_m:g} m (수평 lever arm 0), 앵커–태그 높이 차이 {config.anchor_z_m-config.tag_z_m:.2f} m
- 로봇 허용 영역: x∈[{config.robot_x_min_m:g}, {config.robot_x_max_m:g}] m, |y|≤{config.robot_y_limit_m:.3f} m (그림·위반 진단에만 사용, 운동 강제는 하지 않음)
- 로봇: ({config.start_x_m:g}, {config.start_y_m:g}, 0 rad)에서 시작, {config.step_m} m/step, {config.dt_s} s/step, 명목 주행속도 {config.step_m/config.dt_s:g} m/s, {config.n_steps} step
- DR이 보고하는 상대 운동은 각 step마다 Δs={config.step_m} m, Δyaw=0; 실제 로봇의 해당 상대 운동에는 독립적인 Gaussian 오차가 있음
- DR 상대 이동 표준편차: {config.dr_step_std_m} m/step, 상대 yaw 표준편차 {config.dr_yaw_step_std_deg}°/step
- 최초 3-state pose의 추정 오차: σ_xy={config.initial_xy_std_m} m, σ_yaw={config.initial_yaw_std_deg}° (초기 heading에 별도 유한 사전 정보 존재)
- Range: RSS/도착시간 수신 시뮬레이션이 아닌 **기하학적 range + Gaussian measurement noise**; σ={config.range_std_m} m
- RF 편향 시나리오: 추가 +{config.range_bias_m} m (거리/각도에 무관한 일정한 편향이라는 **가정**)
- RF bias calibration: **시험 데이터와 독립된** {config.independent_calibration_samples}개의 합성 관측으로 bias 추정. 보정 후 남는 공통 bias 불확실성은 calibrated EKF의 4번째 상태로 추적
- 무작위 seed={config.seed}, Monte Carlo {config.runs}회. 복도 벽 충돌 물리모델/반사경로 없음
- **GitHub 근거:** `myoungsunk/sionna-resimulation`, `codex/range-only-bias-consistency-20261011`, `src/qclean_uwb/scenarios/corridor.py` (blob `eba1ab64d5e2117bfd519ceb5cac077b24caf3f8`). 이 수치는 원본 소스의 주석상 실측이 아닌 **placeholder**임.
- 이전 10m × 2m 복도에서 **환경 기하만 변경**. 운동/필터/노이즈 및 10m 주행 길이는 동일하며, 실제 Sionna RT ray tracing은 사용하지 않음.

실행:

```bash
python3 -m pip install numpy pandas matplotlib
python3 corridor_sim.py --runs {config.runs} --seed {config.seed}
python3 sensitivity_yaw.py --runs {config.runs} --seed {config.seed}
python3 qa_checks.py
```

다른 옵션:

```bash
python3 corridor_sim.py --runs 1000 --seed 42 --initial-yaw-deg 4 --range-bias 0.20 --output-dir repeat_seed42
```

## 결과(전체 주행 위치 2D RMSE, 초기 step 제외)

| 방법 | RMSE (m) | 2D NEES 평균 (기대 2) | 95% 위치 타원 실제 포함률 | NIS 평균 (기대 1) |
|---|---:|---:|---:|---:|
'''
    for key in keys:
        v = results[key]
        nis = f'{v["nis_mean"]:.3f}' if v['nis_mean'] is not None else '해당 없음'
        readme += (f'| {key} | {v["rmse_2d_m"]:.3f} | {v["nees_xy_mean"]:.3f} | '
                   f'{v["coverage_xy_95_pct"]:.1f}% | {nis} |\n')
    readme += f'''
- DR 대비 unbiased EKF 2D RMSE 감소율: **{100*(1-rmse_i/rmse_dr):.1f}%** (해당 *합성* 시뮬레이션에 한정)
- Biased raw range EKF 2D RMSE: {rmse_b:.3f} m; 독립 보정 EKF: {rmse_c:.3f} m
- 정상 Range EKF 종료 지점의 95% 타원 포함률: **{results['EKF_IDEAL']['final_coverage_xy_95_pct']:.1f}%** (목표 95%). 초깃값 heading 불확실성을 키우면 더 악화됨.
- Bias EKF는 평균 NIS={results['EKF_BIASED']['nis_mean']:.2f}로 그럴듯하지만 평균 NEES2D={results['EKF_BIASED']['nees_xy_mean']:.1f}로 극심한 공분산 과신을 보임. **NIS 단독으로 정합성을 증명할 수 없음**
- DR→unbiased EKF 2D MSE 개선량의 paired bootstrap 95% CI: **[{boot_ci[0]:.4f}, {boot_ci[1]:.4f}] m²** (단위 표본: 독립 주행)
- 로봇 GT의 허용 영역(보수적 차체 회전 여유) 위반 샘플: {meta['true_robot_wall_violations']['fraction_of_samples_pct']:.3f}%, 경계 위반 주행: {meta['true_robot_wall_violations']['fraction_of_runs_pct']:.1f}%

## 파일 구성

- `corridor_sim.py`: 시뮬레이터·Jacobian EKF·Monte Carlo 및 지표 구현
- `quick_demo.py`: 축약 실행 예제 (DR·정상 EKF·편향 EKF 수치 즉시 출력)
- `sensitivity_yaw.py`: 초기 heading prior 표준편차 0.2°~6° 민감도 실험
- `qa_checks.py`: Jacobian 유한차분·단일 앵커 회전 대칭·난수 재현성·공분산 PSD 검사
- `results.json`: 설정·지표·기준값·paired bootstrap CI (원본 수치)
- `ranging_summary.csv`, `methods_summary.csv`: 수치 요약
- `time_series.csv`: 거리/step별 정확도·NEES·NIS·coverage
- `sample_run_0.csv`: 임의 선택하지 않은 첫 번째 주행의 GT와 필터 상태
- `00_github_geometry_top_side.png`: GitHub 복도의 평면·높이 치수
- `01_corridor_trajectory.png`: 복도/앵커/GT/추정 경로
- `02_accuracy_consistency.png`: RMSE·x/y 분리·NEES·NIS
- `03_ranging_coverage.png`: 거리 에러 및 위치 신뢰타원 포함률
- `sensitivity_initial_yaw.csv`, `04_initial_yaw_sensitivity.png`: 추가 heading 민감도 분석 (별도 script 실행)
- `QA_REPORT.txt`: 별도 QA script 실행 결과

## 수학 모델

상태 $s=[x,y,\\psi]^T$이고 복도 방향은 x, 횡방향은 y.

$$
\\begin{{aligned}}
\\phi_k &= \\psi_k+\\frac{{\\Delta\\psi_k}}{{2}},\\\\
x_{{k+1}} &= x_k+\\Delta s_k\\cos\\phi_k,\\\\
y_{{k+1}} &= y_k+\\Delta s_k\\sin\\phi_k,\\\\
\\psi_{{k+1}} &= \\psi_k+\\Delta\\psi_k.
\\end{{aligned}}
$$

Process covariance: $P^-=FPF^T+G\\operatorname{{diag}}(\\sigma_s^2,\\sigma_\\psi^2)G^T$.

$$
z=\\sqrt{{(x-a_x)^2+(y-a_y)^2+(z_t-z_a)^2}}+b+\\epsilon,
\\quad H=\\begin{{bmatrix}}(x-a_x)/r & (y-a_y)/r & 0\\end{{bmatrix}}
$$

NIS: $\\nu^2/S$ (expectation 1 under model); 2D position NEES: $e_{{xy}}^TP_{{xy}}^{{-1}}e_{{xy}}$ (expectation 2); 95% confidence ellipse: $\\mathrm{{NEES}}_{{xy}}\\leq 5.991$. 3D pose NEES expectation 3. `EKF_CALIBRATED` adds one constant residual-bias state after independent bias calibration, explicitly propagating bias uncertainty across repeated range updates. EKF covariance update uses Joseph form.

## 해석 시 한계 및 연구 활용

1. **이것은 알고리즘 기초 sanity check**입니다. Simulated Gaussian noise와 EKF 가정이 맞아 NIS/NEES가 정상이어도 실제 UWB ranging 성능이 검증되었다는 의미가 아닙니다.
2. 측정은 **range만** 사용합니다. 실제 heading 센서·복도 중심선 제약·벽맵·SLAM·카메라·관성 절대방향은 추가하지 않았습니다.
3. 단일 앵커+상대 DR에는 앵커 주위의 전체 궤적 회전 대칭이 있습니다. **절대 heading은 측정만으로 결정되지 않으며 초기 pose prior에 의존**합니다.
4. x/y 오차를 반드시 분리해야 합니다. 앵커와 복도 끝의 거리 기하 때문에 방향별 거리 관측 민감도가 다릅니다.
5. RF 편향은 시간·방향·거리 무관 고정 +0.2 m라는 인위적 stress case입니다. 복도 다중경로의 시간 상관, NLoS, first-path 검출 편향은 구현하지 않았습니다.
6. 복도 벽의 충돌·접촉 및 운동 제약은 적용하지 않았습니다. 이 시뮬레이션에서는 허용영역 벗어남 비율을 기록합니다. 벽면의 존재는 그림상의 구획만 표시합니다.
7. 평균 NIS/NEES를 검증할 때 모든 연속 시점을 독립표본으로 보지 않습니다. paired bootstrap은 주행별 MSE를 단위 표본으로 사용합니다. `final_coverage_xy_95_pct`는 독립 주행의 종료 지점 기준입니다.
8. Range-only EKF vs DR comparison is not a proof of universal performance: change anchor geometry, yaw noise, priors and bias to assess sensitivity.

## 추가 감사 및 비교 파일

- `GITHUB_GEOMETRY_SOURCE.json`: GitHub branch·commit·blob SHA·기하 설정 스냅샷
- `SOURCE_AND_CHANGE_AUDIT_KO.md`: 이전 시뮬레이션과 GitHub 환경 간 비교, 변경 및 유지 항목
- `BASELINE_VS_GITHUB.csv`: 방법별 이전/신규 지표 비교
- `PATCH_FROM_BASELINE.diff`: 기존 시뮬레이터에서 변경한 코드 위치
- `05_geometry_jacobian.png`: 진행/횡방향 기하학적 range 민감도
- 위 보조 산출물은 현재 ZIP의 스냅샷이며, `corridor_sim.py` 단독 재실행으로는 생성되지 않음.
'''
    (output_dir/'README_KO.md').write_text(readme, encoding='utf-8')
    print('\n=== INPUT ASSUMPTIONS (SYNTHETIC) ===')
    print('runs', config.runs, 'steps', config.n_steps, 'corridor_LWH',
          (config.corridor_length_m,config.corridor_width_m,config.corridor_height_m),
          'anchor_xyz', (config.anchor_x_m, config.anchor_y_m,config.anchor_z_m),
          'tag_z',config.tag_z_m,'start_xy',(config.start_x_m,config.start_y_m))
    print('\n=== RANGE ===')
    print(pd.DataFrame.from_dict(ranging, orient='index').round(4).to_string())
    print('\n=== FILTER METRICS ===')
    print(pd.DataFrame.from_dict(results, orient='index').round(3).to_string())
    print('\n=== PAIRED RUN MSE GAIN CI ===')
    print(meta['pairing'])
    print('wall violations:', meta['true_robot_wall_violations'])
    print('Wrote files to:', output_dir.resolve())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=int, default=Config.runs)
    parser.add_argument('--seed', type=int, default=Config.seed)
    parser.add_argument('--steps', type=int, default=Config.n_steps)
    parser.add_argument('--anchor-x', type=float, default=Config.anchor_x_m)
    parser.add_argument('--anchor-y', type=float, default=Config.anchor_y_m)
    parser.add_argument('--anchor-z', type=float, default=Config.anchor_z_m)
    parser.add_argument('--tag-z', type=float, default=Config.tag_z_m)
    parser.add_argument('--start-x', type=float, default=Config.start_x_m)
    parser.add_argument('--start-y', type=float, default=Config.start_y_m)
    parser.add_argument('--corridor-width', type=float, default=Config.corridor_width_m)
    parser.add_argument('--corridor-length', type=float, default=Config.corridor_length_m)
    parser.add_argument('--corridor-height', type=float, default=Config.corridor_height_m)
    parser.add_argument('--initial-yaw-deg', type=float, default=Config.initial_yaw_std_deg)
    parser.add_argument('--initial-xy-std', type=float, default=Config.initial_xy_std_m)
    parser.add_argument('--dr-step-std', type=float, default=Config.dr_step_std_m)
    parser.add_argument('--dr-yaw-step-deg', type=float, default=Config.dr_yaw_step_std_deg)
    parser.add_argument('--range-std', type=float, default=Config.range_std_m)
    parser.add_argument('--range-bias', type=float, default=Config.range_bias_m)
    parser.add_argument('--calibration-samples', type=int, default=Config.independent_calibration_samples)
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    if args.runs < 10:
        parser.error('runs must be >= 10 for Monte Carlo consistency diagnostics')
    if args.steps < 1 or args.calibration_samples < 1:
        parser.error('steps and calibration-samples must be >= 1')
    if args.range_std <= 0 or args.initial_xy_std <= 0 or args.initial_yaw_deg <= 0:
        parser.error('range-std, initial-xy-std and initial-yaw-deg must be positive')
    if args.dr_step_std < 0 or args.dr_yaw_step_deg < 0 or args.corridor_width <= 0:
        parser.error('motion noise cannot be negative; corridor-width must be positive')
    cfg = Config(runs=args.runs, seed=args.seed, n_steps=args.steps,
                 anchor_x_m=args.anchor_x, anchor_y_m=args.anchor_y,
                 anchor_z_m=args.anchor_z, tag_z_m=args.tag_z,
                 start_x_m=args.start_x, start_y_m=args.start_y,
                 corridor_length_m=args.corridor_length,
                 corridor_height_m=args.corridor_height,
                 corridor_width_m=args.corridor_width,
                 initial_yaw_std_deg=args.initial_yaw_deg,
                 initial_xy_std_m=args.initial_xy_std,
                 dr_step_std_m=args.dr_step_std,
                 dr_yaw_step_std_deg=args.dr_yaw_step_deg,
                 range_std_m=args.range_std, range_bias_m=args.range_bias,
                 independent_calibration_samples=args.calibration_samples)
    if not (0 < cfg.anchor_x_m < cfg.corridor_length_m and
            abs(cfg.anchor_y_m) < cfg.corridor_width_m/2 and
            0 < cfg.tag_z_m < cfg.anchor_z_m < cfg.corridor_height_m):
        parser.error('Anchor/tag not within valid 3D corridor limits')
    if not (cfg.robot_x_min_m <= cfg.start_x_m <= cfg.robot_x_max_m and
            cfg.robot_x_min_m <= cfg.start_x_m+cfg.step_m*cfg.n_steps <= cfg.robot_x_max_m and
            abs(cfg.start_y_m) <= cfg.robot_y_limit_m):
        parser.error('Nominal 10m path start/end outside GitHub robot allowable region')
    run(cfg, args.output_dir)


if __name__ == '__main__':
    main()
