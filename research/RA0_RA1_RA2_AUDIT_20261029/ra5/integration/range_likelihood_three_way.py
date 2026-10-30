#!/usr/bin/env python3
"""RA5 range likelihood A/B/C: controlled saved Full-H RIGID delay synthetic shift.
A = fractional 30%-leading-edge crossing, train-only Gaussian bias/variance.
B = original INTEGER first-tap + train-only bias/variance and categorical p(tap|delay).
C = full complex CFR (equiv exact noise-aware CIR) profile-likelihood of delay,
    with known per-port spectra; conditional best-case template, not deployable model.

All inputs and source SHA locked, train/test disjoint shift values and noise seeds.
No physical pose/angle/reflector RT; no online state-estimator performance claim.
"""
from __future__ import annotations
import argparse,csv,datetime,hashlib,json,math,os,pathlib,sys
import numpy as np
from raw_tap_covariance import make_cir,extract,C0

TRAIN_D=np.array([-.24,-.12,0,.12,.24])
TEST_D=np.array([-.18,-.06,.06,.18])
GRID=np.linspace(-.30,.30,121)
CFR_SNR=(-5.,5.,20.)
def must(ok,msg):
    if not ok:raise RuntimeError(msg)
def file_sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1048576),b""):h.update(b)
    return h.hexdigest()
def seed_for(*k):
    return int(hashlib.sha256(("RA5-RANGE-20261030|"+"|".join(map(str,k))).encode()).hexdigest()[:15],16)
def rigid_shift(H,freq,delta):
    """Toy: all paths shift in common by delta, same two-port pattern and material response."""
    return H*np.exp(-2j*np.pi*(freq-freq[0])[:,None]*delta/C0)
def generate(H,freq,delta,draw,snr_db,noise_rho,jitter_ps,seed):
    """Known circular-complex per-bin noise; same Y delivered to A,B,C."""
    rng=np.random.default_rng(seed);n=len(freq)
    sig=math.sqrt(float(np.mean(abs(H)**2))/10**(snr_db/10.))
    clean=rigid_shift(H,freq,delta)
    U=(rng.standard_normal((draw,n,2))+1j*rng.standard_normal((draw,n,2)))/math.sqrt(2)
    W=(rng.standard_normal((draw,n))+1j*rng.standard_normal((draw,n)))/math.sqrt(2)
    Y=clean[None,:,:]+sig*(math.sqrt(noise_rho)*W[:,:,None]+math.sqrt(1-noise_rho)*U)
    if jitter_ps:
        dt=rng.normal(scale=jitter_ps*1e-12,size=draw)
        Y[:,:,1]+=(np.exp(-2j*np.pi*(freq-freq.mean())[None,:]*dt[:,None])-1)*clean[None,:,1]
    return Y
def fractional_edge(C,df):
    C=np.asarray(C);n=len(C)
    if C.ndim!=3 or C.shape[-1]!=2:raise ValueError("ERR_C_SHAPE")
    base,tap,strong,valid=extract(C,df)
    amp=np.abs(C)[np.arange(n),:,strong]
    peak=amp.max(axis=1);thr=.3*peak
    prev=np.maximum(tap-1,0)
    u=amp[np.arange(n),prev];v=amp[np.arange(n),tap]
    den=v-u
    ok=valid&(tap>0)&np.isfinite(den)&(den>1e-15)&(u<thr)&(thr<=v)
    frac=np.full(n,np.nan)
    frac[ok]=(tap[ok]-1)+(thr[ok]-u[ok])/den[ok]
    return base[:,0],frac*C0/(C.shape[1]*df),tap,strong,ok,valid
def correlated_profile_template(H,freq,rho):
    """Whiten known correlation across receiver ports, profile ONE global complex gain."""
    L=np.linalg.cholesky(np.array([[1.,rho],[rho,1.]]))
    # Y @ (L.T)^-1 => each frequency row noise whitened
    base=np.linalg.solve(L,H.T).T
    phase=np.exp(-2j*np.pi*GRID[:,None]*(freq-freq[0])[None,:]/C0)
    templates=(base[None,:,:]*phase[:,:,None]).reshape(len(GRID),-1)
    norms=np.sqrt(np.sum(abs(templates)**2,axis=1))
    templates/=norms[:,None]
    return L,templates
def raw_profile(Y,L,templates):
    yw=np.linalg.solve(L,Y.transpose(0,2,1)).transpose(0,2,1).reshape(len(Y),-1)
    scores=np.abs(yw@templates.conj().T)**2
    ids=np.argmax(scores,axis=1)
    result=GRID[ids].copy()
    # Interpolate likelihood score parabola within three candidates.
    lo=(ids>0)&(ids<len(GRID)-1)
    ix=np.flatnonzero(lo)
    if len(ix):
        p=ids[ix];a=scores[ix,p-1];b=scores[ix,p];c=scores[ix,p+1]
        den=a-2*b+c
        good=np.isfinite(den)&(den<0)
        off=np.zeros(len(ix))
        off[good]=.5*(a[good]-c[good])/den[good]
        off=np.clip(off,-1,1)
        result[ix]+=off*(GRID[1]-GRID[0])
    return result
def categorical_fit(samples):
    """Dirichlet-smoothed discrete p(n | toy relative delay), interpolate between train locations."""
    taps=sorted({int(q) for v in samples.values() for q in v})
    v=np.zeros((len(TRAIN_D),len(taps)))
    for i,d in enumerate(TRAIN_D):
        row=samples[float(d)]
        for j,t in enumerate(taps):v[i,j]=int(np.sum(row==t))+.5
        v[i]/=v[i].sum()
    return np.asarray(taps,int),v
def categorical_predict(tap,taps,prob):
    # 49-grid conditional posterior support inside TRAIN_D span; train-only prior uniform.
    dense=np.linspace(TRAIN_D[0],TRAIN_D[-1],97)
    p=np.array([np.interp(d,TRAIN_D,prob[:,k]) for d in dense for k in []]) if False else np.column_stack([np.interp(dense,TRAIN_D,prob[:,k]) for k in range(len(taps))])
    mapping={int(t):j for j,t in enumerate(taps)}
    est=np.full(len(tap),np.nan);lower=est.copy();upper=est.copy()
    for i,t in enumerate(tap):
        if int(t) not in mapping:continue
        weights=p[:,mapping[int(t)]]
        weights=weights/weights.sum()
        est[i]=np.dot(dense,weights)
        cdf=np.cumsum(weights)
        lower[i]=np.interp(.025,cdf,dense)
        upper[i]=np.interp(.975,cdf,dense)
    return est,lower,upper
def result_stats(est,truth,sd=None,lower=None,upper=None):
    est=np.asarray(est,float);truth=np.asarray(truth,float)
    ok=np.isfinite(est)&np.isfinite(truth)
    if lower is not None:ok&=np.isfinite(lower)&np.isfinite(upper)
    if not np.any(ok):return dict(n_valid=0,rmse_m=None,mae_m=None,bias_m=None,cov95=None)
    err=est[ok]-truth[ok]
    covered=(np.abs(err)<=1.96*sd) if sd is not None else ((truth[ok]>=lower[ok])&(truth[ok]<=upper[ok]) if lower is not None else None)
    return dict(n_valid=int(ok.sum()),rmse_m=float(np.sqrt(np.mean(err**2))),
      mae_m=float(np.mean(abs(err))),bias_m=float(np.mean(err)),
      cov95=float(np.mean(covered)) if covered is not None else None)
def dump(path,rows):
    keys=sorted(set().union(*(row.keys() for row in rows)))
    with pathlib.Path(path).open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
def one_case(H,freq,case,pose,snr,jitter,noise_rho,train_per,test_per):
    df=float(freq[1]-freq[0])
    must(abs(df-1950000)<1.,"ERR_BIN_SPACING")
    L,tmpl=correlated_profile_template(H,freq,noise_rho)
    training=[];categorical={}
    for di,d in enumerate(TRAIN_D):
        Y=generate(H,freq,float(d),train_per,snr,noise_rho,jitter,seed_for(case,pose,snr,jitter,"TRAIN",di))
        ri,rs,tap,branch,vsub,vraw=fractional_edge(make_cir(Y),df)
        training.append(dict(delta=float(d),r_int=ri,r_sub=rs,tap=tap,valid=vsub))
        categorical[float(d)]=tap[vraw]
    t=np.concatenate([np.full(train_per,v["delta"]) for v in training])
    int_values=np.concatenate([v["r_int"] for v in training])
    sub_values=np.concatenate([v["r_sub"] for v in training])
    bias_i=float(np.mean(int_values-t))
    sd_i=float(np.std(int_values-t-bias_i,ddof=1))
    sub_valid=np.isfinite(sub_values)
    must(sub_valid.sum()>=.95*len(sub_values),"ERR_SUBTAP_TRAIN_VALID")
    bias_s=float(np.mean(sub_values[sub_valid]-t[sub_valid]))
    sd_s=float(np.std(sub_values[sub_valid]-t[sub_valid]-bias_s,ddof=1))
    must(sd_s>0 and sd_i>0,"ERR_TRAIN_ZERO_SD")
    taps,pr=categorical_fit(categorical)
    results=[];diag=[]
    for di,d in enumerate(TEST_D):
        Y=generate(H,freq,float(d),test_per,snr,noise_rho,jitter,seed_for(case,pose,snr,jitter,"TEST",di))
        ri,rs,tap,branch,vsub,vraw=fractional_edge(make_cir(Y),df)
        ml=raw_profile(Y,L,tmpl)
        mcat,lo,hi=categorical_predict(tap,taps,pr)
        truth=np.full(test_per,float(d))
        diags=dict(case=case,pose=pose,snr_db=snr,jitter_ps=jitter,delta_true_m=float(d),
          n=test_per,sub_valid=int(vsub.sum()),n_native_taps=len(set(tap)),
          n_port_values=len(set(branch)),n_unknown_taps=int(np.sum(~np.isfinite(mcat))),
          n_raw_profile_edge=int(np.sum(abs(ml)==abs(GRID[-1]))))
        diag.append(diags)
        predictions=[
         ("B_ORIGINAL_INT_CAL_GAUSS",ri-bias_i,sd_i,None,None),
         ("A_FRACTIONAL_LEADING_EDGE",rs-bias_s,sd_s,None,None),
         ("B_DISCRETE_TAP_POSTERIOR",mcat,None,lo,hi),
         ("C_RAW_COMPLEX_CFR_PROFILE",ml,None,None,None),
        ]
        for name,pred,sd,lower,upper in predictions:
            score=result_stats(pred,truth,sd,lower,upper)
            results.append(dict(case=case,pose=pose,snr_db=snr,jitter_ps=jitter,
             train_per_shift=train_per,test_per_shift=test_per,train_shift_count=len(TRAIN_D),
             test_shift_m=float(d),arm=name,train_bias_range_m=bias_i if name.startswith("B_ORIGINAL") else bias_s if name.startswith("A_") else None,
             train_sd_m=sd,raw_cfr_known_template=name.startswith("C_"),
             **score))
    summary=dict(case=case,pose=pose,snr_db=snr,jitter_ps=jitter,
      train_n=train_per*len(TRAIN_D),test_n=test_per*len(TEST_D),
      calibration_bias_int=bias_i,calibration_sd_int=sd_i,
      calibration_bias_sub=bias_s,calibration_sd_sub=sd_s,
      train_sub_valid_fraction=float(sub_valid.mean()),
      scenario="saved Full H with synthetic rigid shift all paths, stationary FFD port pattern; NOT physical robot movement")
    return results,diag,summary

def main(args):
    out=pathlib.Path(args.out);out.mkdir(parents=True,exist_ok=True)
    root=pathlib.Path(args.rf_root)
    req=["H_"+args.case+".npy","freqs_hz.npy"]
    lock=json.loads(pathlib.Path(args.sha_lock).read_text())
    for name,sha_target in [(req[0],lock["H_sha256"]),(req[1],lock["freq_sha256"])]:
        must((root/name).is_file() and file_sha(root/name)==sha_target,"ERR_SOURCE_SHA "+name)
    arr=np.load(root/req[0],mmap_mode="r",allow_pickle=False)
    freq=np.load(root/req[1],allow_pickle=False)
    require_poses=[int(x) for x in args.poses.split(",")]
    must(len(require_poses)==len(set(require_poses))==2,"ERR_POSES")
    rows=[];diag=[];meta=[]
    for pose in require_poses:
        must(0<=pose<len(arr),"ERR_POSE_INDEX")
        H=np.asarray(arr[pose,:,:,0],complex)
        for snr in CFR_SNR:
            for jit in (0.,150.):
                scores,ds,rec=one_case(H,freq,args.case,pose,snr,jit,.3,args.train,args.test)
                rows.extend(scores);diag.extend(ds);meta.append(rec)
                print("RA5_RANGE_CELL "+json.dumps({k:rec[k] for k in ("case","pose","snr_db","jitter_ps","train_sub_valid_fraction","calibration_sd_int","calibration_sd_sub")}),flush=True)
    dump(out/"RA5_RANGE_THREE_WAY_SCORES.csv",rows)
    dump(out/"RA5_RANGE_THREE_WAY_DIAGNOSTICS.csv",diag)
    dump(out/"RA5_RANGE_TRAIN_CALIBRATION.csv",meta)
    must(len(meta)==12 and len(rows)==12*4*4,"ERR_DENOMINATOR")
    qa=dict(status="PASS_CONTROLLED_THREE_WAY_RANGE_COMPARISON",
       case=args.case,poses=require_poses,n_scenarios=len(meta),
       n_scores=len(rows),n_train_per_delta=args.train,n_test_per_delta=args.test,
       train_deltas_m=TRAIN_D.tolist(),test_deltas_m=TEST_D.tolist(),
       original_H_SHA256=lock["H_sha256"],freq_SHA256=lock["freq_sha256"],
       input_source_commit=lock.get("source_commit"),
       split="TRAIN_AND_TEST_DELAY_VALUES_DISJOINT_AND_RNG_STREAM_DISJOINT",
       same_samples_across_arms=True,calibration_source="ORACLE_CONDITIONAL_TO_SAVED_H_SCENE",
       raw_complex_arm="KNOWN_FULL_H_TEMPLATE_WITH_SINGLE_UNKNOWN_COMPLEX_GAIN_BEST_CASE",
       motion_model="RIGID_ALL_PATH_DELAY_SHIFT; NO NEW RT",
       range_bias_generalization="NOT_TESTED",real_time_receiver_model="NOT_CALIBRATED",
       new_independent_scene="NONE",
       n_actual_RT_solver_calls=0,science_release=False,independent_auditor=False,
       execution_sha=os.getenv("GITHUB_SHA","UNKNOWN"),
       utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (out/"RA5_RANGE_THREE_WAY_QA.json").write_text(json.dumps(qa,indent=2)+"\n")
    print("RA5_RANGE_FINAL "+json.dumps(qa),flush=True)
if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--case",required=True);ap.add_argument("--poses",required=True)
    ap.add_argument("--rf-root",required=True);ap.add_argument("--sha-lock",required=True)
    ap.add_argument("--train",type=int,default=128);ap.add_argument("--test",type=int,default=192)
    ap.add_argument("--out",required=True)
    x=ap.parse_args();must(x.train>=100 and x.test>=100,"ERR_SAMPLES");main(x)
