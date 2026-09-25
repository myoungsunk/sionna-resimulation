from __future__ import annotations

import argparse

from rt_cp_uwb_py.remote import run_remote_sim_new_cp_va_slam


def main() -> int:
    ap = argparse.ArgumentParser(description="Run SIM_NEW_CP_VA_SLAM_01 Stage 0-7 on the configured server.")
    ap.add_argument("--ssh-target", default="root@141.223.86.156")
    ap.add_argument("--remote-root", default="/root/rt_cp_uwb_python_port")
    ap.add_argument("--num-snapshots", type=int, default=200)
    ap.add_argument("--scene-ids", default="R0,R1A,R2,R3,R4,R5")
    ap.add_argument("--trajectory-ids", default="T0,T1,T2,T3,T4,T5,T6,T7")
    ap.add_argument(
        "--scenario-pairs",
        default="",
        help="Optional comma-separated SCENE:TRAJECTORY pairs for stress-test execution.",
    )
    ap.add_argument(
        "--algorithm-ids",
        default="",
        help="Optional comma-separated ablation arm ids. Empty preserves the default B0-B15 set.",
    )
    ap.add_argument("--bandwidth-hz", type=float, default=2.0e9)
    ap.add_argument("--max-reflections", type=int, default=2)
    ap.add_argument("--num-paths-max", type=int, default=18)
    ap.add_argument(
        "--range-estimator-mode",
        choices=["peak_group_center", "lde_proxy", "h10b_artifact_lde", "h10b_artifact_range", "h10b_raw_cir_lde"],
        default="peak_group_center",
    )
    ap.add_argument("--lde-relative-threshold", type=float, default=0.20)
    ap.add_argument("--lde-noise-scale", type=float, default=0.10)
    ap.add_argument("--solver-num-particles", type=int, default=48)
    ap.add_argument("--solver-max-candidates", type=int, default=24)
    ap.add_argument("--solver-da-particle-top", type=int, default=16)
    ap.add_argument("--polarization-mode", choices=["CP", "LP"], default="CP")
    ap.add_argument("--anchor-linear-pol-axis-deg", type=float, default=0.0)
    ap.add_argument("--tag-ant1-linear-pol-axis-deg", type=float, default=0.0)
    ap.add_argument("--tag-ant2-linear-pol-axis-deg", type=float, default=90.0)
    ap.add_argument("--tag-pol-tilt-deg", type=float, default=0.0)
    ap.add_argument("--anchor-pol-tilt-deg", type=float, default=0.0)
    ap.add_argument(
        "--tag-antenna-model-mode",
        choices=["synthetic_proxy", "legacy_h10b_dual_tilted", "tilted_real_pattern"],
        default="synthetic_proxy",
    )
    ap.add_argument(
        "--legacy-dual-tag-artifact-path",
        default="scripts/results/dual_tag_h10b_alpha_sweep_rot0_fixed_azimuth_20260510_fullrun/alpha060_chunks/chunk_0601_0900/dual_tag_features_wide.csv",
    )
    ap.add_argument("--legacy-dual-tag-rssd-channel", choices=["total", "rh", "lh", "mean_pol"], default="total")
    ap.add_argument("--legacy-dual-tag-alpha-deg", type=float, default=60.0)
    ap.add_argument("--legacy-dual-tag-rotation-deg", type=float, default=0.0)
    ap.add_argument("--legacy-dual-tag-rssd-prediction-mode", choices=["auto", "synthetic_proxy", "artifact_lut", "tilted_real_pattern"], default="auto")
    ap.add_argument("--legacy-dual-tag-power-offset-mode", choices=["auto", "none", "match_existing_amp"], default="auto")
    ap.add_argument("--lp-copol-gain-pattern-file", default="LP_+45_new_6G7G_11pts.ffd")
    ap.add_argument("--lp-crosspol-gain-pattern-file", default="LP_-45_new_6G7G_11pts.ffd")
    ap.add_argument("--rx-ant1-rhcp-pattern-file", default="")
    ap.add_argument("--rx-ant1-lhcp-pattern-file", default="")
    ap.add_argument("--rx-ant2-rhcp-pattern-file", default="")
    ap.add_argument("--rx-ant2-lhcp-pattern-file", default="")
    ap.add_argument("--tag-attitude-source", choices=["yaw_only", "yaw_pitch_roll"], default="yaw_only")
    ap.add_argument("--tag-pitch-deg", type=float, default=0.0)
    ap.add_argument("--tag-roll-deg", type=float, default=0.0)
    ap.add_argument("--rx-ant1-mount-rotation", default="")
    ap.add_argument("--rx-ant2-mount-rotation", default="")
    ap.add_argument("--pattern-gain-normalization", choices=["absolute_dbi", "normalized_peak0db", "raw_ffd"], default="absolute_dbi")
    ap.add_argument("--pattern-phase-convention", default="ffd_complex_field")
    ap.add_argument("--pattern-pol-basis", choices=["rhcp_lhcp", "copol_crosspol"], default="rhcp_lhcp")
    ap.add_argument("--use-te-tm-reflection", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--material-fresnel-model", default="te_tm_fresnel")
    ap.add_argument("--path-polarization-tracking", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--wall-offset-noise-m", type=float, default=0.0)
    ap.add_argument("--wall-normal-noise-deg", type=float, default=0.0)
    ap.add_argument("--odometry-noise-scale", type=float, default=1.0)
    ap.add_argument("--range-variance-scale", type=float, default=1.0)
    ap.add_argument("--perturbation-config-id", default="nominal")
    ap.add_argument(
        "--measurement-regularizer-target",
        choices=["none", "all", "positive", "g7", "spread", "g7_or_spread", "g7_or_spread_or_positive"],
        default="none",
    )
    ap.add_argument("--measurement-regularizer-centered-cap", type=float, default=0.0)
    ap.add_argument("--measurement-regularizer-spread-threshold", type=float, default=1.5)
    ap.add_argument("--measurement-regularizer-algorithms", default="B9")
    ap.add_argument("--orientation-control-mode", choices=["nominal", "yaw_noise", "yaw_shuffle", "fixed", "zero"], default="nominal")
    ap.add_argument("--yaw-noise-deg", type=float, default=0.0)
    ap.add_argument("--yaw-shuffle", action="store_true")
    ap.add_argument("--yaw-shuffle-level", choices=["within_slice", "within_sequence"], default="within_slice")
    ap.add_argument("--yaw-fixed-deg", type=float, default=0.0)
    ap.add_argument("--disable-orientation", action="store_true")
    ap.add_argument("--rssd-control-mode", choices=["nominal", "noise", "shuffle", "sign_flip", "zero"], default="nominal")
    ap.add_argument("--rssd-noise-std-db", type=float, default=0.0)
    ap.add_argument("--rssd-noise-scale", type=float, default=0.0)
    ap.add_argument("--rssd-shuffle", action="store_true")
    ap.add_argument("--rssd-shuffle-level", choices=["within_slice", "within_sequence"], default="within_slice")
    ap.add_argument("--rssd-sign-flip", action="store_true")
    ap.add_argument("--disable-rssd", action="store_true")
    ap.add_argument("--run-label", default="", help="Optional stable suffix for parallel remote result directories.")
    ap.add_argument("--conda-python", default="/opt/miniforge3/envs/rt-cp-uwb-py/bin/python")
    ap.add_argument("--no-fetch", action="store_true", help="Do not copy the finished result directory back.")
    ap.add_argument("--background", action="store_true", help="Submit via nohup and return the remote pid/log path.")
    args = ap.parse_args()

    result = run_remote_sim_new_cp_va_slam(
        ssh_target=args.ssh_target,
        remote_root=args.remote_root,
        num_snapshots=args.num_snapshots,
        scene_ids=args.scene_ids,
        trajectory_ids=args.trajectory_ids,
        scenario_pairs=args.scenario_pairs,
        algorithm_ids=args.algorithm_ids,
        bandwidth_hz=args.bandwidth_hz,
        max_reflections=args.max_reflections,
        num_paths_max=args.num_paths_max,
        range_estimator_mode=args.range_estimator_mode,
        lde_relative_threshold=args.lde_relative_threshold,
        lde_noise_scale=args.lde_noise_scale,
        solver_num_particles=args.solver_num_particles,
        solver_max_candidates=args.solver_max_candidates,
        solver_da_particle_top=args.solver_da_particle_top,
        polarization_mode=args.polarization_mode,
        anchor_linear_pol_axis_deg=args.anchor_linear_pol_axis_deg,
        tag_ant1_linear_pol_axis_deg=args.tag_ant1_linear_pol_axis_deg,
        tag_ant2_linear_pol_axis_deg=args.tag_ant2_linear_pol_axis_deg,
        tag_pol_tilt_deg=args.tag_pol_tilt_deg,
        anchor_pol_tilt_deg=args.anchor_pol_tilt_deg,
        tag_antenna_model_mode=args.tag_antenna_model_mode,
        legacy_dual_tag_artifact_path=args.legacy_dual_tag_artifact_path,
        legacy_dual_tag_rssd_channel=args.legacy_dual_tag_rssd_channel,
        legacy_dual_tag_alpha_deg=args.legacy_dual_tag_alpha_deg,
        legacy_dual_tag_rotation_deg=args.legacy_dual_tag_rotation_deg,
        legacy_dual_tag_rssd_prediction_mode=args.legacy_dual_tag_rssd_prediction_mode,
        legacy_dual_tag_power_offset_mode=args.legacy_dual_tag_power_offset_mode,
        lp_copol_gain_pattern_file=args.lp_copol_gain_pattern_file,
        lp_crosspol_gain_pattern_file=args.lp_crosspol_gain_pattern_file,
        rx_ant1_rhcp_pattern_file=args.rx_ant1_rhcp_pattern_file,
        rx_ant1_lhcp_pattern_file=args.rx_ant1_lhcp_pattern_file,
        rx_ant2_rhcp_pattern_file=args.rx_ant2_rhcp_pattern_file,
        rx_ant2_lhcp_pattern_file=args.rx_ant2_lhcp_pattern_file,
        tag_attitude_source=args.tag_attitude_source,
        tag_pitch_deg=args.tag_pitch_deg,
        tag_roll_deg=args.tag_roll_deg,
        rx_ant1_mount_rotation=args.rx_ant1_mount_rotation,
        rx_ant2_mount_rotation=args.rx_ant2_mount_rotation,
        pattern_gain_normalization=args.pattern_gain_normalization,
        pattern_phase_convention=args.pattern_phase_convention,
        pattern_pol_basis=args.pattern_pol_basis,
        use_te_tm_reflection=args.use_te_tm_reflection,
        material_fresnel_model=args.material_fresnel_model,
        path_polarization_tracking=args.path_polarization_tracking,
        wall_offset_noise_m=args.wall_offset_noise_m,
        wall_normal_noise_deg=args.wall_normal_noise_deg,
        odometry_noise_scale=args.odometry_noise_scale,
        range_variance_scale=args.range_variance_scale,
        perturbation_config_id=args.perturbation_config_id,
        measurement_regularizer_target=args.measurement_regularizer_target,
        measurement_regularizer_centered_cap=args.measurement_regularizer_centered_cap,
        measurement_regularizer_spread_threshold=args.measurement_regularizer_spread_threshold,
        measurement_regularizer_algorithms=args.measurement_regularizer_algorithms,
        orientation_control_mode=args.orientation_control_mode,
        yaw_noise_deg=args.yaw_noise_deg,
        yaw_shuffle=args.yaw_shuffle,
        yaw_shuffle_level=args.yaw_shuffle_level,
        yaw_fixed_deg=args.yaw_fixed_deg,
        disable_orientation=args.disable_orientation,
        rssd_control_mode=args.rssd_control_mode,
        rssd_noise_std_db=args.rssd_noise_std_db,
        rssd_noise_scale=args.rssd_noise_scale,
        rssd_shuffle=args.rssd_shuffle,
        rssd_shuffle_level=args.rssd_shuffle_level,
        rssd_sign_flip=args.rssd_sign_flip,
        disable_rssd=args.disable_rssd,
        run_label=args.run_label,
        conda_python=args.conda_python,
        fetch_results=not args.no_fetch,
        background=args.background,
    )
    print(f"remote_out={result['remote_out']}")
    print(f"remote_log={result['remote_log']}")
    print(f"local_out={result['local_out']}")
    if result["log"]:
        last = result["log"][-1]
        print(f"last_returncode={last['returncode']}")
        if last.get("stdout"):
            print(last["stdout"])
        if last.get("stderr"):
            print(last["stderr"])
    return 0 if result["log"] and result["log"][-1]["returncode"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
