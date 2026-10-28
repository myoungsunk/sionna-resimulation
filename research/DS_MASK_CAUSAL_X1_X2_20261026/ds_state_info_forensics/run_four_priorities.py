#!/usr/bin/env python3
"""Stage D1-D4: MB_VAR forensics and signed-delta-s latent observability.
Evidence, not a deployable or tuned filter. Source freeze: a95f49d.
All numeric tests are route-held-out where a predictor is fitted.
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"pol_bias_model"))
import exp_pb as PB
C=PB.C
CASES=list(C.CASES)
BIAS=("B0","L0","L1","L2")
OUT=C.OUT
EPS=1.e-12

def feature(H):
    # Same first-path selector and Hann/4x IFFT as S1.
    H=np.asarray(H,dtype=np.complex128)
    if H.ndim==4: H=H[:,:,:,0]
    n,nf,_=H.shape
    win=.5-.5*np.cos(2*np.pi*np.arange(nf)/(nf-1))
    cir=np.fft.ifft(H*win[None,:,None],n=4*nf,axis=1)*nf
    amp=np.abs(cir); power=amp**2
    ii=np.arange(n); branch=np.argmax(np.max(amp,axis=1),axis=1)
    strong=amp[ii,:,branch]
    tap=np.argmax(strong>=.3*np.max(strong,axis=1)[:,None],axis=1)
    def s(o):
        ix=np.clip(tap+o,0,4*nf-1)
        P=power[ii,ix,:]; den=P.sum(axis=1)
        return (P[:,0]-P[:,1])/np.maximum(den,EPS)
    return s(0),s(1)-s(0),tap

def csv(df,name):
    if df.empty: raise RuntimeError("EMPTY_"+name)
    df.to_csv(OUT/name,index=False,float_format="%.16g")

def assert_close(a,b,tol,tag):
    e=np.max(np.abs(np.asarray(a,dtype=float)-np.asarray(b,dtype=float)))
    if not np.isfinite(e) or e>tol:raise RuntimeError(f"{tag} maxdiff={e}")
    return float(e)

def observations():
    records=[]
    for cid in CASES:
        Hf,Hl,samples=C.load_rf(cid)
        # Original pose IDs are mapped via samples JSON; never assume row ordinal.
        ids=[int(p["pose_id"]) for p in samples]
        for lo in range(0,len(ids),100):
            fs,fd,ft=feature(Hf[lo:lo+100])
            ls,ld,lt=feature(Hl[lo:lo+100])
            for k,pose in enumerate(ids[lo:lo+100]):
                records.append(dict(case=cid,route=cid.split("_")[0],
                    pose_id=pose,s_full=float(fs[k]),s_los=float(ls[k]),
                    ds_full=float(fd[k]),ds_los=float(ld[k]),
                    q_delta=float(fd[k]-ld[k]),e_pol=float(fs[k]-ls[k]),
                    tap_full=int(ft[k]),tap_los=int(lt[k])))
    x=pd.DataFrame(records)
    if x.duplicated(["case","pose_id"]).any():raise RuntimeError("DUPLICATE_POSE_ID")
    if not np.isfinite(x[["q_delta","e_pol"]].to_numpy()).all():raise RuntimeError("NONFINITE_RF")
    return x

def linear_fit(train,test):
    # y=e_pol ~ intercept + slope*q_delta. Equal route weights, held-out route;
    # This is a conditional bias information probe, not a recursive filter.
    routes=sorted(train.route.unique())
    X=np.column_stack([np.ones(len(train)),train.q_delta])
    y=train.e_pol.to_numpy()
    ww=np.array([1/max(np.sum(train.route==r),1) for r in train.route])
    ww=ww/ww.sum()
    gram=X.T@(ww[:,None]*X)
    reg=np.diag([1.e-12,1.e-7])
    beta=np.linalg.solve(gram+reg,X.T@(ww*y))
    pred=beta[0]+beta[1]*test.q_delta.to_numpy()
    return beta,pred

def info_probe(df):
    results=[]; perpose=[]
    for route in ("R2","R4","R5"):
        train=df[df.route!=route];test=df[df.route==route]
        coef,pred=linear_fit(train,test)
        y=test.e_pol.to_numpy();err=y-pred
        baseline=np.mean(y*y); mse=np.mean(err*err)
        # Bias+delta covariance from held-out data (diagnostic only).
        X=np.column_stack([y,test.q_delta.to_numpy()])
        cov=np.cov(X,rowvar=False)
        ridge=1.e-12
        correlation=float(cov[0,1]/np.sqrt(max(cov[0,0]*cov[1,1],ridge)))
        var_cond=max(float(cov[0,0]-cov[0,1]**2/max(cov[1,1],ridge)),0)
        # Incremental information ratio is descriptive; may be <1 for
        # badly generalizing predictors. Not a dynamic Fisher or EKF forecast.
        ratio=float(baseline/max(mse,ridge))
        results.append(dict(held_route=route,train_routes=",".join(sorted(train.route.unique())),
            n_train=len(train),n_test=len(test),intercept=coef[0],slope=coef[1],
            e_pol_rms=float(np.sqrt(baseline)),residual_rms=float(np.sqrt(mse)),
            heldout_R2_energy=1-mse/max(baseline,ridge),
            heldout_incremental_precision_ratio=ratio,
            empirical_cov_s_q=cov[0,1],empirical_var_s=cov[0,0],
            empirical_var_q=cov[1,1],empirical_corr=correlation,
            empirical_conditional_var_s_given_q=var_cond))
        tmp=test[["case","route","pose_id","q_delta","e_pol","tap_full","tap_los"]].copy()
        tmp["pred_pol"]=pred;tmp["unexplained_pol"]=err;tmp["held_route"]=route
        perpose.append(tmp)
    csv(pd.DataFrame(results),"D3_HELDOUT_INFORMATION.csv")
    csv(pd.concat(perpose,ignore_index=True),"D3_POSE_PREDICTIONS.csv.gz")
    return results

def trial(cid,bias):
    ref=C.load_control(cid,"B0")
    jb,jm=ref["jb"],ref["jm"]
    t=ref["t_s"];gt=ref["truth_scoring_only"]
    z=ref["nu"][:,jb]+ref["h"][:,jb]+ref["mu"][:,jb]
    ds,gy,dt,x0=PB.build_controls(t,gt[:,:3],bias)
    if bias in ("B0","L2"):
        original=C.load_control(cid,bias)
        err=assert_close(ds, C.controls_from(original["x"][:,jb], original["prior"][:,jb],t)[0],1e-10,"ODOM_PARITY")
    else:err=np.nan
    acc=PB.gated_mask(z,ref["mu"][:,jb],ref["R"][:,jb],ds,gy,dt,
        np.r_[x0,0.],ref["Pprior"][0,jb],C.CASES[cid],C.base_model())
    if bias in ("B0","L2") and not np.array_equal(acc,original["acc"][:,jb]):
        raise RuntimeError("ORIGINAL_MASK_PARITY")
    xbase=np.r_[x0,0.]
    Pbase=ref["Pprior"][0,jb].copy()
    model=C.base_model()
    arms={}
    for label,mu,add in [
        ("BB_ORIG",ref["mu"][:,jb],False),
        ("MB_ORIG",ref["mu"][:,jm],False),
        ("MB_VAR",ref["mu"][:,jm],True)
    ]:
        x=xbase.copy();P=Pbase.copy();out=[]
        for k in range(len(t)):
            if k: x,P=C.predict_one(x,P,ds[k],gy[k],dt[k])
            prior=x.copy();Pprior=P.copy()
            h,H=model.batch(x[None],C.CASES[cid]);h=h[0];H=H[0]
            residual=z[k]-h-mu[k]
            R0=ref["R"][k,jb].copy(); R=R0.copy()
            rho=float(np.linalg.norm(x[:2]-np.asarray(C.CASES[cid]["anchor"][:2])))
            sig=PB.sig(rho)
            if add:R[1,1]+=sig**2
            S=H@P@H.T+R
            K=np.linalg.solve(S,H@P).T
            if acc[k]:
                x=x+K@residual; x[2]=PB.wrap(x[2])
                A=np.eye(4)-K@H;P=A@P@A.T+K@R@K.T;P=(P+P.T)*.5
                inc=K@residual
            else:inc=np.zeros(4)
            out.append(dict(case=cid,bias=bias,arm=label,k=k,t_s=t[k],
                accepted=bool(acc[k]),rho_prior=rho,sigma_b=sig,
                prior_x=prior[0],prior_y=prior[1],prior_psi=prior[2],
                prior_bg=prior[3],post_x=x[0],post_y=x[1],post_psi=x[2],
                post_bg=x[3],Ppsi=P[2,2],Pxy=P[0,1],
                P_xpsi=P[0,2],P_ypsi=P[1,2],
                nu_r=residual[0],nu_s=residual[1],
                Rrr=R[0,0],Rss=R[1,1],Rss_original=R0[1,1],
                Sss=S[1,1],Srs=S[0,1],
                Ks_psi=K[2,1],Kr_psi=K[2,0],
                Ks_x=K[0,1],Ks_y=K[1,1],
                dpsi_s=K[2,1]*residual[1] if acc[k] else 0.,
                dpsi_r=K[2,0]*residual[0] if acc[k] else 0.,
                dpsi_total=inc[2],e_psi_prior=float(PB.wrap(prior[2]-gt[k,2])),
                e_psi_post=float(PB.wrap(x[2]-gt[k,2])),
                e_xy_post=float(np.linalg.norm(x[:2]-gt[k,:2])),
                truth_x=gt[k,0],truth_y=gt[k,1],truth_psi=gt[k,2])))
        f=pd.DataFrame(out)
        if label in ("BB_ORIG","MB_ORIG") and bias in ("B0","L2"):
            ix=jb if label=="BB_ORIG" else jm
            errx=assert_close(f[["post_x","post_y","post_psi","post_bg"]].to_numpy(),
                    original["x"][:,ix,:4],1e-8,"BASE_STATE_PARITY")
        arms[label]=f
    return arms

def forensics(arms):
    joined=pd.concat(arms,ignore_index=True)
    csv(joined,"D4_PACKET_GAIN_LEDGER.csv.gz")
    groups=[]
    for (cid,bias),g in joined.groupby(["case","bias"]):
        b=g[g.arm=="BB_ORIG"];m=g[g.arm=="MB_ORIG"];v=g[g.arm=="MB_VAR"]
        for a in (b,m,v):
            a=a.sort_values("k")
        if not np.array_equal(b.k,m.k) or not np.array_equal(v.k,b.k):raise RuntimeError("K_MISMATCH")
        if not np.array_equal(b.accepted,m.accepted) or not np.array_equal(v.accepted,b.accepted):
            raise RuntimeError("MASK_MISMATCH")
        for scope,mask in [("scoring",v.t_s.to_numpy()>=30),
                           ("first_pass_post60",np.logical_and(v.t_s.to_numpy()>=30,v.t_s.to_numpy()<90))]:
            # The second scope is exploratory and NOT a physically aligned pass window;
            # scoring is the predefined primary comparison.
            if not mask.any():continue
            for name,tab in [("BB_ORIG",b),("MB_ORIG",m),("MB_VAR",v)]:
                t=tab.iloc[np.flatnonzero(mask)]
                head=t.e_psi_post.to_numpy()*180/np.pi
                groups.append(dict(case=cid,bias=bias,scope=scope,arm=name,n=len(t),
                    heading_rmse_deg=float(np.sqrt(np.mean(head**2))),
                    xy_rmse_cm=float(np.sqrt(np.mean(t.e_xy_post.to_numpy()**2))*100),
                    mean_dpsi_s_deg=float(np.mean(t.dpsi_s)*180/np.pi),
                    rms_dpsi_s_deg=float(np.sqrt(np.mean(t.dpsi_s**2))*180/np.pi),
                    cross_psi_gain_error=float(np.mean(t.e_psi_prior*t.dpsi_s)),
                    dpsi_s_energy=float(np.mean(t.dpsi_s**2)),
                    heading_prior_energy=float(np.mean(t.e_psi_prior**2)),
                    accepted=int(np.sum(t.accepted)),
                    mean_Rss=float(np.mean(t.Rss)),
                    mean_Ks_psi=float(np.mean(t.Ks_psi))))
        # Exact instant packet loss of benefit: (post-error squared)
        # compared under separate priors is not a causal contrast; label it.
        d=pd.DataFrame(dict(case=cid,bias=bias,t_s=v.t_s.to_numpy(),
            BB_err=v.e_psi_post.to_numpy()*0+b.e_psi_post.to_numpy(),
            MB_err=m.e_psi_post.to_numpy(),VAR_err=v.e_psi_post.to_numpy(),
            delta_var_mse_deg2=(v.e_psi_post.to_numpy()**2-m.e_psi_post.to_numpy()**2)*(180/np.pi)**2,
            delta_var_psi_gain_deg=(v.dpsi_s.to_numpy()-m.dpsi_s.to_numpy())*180/np.pi,
            delta_var_Rss=v.Rss.to_numpy()-m.Rss.to_numpy(),
            accepted=v.accepted.to_numpy()))
        csv(d,f"D4_FAILURE_SERIES_{cid}_{bias}.csv")
    csv(pd.DataFrame(groups),"D4_ARM_DECOMPOSITION.csv")
    return joined

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--step",choices=["info","forensics","all"],default="all")
    ap.add_argument("--cases",default="all")
    ap.add_argument("--biases",default="B0,L2")
    a=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    cs=CASES if a.cases=="all" else [x.strip() for x in a.cases.split(",")]
    bs=[x.strip() for x in a.biases.split(",")]
    if not set(cs)<=set(CASES) or not set(bs)<=set(BIAS):raise ValueError("unknown case/bias")
    if a.step in ("info","all"):
        q=observations();csv(q,"D3_FULL_LOS_DELTA_TABLE.csv.gz")
        info=info_probe(q);print("D3_DONE",json.dumps(info),flush=True)
    if a.step in ("forensics","all"):
        tables=[]
        for c in cs:
            for b in bs:
                print("D4_START",c,b,flush=True)
                arms=trial(c,b)
                tables.extend(arms.values())
                print("D4_DONE",c,b,flush=True)
        joined=forensics(tables)
        print("D4_ROWS",len(joined),flush=True)
    contract=dict(base_commit="a95f49d90bae532d386ed169e7d6d01382b2a311",
         scope="fixed BASE generated mask each gyro level; offline source",
         route_holdout=True,independent_bias_replications=False,
         info_claim="empirical heldout conditional prediction only, not dynamical Fisher",
         code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (OUT/"RUN_RECEIPT.json").write_text(json.dumps(contract,indent=2))
if __name__=="__main__":main()
