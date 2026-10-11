"""Tiny synthetic file-contract test. Not a native RF or physical trial."""
import json
import numpy as np

from qclean_uwb.drivesim import body_ekf_bridge as B
from scripts.drive_sim.evaluate_body_probe_physical_trajectory import evaluate

def test_offline_paired_replay_has_no_truth_to_filter(tmp_path):
    n=1
    P0=np.array([.01,.01,.007615435494667713,4.386490844928604e-6,.00010816,.00004096])
    init=[7.,0.,0.,0.,0.,0.]
    cfg=dict(
        physical=dict(nominal_radius_m=.033,nominal_wheelbase_m=.287,
                      init_true_xyyaw_rad=[7.,0.,0.]),
        sensor=dict(gyro_N_rad_sqrt_s=.0002617993877991494,
                    bias_rw_rad_s_sqrt_s=0,k_distance_m=2e-5,
                    k_yaw_rad=1e-4,k_yaw_distance_rad2_m=1e-5),
        initial_filter=dict(x0=init,P0_diagonal=P0.tolist(),
             known_wheelbase_error=0,range_sigma_m=.05,
             range_extra_sigma_m=.05,s_mismatch_sigma=.09),
        rf=dict(mode="range_only",anchor_x_m=4.,mount_deg=0.))
    (tmp_path/"MANIFEST.json").write_text(json.dumps(dict(config=cfg)))
    (tmp_path/"EXECUTION_STATUS.json").write_text(json.dumps(dict(status="CONTROL_COMPLETE_RF_COLLECTED")))
    xp=np.array([init],float)
    xp[0,0]+=.02
    covariance=np.array([np.diag(P0)],float)
    np.savez_compressed(tmp_path/"STATE_TRACE.npz",
        t_s=np.array([.2]),dt_s=np.array([.2]),
        ds_odom=np.zeros(1),dtheta_odom=np.zeros(1),dtheta_gyro=np.zeros(1),
        encoder_left_rad=np.zeros(1),encoder_right_rad=np.zeros(1),
        phase=np.array(["MEASURE"]),x_after_RF=xp,P_after_RF=covariance)
    np.savez_compressed(tmp_path/"ORACLE_EVAL_ONLY.npz",true_xyyaw=np.array([[7.,0.,0.]]))
    np.savez_compressed(tmp_path/"PROBE_RF_PACKETS.npz",
        time_rf_s=np.array([.2]),corresponding_state_index=np.array([0]),
        range_m=np.array([np.hypot(3.,2.2)]))
    result=evaluate(tmp_path)
    assert result["n_rf_packets"]==1
    assert result["scientific_PASS"] is False
    assert result["RF_heading_update_performed"] is False
    stats=result["metrics"]["full_route_sensor_window"]
    assert abs(stats["range_only"]["position_rmse_m"]-.02)<1e-10
    assert stats["rf_off_replay"]["position_rmse_m"]<1e-6
    assert result["comparison"].startswith("identical physical path")
