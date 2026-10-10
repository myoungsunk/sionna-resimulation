"""Mock-only causal full-drive/probe/resume contracts. Not real Sionna or calibrated RF."""
import numpy as np
import pytest
from qclean_uwb.drivesim.body_active_drive import ActiveDrivePolicy,ContinuousRFQualityDrive
from qclean_uwb.drivesim.body_dynamics import DifferentialDriveBodyPlant,DriveDynamicsConfig,GroundSlipConfig
from qclean_uwb.drivesim.body_sensor_adapter import RunRealization,SensorAdapterConfig
from qclean_uwb.drivesim.body_sensor_stream import BodySensorStream
from qclean_uwb.drivesim.body_ekf_bridge import ProbeEKF6,V2BodyFilterConfig
from qclean_uwb.drivesim.body_pose_channel import FirstPathReceiver,RFChannel
from qclean_uwb.drivesim.body_probe_controller import ProbeMotionConfig
from qclean_uwb.drivesim.filter_v2 import transition

FAST=DriveDynamicsConfig(motor_time_constant_s=0.,max_wheel_accel_rad_s2=1e5,
                         max_wheel_speed_rad_s=8.,max_step_s=.02)
QUIET=SensorAdapterConfig(gyro_N_rad_sqrt_s=0.,bias_rw_rad_s_sqrt_s=0.,
                          k_distance_m=0.,k_yaw_rad=0.,k_yaw_distance_rad2_m=0.)

class FakeRF:
    """Deterministic analytic first-path H, never research-performance evidence."""
    def __init__(self):
        self.requests=[]
        self.freq=np.linspace(6.2504e9,6.7496e9,257)
        self.mount_deg=0.
    def generate(self,request):
        self.requests.append(request)
        x,y,psi=request.true_pose_xyyaw
        r=np.linalg.norm([x-4.,y,2.2])
        base=np.exp(-2j*np.pi*self.freq*r/299792458.)
        H=np.zeros((257,2,2),complex)
        H[:,0,0]=.002*base
        H[:,1,0]=.001*base
        return RFChannel(request,self.freq,H,None,{"source_id":"UNIT_TEST_ONLY"})

def setup(quality_series=(.9,.2,.9,.9),joint_delta=.008,
          offsets=(0.,10.,20.),mode="valid"):
    realization=RunRealization(0.,0.,0.,0.)
    geom=realization.geometry()
    plant=DifferentialDriveBodyPlant(geometry=geom,drive=FAST,
                slip=GroundSlipConfig(),pose0=(7.,.1,0.),seed=5)
    sensors=BodySensorStream(geom,realization,noise=QUIET,seed=5)
    cfg=V2BodyFilterConfig(use_s=False,use_range=True,
         mount_deg=0.,anchor_xyz=(4.,0.,2.65),robot_z=.45,
         bias_rw_std=0.,s_mismatch_sigma=.09)
    ekf=ProbeEKF6(cfg,None,[7.,.1,0.,0.,0.,0.],rf_mode="range_only")
    backend=FakeRF()
    qcalls=[];single_calls=[];joints=[]
    def quality(packet,x,P):
        assert packet.packet_id not in [v[0] for v in qcalls]
        assert x.shape==(6,) and P.shape==(6,6)
        q=quality_series[min(len(qcalls),len(quality_series)-1)]
        qcalls.append((packet.packet_id,q))
        return q
    def single_update(f,packet,q):
        # Toy heading observation; no FFD-LUT validity claim.
        assert f.pending is not None
        H=np.zeros(6);H[2]=.8
        h=.58 + .8*(f.estimate[2])
        y,R,S,status=f.f.scalar(packet.s,h,H,.03,"s")
        f.pending.update(s_status=status,s_R=R,s_S=S,s_H=H,s_innovation=y)
        single_calls.append((packet.packet_id,q,status))
        return {"status":status,"model_id":"UNIT_TEST_SYNTHETIC_SCALAR"}
    def joint_update(f,packets):
        assert f.pending is None
        assert len(packets)==len(offsets)
        assert all(p["point_index"]==i for i,p in enumerate(packets))
        assert all(p["first_cluster_window_taps"]==(4,8,16) for p in packets)
        assert all(p["first_cluster_availability"]=="SIMULATED_AMPLITUDE_CIR_ONLY" for p in packets)
        assert all(len(p["first_cluster_s"])==3 for p in packets)
        assert all(np.isfinite(p["first_cluster_s"]).all() for p in packets)
        assert all(np.shape(p["P6_pre_rf"])==(6,6) for p in packets)
        assert all(len(p["estimated_pose_pre_rf"])==3 for p in packets)
        joints.append([p["packet_id"] for p in packets])
        if mode=="bad_receipt":
            return {}
        c=f.f.comps[0]
        c.x[2]+=joint_delta
        c.P[2,2]*=.95
        return {"status":"APPLIED_TO_P6","covariance_model_id":"UNIT_TEST_TOY_POSTERIOR",
                "scientific_PASS":False}
    policy=ActiveDrivePolicy(threshold_good=.5,cooldown_drive_steps=50,max_probes=2,
        probe_offsets_deg=offsets,max_probe_duration_s=40.)
    motion=ProbeMotionConfig(offsets_deg=offsets,settle_duration_s=.2,
        rf_integration_s=.2,max_total_duration_s=40.)
    driver=ContinuousRFQualityDrive(plant=plant,sensors=sensors,ekf=ekf,
        receiver=FirstPathReceiver(snr_db=70.,range_sigma_m=0.,seed=42),
        rf_backend=backend,quality_fn=quality,single_s_update=single_update,
        probe_joint_update=joint_update,policy=policy,probe_motion=motion)
    return driver,backend,qcalls,single_calls,joints

def test_drive_trigger_stop_probe_joint_update_and_resume_same_P6():
    driver,backend,quality,singles,joints=setup()
    result=driver.run([(0.,0.) for _ in range(4)])
    assert result["n_drive_steps"]==4
    assert result["n_triggered_probes"]==1
    assert len(singles)==3  # all except the trigger; probe s deferred
    assert len(joints)==1 and len(joints[0])==3
    assert len(backend.requests)==4+3  # drive RF plus three actual settled body poses
    assert result["events"][0]["original_trigger_packet"] not in joints[0]
    assert result["events"][0]["joint_result"]["covariance_model_id"]=="UNIT_TEST_TOY_POSTERIOR"
    assert result["normal_records"][1]["probe_trigger"]
    assert result["normal_records"][2]["actual_elapsed_s"]>result["normal_records"][1]["actual_elapsed_s"]+.2
    assert driver.plant.t_s==pytest.approx(driver.sensors.t_s)
    assert driver.plant.t_s==pytest.approx(driver.ekf.last_t)
    assert np.isfinite(driver.ekf.covariance).all()
    assert result["trace"]["P_after_RF"].shape[1:]==(6,6)
    assert result["trace"]["t_s"].shape[0] > 4
    # A joint posterior is in the LAST probe record and propagates into NEXT DRIVE,
    # not just a one-shot offline heading comparison.
    ev=result["events"][0]
    after=driver.ekf.records[ev["new_ekf_record_count"]-1]
    nxt=driver.ekf.records[ev["new_ekf_record_count"]]
    assert after["site_joint_model_id"]=="UNIT_TEST_TOY_POSTERIOR"
    b=driver.ekf.cfg.wheel_base/(1+driver.ekf.cfg.known_wheelbase_error)
    pred,F,G=transition(after["x_after_RF"],nxt["ds_odom"],nxt["dtheta_gyro"],nxt["dt_s"],b)
    assert nxt["x_pred_before_odom"]==pytest.approx(pred,abs=1e-10)
    assert result["scientific_PASS"] is False

def test_high_confidence_never_stops_and_applies_s_each_step():
    driver,backend,quality,singles,joints=setup((.95,.96,.97,.98))
    result=driver.run([(0.,0.) for _ in range(4)])
    assert result["n_triggered_probes"]==0
    assert len(singles)==4 and len(joints)==0
    assert len(backend.requests)==4

def test_unidentified_joint_model_receipt_fails_closed():
    driver,backend,quality,singles,joints=setup(mode="bad_receipt")
    with pytest.raises(ValueError,match="posterior covariance model"):
        driver.run([(0.,0.),(0.,0.)])

def test_quality_cannot_be_nonfinite():
    driver,backend,quality,singles,joints=setup((float("nan"),))
    with pytest.raises(ValueError,match="quality"):
        driver.drive_one(0.,0.)

def test_policy_rejects_yaw_only_and_wrong_clock():
    with pytest.raises(ValueError,match="2 or 3"):
        ActiveDrivePolicy(probe_offsets_deg=(0.,)).validate()
    with pytest.raises(ValueError,match="sensor clock"):
        ActiveDrivePolicy(physics_dt_s=.03).validate()


def test_simulated_first_arrival_gate_ratio_has_consistent_shared_tap():
    driver,backend,quality,singles,joints=setup((.97,))
    result=driver.run([(0.,0.)])
    assert result["n_triggered_probes"]==0
    from qclean_uwb.drivesim.body_pose_channel import FirstPathReceiver
    req=backend.requests[0]
    channel=backend.generate(req)
    packet,_=FirstPathReceiver(snr_db=90.,range_sigma_m=0.,seed=13).receive(channel)
    assert packet.detected
    assert packet.first_cluster_window_taps==(4,8,16)
    assert packet.first_cluster_availability=="SIMULATED_AMPLITUDE_CIR_ONLY"
    assert len(packet.first_cluster_port_energy)==3
    assert all(len(e)==2 and all(v>0 for v in e) for e in packet.first_cluster_port_energy)
    assert abs(packet.s-0.6)<.01
    assert all(abs(v-.6)<.01 for v in packet.first_cluster_s)
    assert packet.selected_tap>=0


def test_actual_site_point_mixture_module_is_carried_into_next_drive(monkeypatch):
    from qclean_uwb.drivesim import body_site_mixture as mix
    from qclean_uwb.drivesim.body_site_mixture import SitePointMixture6,NominalSitePointCovariance
    def mock_lut(lut,anchor,robot_z,x,y,psi,mount,with_jac=False):
        import math
        value=.50+.02*x-.015*y+.30*math.sin(2*float(psi))
        jac=np.array([.02,-.015,.60*math.cos(2*float(psi))])
        return (value,jac) if with_jac else value
    monkeypatch.setattr(mix,"s_model",mock_lut)
    driver,backend,quality,singles,_=setup((.2,.9,.9,.9))
    # This object just activates the synthetic analytic LUT; actual deployment
    # requires a hash-verified fixed FFD LoS LUT and source-backed covariance.
    driver.ekf.lut=object()
    spec=NominalSitePointCovariance(maximum_station_xy_est_change_m=.5)
    driver.joint_update=SitePointMixture6(spec)
    res=driver.run([(0.,0.) for _ in range(4)])
    assert res["n_triggered_probes"]==1
    joint=res["events"][0]["joint_result"]
    assert joint["status"]=="APPLIED_UNCALIBRATED_MIXTURE"
    assert joint["n_used"]==3 and joint["n_modes"]==16
    assert not joint["scientific_PASS"]
    assert joint["cross_time_pose_measurement_covariance"]=="UNVERIFIED_APPROXIMATION"
    assert len(joint["q_point_bad"])==3 and 0<=joint["q_site_bad"]<=1
    assert np.linalg.eigvalsh(driver.ekf.covariance).min()>=-1e-9
    last_probe=driver.ekf.records[res["events"][0]["new_ekf_record_count"]-1]
    first_following=driver.ekf.records[res["events"][0]["new_ekf_record_count"]]
    from qclean_uwb.drivesim.filter_v2 import transition
    b=driver.ekf.cfg.wheel_base/(1+driver.ekf.cfg.known_wheelbase_error)
    expected,*_=transition(last_probe["x_after_RF"],first_following["ds_odom"],
                           first_following["dtheta_gyro"],first_following["dt_s"],b)
    assert first_following["x_pred_before_odom"]==pytest.approx(expected,abs=1e-10)
