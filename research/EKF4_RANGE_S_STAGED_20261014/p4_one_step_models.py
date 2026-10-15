"""Frozen RF P4 one-step methods: D0/J3/J4/frozen-sequential/SR4/MAP4.

All comparisons use ONE same prior and ONE common frozen R0 joint gate.
No scorer, no truth access, no state or observation carryover across time.
"""
from __future__ import annotations
import math
import numpy as np
from core import gaussian_update,sequential_affine,map_update,wrap
from p3_rf_adapter4 import FrozenLut,R0,GATE_JOINT

BIAS_PRIOR_STD_RAD_S=math.radians(.1)
CONVERGENCE_GRADIENT=1e-8
MAX_MAP_ITER=80

def prior_pair(trace,k):
    mu3=trace.prior_x[k].copy()
    P3=trace.prior_P[k].copy()
    mu4=np.r_[mu3,0.]
    P4=np.zeros((4,4),float);P4[:3,:3]=P3
    P4[3,3]=BIAS_PRIOR_STD_RAD_S**2
    return mu3,P3,mu4,P4

def frozen_model(h,H):
    return lambda x:(h,H)

def measurement(lut,case,x):
    return lut.model(x,case)

def common_gate(trace,k,case,lut):
    mu3,P3,mu4,P4=prior_pair(trace,k)
    if not trace.detected[k]:
        return {"status":"MISSING","accepted":False,"nis":None,
                "mu3":mu3,"P3":P3,"mu4":mu4,"P4":P4}
    z=np.array([trace.z_range[k],trace.z_s[k]],float)
    h,H=measurement(lut,case,mu4)
    S=H@P4@H.T+R0
    innovation=z-h
    nis=float(innovation@np.linalg.solve(S,innovation))
    source_nis=float(trace.nis[k])
    if abs(nis-source_nis)>1e-7:
        raise RuntimeError("FROZEN_P3_P4_GATE_NIS_DIFFERENCE")
    accepted=nis<=GATE_JOINT
    if bool(trace.status[k]=="applied")!=accepted:
        raise RuntimeError("P4_ORIGINAL_COMMON_NIS_MASK_DIFFERENCE")
    return {"status":"ACCEPTED" if accepted else "GATE_REJECT",
            "accepted":accepted,"nis":nis,
            "mu3":mu3,"P3":P3,"mu4":mu4,"P4":P4,
            "z":z,"h":h,"H":H,"R":R0}

def fixed_methods(prior,case,lut):
    mu3,P3,mu4,P4=[prior[k] for k in ("mu3","P3","mu4","P4")]
    out={"D0":(mu3.copy(),P3.copy())}
    if not prior["accepted"]:
        for name in ("J3","J4","SF4_R","SF4_S","SR4"):
            out[name]=(mu3.copy(),P3.copy()) if name=="J3" else (mu4.copy(),P4.copy())
        return out,{"accepted":False}
    z,h,H,R=[prior[k] for k in ("z","h","H","R")]
    h3=h.copy();H3=H[:,:3].copy()
    x3,C3,_=gaussian_update(mu3,P3,z,frozen_model(h3,H3),R)
    x4,C4,_=gaussian_update(mu4,P4,z,frozen_model(h,H),R)
    xr,Pr,_=sequential_affine(mu4,P4,z,h,H,R)
    xi,Pi,_=sequential_affine(mu4,P4,z[::-1],h[::-1],
                               H[::-1],R[::-1,::-1])
    # R0 diagonal; process range one time, then s one time using
    # newly linearized s LUT (NOT the originally frozen H_s).
    if abs(R[0,1])>0:
        raise RuntimeError("SR4_NONDIAGONAL_R_REQUIRES_CORRELATED_CONDITIONAL")
    range_model=lambda x:(measurement(lut,case,x)[0][:1],
                           measurement(lut,case,x)[1][:1])
    s_model=lambda x:(measurement(lut,case,x)[0][1:],
                       measurement(lut,case,x)[1][1:])
    xa,Pa,_=gaussian_update(mu4,P4,z[:1],range_model,R[:1,:1])
    xs,Ps,_=gaussian_update(xa,Pa,z[1:],s_model,R[1:,1:])
    if np.max(np.abs(x4[:3]-x3))>1e-9 or np.max(np.abs(C4[:3,:3]-C3))>1e-9:
        raise RuntimeError("J3_J4_ZERO_CROSS_POSE_PARITY")
    if abs(x4[3])>1e-12 or abs(C4[3,3]-P4[3,3])>1e-12 or np.max(abs(C4[:3,3]))>1e-12:
        raise RuntimeError("ZERO_CROSS_BIAS_SPURIOUS_RF_INFORMATION")
    wrapdiff=lambda x,y:max(float(np.max(abs(x[:2]-y[:2]))),
                             abs(float(wrap(x[2]-y[2]))),
                             float(np.max(abs(x[3:]-y[3:]))))
    errors={"frozen_seq_r_state":wrapdiff(xr,x4),
            "frozen_seq_s_state":wrapdiff(xi,x4),
            "frozen_seq_r_cov":float(np.max(abs(Pr-C4))),
            "frozen_seq_s_cov":float(np.max(abs(Pi-C4))),
            "J3_J4_pose_state":wrapdiff(np.r_[x3,0.],x4),
            "J3_J4_pose_cov":float(np.max(abs(C3-C4[:3,:3])))}
    if max(errors.values())>1e-9:
        raise RuntimeError("FROZEN_JOINT_SEQUENTIAL_MISMATCH "+str(errors))
    for x,p in ((x3,C3),(x4,C4),(xr,Pr),(xi,Pi),(xs,Ps)):
        if not(np.isfinite(x).all() and np.isfinite(p).all()
               and np.linalg.eigvalsh(p).min()>0):
            raise RuntimeError("POSTERIOR_NONFINITE_OR_NOT_PD")
    out.update({"J3":(x3,C3),"J4":(x4,C4),
                "SF4_R":(xr,Pr),"SF4_S":(xi,Pi),"SR4":(xs,Ps)})
    return out,{"accepted":True,**errors}

def check_map_stationarity(mu,P,z,lut,case,r):
    if r.status!="CONVERGED" or r.gradient_inf>CONVERGENCE_GRADIENT:
        raise RuntimeError("MAP_NOT_CONVERGED_AT_FROZEN_CRITERION")
    Lp,Lr=np.linalg.cholesky(P),np.linalg.cholesky(R0)
    y=np.linalg.solve(Lp,r.prior_delta)
    h,H=measurement(lut,case,mu+r.prior_delta)
    v=np.linalg.solve(Lr,z-h)
    B=np.linalg.solve(Lr,H@Lp)
    grad=y-B.T@v
    g=float(np.max(abs(grad)))
    cost=.5*float(y@y+v@v)
    cov=Lp@np.linalg.solve(np.eye(len(mu))+B.T@B,Lp.T)
    if (g>CONVERGENCE_GRADIENT or abs(cost-r.cost)>1e-11
            or not np.allclose(cov,r.P,rtol=1e-8,atol=1e-12)):
        raise RuntimeError("INDEPENDENT_MAP_COST_GRADIENT_OR_COVARIANCE_FAIL")
    if not (np.isfinite(r.x).all() and np.isfinite(r.P).all() and np.linalg.eigvalsh(r.P).min()>0):
        raise RuntimeError("MAP_NONFINITE_OR_NON_PD")
    return {"independent_gradient_inf":g,"independent_cost":cost,
            "local_covariance_min_eigenvalue":float(np.linalg.eigvalsh(r.P).min())}

def map_methods(prior,case,lut):
    if not prior["accepted"]:
        return [(prior["mu4"].copy(),prior["P4"].copy(),prior["status"],None)]*2
    mu,P,z=prior["mu4"],prior["P4"],prior["z"]
    model=lambda x:measurement(lut,case,x)
    outputs=[]
    for name,rf in (("M4_P",False),("M4_R",True)):
        result=map_update(mu,P,z,model,R0,range_first=rf,
                          max_iter=MAX_MAP_ITER,gradient_tol=CONVERGENCE_GRADIENT)
        diagnostic={"status":result.status,
                    "gradient_inf":result.gradient_inf,"cost":result.cost,
                    "iterations":result.iterations,"history":result.history}
        if result.status!="CONVERGED":
            outputs.append((None,None,"NUMERICAL_INVALID",diagnostic))
            continue
        try:
            quality=check_map_stationarity(mu,P,z,lut,case,result)
            diagnostic.update(quality)
            outputs.append((result.x,result.P,"CONVERGED",diagnostic))
        except Exception as exc:
            diagnostic["verification_error"]=repr(exc)
            outputs.append((None,None,"NUMERICAL_INVALID",diagnostic))
    return outputs
