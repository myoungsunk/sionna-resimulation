"""Read-only geometric detection of original 2-degree LUT cell boundaries.

P4/P5 cannot assume differentiability of trilinear interpolation at knots.
No resmoothing, no observation-model modification, no convergence declaration.

This testable module returns detected crossings *and* near-boundary margins
for the exact theta, phi_tx, phi_rx geometry of the frozen RF adapter.
"""
from __future__ import annotations
import math
import numpy as np

GRID_DEG=2.0
ANGLES=("theta_deg","phi_tx_deg","phi_rx_deg")
NEAR_DEG=1e-3

def lut_angles(x,case):
    """Match the original frozen physical geometry, in degrees."""
    x=np.asarray(x,float)
    if x.shape not in ((3,),(4,)) or not np.isfinite(x).all():
        raise ValueError("INVALID_POSE")
    ax,ay,az=(float(v) for v in case["anchor"])
    dz=az-float(case["robot_z_m"])
    u,v=float(x[0]-ax),float(x[1]-ay)
    rho2=u*u+v*v
    if rho2<=0.01:
        raise ValueError("NEAR_ANCHOR_HORIZONTAL_SINGULARITY")
    theta=math.degrees(math.atan2(math.sqrt(rho2),dz))
    tx=math.degrees(math.atan2(-v,u))
    rx=(math.degrees(math.atan2(-v,-u))-math.degrees(float(x[2]))
        -float(case["mount_deg"])+180.)%360.-180.
    return np.array([theta,tx,rx],float)

def nearest_knot_degrees(angle):
    """Signed offset to nearest 2-degree periodic knot (or theta grid)."""
    return GRID_DEG*round(float(angle)/GRID_DEG)

def boundary_report(x,case):
    a=lut_angles(x,case)
    nearest=np.array([nearest_knot_degrees(v) for v in a])
    distance=np.abs(a-nearest)
    return {"angles_deg":dict(zip(ANGLES,map(float,a))),
            "nearest_grid_deg":dict(zip(ANGLES,map(float,nearest))),
            "grid_distance_deg":dict(zip(ANGLES,map(float,distance))),
            "min_grid_distance_deg":float(distance.min()),
            "on_or_near_knot":bool(np.any(distance<=NEAR_DEG)),
            "near_knot_dimensions":[ANGLES[i] for i in range(3) if distance[i]<=NEAR_DEG]}

def segment_crossings(x0,x1,case,*,samples=129,root_tol=1e-9):
    """Detect and bisect 2-degree cell-boundary crossings on a pose segment.

    Samples the actual nonlinear angle geometry, then bisects every observed
    crossing. For azimuths we unwrap the sampled angular path. The method
    is conservative but is not an exhaustive interval arithmetic certificate
    for arbitrary paths. If the anchor pole is reached, return NOT_VALID
    rather than hiding singular data.
    """
    if samples<17 or not isinstance(samples,int):
        raise ValueError("INSUFFICIENT_GEOMETRY_SAMPLING")
    p=np.asarray(x0,float)
    q=np.asarray(x1,float)
    if p.shape!=q.shape:raise ValueError("STATE_SHAPE_MISMATCH")
    tau=np.linspace(0.,1.,samples)
    raw=[]
    try:
        for t in tau:
            raw.append(lut_angles(p+t*(q-p),case))
    except ValueError as exc:
        return {"status":"INVALID_GEOMETRY","reason":str(exc),
                "events":[],"sample_count":samples,"boundary_touch_count":0}
    arr=np.asarray(raw)
    arr[:,1:]=np.rad2deg(np.unwrap(np.deg2rad(arr[:,1:]),axis=0))
    events=[]
    def unwrap_near(y,ref):
        return float(ref+((float(y)-float(ref)+180)%360)-180)
    for dim in range(3):
        for k in range(samples-1):
            a=float(arr[k,dim]);b=float(arr[k+1,dim])
            lo,hi=sorted((a,b))
            left=int(math.ceil((lo+root_tol)/GRID_DEG))
            right=int(math.floor((hi-root_tol)/GRID_DEG))
            # An exact knot at a sampled endpoint is diagnosed separately.
            for n in range(left,right+1):
                target=float(n*GRID_DEG)
                if target<lo-root_tol or target>hi+root_tol:continue
                low,high=float(tau[k]),float(tau[k+1])
                xlo=a-target
                xhi=b-target
                if xlo*xhi>0:continue
                for _ in range(52):
                    mid=.5*(low+high)
                    try:
                        at=float(lut_angles(p+mid*(q-p),case)[dim])
                    except ValueError:
                        return {"status":"INVALID_GEOMETRY",
                                "reason":"SINGULAR_BISECTION","events":events,
                                "sample_count":samples,"boundary_touch_count":0}
                    if dim in (1,2):at=unwrap_near(at,.5*(a+b))
                    error=at-target
                    if abs(error)<=root_tol or high-low<1e-12:
                        low=high=mid
                        break
                    if xlo*error<=0:high=mid;xhi=error
                    else:low=mid;xlo=error
                troot=.5*(low+high)
                events.append({"dimension":ANGLES[dim],
                               "boundary_deg":float(((target+180.)%360.)-180.)
                               if dim>0 else target,
                               "cross_fraction":troot,
                               "state_at_cross":list(map(float,p+troot*(q-p))),
                               "angle_unwrapped_deg":target})
    # Deduplicate crossings counted at shared interval endpoints.
    unique={}
    for e in events:
        key=(e["dimension"],round(e["angle_unwrapped_deg"],8),
             round(e["cross_fraction"],9))
        unique[key]=e
    events=sorted(unique.values(),key=lambda v:(v["cross_fraction"],v["dimension"]))
    nearest_start=boundary_report(p)
    nearest_end=boundary_report(q)
    return {"status":"CROSSING" if events else
               ("KNOT_NEARBY" if nearest_start["on_or_near_knot"] or
                nearest_end["on_or_near_knot"] else "WITHIN_CELLS"),
            "events":events,"sample_count":samples,
            "boundary_touch_count":int(nearest_start["on_or_near_knot"])+
                                    int(nearest_end["on_or_near_knot"]),
            "start":nearest_start,"end":nearest_end,
            "warning":"finite-sample detection; not a formal global all-crossing guarantee"}
