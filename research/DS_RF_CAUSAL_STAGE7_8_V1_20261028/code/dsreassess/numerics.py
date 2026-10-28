"""Rebuilt EKF mathematics. No imports of historic EKF update/predict implementations.

Only the frozen physical SourceFFD and sensor input generator are used as
reference dependencies by io.py, after which OFF parity is mandatory.
Units: x,y [m], yaw [rad], gyro bias [rad/s], optional range bias [m].
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np

PI = math.pi
DEG = 180.0 / PI


def wrap(theta):
    return (np.asarray(theta) + PI) % (2 * PI) - PI


def sym(a):
    a = np.asarray(a, dtype=float)
    return (a + a.T) * 0.5


def psd_check(p, *, tol=1e-11, name="P"):
    if not np.isfinite(p).all():
        raise ValueError(f"{name}: nonfinite")
    if p.shape[0] != p.shape[1] or np.max(np.abs(p-p.T)) > 1e-11:
        raise ValueError(f"{name}: not symmetric")
    lo = float(np.linalg.eigvalsh(sym(p))[0])
    if lo < -tol:
        raise ValueError(f"{name}: negative eigenvalue {lo}")
    return lo


def sinc_and_derivative(a: float) -> tuple[float, float]:
    """d[sin(a/2)/(a/2)]/da. Exact original sinc quadrature convention."""
    if abs(a) < 1e-4:
        a2 = a*a
        return (1-a2/24+a2*a2/1920-a2**3/322560,
                -a/12+a**3/480-a**5/53760)
    half = a/2
    return math.sin(half)/half, (half*math.cos(half)-math.sin(half))/(2*half*half)


def transition(x: np.ndarray, ds: float, dtheta: float, dt: float):
    """Return (f(x,u), F=df/dx, G=df/du); gyro-bias index=3."""
    x = np.asarray(x, float)
    if x.shape not in {(4,), (5,)} or dt <= 0 or not np.isfinite([ds,dtheta,dt]).all():
        raise ValueError("transition: shape or control")
    a = float(dtheta-x[3]*dt)
    c, dc = sinc_and_derivative(a)
    ph = float(x[2] + a/2)
    u = np.array([math.cos(ph), math.sin(ph)])
    up = np.array([-u[1],u[0]])
    d = ds*c*u
    v = ds*(dc*u + 0.5*c*up)
    y = x.copy()
    y[:2] += d
    y[2] = float(wrap(x[2]+a))
    F = np.eye(len(x))
    F[:2,2] = [-d[1],d[0]]
    F[:2,3] = -dt*v
    F[2,3] = -dt
    G = np.zeros((len(x),3))
    G[:2,0] = c*u
    G[:2,1] = v
    G[2,1] = 1
    G[3,2] = 1
    return y,F,G


def propagate(x, P, ds, dtheta, dt, *, range_bias_q=0.0, tangent_q=0.0,
              anchor_xy=None):
    """Reference-compatible 4-state predict, plus optional 5th bias and process Q_t.

    range_bias_q: [m^2/s]; tangent_q: [m^2/s].
    For 5-state, the fourth-column (gyro-bias) input noise stays zero.
    """
    y,F,G = transition(x,ds,dtheta,dt)
    Qin = np.diag([2e-5*abs(float(ds)),math.radians(.015)**2*float(dt),0.])
    C = F @ P @ F.T + G @ Qin @ G.T
    if len(x)==5:
        if range_bias_q < 0:
            raise ValueError("range_bias_q negative")
        C[4,4] += range_bias_q*dt
    if tangent_q:
        if anchor_xy is None or tangent_q < 0:
            raise ValueError("tangent Q requires anchor and q >= 0")
        radial = y[:2]-np.asarray(anchor_xy,float)
        n = np.linalg.norm(radial)
        if n < 1e-7:
            raise ValueError("undefined tangent Q axis close to anchor")
        ut = np.array([-radial[1],radial[0]])/n
        C[:2,:2] += tangent_q*dt*np.outer(ut,ut)
    C = sym(C)
    psd_check(C)
    return y,C,F


def range_h(xy, case, *, anchor=None, b_old: float):
    a=np.asarray(case['anchor'] if anchor is None else anchor,float)
    height=a[2]-float(case['robot_z_m'])
    if height<=0:
        raise ValueError("nonpositive anchor height relative to robot")
    xy=np.asarray(xy,float)
    dx=xy[:2]-a[:2]
    rr=float(np.sqrt(dx@dx+height*height))
    out=np.zeros(4)
    out[:2]=dx/rr
    return rr+b_old, out


def maybe_spd(R, floor=1e-12):
    R=sym(np.asarray(R,float))
    if R.shape!=(2,2) or not np.isfinite(R).all():
        raise ValueError("R invalid")
    lam=np.linalg.eigvalsh(R)
    if lam.min() <= floor:
        raise ValueError(f"R not strictly PD (min eig {lam.min()})")
    return R


@dataclass
class Update:
    x: np.ndarray
    P: np.ndarray
    K: np.ndarray
    H: np.ndarray
    h: np.ndarray
    nu: np.ndarray
    S: np.ndarray
    nis: float
    accepted: bool


def joint_update(x, P, z, h, H, mu, R, accepted: bool,
                 tangent_cut_xy=None):
    """2-channel joint update with Joseph covariance and *frozen* accept mask.

    tangent_cut_xy is oracle/diagnostic; never silently used in deployable arms.
    Rejects conserve x/P exactly, while retaining diagnostic K/NIS.
    """
    x=np.asarray(x,float); P=np.asarray(P,float)
    H=np.asarray(H,float); h=np.asarray(h,float)
    z=np.asarray(z,float); mu=np.asarray(mu,float)
    if H.shape!=(2,len(x)) or z.shape!=(2,) or h.shape!=(2,) or mu.shape!=(2,):
        raise ValueError("joint_update: incompatible shapes")
    R=maybe_spd(R)
    nu=z-h-mu
    S=maybe_spd(H@P@H.T+R)
    hp=H@P
    K=np.linalg.solve(S,hp).T
    nis=float(nu@np.linalg.solve(S,nu))
    if tangent_cut_xy is not None:
        ut=np.asarray(tangent_cut_xy,float)
        if ut.shape!=(2,) or abs(np.linalg.norm(ut)-1)>1e-9:
            raise ValueError("invalid tangent cut axis")
        K[:2,0] -= ut*np.dot(K[:2,0],ut)
        if abs(np.dot(K[:2,0],ut))>1e-10:
            raise AssertionError("tangent leak after cut")
    if not accepted:
        return Update(x.copy(),P.copy(),K,H.copy(),h.copy(),nu,S,nis,False)
    y=x+K@nu
    y[2]=float(wrap(y[2]))
    A=np.eye(len(x))-K@H
    C=sym(A@P@A.T+K@R@K.T)
    psd_check(C)
    if not np.allclose(y-x if abs(x[2]-y[2])<PI else
                       np.r_[y[:2]-x[:2],wrap(y[2]-x[2]),y[3:]-x[3:]], K@nu,atol=1e-10,rtol=0):
        raise AssertionError("delta != K * innovation")
    return Update(y,C,K,H.copy(),h.copy(),nu,S,nis,True)


def augment(h, H, range_bias):
    """Extend frozen four-state FFD to [x,y,psi,b_g,b_r]."""
    h=np.asarray(h,float).copy(); H=np.asarray(H,float).copy()
    if h.shape!=(2,) or H.shape!=(2,4):
        raise ValueError("FFD dimensions")
    h[0] += float(range_bias)
    HH=np.zeros((2,5))
    HH[:,:4]=H
    HH[0,4]=1.0
    return h,HH
