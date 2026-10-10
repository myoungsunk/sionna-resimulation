"""Uncalibrated site+point mixture tests: deterministic mock-LUT, never RF science."""
import math
from types import SimpleNamespace

import numpy as np
import pytest

from qclean_uwb.drivesim import body_site_mixture as M
from qclean_uwb.drivesim.body_ekf_bridge import ProbeEKF6, V2BodyFilterConfig
from qclean_uwb.drivesim.body_site_mixture import (
    SitePointMixture6, NominalSitePointCovariance)

def synthetic_lut(lut,anchor,robot_z,x,y,psi,mount,with_jac=False):
    # Nonlinear mock signal with full x/y/yaw derivatives. Synthetic only.
    q=float(.50+.02*x-.015*y+.30*math.sin(2*psi))
    j=np.array([.02,-.015,.60*math.cos(2*psi)])
    return (q,j) if with_jac else q

def build():
    cfg=V2BodyFilterConfig(use_s=False,use_range=True,mount_deg=0.,
        anchor_xyz=(4.,0.,2.65),robot_z=.45,bias_rw_std=0.,
        s_mismatch_sigma=.09)
    ekf=ProbeEKF6(cfg,object(),[7.,.1,0.,0.,0.,0.],rf_mode="range_only")
    return ekf

def points(bad=False):
    pts=[]
    for i,delta in enumerate([0.,math.radians(10),math.radians(20)]):
        val=synthetic_lut(None,None,None,7.,.1,delta,0)
        if bad and i==1:val+=.80
        pts.append(dict(packet_id=f"p{i}",detected=True,s=val,
             estimate_yaw_pre_rf_rad=delta,
             estimated_pose_pre_rf=[7.,.1,delta],
             P6_pre_rf=np.eye(6).tolist(),point_index=i))
    return pts

def test_mixture_updates_full_P6_without_groundtruth(monkeypatch):
    monkeypatch.setattr(M,"s_model",synthetic_lut)
    ekf=build()
    P0=ekf.covariance.copy();x0=ekf.estimate.copy()
    model=SitePointMixture6()
    status=model(ekf,points(bad=True))
    P=ekf.covariance;x=ekf.estimate
    assert status["status"]=="APPLIED_UNCALIBRATED_MIXTURE"
    assert status["covariance_model_id"].startswith("NOMINAL_")
    assert status["calibration"]=="NOT_CALIBRATED_HELDOUT"
    assert not status["scientific_PASS"]
    assert status["n_used"]==3 and status["n_modes"]==16
    assert 0<=status["q_site_bad"]<=1
    assert len(status["q_point_bad"])==3
    assert all(0<=v<=1 for v in status["q_point_bad"])
    assert status["q_point_bad"][1]>status["q_point_bad"][0]
    assert P.shape==(6,6) and np.isfinite(P).all()
    assert np.linalg.eigvalsh(P).min()>=-1e-9
    assert not np.allclose(P,P0) and np.linalg.norm(x-x0)>0
    with pytest.raises(ValueError,match="already used"):
        model(ekf,points(bad=True))

def test_mixture_reports_higher_site_risk_for_inconsistent_angle(monkeypatch):
    monkeypatch.setattr(M,"s_model",synthetic_lut)
    a=build();b=build()
    clean=SitePointMixture6()(a,points(False))
    bad=SitePointMixture6()(b,points(True))
    assert bad["q_site_bad"]>clean["q_site_bad"]

def test_mixture_validates_missing_and_station_motion(monkeypatch):
    monkeypatch.setattr(M,"s_model",synthetic_lut)
    m=SitePointMixture6()
    f=build()
    p=points()
    p[2]["estimated_pose_pre_rf"]=[7.5,.1,p[2]["estimate_yaw_pre_rf_rad"]]
    with pytest.raises(ValueError,match="same-site"):
        m(f,p)
    p=points()
    p[1]["detected"]=False
    good=m(f,p)
    assert good["n_used"]==2 and good["unavailable_point_ids"]==["p1"]

def test_mixture_requires_original_lut_and_positive_covariance():
    f=build();f.lut=None
    with pytest.raises(ValueError,match="frozen LoS LUT"):
        SitePointMixture6()(f,points())
    with pytest.raises(ValueError,match="invalid site/point priors"):
        NominalSitePointCovariance(site_bad_prior=1.).validate()
