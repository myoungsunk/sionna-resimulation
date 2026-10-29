#!/usr/bin/env python3
"""A4 selected-case first packet causal instrumentation. Historical inputs read only."""
import csv, json, math, pathlib, sys
import numpy as np
import ra4_effect_isolation as A

CASES=("R5_aA_m0","R4_aB_m0","R2_aA_m45")
LEV={"B0":0.,"L0":.01,"L1":.05,"L2":.20}

def d(a,b):
    return float(np.max(np.abs(np.asarray(a)-np.asarray(b))))

def check(ok,s):
    if not ok:raise RuntimeError(s)

def prior(D,X,P,k):
    if k==0:return D["x0"].copy(),D["P0"].copy()
    ds,gy,dt=(float(D[q][k]) for q in ("ds","gy","dt"))
    q=np.diag([2e-5*abs(ds),math.radians(.015)**2*dt,0.])
    return A.predict(X[k-1],P[k-1],ds,gy,dt,q)[:2]

def first_gate(D,mu,model,var,case):
    f=A.run_arm(D,mu,model,var,"BASE_FIXED")
    s=A.run_arm(D,mu,model,var,"SELF_NIS")
    ix=np.flatnonzero(f[2]!=s[2])
    obj=dict(case=case,variance=var,packets=len(D["t"]),
       n_fixed=int(f[2].sum()),n_self=int(s[2].sum()),
       n_flips=int(len(ix)),head_fixed=A.E.scores(D,f[0],f[1])["head_rmse"],
       head_self=A.E.scores(D,s[0],s[1])["head_rmse"],
       xy_fixed_cm=A.E.scores(D,f[0],f[1])["xy_rmse_cm"],
       xy_self_cm=A.E.scores(D,s[0],s[1])["xy_rmse_cm"])
    if not len(ix):
        obj["status"]="NO_FLIP";return obj
    k=int(ix[0]);xf,pf=prior(D,f[0],f[1],k);xs,ps=prior(D,s[0],s[1],k)
    err=max(d(xf,xs),d(pf,ps),abs(f[3][k]-s[3][k]))
    check(err<1e-10,"ERR_FIRST_GATE_PRIOR "+case+var+" "+str(err))
    Hh,H=model.batch(xf[None],D["spec"]);Hh=Hh[0];H=H[0]
    R=D["R"][k].copy()
    if var!="NONE":R[1,1]+=f[3][k]**2
    v=D["z"][k]-Hh-mu[k];S=H@pf@H.T+R;K=np.linalg.solve(S,H@pf).T
    nis=float(v@np.linalg.solve(S,v))
    check(abs(nis-s[4][k])<1e-9,"ERR_NIS_REPLAY")
    obj.update(status="FIRST_FLIP",first_packet=k,t_s=float(D["t"][k]),
         fixed_accept=bool(f[2][k]),self_accept=bool(s[2][k]),
         baseline_mask=bool(D["acc"][k]),prior_parity_max=err,
         rho_previous_post=float(math.hypot(*(f[0][k-1,:2]-D["anchor"]))) if k else float(math.hypot(*(D["x0"][:2]-D["anchor"]))),
         rho_prior=float(math.hypot(*(xf[:2]-D["anchor"]))),
         sigma_used=float(f[3][k]),R_ss=float(R[1,1]),nis=nis,
         innovation_r=float(v[0]),innovation_s=float(v[1]),K_norm=float(np.linalg.norm(K)),
         posterior_x_diff=d(f[0][k],s[0][k]),
         posterior_P_diff=d(f[1][k],s[1][k]))
    return obj

def sigma_timing(D,mu,model,case):
    l=A.run_arm(D,mu,model,"LEGACY","BASE_FIXED")
    p=A.run_arm(D,mu,model,"PRIOR","BASE_FIXED")
    ix=np.flatnonzero(np.abs(l[3]-p[3])>1e-15)
    if not len(ix):return dict(case=case,status="NO_SIGMA_DIFF")
    k=int(ix[0]);xl,pl=prior(D,l[0],l[1],k);xp,pp=prior(D,p[0],p[1],k)
    return dict(case=case,status="TIMING_DIFFERENCE",first_packet=k,
       rho_prev=float(math.hypot(*((l[0][k-1,:2] if k else D["x0"][:2])-D["anchor"]))),
       rho_current=float(math.hypot(*(xl[:2]-D["anchor"]))),
       sigma_legacy=float(l[3][k]),sigma_prior=float(p[3][k]),
       Rss_legacy=float(D["R"][k,1,1]+l[3][k]**2),
       Rss_prior=float(D["R"][k,1,1]+p[3][k]**2),
       prior_x_diff=d(xl,xp),prior_P_diff=d(pl,pp),
       post_x_diff=d(l[0][k],p[0][k]),post_P_diff=d(l[1][k],p[1][k]),
       n_mask_diff=int(np.count_nonzero(l[2]!=p[2])))

def fixtures(D,mus,model,case):
    d0=dict(D);n=min(60,len(D["t"]))
    for key in ("t","gt","z","R","acc","ds","gy","dt","hg"):d0[key]=D[key][:n]
    count=0
    for mu in mus.values():
      for gate in A.GATES:
        ori=A.run_arm(d0,mu,model,"NONE",gate)
        orig=A.E.sig
        try:
            A.E.sig=lambda rho:0.
            for var in ("LEGACY","PRIOR"):
                z=A.run_arm(d0,mu,model,var,gate)
                check(max(d(z[0],ori[0]),d(z[1],ori[1]),d(z[3],0.))<1e-10 and np.array_equal(z[2],ori[2]),
                      "ERR_SIGMA_ZERO "+case+var+gate)
                count+=1
        finally:A.E.sig=orig
    for gate in A.GATES:
      for var in A.VARS:
        a=A.run_arm(d0,mus["BB"],model,var,gate)
        b=A.run_arm(d0,mus["BB"].copy(),model,var,gate)
        check(max(d(a[0],b[0]),d(a[1],b[1]),d(a[3],b[3]))<1e-10 and np.array_equal(a[2],b[2]),"ERR_EQUAL_MU "+case)
        count+=1
    return count

def dump(path,rows):
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=sorted(set().union(*(x.keys() for x in rows))))
        w.writeheader();w.writerows(rows)

def main(out):
    out=pathlib.Path(out);out.mkdir(exist_ok=True,parents=True);model=A.C.base_model()
    gate=[];semantic=[];sensor=[];count=0
    for case in CASES:
        D,mus=A.make_D(case,"B0",model)
        count+=fixtures(D,mus,model,case)
        for lev,bias in LEV.items():
            ds,gy,dt,x0=A.E.build_controls(D["t"],D["gt"][:,:3],lev)
            rec=dict(case=case,level=lev,ds_err=d(ds,D["ds"]),x0_err=d(np.r_[x0,0.],D["x0"]),
                dt_err=d(dt,D["dt"]),gyro_bias_only_err=d(gy-D["gy"],math.radians(bias)*dt))
            sensor.append(rec)
            check(max(rec[k] for k in ("ds_err","x0_err","dt_err","gyro_bias_only_err"))<1e-10,
                "ERR_SENSOR_NOT_BIAS_ONLY "+case+lev)
        gate.append(first_gate(D,mus["MB"],model,"LEGACY",case))
        gate.append(first_gate(D,mus["MB"],model,"PRIOR",case))
        semantic.append(sigma_timing(D,mus["MB"],model,case))
        print("A4_GATE "+json.dumps(gate[-2:],ensure_ascii=False),flush=True)
        print("A4_SEMANTIC "+json.dumps(semantic[-1],ensure_ascii=False),flush=True)
    for name,data in (("GATE_FIRST.csv",gate),("SEMANTIC_FIRST.csv",semantic),("SENSOR_NOISE.csv",sensor)):
        dump(out/name,data)
    qa=dict(status="PASS_SELECTED_B0_A4_DIAGNOSTICS",cases=CASES,n_sigma0_and_equal_mu_fixture_tests=count,
       sensor_bias_only_checks=len(sensor),n_gate_pairs=len(gate),gate_first_flips=sum(x["status"]=="FIRST_FLIP" for x in gate),
       scope="3 selected B0 cases; 60-packet prefix identity fixtures; full-length first-flip tests.",
       initial_XY_heading_noise_factorial="NOT_RUN",independent_audit=False,science_release=False)
    (out/"A4_QA.json").write_text(json.dumps(qa,indent=2)+"\n")
    print("A4_FINAL "+json.dumps(qa),flush=True)
if __name__=="__main__":main(sys.argv[1] if len(sys.argv)>1 else "a4_diag_out")
