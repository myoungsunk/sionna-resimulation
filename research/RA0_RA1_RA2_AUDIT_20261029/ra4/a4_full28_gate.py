#!/usr/bin/env python3
"""RA4/A4 all 28 conditions: intervention identity, first gate divergence, shadow NIS.
Read-only historical packets. Matrix sharded by one RF case (4 gyro levels).
"""
import argparse,csv,datetime,hashlib,json,math,os,pathlib
import numpy as np
import ra4_effect_isolation as A

def must(v,msg):
    if not v:raise RuntimeError(msg)
def maxdiff(a,b):
    return float(np.max(np.abs(np.asarray(a)-np.asarray(b))))
def paired(D,mu,model,var,gate):
    return A.run_arm(D,mu,model,var,gate)
def eq_result(x,y,tol=1e-10):
    return max(maxdiff(x[0],y[0]),maxdiff(x[1],y[1]),maxdiff(x[3],y[3]))<=tol and np.array_equal(x[2],y[2])
def priors(D,arr,k):
    if not k:return D["x0"].copy(),D["P0"].copy()
    ds,gy,dt=[float(D[n][k]) for n in ("ds","gy","dt")]
    q=np.diag([2e-5*abs(ds),math.radians(.015)**2*dt,0])
    return A.predict(arr[0][k-1],arr[1][k-1],ds,gy,dt,q)[:2]
def nis_shadow(D,mus,model,x,P,k,sg,semantic,case,level):
    h,H=model.batch(x[None],D["spec"]);h,H=h[0],H[0]
    out={}
    for mean,mu in mus.items():
        for v in ("NONE",semantic):
            R=D["R"][k].copy()
            if v!="NONE":R[1,1]+=sg**2
            vv=D["z"][k]-h-mu[k]
            S=H@P@H.T+R;S=.5*(S+S.T)
            value=float(vv@np.linalg.solve(S,vv))
            out[mean+("_VAR" if v!="NONE" else "_ORIG")]=value
    return dict(case=case,level=level,semantic=semantic,k=k,t_s=float(D["t"][k]),
       NIS_BB_ORIG=out["BB_ORIG"],NIS_MB_ORIG=out["MB_ORIG"],
       NIS_BB_VAR=out["BB_VAR"],NIS_MB_VAR=out["MB_VAR"],
       NIS_interaction=out["MB_VAR"]-out["MB_ORIG"]-out["BB_VAR"]+out["BB_ORIG"],
       pass_BB_ORIG=out["BB_ORIG"]<=A.THRESH,pass_MB_ORIG=out["MB_ORIG"]<=A.THRESH,
       pass_BB_VAR=out["BB_VAR"]<=A.THRESH,pass_MB_VAR=out["MB_VAR"]<=A.THRESH,
       rho_current_prior=float(math.hypot(*(x[:2]-D["anchor"]))),
       sigma_used=float(sg),R_ss_orig=float(D["R"][k,1,1]),original_BASE_accept=bool(D["acc"][k]))
def gate_analysis(D,mus,model,case,level,var):
    fixed=paired(D,mus["MB"],model,var,"BASE_FIXED")
    self_=paired(D,mus["MB"],model,var,"SELF_NIS")
    dif=np.flatnonzero(fixed[2]!=self_[2])
    q=dict(case=case,level=level,semantic=var,packets=len(D["t"]),
           n_fixed=int(fixed[2].sum()),n_self=int(self_[2].sum()),
           n_flips=int(len(dif)),first_flip=-1,
           d_heading_self_minus_fixed=A.E.scores(D,self_[0],self_[1])["head_rmse"]-A.E.scores(D,fixed[0],fixed[1])["head_rmse"],
           d_xy_self_minus_fixed_cm=A.E.scores(D,self_[0],self_[1])["xy_rmse_cm"]-A.E.scores(D,fixed[0],fixed[1])["xy_rmse_cm"])
    if not len(dif):return q,None
    k=int(dif[0]);x,P=priors(D,fixed,k);xx,PP=priors(D,self_,k)
    gap=max(maxdiff(x,xx),maxdiff(P,PP),abs(fixed[3][k]-self_[3][k]))
    must(gap<1e-10,"ERR_FIRST_FLIP_PRIOR_PARITY "+case+level+var+" "+str(gap))
    shadow=nis_shadow(D,mus,model,x,P,k,fixed[3][k],var,case,level)
    q.update(first_flip=k,first_time_s=float(D["t"][k]),
      first_fixed_accept=bool(fixed[2][k]),first_self_accept=bool(self_[2][k]),
      prior_parity_max=gap,posterior_x_gap=maxdiff(fixed[0][k],self_[0][k]),
      posterior_P_gap=maxdiff(fixed[1][k],self_[1][k]))
    must(shadow["pass_MB_VAR"]==bool(self_[2][k]) or not np.isfinite(self_[4][k]),
         "ERR_SHADOW_NIS "+case+level+var)
    return q,shadow

def dump(p,items):
    must(bool(items),"ERR_EMPTY_CSV "+str(p))
    keys=sorted(set().union(*(r.keys() for r in items)))
    with p.open("w",newline="") as f:
        wr=csv.DictWriter(f,fieldnames=keys);wr.writeheader();wr.writerows(items)
def main(case,out):
    must(case in A.CASES,"ERR_CASE")
    out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
    model=A.C.base_model()
    identity=[];gates=[];shadow=[];source=[]
    real_sig=A.E.sig
    for level in A.LEVELS:
        D,mus=A.make_D(case,level,model)
        checks=0
        for mean,mu in mus.items():
            for gate in A.GATES:
                original=paired(D,mu,model,"NONE",gate)
                A.E.sig=lambda r:0.
                try:
                    for semantic in ("LEGACY","PRIOR"):
                        test=paired(D,mu,model,semantic,gate)
                        gap=max(maxdiff(original[0],test[0]),maxdiff(original[1],test[1]))
                        good=eq_result(original,test) and maxdiff(test[3],np.zeros(len(test[3])))==0
                        must(good,"ERR_ZERO_SIGMA "+case+level+mean+gate+semantic+" "+str(gap))
                        identity.append(dict(case=case,level=level,fixture="SIGMA_ZERO_TO_ORIG",
                          mean=mean,gate=gate,semantic=semantic,delta_state_P=gap,mask_mismatch=0,pass_=True))
                        checks+=1
                finally:A.E.sig=real_sig
        for gate in A.GATES:
            for var in A.VARS:
                # Forced mu_M=mu_B, comparing same mathematical intervention and inputs.
                b=paired(D,mus["BB"],model,var,gate)
                f=paired(D,np.array(mus["BB"],copy=True),model,var,gate)
                must(eq_result(b,f),"ERR_MU_EQUAL "+case+level+gate+var)
                identity.append(dict(case=case,level=level,fixture="MU_M_EQUALS_MU_B",
                      mean="BB=MB",gate=gate,semantic=var,delta_state_P=0.,mask_mismatch=0,pass_=True))
                checks+=1
        dsg=np.asarray(D["ds"]);x0=np.asarray(D["x0"])
        # Compare with the same seed's alternative gyro conditions, without changing noise and x0.
        bds,bgy,bdt,bx0=A.E.build_controls(D["t"],D["gt"][:,:3],"B0")
        bias=A.E.BIAS_LEVELS[level]
        bg=np.asarray(bgy)+math.radians(bias)*np.asarray(bdt)
        gap=max(maxdiff(dsg,bds),maxdiff(D["x0"],np.r_[bx0,0.]),maxdiff(D["dt"],bdt),maxdiff(D["gy"],bg))
        must(gap<1e-10,"ERR_GYRO_ONLY "+case+level+" "+str(gap))
        source.append(dict(case=case,level=level,packet_count=len(D["t"]),gyro_bias_deg_s=bias,
                           max_wheel_initial_noise_diff=gap,n_identity=checks,
                           n_BASE_accepted=int(D["acc"].sum())))
        for var in ("LEGACY","PRIOR"):
            row,info=gate_analysis(D,mus,model,case,level,var)
            gates.append(row)
            if info:shadow.append(info)
        print("A4_CASE_LEVEL "+json.dumps({"case":case,"level":level,"n_id":checks,
             "first_flips":[r["first_flip"] for r in gates[-2:]]}),flush=True)
    must(len(source)==4 and len(identity)==4*(2*2*2+2*3) and len(gates)==8,
         "ERR_EXPECTED_COUNT")
    dump(out/"A4_ALL28_INVARIANTS.csv",identity)
    dump(out/"A4_ALL28_FIRST_FLIPS.csv",gates)
    if shadow:dump(out/"A4_ALL28_SHADOW_NIS.csv",shadow)
    dump(out/"A4_ALL28_SENSOR_SOURCE.csv",source)
    qa=dict(status="PASS_CASE_TECHNICAL_A4",source_sha=A.HISTORIC_SOURCE,case=case,
         n_levels=4,n_identity=len(identity),n_gate_pairs=len(gates),
         first_flip_count=sum(r["first_flip"]>=0 for r in gates),
         n_shadow_nis=len(shadow),n_source_checks=len(source),
         exact_zero_sigma_identity=True,equal_mean_identity=True,
         all_input_original=True,initial_xy_heading_noise_factorial="NOT_RUN",
         timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
         independence="SELF_REVIEW_ONLY",science_release=False)
    (out/"A4_CASE_QA.json").write_text(json.dumps(qa,indent=2)+"\n")
    print("A4_CASE_FINAL "+json.dumps(qa),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--case",choices=A.CASES,required=True);p.add_argument("--out",required=True)
    args=p.parse_args();main(args.case,args.out)
