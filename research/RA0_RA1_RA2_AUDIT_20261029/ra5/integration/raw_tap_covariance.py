#!/usr/bin/env python3
"""RA5-I1: source-preserving complex CFR noise -> first-path r,s0,s1,ds1 covariance.
Purpose: characterize SAME-PACKET nonlinear feature noise, NOT estimate physical
multipath model error or infer a deployed receiver's synchronization capability.
"""
from __future__ import annotations
import argparse,csv,datetime,hashlib,json,math,os,pathlib
import numpy as np

C0=299792458.0
T=np.array([[1.,0.,0.],[0.,1.,0.],[0.,-1.,1.]])
def require(test,msg):
    if not test:raise RuntimeError(msg)
def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1<<20),b""):h.update(chunk)
    return h.hexdigest()
def make_cir(H):
    """H (...,N,2), complex. Return CIR (...,4*N,2), same Hann and IFFT scaling as historical."""
    H=np.asarray(H)
    require(H.ndim>=2 and H.shape[-1]==2 and H.shape[-2]>4,"ERR_H_SHAPE")
    n=H.shape[-2]
    w=.5-.5*np.cos(2*np.pi*np.arange(n)/(n-1))
    return np.fft.ifft(H*w.reshape((1,)*(H.ndim-2)+(n,1)),n=4*n,axis=-2)*n
def extract(C,df,tap_override=None):
    """Detector exactly stronger-RX 30% earliest edge, common tap. No ground truth in inference."""
    C=np.asarray(C)
    if C.ndim==2:C=C[None,:,:]
    require(C.ndim==3 and C.shape[-1]==2,"ERR_CIR_SHAPE")
    nrow,ncir,_=C.shape
    a=np.abs(C)
    strong=np.argmax(a.max(axis=1),axis=1)
    mag=a[np.arange(nrow),:,strong]
    peak=mag.max(axis=1)
    valid=np.isfinite(peak)&(peak>0)
    tap=np.argmax(mag>=.30*peak[:,None],axis=1) if tap_override is None else np.full(nrow,int(tap_override))
    valid &= (tap>=0)&(tap+1<ncir)
    tap=np.clip(tap,0,ncir-2)
    p0=a[np.arange(nrow),tap]**2
    p1=a[np.arange(nrow),tap+1]**2
    den0=p0.sum(axis=1);den1=p1.sum(axis=1)
    valid &= (den0>np.finfo(float).tiny)&(den1>np.finfo(float).tiny)
    z=np.full((nrow,3),np.nan)
    good=np.flatnonzero(valid)
    z[good,0]=tap[good]*C0/(ncir*df)
    z[good,1]=(p0[good,0]-p0[good,1])/den0[good]
    z[good,2]=(p1[good,0]-p1[good,1])/den1[good]
    return z,tap,strong,valid
def noise_trials(H,freq,snr_db,jitter_ps,port_corr,n_draw,seed,chunk=128):
    """AWGN in complex CFR bins, optional RX timing jitter, selection rerun per trial.
    snr_db = mean complex per-bin signal power / complex noise power.
    noise correlation across RX ports is assumed REAL nonnegative rho; per frequency independent.
    jitter applies only to second port; normal iid time offset, no clock random walk.
    """
    require(-.999<port_corr<1 and n_draw>=5 and jitter_ps>=0,"ERR_NOISE_CONFIG")
    H=np.asarray(H,dtype=np.complex128)
    freq=np.asarray(freq,dtype=float)
    require(H.shape==(len(freq),2) and np.all(np.isfinite(H)),"ERR_H_NOT_FINITE")
    df=float(freq[1]-freq[0])
    require(np.max(abs(np.diff(freq)-df))<1e-2,"ERR_FREQ_GRID")
    power=float(np.mean(abs(H)**2))
    require(power>0,"ERR_ZERO_SOURCE")
    sigma=math.sqrt(power/(10**(snr_db/10)))
    clean,z0tap,z0port,z0valid=extract(make_cir(H),df)
    require(z0valid[0],"ERR_CLEAN_INVALID")
    rng=np.random.default_rng(seed)
    obs=[];taps=[];ports=[];allvalid=[]
    f0=freq-freq.mean()
    for st in range(0,n_draw,chunk):
        m=min(chunk,n_draw-st)
        common=(rng.standard_normal((m,len(freq)))+1j*rng.standard_normal((m,len(freq))))/math.sqrt(2)
        indep=(rng.standard_normal((m,len(freq),2))+1j*rng.standard_normal((m,len(freq),2)))/math.sqrt(2)
        n=sigma*(math.sqrt(port_corr)*common[:,:,None]+math.sqrt(1-port_corr)*indep) if port_corr>=0 else None
        require(n is not None,"ERR_NEGATIVE_RX_CORRELATION_UNSUPPORTED")
        signal=np.broadcast_to(H,(m,len(freq),2)).copy()
        if jitter_ps:
            dt=rng.normal(scale=1e-12*jitter_ps,size=m)
            signal[:,:,1]*=np.exp(-2j*np.pi*dt[:,None]*f0[None,:])
        z,tap,port,valid=extract(make_cir(signal+n),df)
        obs.append(z);taps.append(tap);ports.append(port);allvalid.append(valid)
    Z=np.concatenate(obs);tp=np.concatenate(taps);pr=np.concatenate(ports);good=np.concatenate(allvalid)
    require(len(Z)==n_draw and good.sum()>=max(10,.95*n_draw),"ERR_EXCESSIVE_NULL_SAMPLES")
    Z=Z[good]
    R=np.cov(Z,rowvar=False)
    Rt=np.cov(Z@T.T,rowvar=False)
    transform_error=float(np.max(np.abs(Rt-T@R@T.T)))
    require(transform_error<1e-10,"ERR_COV_TRANSFORM "+str(transform_error))
    eig=np.linalg.eigvalsh((R+R.T)/2)
    require(np.all(np.isfinite(eig)) and eig[0]>-1e-10,"ERR_COV_NOT_PSD")
    zmean=Z.mean(axis=0)
    bias=zmean-clean[0]
    varR=float(R[0,0]);varS=float(R[1,1]);varDs=float(Rt[2,2])
    covSds=float(Rt[1,2])
    expected_ds_var=float(R[2,2]+R[1,1]-2*R[1,2])
    require(abs(expected_ds_var-varDs)<1e-12,"ERR_SHARED_TAP_VARIANCE")
    out=dict(snr_db=snr_db,jitter_ps=jitter_ps,port_corr=port_corr,
      n_draw=n_draw,n_valid=len(Z),clean_r_m=float(clean[0,0]),
      clean_s0=float(clean[0,1]),clean_s1=float(clean[0,2]),
      clean_tap=int(z0tap[0]),clean_strong_port=int(z0port[0]),
      tap_flip_n=int(np.sum(tp[good]!=z0tap[0])),
      tap_flip_rate=float(np.mean(tp[good]!=z0tap[0])),
      port_flip_rate=float(np.mean(pr[good]!=z0port[0])),
      mean_delta_r_m=float(bias[0]),mean_delta_s0=float(bias[1]),
      mean_delta_s1=float(bias[2]),var_r_m2=varR,var_s0=varS,
      var_ds1=varDs,cov_s0_ds1=covSds,
      cov_r_s0=float(R[0,1]),cov_r_ds1=float(Rt[0,2]),
      cov_matrix_raw=R.tolist(),cov_matrix_ds=Rt.tolist(),
      cov_eig_min=float(eig[0]),cov_eig_max=float(eig[-1]),
      covariance_rank=int(np.linalg.matrix_rank(R,tol=1e-12)),
      covariance_fullrank=bool(np.min(eig)>1e-12),
      covariance_equivalence_max=transform_error,
      gaussianity_verified=False,
      receiver_model="synthetic independent complex CFR noise and optional iid RX jitter",
      physical_error_identified=False)
    if out["covariance_fullrank"]:
        Rzz=R[:2,:2]
        if np.linalg.cond(Rzz)<1e10:
            c=Rt[2,:2]
            out["conditional_var_ds1_given_r_s0"]=float(Rt[2,2]-c@np.linalg.solve(Rzz,c))
        else:out["conditional_var_ds1_given_r_s0"]=None
    else:out["conditional_var_ds1_given_r_s0"]=None
    return out

def selftest():
    H=np.stack([np.linspace(1,2,257)+0j,np.linspace(.5,1,257)*np.exp(.5j)],axis=1)
    clean,tap,port,v=extract(make_cir(H),1950000.)
    require(v[0],"ERR_SELFTEST")
    g=np.random.default_rng(0)
    V=g.standard_normal((100,3))
    require(np.max(np.abs(np.cov(V@T.T,rowvar=False)-T@np.cov(V,rowvar=False)@T.T))<1e-12,"ERR_TRANSFORM")
    # deterministic duplicate is not new sample: [r,s0,d0], d0=s0 minus known constant.
    R=np.cov(V,rowvar=False);Z=np.c_[V[:,:2],V[:,1]-1.]
    require(np.linalg.matrix_rank(np.cov(Z,rowvar=False),tol=1e-12)==2,"ERR_DUPLICATE_RANK")
    test=noise_trials(H,np.linspace(6250400000,6749600000,257),10,0,0.3,256,123)
    require(test["covariance_equivalence_max"]<1e-10,"ERR_SELFTEST_COV")
    return test

def write_csv(path,rows):
    keys=sorted(set().union(*(r.keys() for r in rows)))
    with path.open("w",newline="") as f:
        wr=csv.DictWriter(f,fieldnames=keys);wr.writeheader();wr.writerows(rows)

def main(args):
    out=pathlib.Path(args.out);out.mkdir(parents=True,exist_ok=True)
    if args.mode=="fixture":
        data=selftest()
        summary=dict(status="PASS_MATH_AND_CFR_SYNTHETIC_SMOKE",fixture=data,
            physical_conclusion=False)
        (out/"SMOKE.json").write_text(json.dumps(summary,indent=2)+"\n")
        print("RA5_TAP_FIXTURE "+json.dumps({k:data[k] for k in ("covariance_equivalence_max","covariance_rank","tap_flip_rate")}),flush=True)
        return
    root=pathlib.Path(args.rf_root)
    hfile=root/("H_"+args.case+".npy");f=root/"freqs_hz.npy"
    require(hfile.is_file() and f.is_file(),"ERR_H_SOURCE_MISSING")
    hashes=json.loads(pathlib.Path(args.hash_lock).read_text())
    require(sha(hfile)==hashes["H_sha256"] and sha(f)==hashes["freq_sha256"],"ERR_SOURCE_HASH")
    h=np.load(hfile,mmap_mode="r",allow_pickle=False);freq=np.load(f,allow_pickle=False)
    require(h.ndim==4 and h.shape[1:]==(257,2,2),"ERR_H_SHAPE")
    ids=[int(x) for x in args.poses.split(",")];require(len(ids)>=2 and len(set(ids))==len(ids),"ERR_POSE_SET")
    rows=[]
    for p in ids:
        require(0<=p<len(h),"ERR_POSE_ID")
        H=np.asarray(h[p,:,:,0],dtype=np.complex128)
        for snr in (-5.,5.,20.):
            for jit in (0.,150.):
                for rho in (0.,.5):
                    key=int(hashlib.sha256(f"{args.case}|{p}|{snr}|{jit}|{rho}|20261030".encode()).hexdigest()[:15],16)
                    rec=noise_trials(H,freq,snr,jit,rho,args.draw,key)
                    rec.update(case=args.case,pose_id=p,H_sha256=hashes["H_sha256"],freq_sha256=hashes["freq_sha256"],seed=key)
                    rows.append(rec)
        print("RA5_TAP_POSE "+json.dumps(dict(case=args.case,pose=p,n=len(rows))),flush=True)
    write_csv(out/"RA5_TAP_COVARIANCE.csv",[{k:v for k,v in r.items() if k not in ("cov_matrix_raw","cov_matrix_ds")} for r in rows])
    (out/"RA5_TAP_COVARIANCE_MATRICES.json").write_text(json.dumps(rows,indent=2)+"\n")
    qa=dict(status="PASS_ASSUMED_COMPLEX_CFR_MONTE_CARLO",case=args.case,n_poses=len(ids),
      n_cells=len(rows),min_n_draw=args.draw,all_pass=all(r["covariance_equivalence_max"]<1e-10 for r in rows),
      singular_R_cells=sum(not r["covariance_fullrank"] for r in rows),
      tap_switching_cells=sum(r["tap_flip_n"]>0 for r in rows),
      interpretation="observational noise given pinned H and assumed receiver model; NOT calibrated deployed sensor R",
      incremental_Fisher="NOT_COMPUTED_UNTIL_J1_SOURCE_PARITY",
      environment_test="NO_NEW_SCENE",source_H_hash=hashes["H_sha256"],
      independent_auditor=False,utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (out/"RA5_TAP_QA.json").write_text(json.dumps(qa,indent=2)+"\n")
    print("RA5_TAP_FINAL "+json.dumps(qa),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=["fixture","source"],default="fixture")
    p.add_argument("--case");p.add_argument("--rf-root");p.add_argument("--hash-lock")
    p.add_argument("--poses",default="0,150");p.add_argument("--draw",type=int,default=512)
    p.add_argument("--out",required=True)
    main(p.parse_args())
