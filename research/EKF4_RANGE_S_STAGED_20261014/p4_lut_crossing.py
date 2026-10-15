"""Exact-input 2-degree LUT cell-boundary events on a MAP search segment.

For y(t)=y0+t*d, detects crossings of theta, phi_tx and phi_rx grid
planes WITHOUT altering the frozen RF LUT, likelihood, R, or prior.
Clips no angle, and marks near-pole / unresolved fast rotations invalid.
Analytic chain-rule h/H remains frozen and unchanged.
"""
from __future__ import annotations
import math
import numpy as np

KNOT_SPACING_DEG=2.0
MAX_INTRA_SEGMENT_ANGLE_DEG=0.5
MIN_HORIZONTAL_POLE_DISTANCE_M=0.1

def _angles(x,case):
    x=np.asarray(x,float)
    ax,ay,az=(float(v) for v in case["anchor"])
    u,v=float(x[0]-ax),float(x[1]-ay)
    rh=math.hypot(u,v)
    if rh<MIN_HORIZONTAL_POLE_DISTANCE_M:
        raise ValueError("LUT_STEP_NEAR_ANCHOR_POLE")
    h=float(az-case["robot_z_m"])
    theta=math.degrees(math.atan2(rh,h))
    tx=math.degrees(math.atan2(-v,u))
    rx=(math.degrees(math.atan2(-v,-u))-math.degrees(x[2])-float(case["mount_deg"])+180.)%360.-180.
    return np.array([theta,tx,rx],float)

def _unwrap(angles):
    q=np.array(angles,copy=True,dtype=float)
    q[:,1:]=np.rad2deg(np.unwrap(np.deg2rad(q[:,1:]),axis=0))
    return q

def nearest_grid(angles):
    arr=np.asarray(angles,float)
    nearest=KNOT_SPACING_DEG*np.rint(arr/KNOT_SPACING_DEG)
    return {"angles_deg":arr.tolist(),
            "nearest_grid_deg":nearest.tolist(),
            "distance_deg":np.abs(nearest-arr).tolist(),
            "min_grid_distance_deg":float(np.min(np.abs(nearest-arr)))}

def step_crossings(y0,d,Lp,mu,case,*,initial_segments=64,max_segments=2048):
    """Resolve all 2° grid crossings along ONE candidate MAP step.

    phi angles are unwrapped along the line; periodic +/-180 seam is a
    regular grid plane. If rapid rotations remain under-resolved, return
    explicit error rather than an invented no-crossings answer.
    """
    y0=np.asarray(y0,float)
    d=np.asarray(d,float)
    Lp=np.asarray(Lp,float)
    mu=np.asarray(mu,float)
    if y0.shape!=d.shape or Lp.shape!=(len(y0),len(y0)):
        raise ValueError("INVALID_SEARCH_SEGMENT_DIMENSION")
    if not(np.isfinite(y0).all() and np.isfinite(d).all()
           and np.isfinite(Lp).all() and np.isfinite(mu).all()):
        raise ValueError("NONFINITE_LUT_SEGMENT")
    def ang(t):
        return _angles(mu+Lp@(y0+float(t)*d),case)
    n=initial_segments
    while True:
        ts=np.linspace(0.,1.,n+1)
        raw=np.array([ang(t) for t in ts])
        unwrapped=_unwrap(raw)
        angular_diff=np.max(np.abs(np.diff(unwrapped,axis=0)))
        if angular_diff<=MAX_INTRA_SEGMENT_ANGLE_DEG:
            break
        if n>=max_segments:
            raise RuntimeError("UNRESOLVED_RAPID_LUT_ANGLE_CHANGE")
        n=min(n*2,max_segments)
    hits=[]
    labels=("theta","phi_tx","phi_rx")
    for i in range(n):
        a,b=unwrapped[i],unwrapped[i+1]
        for axis in range(3):
            lo,hi=sorted((float(a[axis]),float(b[axis])))
            levels=np.arange(math.ceil((lo-1e-10)/KNOT_SPACING_DEG),
                             math.floor((hi+1e-10)/KNOT_SPACING_DEG)+1)
            for level in levels:
                knot=KNOT_SPACING_DEG*float(level)
                if abs(float(a[axis])-knot)<1e-12:
                    t=float(ts[i])
                elif abs(float(b[axis])-knot)<1e-12:
                    t=float(ts[i+1])
                elif (float(a[axis])-knot)*(float(b[axis])-knot)>0:
                    continue
                else:
                    left,right=float(ts[i]),float(ts[i+1])
                    sign_a=float(a[axis])-knot
                    for _ in range(48):
                        mid=.5*(left+right)
                        rawmid=ang(mid)
                        if axis==0:
                            mid_angle=float(rawmid[axis])
                        else:
                            expected=float(a[axis])+(mid-float(ts[i]))/(float(ts[i+1])-float(ts[i]))*(float(b[axis])-float(a[axis]))
                            mid_angle=float(rawmid[axis])+360.*round((expected-float(rawmid[axis]))/360.)
                        err=mid_angle-knot
                        if abs(err)<1e-12 or right-left<1e-13:
                            break
                        if err*sign_a<=0:right=mid
                        else:
                            left=mid
                            sign_a=err
                    t=.5*(left+right)
                if 1e-12<t<1.-1e-12:
                    hits.append({"t":t,"angle":labels[axis],
                                 "knot_deg":knot})
    seen=set();uni=[]
    for h in sorted(hits,key=lambda x:x["t"]):
        key=(h["angle"],round(h["t"],11))
        if key not in seen:
            seen.add(key);uni.append(h)
    return {
        "status":"RESOLVED","segments":int(n),
        "max_segment_angle_delta_deg":float(angular_diff),
        "start":nearest_grid(unwrapped[0]),"end":nearest_grid(unwrapped[-1]),
        "events":uni}

def candidate_grid_events(cost,y0,d,Lp,mu,case,*,resolved_eps=32):
    """Inspect original J exactly at crossings and just to either side.

    A candidate is accepted ONLY when original objective decrease exceeds
    the float64 uncertainty margin. This is a *search helper*, NOT any
    certificate of Clarke stationarity or posterior covariance.
    """
    trace=step_crossings(y0,d,Lp,mu,case)
    c0=float(cost(y0))
    eps=np.finfo(float).eps
    margin=resolved_eps*eps*max(1.,abs(c0))
    grid=[1.]
    for hit in trace["events"]:
        t=hit["t"]
        grid.extend([t,max(0.,t-1e-7),min(1.,t+1e-7)])
    grid=sorted(set(round(v,13) for v in grid if v>0))
    scored=[]
    for t in grid:
        y=y0+float(t)*d
        val=float(cost(y))
        if not np.isfinite(val):continue
        scored.append({"t":t,"cost":val,"delta_J":math.fsum([val,-c0]),
                       "resolved_improvement":val<c0-margin})
    decreasing=[row for row in scored if row["resolved_improvement"]]
    best=min(decreasing,key=lambda row:row["cost"]) if decreasing else None
    return {"crossing":trace,"cost_initial":c0,"floating_decrease_margin":float(margin),
            "cost_candidates":scored,"best":best}
