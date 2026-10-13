"""P1 synthetic four-arm integration smoke: NOT a stored-RF performance test."""
import math
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ekf3 import EKF3, archived_direct_s_model


def synthetic_s(x):
    H = np.array([0.03, -0.07, 0.45])
    return float(0.2 + H @ x), H.copy()


def test_four_arm_predict_update_smoke():
    x0 = np.array([1.2, -0.3, .5])
    P0 = np.diag([.1**2, .1**2, math.radians(5)**2])
    anchor = (4.0, 0.0, 2.65)
    truth = EKF3(x0, np.zeros((3,3)))
    states = {a: EKF3(x0 + [.01, -.02, .01], P0) for a in ("D0", "A", "B", "C")}
    counts = {a: 0 for a in states}
    for k in range(1, 31):
        ds = .04
        dyaw = .01*math.sin(k/10)
        truth.predict(ds, dyaw, .2, Q_input=np.zeros((2,2)))
        obs_s = synthetic_s(truth.x)[0] + .005*math.sin(k)
        obs_range = np.linalg.norm([truth.x[0]-anchor[0], truth.x[1]-anchor[1],.45-anchor[2]])-.5315983906250129+.01*math.cos(k)
        for mode, f in states.items():
            f.predict(ds, dyaw, .2)
            if mode == "A":
                rec = f.update_heading(obs_s, .0081, s_model=synthetic_s)
            elif mode == "B":
                rec = f.update_range(obs_range,.0068578637,anchor_xyz_m=anchor,tag_height_m=.45)
            elif mode == "C":
                rec = f.update_joint(obs_s,obs_range,.0081,.0068578637,0.,s_model=synthetic_s,anchor_xyz_m=anchor,tag_height_m=.45)
            else:
                rec = None
            if rec is not None and rec.status == "applied": counts[mode] += 1
            assert f.x.shape==(3,) and f.P.shape==(3,3)
            assert np.isfinite(f.x).all() and np.linalg.eigvalsh(f.P).min() >= -1e-12
    assert counts["A"] > 0 and counts["B"] > 0 and counts["C"] > 0
    assert not np.array_equal(states["A"].P,states["B"].P)
    assert not np.array_equal(states["C"].P,states["D0"].P)


def test_archived_lut_adapter_contract_with_stub(monkeypatch):
    """Tests call argument order; does not certify actual RF LUT correctness."""
    import types
    pkg=types.ModuleType("qclean_uwb")
    pkg.__path__ = []
    drivesim=types.ModuleType("qclean_uwb.drivesim")
    drivesim.__path__ = []
    lut_mod=types.ModuleType("qclean_uwb.drivesim.hs_lut")
    captured={}
    def model(lut,anchor,z,x,y,yaw,mount,with_jac=False):
        captured.update(lut=lut,anchor=anchor,z=z,x=x,y=y,yaw=yaw,mount=mount,with_jac=with_jac)
        return .1, np.array([.01,.02,.3])
    lut_mod.s_model=model
    for key,val in [(pkg.__name__,pkg),(drivesim.__name__,drivesim),(lut_mod.__name__,lut_mod)]:
        monkeypatch.setitem(sys.modules,key,val)
    ref=object()
    obs=archived_direct_s_model(ref,anchor_xyz_m=(4,0,2.65),tag_height_m=.45,mount_deg=45)
    y,H=obs(np.array([1.0,2.0,.3]))
    assert y==.1 and np.allclose(H,[.01,.02,.3])
    assert captured==dict(lut=ref,anchor=(4,0,2.65),z=.45,x=1.,y=2.,yaw=.3,mount=45,with_jac=True)
