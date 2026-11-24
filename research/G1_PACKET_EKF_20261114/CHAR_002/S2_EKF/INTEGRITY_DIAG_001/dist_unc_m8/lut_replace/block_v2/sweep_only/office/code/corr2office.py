"""Corridor-trained SWB applied in the Office (DIAGNOSTIC). Office pose (x, y, psi) -> Corridor pose (10 + s*rho, 0, psi):
rho = horizontal distance to the Office anchor (5, 2.2), s = +1 if x >= 5 else -1 (anchor side), same anchor / tag heights (2.65 / 0.45 m),
psi unchanged (world frame). Jacobian by the chain rule: d/dx_o = s*(x-5)/rho * d/dx_c, d/dy_o = s*(y-2.2)/rho * d/dx_c (corridor d/dy_c at y = 0 unused).
The corridor block has data only along the corridor axis (azimuth around the anchor ~0 / 180 deg); Office azimuth dependence is ignored."""
import sys, numpy as np
sys.path.insert(0, "/home/claude/lut5"); import sw_block as SB
AO = np.array([5., 2.2]); _B = None
def block():
    global _B
    if _B is None: _B = SB.SWB()
    return _B
def evalc(x, y, psi):
    x, y, psi = (np.atleast_1d(np.asarray(v, float)) for v in (x, y, psi)); dx, dy = x - AO[0], y - AO[1]; rho = np.maximum(np.hypot(dx, dy), 1e-6); s = np.where(dx >= 0, 1., -1.)
    xc = 10. + s * rho; val, sx, _, sp = block().eval(xc, np.zeros_like(xc), psi); return val, sx * s * dx / rho, sx * s * dy / rho, sp
def s_fn():
    def fn(states, case):
        st = np.asarray(states, float); v, gx, gy, gp = evalc(st[:, 0], st[:, 1], st[:, 2]); return v, np.c_[gx, gy, gp]
    return fn
