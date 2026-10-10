import math
import numpy as np
import pytest
from qclean_uwb.drivesim.uncertainty import ResidualTable, antenna_phase_deg
from qclean_uwb.drivesim.filters import DriveFilter, FilterConfig


def table(mode="joint"):
    return ResidualTable((5.,10.),(15.,30.),.2,np.array([.1,np.nan,.3]),np.array([[.08,np.nan,.12],[np.nan]*3,[.25,.3,.35]]),(2.,15.),mode)


def test_phase_is_world_yaw_phase_with_90_degree_period():
    assert antenna_phase_deg(math.radians(45)) == 45
    assert antenna_phase_deg(math.radians(90)) == 0
    assert antenna_phase_deg(math.radians(3),45) == pytest.approx(42)


def test_sparse_cell_fallback_and_out_of_support():
    t=table()
    assert t.sigma([3,0],0,(0,0,0),0,0) == .08
    assert t.sigma([3,0],math.radians(20),(0,0,0),0,0) == .1
    assert t.sigma([7,0],0,(0,0,0),0,0) == .2
    assert t.sigma([16,0],0,(0,0,0),0,0) == .2


def test_legacy_sigma_unchanged_and_online_state_table():
    legacy=DriveFilter(FilterConfig(s_mismatch_sigma=.16),None,np.zeros(6))
    assert legacy._mismatch_sigma([4,0],0)==.16
    f=DriveFilter(FilterConfig(s_residual_table=table(),anchor_xyz=(0,0,0),robot_z=0),None,[3,0,0,0,0,0])
    assert f._s_R(1,1,xy=[3,0],psi=0)==pytest.approx(.08**2)
    with pytest.raises(ValueError,match="ESTIMATED_POSE"):f._s_R(1,1)


def test_unsupported_filter_and_invalid_table_fail_explicitly():
    with pytest.raises(ValueError,match="DIRECT_EKF"):
        DriveFilter(FilterConfig(kind="gsf",s_residual_table=table()),None,np.zeros(6))
    with pytest.raises(ValueError,match="FALLBACK"):
        ResidualTable((5.,10.),(15.,30.),0,np.ones(3),np.ones((3,3)),(2.,15.))
    with pytest.raises(ValueError,match="NONFINITE"):
        table().sigma([np.nan,0],0,(0,0,0),0,0)
