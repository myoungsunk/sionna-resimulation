"""Nominal first-cluster risk and frozen direct-LUT s EKF update wiring only."""
import math
from types import SimpleNamespace
import numpy as np
import pytest
from qclean_uwb.drivesim import body_active_policies as Q
from qclean_uwb.drivesim.body_active_policies import (
    NominalFPQuality,NominalFPQualityConfig,
    NominalFPLUTUpdate)
from qclean_uwb.drivesim.body_ekf_bridge import ProbeEKF6,V2BodyFilterConfig

def fake_s_model(lut,a,z,x,y,psi,mount,with_jac=False):
    h=.5+.8*psi+.01*x
    J=np.array([.01,0.,.8])
    return (float(h),J) if with_jac else float(h)

def packet(s=.57,cluster=None):
    return SimpleNamespace(detected=True,s=s,power=(.0006,.0004),
       first_cluster_s=cluster,first_cluster_availability="SIMULATED_AMPLITUDE_CIR_ONLY")

def test_quality_responds_to_innovation_and_simulated_first_cluster(monkeypatch):
    monkeypatch.setattr(Q,"s_model",fake_s_model)
    q=NominalFPQuality(object(),(4.,0.,2.65),.45,0.)
    x=np.array([7.,0.,0.,0.,0.,0.])
    P=np.diag([.01,.01,math.radians(5)**2,1e-6,.001,.001])
    clean=q(packet(.57,cluster=(.57,.57,.57)),x,P)
    bad=q(packet(-.7,cluster=(-.7,-.7,-.7)),x,P)
    changed=q(packet(.57,cluster=(.2,.37,.57)),x,P)
    assert 0<bad<clean<=1
    assert 0<changed<clean
    assert q.last_diagnostic["FP_cluster_max_s_difference"]>0
    assert q.last_diagnostic["calibration"]=="UNVALIDATED_SCIENTIFIC_PROTOTYPE"

def test_nominal_single_s_update_uses_s_gate_and_full_P6(monkeypatch):
    monkeypatch.setattr(Q,"s_model",fake_s_model)
    cfg=V2BodyFilterConfig(use_range=True,use_s=False,anchor_xyz=(4.,0.,2.65),robot_z=.45,
                           mount_deg=0.,bias_rw_std=0.,s_mismatch_sigma=.09)
    ekf=ProbeEKF6(cfg,object(),[7.,0.,0.,0.,0.,0.],rf_mode="range_only")
    inp=SimpleNamespace(t_s=.2,dt_s=.2,ds_odom=0.,dtheta_odom=0.,
                        dtheta_gyro=0.,encoder_left_rad=0.,encoder_right_rad=0.)
    ekf.start_interval(inp,phase="DRIVE")
    P0=ekf.covariance.copy()
    w=NominalFPLUTUpdate()
    out=w(ekf,packet(s=.67),q_good=.8)
    assert out["model_id"].startswith("UNVALIDATED_")
    assert out["R_s_effective"]>=.09**2
    assert out["status"] in ("applied","rejected")
    assert np.linalg.eigvalsh(ekf.covariance).min()>=-1e-9
    if out["status"]=="applied":
        assert ekf.covariance[2,2]<P0[2,2]
    ekf.finish_interval()
    assert ekf.traces()["P_after_RF"].shape==(1,6,6)
    with pytest.raises(RuntimeError,match="outside"):
        w(ekf,packet(),q_good=.8)

def test_bad_quality_or_no_ffd_fails():
    with pytest.raises(ValueError,match="frozen LoS LUT"):
        NominalFPQuality(None,(4.,0.,2.65),.45,0.)
    with pytest.raises(ValueError):
        NominalFPQualityConfig(cluster_absdiff_scale=-.1).validate()
