"""Contract tests only: no native Sionna, hardware or MC campaign runs here."""
import math
import numpy as np
import pytest

from qclean_uwb.drivesim.body_dynamics import (
    DifferentialDriveBodyPlant, DriveDynamicsConfig, GroundSlipConfig)
from qclean_uwb.drivesim.body_sensor_adapter import RunRealization, SensorAdapterConfig
from qclean_uwb.drivesim.body_sensor_stream import BodySensorStream
from qclean_uwb.drivesim.body_ekf_bridge import ProbeEKF6, V2BodyFilterConfig
from qclean_uwb.drivesim.body_probe_controller import ProbeBodyController, ProbeMotionConfig
from qclean_uwb.drivesim.body_probe_loop import BodyProbeLoop, ProbeLoopClock
from qclean_uwb.drivesim.body_pose_channel import (
    RFPoseRequest, RFChannel, RFFilterPacket, FirstPathReceiver, NativeSionnaAtPose)

FAST = DriveDynamicsConfig(motor_time_constant_s=0.,
                           max_wheel_accel_rad_s2=1e5,
                           max_wheel_speed_rad_s=8.,
                           max_step_s=.02)
NO_SENSOR_NOISE = SensorAdapterConfig(
    gyro_N_rad_sqrt_s=0., bias_rw_rad_s_sqrt_s=0.,
    k_distance_m=0.,k_yaw_rad=0.,k_yaw_distance_rad2_m=0.)


class FakeRFBackend:
    """Analytical synthetic input for wiring tests, NOT scientific RF evidence."""
    def __init__(self):
        self.requests=[]
        self.freq=np.linspace(6.2504e9,6.7496e9,257)

    def generate(self,request):
        self.requests.append(request)
        x,y,_=request.true_pose_xyyaw
        dist=np.linalg.norm([x-4.,y,2.65-.45])
        phase=np.exp(-2j*np.pi*self.freq*dist/299792458.)
        H=np.zeros((257,2,2),complex)
        H[:,0,0]=.002*phase
        H[:,1,0]=.001*phase
        return RFChannel(request,self.freq,H,None,{"source_id":"UNIT_TEST_MOCK_ONLY"})


def build_loop(offsets=(0.,),slip=GroundSlipConfig(),x_est=7.):
    realization=RunRealization(0.,0.,0.,0.)
    geom=realization.geometry()
    plant=DifferentialDriveBodyPlant(
        geometry=geom,drive=FAST,slip=slip,pose0=(7.,.1,0.),seed=4)
    stream=BodySensorStream(geom,realization,noise=NO_SENSOR_NOISE,seed=4)
    cfg=V2BodyFilterConfig(
        use_s=False,use_range=True,mount_deg=0.,
        anchor_xyz=(4.,0.,2.65),robot_z=.45,
        bias_rw_std=0.,s_mismatch_sigma=.09)
    ekf=ProbeEKF6(cfg,None,[x_est,.1,0.,0.,0.,0.],rf_mode="range_only")
    controller=ProbeBodyController(0.,ProbeMotionConfig(
        offsets_deg=offsets,settle_duration_s=.2,rf_integration_s=.2,
        max_stage_duration_s=15.,max_total_duration_s=40.))
    mock=FakeRFBackend()
    loop=BodyProbeLoop(plant=plant,sensors=stream,ekf=ekf,
                       controller=controller,rf_backend=mock,
                       receiver=FirstPathReceiver(snr_db=70.,range_sigma_m=0.,seed=5),
                       clock=ProbeLoopClock(sensor_dt_s=.2,physics_dt_s=.02,max_duration_s=20.))
    return loop,mock


def test_actual_pose_and_packet_time_feed_rf_backend():
    loop,backend=build_loop()
    result=loop.run()
    assert result["status"]=="CONTROL_COMPLETE_RF_COLLECTED"
    assert result["n_rf_packets"]==1
    req=backend.requests[0]
    assert req.t_s==pytest.approx(result["measured_rf_packets"][0]["t_s"])
    oracle=[v for v in result["physical_oracle_eval_only"] if abs(v["t_s"]-req.t_s)<1e-7][0]
    assert req.true_pose_xyyaw==pytest.approx(oracle["true_pose_xyyaw"])
    assert req.point_index==0
    assert result["rf_oracle_eval_only"][0]["source_id"]=="UNIT_TEST_MOCK_ONLY"
    # All times and covariance stages have a real 6x6 shape, not yaw-only sigma.
    t=result["full_P6_trace"]
    assert t["P_pred_before_odom"].shape[1:]==(6,6)
    assert t["P_after_odom"].shape[1:]==(6,6)
    assert t["P_after_range"].shape[1:]==(6,6)
    assert t["P_before_RF"].shape[1:]==(6,6)
    assert t["P_after_RF"].shape[1:]==(6,6)
    assert t["F"].shape[1:]==(6,6)
    assert t["odom_C"].shape[1:]==(6,)

def test_physical_slip_moves_truth_but_does_not_double_count_encoder_noise():
    loop,backend=build_loop(offsets=(0.,10.),
        slip=GroundSlipConfig(baseline_right=.05,baseline_icr_offset_m=.005))
    result=loop.run()
    assert len(backend.requests)>=1
    assert any(abs(v["true_pose_xyyaw"][2])>1e-3 for v in result["physical_oracle_eval_only"])
    assert any(abs(v["true_pose_xyyaw"][0]-7.)>1e-6 or abs(v["true_pose_xyyaw"][1]-.1)>1e-6
               for v in result["physical_oracle_eval_only"])
    assert result["scientific_PASS"] is False

def test_exact_pose_backend_fails_closed_without_FFD(tmp_path):
    with pytest.raises(FileNotFoundError):
        NativeSionnaAtPose(output_scene_dir=tmp_path/"scene",
                           bank_dir=tmp_path/"banks",
                           bank_manifest=tmp_path/"missing.json")

def test_joint_sr_refuses_missing_covariance():
    cfg=V2BodyFilterConfig(use_s=True,use_range=True)
    f=ProbeEKF6(cfg,object(),[7.,0.,0.,0.,0.,0.],rf_mode="joint_sr_diagnostic")
    class Increment:
        t_s=.2;dt_s=.2;ds_odom=0.;dtheta_odom=0.;dtheta_gyro=0.
        encoder_left_rad=0.;encoder_right_rad=0.
    f.start_interval(Increment(),phase="MEASURE")
    packet=RFFilterPacket("p",.2,True,4.,.3,(1.,2.),4,42.)
    with pytest.raises(ValueError,match="sourced covariance"):
        f.apply_rf(packet)

def test_bad_sensor_timestamps_fail_not_interpolate():
    r=RunRealization(0.,0.,0.,0.)
    p=DifferentialDriveBodyPlant(geometry=r.geometry(),drive=FAST)
    s=BodySensorStream(r.geometry(),r,noise=NO_SENSOR_NOISE)
    ticks=[p.step(command_v_m_s=0.,command_w_rad_s=0.,dt_s=.02) for _ in range(9)]
    with pytest.raises(ValueError,match="PHYSICAL_TICK_GAP_OR_OVERLAP"):
        bad=ticks[1:]
        s.measure(bad)
