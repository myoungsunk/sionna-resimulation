from __future__ import annotations

import json
import shlex
import subprocess
from datetime import datetime
from pathlib import Path

from .parity import find_latest_baseline_csv


def run_remote_parity(
    ssh_target: str = "root@141.223.86.156",
    remote_root: str = "/root/rt_cp_uwb_python_port",
    local_root: str | Path | None = None,
    cases_csv: str | Path | None = None,
    baseline_csv: str | Path | None = None,
    max_cases: int = 30,
    replay_fp_hints: bool = False,
) -> dict:
    local_root = Path(local_root or Path(__file__).resolve().parents[1])
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    remote_out = f"{remote_root}/results/python_server_parity_{stamp}"
    remote_baseline = f"{remote_root}/results/baseline"
    local_out = local_root / "results" / f"python_server_parity_{stamp}"
    local_out.mkdir(parents=True, exist_ok=True)
    baseline_csv = Path(baseline_csv) if baseline_csv else find_latest_baseline_csv(local_root / "results", local_out)
    remote_baseline_csv = f"{remote_baseline}/{baseline_csv.name}" if baseline_csv is not None else None
    cases_csv = Path(cases_csv) if cases_csv else None
    remote_cases_csv = f"{remote_root}/{cases_csv.name}" if cases_csv is not None else None
    commands = [
        ["ssh", ssh_target, f"mkdir -p {remote_root} {remote_baseline}"],
        ["scp", "-r", str(local_root / "rt_cp_uwb_py"), f"{ssh_target}:{remote_root}/"],
        ["scp", str(local_root / "CP_SCENARIO_A_7CASE.csv"), f"{ssh_target}:{remote_root}/"],
    ]
    for ffd_name in ["RHCP_new_6G7G_11pts.ffd", "LHCP_new_6G7G_11pts.ffd"]:
        ffd_path = local_root / ffd_name
        if ffd_path.exists():
            commands.append(["scp", str(ffd_path), f"{ssh_target}:{remote_root}/"])
    if baseline_csv is not None:
        commands.append(["scp", str(baseline_csv), f"{ssh_target}:{remote_baseline}/"])
    if cases_csv is not None:
        commands.append(["scp", str(cases_csv), f"{ssh_target}:{remote_root}/"])
    conda_python = "conda run -n rt-cp-uwb-py python"
    dependency_probe = (
        f"{conda_python} -c "
        "'import numpy,pandas,scipy,sklearn,matplotlib,yaml; "
        "print(\"rt-cp-uwb-py dependency probe ok\")'"
    )
    parity_cmd = f"cd {remote_root} && PYTHONPATH={remote_root} {conda_python} -m rt_cp_uwb_py.cli.run_parity_suite --baseline-root {remote_baseline} --out {remote_out} --max-cases {int(max_cases)}"
    if remote_baseline_csv is not None:
        parity_cmd += f" --baseline-csv {remote_baseline_csv}"
    if remote_cases_csv is not None:
        parity_cmd += f" --cases-csv {remote_cases_csv}"
    if replay_fp_hints:
        parity_cmd += " --replay-fp-hints"
    commands.extend([
        ["ssh", ssh_target, dependency_probe],
        ["ssh", ssh_target, parity_cmd],
        ["scp", "-r", f"{ssh_target}:{remote_out}/.", str(local_out)],
    ])
    log = []
    for cmd in commands:
        proc = subprocess.run(
            cmd,
            cwd=local_root,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        log.append({"cmd": cmd, "returncode": proc.returncode, "stdout": stdout[-4000:], "stderr": stderr[-4000:]})
        if proc.returncode != 0:
            break
    result = {
        "ssh_target": ssh_target,
        "remote_root": remote_root,
        "remote_out": remote_out,
        "local_out": str(local_out),
        "baseline_csv": str(baseline_csv) if baseline_csv else None,
        "cases_csv": str(cases_csv) if cases_csv else None,
        "max_cases": int(max_cases),
        "replay_fp_hints": bool(replay_fp_hints),
        "log": log,
    }
    (local_out / "remote_execution_log.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def run_remote_sim_new_cp_va_slam(
    ssh_target: str = "root@141.223.86.156",
    remote_root: str = "/root/rt_cp_uwb_python_port",
    local_root: str | Path | None = None,
    num_snapshots: int = 200,
    scene_ids: str = "R0,R1A,R2,R3,R4,R5",
    trajectory_ids: str = "T0,T1,T2,T3,T4,T5,T6,T7",
    scenario_pairs: str = "",
    algorithm_ids: str = "",
    bandwidth_hz: float = 2.0e9,
    max_reflections: int = 2,
    num_paths_max: int = 18,
    range_estimator_mode: str = "peak_group_center",
    lde_relative_threshold: float = 0.20,
    lde_noise_scale: float = 0.10,
    solver_num_particles: int = 48,
    solver_max_candidates: int = 24,
    solver_da_particle_top: int = 16,
    polarization_mode: str = "CP",
    anchor_linear_pol_axis_deg: float = 0.0,
    tag_ant1_linear_pol_axis_deg: float = 0.0,
    tag_ant2_linear_pol_axis_deg: float = 90.0,
    tag_pol_tilt_deg: float = 0.0,
    anchor_pol_tilt_deg: float = 0.0,
    tag_antenna_model_mode: str = "synthetic_proxy",
    legacy_dual_tag_artifact_path: str = (
        "scripts/results/dual_tag_h10b_alpha_sweep_rot0_fixed_azimuth_20260510_fullrun/"
        "alpha060_chunks/chunk_0601_0900/dual_tag_features_wide.csv"
    ),
    legacy_dual_tag_rssd_channel: str = "total",
    legacy_dual_tag_alpha_deg: float = 60.0,
    legacy_dual_tag_rotation_deg: float = 0.0,
    legacy_dual_tag_rssd_prediction_mode: str = "auto",
    legacy_dual_tag_power_offset_mode: str = "auto",
    lp_copol_gain_pattern_file: str = "LP_+45_new_6G7G_11pts.ffd",
    lp_crosspol_gain_pattern_file: str = "LP_-45_new_6G7G_11pts.ffd",
    rx_ant1_rhcp_pattern_file: str = "",
    rx_ant1_lhcp_pattern_file: str = "",
    rx_ant2_rhcp_pattern_file: str = "",
    rx_ant2_lhcp_pattern_file: str = "",
    tag_attitude_source: str = "yaw_only",
    tag_pitch_deg: float = 0.0,
    tag_roll_deg: float = 0.0,
    rx_ant1_mount_rotation: str = "",
    rx_ant2_mount_rotation: str = "",
    pattern_gain_normalization: str = "absolute_dbi",
    pattern_phase_convention: str = "ffd_complex_field",
    pattern_pol_basis: str = "rhcp_lhcp",
    use_te_tm_reflection: bool = True,
    material_fresnel_model: str = "te_tm_fresnel",
    path_polarization_tracking: bool = True,
    wall_offset_noise_m: float = 0.0,
    wall_normal_noise_deg: float = 0.0,
    odometry_noise_scale: float = 1.0,
    range_variance_scale: float = 1.0,
    perturbation_config_id: str = "nominal",
    measurement_regularizer_target: str = "none",
    measurement_regularizer_centered_cap: float = 0.0,
    measurement_regularizer_spread_threshold: float = 1.5,
    measurement_regularizer_algorithms: str = "B9",
    orientation_control_mode: str = "nominal",
    yaw_noise_deg: float = 0.0,
    yaw_shuffle: bool = False,
    yaw_shuffle_level: str = "within_slice",
    yaw_fixed_deg: float = 0.0,
    disable_orientation: bool = False,
    rssd_control_mode: str = "nominal",
    rssd_noise_std_db: float = 0.0,
    rssd_noise_scale: float = 0.0,
    rssd_shuffle: bool = False,
    rssd_shuffle_level: str = "within_slice",
    rssd_sign_flip: bool = False,
    disable_rssd: bool = False,
    run_label: str = "",
    conda_python: str = "/opt/miniforge3/envs/rt-cp-uwb-py/bin/python",
    fetch_results: bool = True,
    background: bool = False,
) -> dict:
    """Run SIM_NEW_CP_VA_SLAM_01 on the configured Linux server.

    This launcher mirrors the existing parity remote workflow but copies the
    Stage 0-7 simulation runner, schema validator, Python package, and docs. It
    can either block until completion and fetch outputs, or submit a nohup job
    and return the remote log path for a long main/long run.
    """

    local_root = Path(local_root or Path(__file__).resolve().parents[1])
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_label = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(run_label).strip())
    run_suffix = f"{stamp}_{safe_label}" if safe_label else stamp
    remote_out = f"{remote_root}/results/sim_new_cp_va_slam_server_{run_suffix}"
    local_out = local_root / "results" / f"sim_new_cp_va_slam_server_{run_suffix}"
    local_out.mkdir(parents=True, exist_ok=True)
    remote_log = f"{remote_out}.log"
    remote_pid = f"{remote_out}.pid"

    run_cmd = (
        f"cd {remote_root} && PYTHONPATH={remote_root} {conda_python} "
        "scripts/run_sim_new_cp_va_slam_all_stages.py "
        f"--output-dir {remote_out} "
        f"--run-id SIM_NEW_CP_VA_SLAM_01_SERVER_{run_suffix} "
        f"--num-snapshots {int(num_snapshots)} "
        f"--bandwidth-hz {float(bandwidth_hz)} "
        f"--max-reflections {int(max_reflections)} "
        f"--num-paths-max {int(num_paths_max)} "
        f"--range-estimator-mode {range_estimator_mode} "
        f"--lde-relative-threshold {float(lde_relative_threshold)} "
        f"--lde-noise-scale {float(lde_noise_scale)} "
        f"--solver-num-particles {int(solver_num_particles)} "
        f"--solver-max-candidates {int(solver_max_candidates)} "
        f"--solver-da-particle-top {int(solver_da_particle_top)} "
        f"--polarization-mode {polarization_mode} "
        f"--anchor-linear-pol-axis-deg {float(anchor_linear_pol_axis_deg)} "
        f"--tag-ant1-linear-pol-axis-deg {float(tag_ant1_linear_pol_axis_deg)} "
        f"--tag-ant2-linear-pol-axis-deg {float(tag_ant2_linear_pol_axis_deg)} "
        f"--tag-pol-tilt-deg {float(tag_pol_tilt_deg)} "
        f"--anchor-pol-tilt-deg {float(anchor_pol_tilt_deg)} "
        f"--tag-antenna-model-mode {tag_antenna_model_mode} "
        f"--legacy-dual-tag-artifact-path {legacy_dual_tag_artifact_path} "
        f"--legacy-dual-tag-rssd-channel {legacy_dual_tag_rssd_channel} "
        f"--legacy-dual-tag-alpha-deg {float(legacy_dual_tag_alpha_deg)} "
        f"--legacy-dual-tag-rotation-deg {float(legacy_dual_tag_rotation_deg)} "
        f"--legacy-dual-tag-rssd-prediction-mode {legacy_dual_tag_rssd_prediction_mode} "
        f"--legacy-dual-tag-power-offset-mode {legacy_dual_tag_power_offset_mode} "
        f"--lp-copol-gain-pattern-file {lp_copol_gain_pattern_file} "
        f"--lp-crosspol-gain-pattern-file {lp_crosspol_gain_pattern_file} "
        f"--rx-ant1-rhcp-pattern-file {shlex.quote(str(rx_ant1_rhcp_pattern_file))} "
        f"--rx-ant1-lhcp-pattern-file {shlex.quote(str(rx_ant1_lhcp_pattern_file))} "
        f"--rx-ant2-rhcp-pattern-file {shlex.quote(str(rx_ant2_rhcp_pattern_file))} "
        f"--rx-ant2-lhcp-pattern-file {shlex.quote(str(rx_ant2_lhcp_pattern_file))} "
        f"--tag-attitude-source {shlex.quote(str(tag_attitude_source))} "
        f"--tag-pitch-deg {float(tag_pitch_deg)} "
        f"--tag-roll-deg {float(tag_roll_deg)} "
        f"--rx-ant1-mount-rotation {shlex.quote(str(rx_ant1_mount_rotation))} "
        f"--rx-ant2-mount-rotation {shlex.quote(str(rx_ant2_mount_rotation))} "
        f"--pattern-gain-normalization {shlex.quote(str(pattern_gain_normalization))} "
        f"--pattern-phase-convention {shlex.quote(str(pattern_phase_convention))} "
        f"--pattern-pol-basis {shlex.quote(str(pattern_pol_basis))} "
        f"{'--use-te-tm-reflection' if use_te_tm_reflection else '--no-use-te-tm-reflection'} "
        f"--material-fresnel-model {material_fresnel_model} "
        f"{'--path-polarization-tracking' if path_polarization_tracking else '--no-path-polarization-tracking'} "
        f"--wall-offset-noise-m {float(wall_offset_noise_m)} "
        f"--wall-normal-noise-deg {float(wall_normal_noise_deg)} "
        f"--odometry-noise-scale {float(odometry_noise_scale)} "
        f"--range-variance-scale {float(range_variance_scale)} "
        f"--perturbation-config-id {perturbation_config_id} "
        f"--measurement-regularizer-target {measurement_regularizer_target} "
        f"--measurement-regularizer-centered-cap {float(measurement_regularizer_centered_cap)} "
        f"--measurement-regularizer-spread-threshold {float(measurement_regularizer_spread_threshold)} "
        f"--measurement-regularizer-algorithms {measurement_regularizer_algorithms} "
        f"--orientation-control-mode {orientation_control_mode} "
        f"--yaw-noise-deg {float(yaw_noise_deg)} "
        f"{'--yaw-shuffle' if yaw_shuffle else ''} "
        f"--yaw-shuffle-level {yaw_shuffle_level} "
        f"--yaw-fixed-deg {float(yaw_fixed_deg)} "
        f"{'--disable-orientation' if disable_orientation else ''} "
        f"--rssd-control-mode {rssd_control_mode} "
        f"--rssd-noise-std-db {float(rssd_noise_std_db)} "
        f"--rssd-noise-scale {float(rssd_noise_scale)} "
        f"{'--rssd-shuffle' if rssd_shuffle else ''} "
        f"--rssd-shuffle-level {rssd_shuffle_level} "
        f"{'--rssd-sign-flip' if rssd_sign_flip else ''} "
        f"{'--disable-rssd' if disable_rssd else ''} "
        f"--scene-ids {scene_ids} "
        f"--trajectory-ids {trajectory_ids}"
    )
    if scenario_pairs:
        run_cmd += f" --scenario-pairs {scenario_pairs}"
    if algorithm_ids:
        run_cmd += f" --algorithm-ids {algorithm_ids}"
    validate_cmd = (
        f"cd {remote_root} && PYTHONPATH={remote_root} {conda_python} "
        "scripts/validate_sim_new_cp_va_slam_schema.py "
        f"--output-dir {remote_out} --priority all"
    )
    if background:
        server_run_cmd = f"mkdir -p {remote_out} && nohup bash -lc {json.dumps(run_cmd + ' && ' + validate_cmd)} > {remote_log} 2>&1 & echo $! > {remote_pid}"
    else:
        server_run_cmd = run_cmd + " && " + validate_cmd

    commands = [
        ["ssh", ssh_target, f"mkdir -p {remote_root}/scripts {remote_root}/docs/sim_new_cp_va_slam {remote_root}/results"],
        ["scp", "-r", str(local_root / "rt_cp_uwb_py"), f"{ssh_target}:{remote_root}/"],
        ["scp", str(local_root / "scripts" / "run_sim_new_cp_va_slam_all_stages.py"), f"{ssh_target}:{remote_root}/scripts/"],
        ["scp", str(local_root / "scripts" / "run_sim_new_cp_va_slam_stage01.py"), f"{ssh_target}:{remote_root}/scripts/"],
        ["scp", str(local_root / "scripts" / "validate_sim_new_cp_va_slam_schema.py"), f"{ssh_target}:{remote_root}/scripts/"],
        ["scp", "-r", str(local_root / "docs" / "sim_new_cp_va_slam"), f"{ssh_target}:{remote_root}/docs/"],
        ["scp", str(local_root / "lp_simulation_config_schema.md"), f"{ssh_target}:{remote_root}/"],
        ["scp", str(local_root / "lp_extended_output_schema.csv"), f"{ssh_target}:{remote_root}/"],
        [
            "ssh",
            ssh_target,
            f"{conda_python} -c 'import numpy,pandas,h5py; print(\"sim_new_cp_va_slam dependency probe ok\")'",
        ],
        ["ssh", ssh_target, server_run_cmd],
    ]
    tag_model = str(tag_antenna_model_mode).strip().lower()
    if tag_model in {"legacy_h10b_dual_tilted", "legacy_h10b", "legacy_dual_tag_h10b", "h10b_dual_tag"}:
        artifact_path = Path(str(legacy_dual_tag_artifact_path))
        local_artifact = artifact_path if artifact_path.is_absolute() else local_root / artifact_path
        remote_artifact = str(legacy_dual_tag_artifact_path).replace("\\", "/")
        if local_artifact.exists():
            remote_parent = str(Path(remote_artifact).parent).replace("\\", "/")
            commands.insert(-2, ["ssh", ssh_target, f"mkdir -p {remote_root}/{remote_parent}"])
            commands.insert(-2, ["scp", str(local_artifact), f"{ssh_target}:{remote_root}/{remote_artifact}"])
    pattern_files = {
        str(lp_copol_gain_pattern_file),
        str(lp_crosspol_gain_pattern_file),
        str(rx_ant1_rhcp_pattern_file),
        str(rx_ant1_lhcp_pattern_file),
        str(rx_ant2_rhcp_pattern_file),
        str(rx_ant2_lhcp_pattern_file),
    }
    for ffd_file in {item for item in pattern_files if item.strip()}:
        ffd_path = Path(ffd_file)
        if not ffd_path.is_absolute():
            ffd_path = local_root / ffd_path
        if ffd_path.exists():
            commands.insert(-2, ["scp", str(ffd_path), f"{ssh_target}:{remote_root}/"])
    if fetch_results and not background:
        commands.append(["scp", "-r", f"{ssh_target}:{remote_out}/.", str(local_out)])
    if background:
        commands.append(["ssh", ssh_target, f"cat {remote_pid}"])

    log = []
    for cmd in commands:
        proc = subprocess.run(
            cmd,
            cwd=local_root,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        log.append({"cmd": cmd, "returncode": proc.returncode, "stdout": stdout[-4000:], "stderr": stderr[-4000:]})
        if proc.returncode != 0:
            break

    result = {
        "ssh_target": ssh_target,
        "remote_root": remote_root,
        "remote_out": remote_out,
        "remote_log": remote_log,
        "remote_pid": remote_pid,
        "local_out": str(local_out),
        "num_snapshots": int(num_snapshots),
        "scene_ids": scene_ids,
        "trajectory_ids": trajectory_ids,
        "scenario_pairs": scenario_pairs,
        "algorithm_ids": algorithm_ids,
        "bandwidth_hz": float(bandwidth_hz),
        "max_reflections": int(max_reflections),
        "num_paths_max": int(num_paths_max),
        "range_estimator_mode": str(range_estimator_mode),
        "lde_relative_threshold": float(lde_relative_threshold),
        "lde_noise_scale": float(lde_noise_scale),
        "solver_num_particles": int(solver_num_particles),
        "solver_max_candidates": int(solver_max_candidates),
        "solver_da_particle_top": int(solver_da_particle_top),
        "wall_offset_noise_m": float(wall_offset_noise_m),
        "wall_normal_noise_deg": float(wall_normal_noise_deg),
        "odometry_noise_scale": float(odometry_noise_scale),
        "range_variance_scale": float(range_variance_scale),
        "tag_antenna_model_mode": str(tag_antenna_model_mode),
        "legacy_dual_tag_artifact_path": str(legacy_dual_tag_artifact_path),
        "legacy_dual_tag_rssd_channel": str(legacy_dual_tag_rssd_channel),
        "legacy_dual_tag_alpha_deg": float(legacy_dual_tag_alpha_deg),
        "legacy_dual_tag_rotation_deg": float(legacy_dual_tag_rotation_deg),
        "legacy_dual_tag_rssd_prediction_mode": str(legacy_dual_tag_rssd_prediction_mode),
        "legacy_dual_tag_power_offset_mode": str(legacy_dual_tag_power_offset_mode),
        "rx_ant1_rhcp_pattern_file": str(rx_ant1_rhcp_pattern_file),
        "rx_ant1_lhcp_pattern_file": str(rx_ant1_lhcp_pattern_file),
        "rx_ant2_rhcp_pattern_file": str(rx_ant2_rhcp_pattern_file),
        "rx_ant2_lhcp_pattern_file": str(rx_ant2_lhcp_pattern_file),
        "tag_attitude_source": str(tag_attitude_source),
        "tag_pitch_deg": float(tag_pitch_deg),
        "tag_roll_deg": float(tag_roll_deg),
        "rx_ant1_mount_rotation": str(rx_ant1_mount_rotation),
        "rx_ant2_mount_rotation": str(rx_ant2_mount_rotation),
        "pattern_gain_normalization": str(pattern_gain_normalization),
        "pattern_phase_convention": str(pattern_phase_convention),
        "pattern_pol_basis": str(pattern_pol_basis),
        "perturbation_config_id": str(perturbation_config_id),
        "orientation_control_mode": str(orientation_control_mode),
        "yaw_noise_deg": float(yaw_noise_deg),
        "yaw_shuffle": bool(yaw_shuffle),
        "yaw_shuffle_level": str(yaw_shuffle_level),
        "yaw_fixed_deg": float(yaw_fixed_deg),
        "disable_orientation": bool(disable_orientation),
        "rssd_control_mode": str(rssd_control_mode),
        "rssd_noise_std_db": float(rssd_noise_std_db),
        "rssd_noise_scale": float(rssd_noise_scale),
        "rssd_shuffle": bool(rssd_shuffle),
        "rssd_shuffle_level": str(rssd_shuffle_level),
        "rssd_sign_flip": bool(rssd_sign_flip),
        "disable_rssd": bool(disable_rssd),
        "run_label": str(run_label),
        "fetch_results": bool(fetch_results),
        "background": bool(background),
        "log": log,
    }
    (local_out / "remote_execution_log.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
