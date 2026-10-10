"""Unit-contract tests only; no RF, Monte Carlo or robot simulation campaign."""
import math
import pytest
from qclean_uwb.drivesim.body_dynamics import (
    DifferentialDriveBodyPlant as Plant, DriveDynamicsConfig as Drive,
    GroundSlipConfig as Slip, WheelGeometry, exact_body_twist_step)
from qclean_uwb.drivesim.body_sensor_adapter import (
    RunRealization, SensorAdapterConfig, sensor_v2_from_physics,
    draw_sensor_v2_realization)
from qclean_uwb.drivesim.body_probe_controller import ProbeBodyController,ProbeMotionConfig

FAST=Drive(motor_time_constant_s=0.,max_wheel_accel_rad_s2=100000.,max_wheel_speed_rad_s=100.)

def test_se2():
    x,y,a=exact_body_twist_step(0,0,0,1,0,1,1)
    assert (x,y,a)==pytest.approx((math.sin(1),1-math.cos(1),1))
    assert exact_body_twist_step(0,0,0,0,1,0,1)==pytest.approx((0,1,0))

def test_geometry_v2_convention():
    g=WheelGeometry(common_scale=.01,wheel_asymmetry=.02,wheelbase_error=.01)
    assert g.actual()==pytest.approx((.033/(1.01*.99),.033/(1.01*1.01),.287/1.01))

def test_symmetric_rotation_xy_is_zero():
    p=Plant(drive=FAST)
    q=p.step(command_v_m_s=0.,command_w_rad_s=.2,dt_s=.01)
    assert q.true_pose_xyyaw[:2]==pytest.approx((0,0),abs=1e-12)
    assert q.motor_delta_left_rad==-q.motor_delta_right_rad

def test_asymmetric_slip_changes_true_xy():
    p=Plant(drive=FAST,slip=Slip(baseline_right=.05))
    q=p.step(command_v_m_s=0.,command_w_rad_s=.2,dt_s=.01)
    assert q.true_pose_xyyaw[0]<0 and q.true_delta_yaw_rad<.001

def test_icr_slip_changes_true_y():
    p=Plant(drive=FAST,slip=Slip(baseline_icr_offset_m=.01))
    q=p.step(command_v_m_s=0.,command_w_rad_s=.2,dt_s=.01)
    assert q.true_pose_xyyaw[1]<0

def test_motor_acceleration_limited():
    p=Plant()
    q=p.step(command_v_m_s=.2,command_w_rad_s=0.,dt_s=.01)
    assert abs(q.wheel_rate_left_rad_s)<=.080000001
    with pytest.raises(ValueError):
        p.step(command_v_m_s=0.,command_w_rad_s=0.,dt_s=.2)

def test_encoder_shaft_and_gyro_truth_are_separate():
    r=RunRealization(0.,0.,.02,.01,.01)
    g=r.geometry()
    p=Plant(geometry=g,drive=FAST,slip=Slip(baseline_right=.05))
    ticks=[p.step(command_v_m_s=0.,command_w_rad_s=.2,dt_s=.01) for _ in range(20)]
    zero=SensorAdapterConfig(gyro_N_rad_sqrt_s=0.,k_distance_m=0.,k_yaw_rad=0.,k_yaw_distance_rad2_m=0.)
    data,oracle=sensor_v2_from_physics(ticks,[0.,.2],geometry=g,realization=r,noise=zero)
    assert data['encoder_angle_rad'][1]==pytest.approx((
        sum(q.motor_delta_left_rad for q in ticks),sum(q.motor_delta_right_rad for q in ticks)))
    assert data['dtheta_gyro'][1]==pytest.approx(sum(q.true_delta_yaw_rad for q in ticks))
    assert data['dtheta_odom'][1]!=pytest.approx(data['dtheta_gyro'][1])
    assert 'true_pose_xyyaw' not in data
    assert oracle['slip_episode_mask'][1]
    with pytest.raises(ValueError,match='GEOMETRY_REALIZATION_MISMATCH'):
        sensor_v2_from_physics(ticks,[0.,.2],geometry=WheelGeometry(),realization=r,noise=zero)

def test_sensor_timestamps_must_match_physics():
    p=Plant(drive=FAST)
    ticks=[p.step(command_v_m_s=0.,command_w_rad_s=0.,dt_s=.01) for _ in range(20)]
    with pytest.raises(ValueError):
        sensor_v2_from_physics(ticks,[0.,.195],geometry=WheelGeometry(),realization=RunRealization(0.,0.,0.,0.))

def test_drift_seed_repeatable():
    a=draw_sensor_v2_realization(level=1,seed=42)
    assert a==draw_sensor_v2_realization(level=1,seed=42)
    assert abs(a.gyro_scale)==pytest.approx(.01)

def test_probe_uses_estimated_feedback_and_settles_before_firing():
    c=ProbeBodyController(0.,ProbeMotionConfig(offsets_deg=(0.,10.)))
    out=[c.update(estimated_yaw_rad=0.,estimated_yaw_rate_rad_s=0.,dt_s=.1) for _ in range(9)]
    assert [x.rf_point_index for x in out if x.rf_fire]==[0]
    assert c.phase=='ROTATE'
    x=c.update(estimated_yaw_rad=0.,estimated_yaw_rate_rad_s=0.,dt_s=.1)
    assert x.command_angular_rad_s>0 and not x.rf_fire

def test_probe_unsettled_never_fires():
    c=ProbeBodyController(0.,ProbeMotionConfig(offsets_deg=(0.,)))
    for _ in range(5):
        x=c.update(estimated_yaw_rad=0.,estimated_yaw_rate_rad_s=math.radians(10),dt_s=.1)
    assert not x.rf_fire
