"""Write the DRIVE_SIM S0 pre-registration (thresholds, hypotheses, trajectory/probe settings).

Run once, then commit the output BEFORE any parity comparison or filter run is looked at:
  python scripts/drive_sim_s0_prereg.py --out results/DRIVE_SIM_20261007/S0/PREREG.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from qclean_uwb.drivesim.config import config_sha256, param, validate_params  # noqa: E402

PLAN = "results/DRIVE_SIM_20261007/PLAN.md"


def build() -> dict:
    A, D, X, F = "assumption", "derived", "adopted", "deferred"
    p = lambda v, st, src, unit=None: param(v, st, src, unit)  # noqa: E731
    cfg = {
        "schema": "DRIVE_SIM_S0_PREREG_v1",
        "plan": PLAN,
        "base_commit": p("c13797a", X, "user decision: base branch determined-turing-vxge0c"),
        "gates": {
            "G1_A_reproducibility": {"h_rel_err_max": p(1e-6, D, "PLAN §5: determinism check")},
            "G2_B_per_bin_trace": {
                "h_rel_err_median_max": p(1e-4, D, "PLAN §5"), "h_rel_err_max": p(1e-3, D, "PLAN §5"),
                "fp_index_match_min": p(1.0, D, "PLAN §5"), "abs_ds_max": p(1e-3, D, "1e-3 ~ 0.03 deg at slope 0.03/deg"),
                "range_diff_max_m": p(1e-3, D, "PLAN §5")},
            "G2p_B_node_interpolation": {
                "abs_ds_max": p(2e-3, D, "PLAN §5"), "fp_index_match_min": p(0.995, D, "PLAN §5"), "range_diff_max_m": p(2e-3, D, "PLAN §5")},
            "G3_path_continuity": {"unmatched_paths_max": p(0, D, "PLAN §5"), "classify_paths_tol_s": p(5e-14, X, "reflection_attribution.classify_paths default")},
            "G4_out_of_range_yaw": {"criteria": p("same as G2", D, "PLAN §5"), "positions": p(3, A, "PLAN §4 S2")},
        },
        "los_check": {"cases": p(48, X, "CORRIDOR_SWEEP_20261006/LOS_CHECK.json"), "rel_err_max": p(1e-4, X, "corridor_sionna_run.los_check"),
                      "branch_max_rel_err": p(6.066984088847065e-07, X, "CORRIDOR_SWEEP_20261006/LOS_CHECK.json")},
        "trajectory": {
            "speed_m_s": p(0.2, A, "user spec"), "sim_uwb_rate_hz": p(5.0, A, "user spec"), "x_range_m": p([1.0, 19.0], X, "CorridorSetup.robot_x_range_m"),
            "grid_step_m": p(0.04, D, "0.2 m/s / 5 Hz"),
            "lateral_y0_m": p([0.0, 0.35], A, "review item 4: y=0 is a special case (equal side-wall delays)"),
            "heading_wobble_deg": p({"form": "A*sin(2*pi*t/Tw + phi), phi seeded", "A": 4.0, "Tw_s": 12.0}, A, "review item 4: +-3-5 deg; concrete form fixed here"),
            "initial_pose_sigma": p({"theta_deg": 5.0, "xy_m": 0.1}, A, "review item 4"),
            "turn_at_end": p("in-place 180 deg; turn_phase flag on samples", A, "review item 4"),
            "lever_arm_m": p(0.0, A, "antenna above base_link rotation centre; nonzero is v2 sensitivity"),
            "mount_offsets_deg": p([0.0, 45.0], A, "H3; offset = antenna x-axis yaw vs robot forward (not polarisation)"),
        },
        "probe": {
            "rate_deg_s": p(25.0, A, "5 deg per 5 Hz sample = required 5 deg resolution"),
            "span_deg": p([-45.0, 45.0], A, "user spec"), "step_deg": p(5.0, A, "user spec"),
            "sequence": p("to -45 (1.8 s) -> sweep to +45 (3.6 s, 19 samples) -> back to heading (1.8 s) = 7.2 s", D, "rate and span"),
            "period_T_s": p([10, 20, 60, None], A, "None = no probe (P0)"), "station_snap": p("4 cm travel grid", D, "lets T sweep reuse the same RF"),
        },
        "experiment": {
            "seeds": p(50, A, "user spec"), "drift_levels": p(3, A, "user spec"), "snr_levels": p(2, A, "user spec"),
            "snr_values_db_at_10m_los_copol": p(None, F, "fixed in S3 from noise_var_H_bin before any filter run"),
            "baselines": p(["odom+imu", "+range", "+range+s(P0)", "+range+s+probe(P1)", "inverse_heading", "P0-noturn"], A, "PLAN §4 S6"),
            "P2_adaptive_probe": p("out of scope (v2)", X, "user decision"),
        },
        "test": {
            "unit": p("paired by seed within condition (drift x SNR x lateral x mount offset)", A, "PLAN §6"),
            "metric": p("run heading RMSE excluding first 30 s", A, "PLAN §6"),
            "test": p("paired two-sided Wilcoxon signed-rank, alpha=0.01, Holm over the conditions of one hypothesis", A, "PLAN §6"),
            "effect": p("median paired difference with bootstrap 95% CI (10000 resamples)", A, "PLAN §6"),
            "improvement_rule": p("Holm-significant AND median relative improvement >= 10%", A, "PLAN §6 proposal"),
            "wrong_branch": p({"threshold_deg": 20.0, "sensitivity_deg": [10.0, 30.0], "excluded_s": 30.0}, A, "PLAN §6 proposal"),
            "H4_X_percent": p(10.0, X, "user decision"),
        },
        "hypotheses": {
            "H1": "range + s has lower heading RMSE than odom+IMU only (per drift level)",
            "H2": "s as a measurement beats heading inverted from s",
            "H3": ("passive (P0) heading RMSE, straight travel: ideal-curve prediction is that the 45 deg mount is LOWER than 0 deg "
                   "(s=-cos 2*(heading+mount): slope 0 at antenna yaw 0, maximal at 45)."),
            "H3_alt": ("user intuition recorded before any result: the 0 deg mount is preferable for straight travel and the 45 deg mount for 45 deg "
                       "travel. Two-sided test decides between H3 and H3_alt; the corridor only has heading 0/180 so only half of the intuition "
                       "is testable here (RF equivalence: only (heading+mount) mod 180 enters s)."),
            "H4": "largest probe period T in {10,20,60} s whose wrong-branch fraction (seed mean) has bootstrap 95% upper bound <= X percent",
        },
        "claim_boundary": "simulation only, placeholder parameters, no hardware validation; s is not q_clean and says nothing about range error guarantees",
    }
    errors = validate_params(cfg)
    assert not errors, errors
    return cfg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    cfg = build()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(dict(config_sha256=config_sha256(cfg), config=cfg), indent=1, ensure_ascii=False), encoding="utf8")
    print(args.out, config_sha256(cfg))


if __name__ == "__main__":
    main()
