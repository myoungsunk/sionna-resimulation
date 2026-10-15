"""Additional R5 pre-run geometry checks; original frozen LUT unchanged."""
import math
import numpy as np
import pytest
from p4_lut_boundary import lut_angles,boundary_report,segment_crossings,GRID_DEG

CASE={"id":"R2_aA_m0","anchor":[4.,0.,2.65],"robot_z_m":.45,"mount_deg":0.}

def near_phi_tx_knot():
    u=-1.244123
    v=-u*math.tan(math.radians(-156.))
    return np.array([4.+u,v,.106701,0.],float)

def test_frozen_lut_phi_tx_grid_geometry_exact_knot():
    x=near_phi_tx_knot()
    assert abs(lut_angles(x,CASE)[1]+156)<1e-10
    info=boundary_report(x,CASE)
    assert info["on_or_near_knot"] and "phi_tx_deg" in info["near_knot_dimensions"]
    assert info["min_grid_distance_deg"]<1e-9

def test_yaw_sweep_crossing_reports_physical_cell_and_fraction():
    x=near_phi_tx_knot()
    a=x.copy();b=x.copy()
    a[1]-=.01;b[1]+=.01
    result=segment_crossings(a,b,CASE,samples=33)
    crossings=[e for e in result["events"] if
               e["dimension"]=="phi_tx_deg" and abs(e["boundary_deg"]+156)<1e-8]
    assert result["status"]=="CROSSING" and crossings
    near=min(crossings,key=lambda e:abs(e["cross_fraction"]-.5))
    assert abs(near["cross_fraction"]-.5)<1e-5
    assert abs(lut_angles(near["state_at_cross"],CASE)[1]+156)<1e-7

def test_no_spurious_crossing_when_pose_unchanged():
    x=np.array([5.11,.35,.34,0.])
    scan=segment_crossings(x,x,CASE)
    assert scan["status"] in ("KNOT_NEARBY","WITHIN_CELLS")
    assert not scan["events"]

def test_wrap_yaw_periodic_angle_coordinate():
    x=np.array([5.14,-.44,.32,0.])
    y=x.copy();y[2]+=2*math.pi
    left=lut_angles(x,CASE)
    right=lut_angles(y,CASE)
    np.testing.assert_allclose(left,right,atol=1e-9,rtol=0)

def test_near_anchor_singularity_does_not_fake_boundary():
    x=np.array([4.,0.,0.,0.])
    with pytest.raises(ValueError,match="SINGULARITY"):
        boundary_report(x,CASE)
    other=np.array([4.2,0.,0.,0.])
    r=segment_crossings(x,other,CASE)
    assert r["status"]=="INVALID_GEOMETRY"

def test_grid_step_contract():
    assert GRID_DEG==2.
    x=np.array([5.25,.56,.47,0.])
    r=boundary_report(x,CASE)
    assert set(r["angles_deg"])=={"theta_deg","phi_tx_deg","phi_rx_deg"}
    assert 0<=r["min_grid_distance_deg"]<=1.
