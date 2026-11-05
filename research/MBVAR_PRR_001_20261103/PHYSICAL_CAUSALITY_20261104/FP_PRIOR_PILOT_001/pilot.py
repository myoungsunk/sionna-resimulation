"""Exploratory frozen-prior CIR first-path selection, never ground-truth aided.

Original archived CLEAN Full/LoS RF, 257 bins, two RX, 1028-pt Hann IFFT.
The candidate selector sees Full CIR and the archived PRE-measurement MB_VAR
SourceFFD h_r/H/Pprior only. LoS and true pose labels exist in scorer only.
No new RT, mean/R fitting, recursive EKF or trained model.
"""
import argparse
import csv
import json
from pathlib import Path
import numpy as np

C0=299792458.0
NFFT=1028
ROUTES={"R2":979,"R4":742,"R5":1415}
ROOT=Path('results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C')
CELL=Path('research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/C1/C1A_001/RESULTS_001/cells')

def observe(h):
    nbin=h.shape[1]
    if nbin!=257 or h.shape[2]!=2:raise ValueError("two-RX 257-bin original CFR required")
    cir=np.fft.ifft(h*np.hanning(nbin)[None,:,None],n=NFFT,axis=1)*nbin
    mag=np.abs(cir)
    rx=mag.max(axis=1).argmax(axis=1)
    strong=np.take_along_axis(mag,rx[:,None,None],axis=2)[:,:,0]
    peak=strong.max(axis=1)
    if np.any(peak<=0):raise ValueError("zero-peak packet")
    index=(strong>=.30*peak[:,None]).argmax(axis=1)
    return cir,strong,peak,index

def polar(cir,index):
    power=np.abs(cir[np.arange(len(cir)),index,:])**2
    den=power.sum(axis=1)
    return np.divide(power[:,0]-power[:,1],den,
        out=np.full(len(cir),np.nan),where=den>0)

def choose(raw,strong,peak,pred_r,sigma,step):
    """Causal frozen-prior selector. No LoS, GT, future sample or route lookup."""
    n=len(raw);chosen=raw.copy()
    status=np.zeros(n,dtype=np.int8) # 0 unchanged, 1 selected, 2 uncertainty hold
    for i in range(n):
        p=float(pred_r[i]);s=float(sigma[i]);r0=int(raw[i])
        if not(np.isfinite(p) and np.isfinite(s) and s>0 and 0<=p<75):
            status[i]=2;continue
        if s>0.75:
            status[i]=2;continue
        r_obs=r0*step
        if abs(r_obs-p)<=max(step,s):
            continue
        low=max(0,r0-5,int(np.floor((p-2*s)/step)))
        high=min(strong.shape[1]-1,r0+5,int(np.ceil((p+2*s)/step)))
        if low>high:
            status[i]=2;continue
        ids=np.arange(low,high+1)
        ids=ids[(np.abs(ids*step-p)<=2*s)&(strong[i,ids]>=.10*peak[i])]
        if not len(ids):
            status[i]=2;continue
        evidence=np.maximum(strong[i,ids]/peak[i],1e-9)
        scores=((ids*step-p)/s)**2-0.7*np.log(evidence)
        cand=int(ids[np.argmin(scores)])
        raw_score=((r_obs-p)/s)**2-0.7*np.log(max(strong[i,r0]/peak[i],1e-9))
        if cand!=r0 and raw_score-float(np.min(scores))>=.8:
            chosen[i]=cand;status[i]=1
        else:
            status[i]=2
    return chosen,status

def stats(x):
    x=np.asarray(x,dtype=float)
    if not len(x):return None
    return dict(mean=float(x.mean()),median=float(np.median(x)),
        p90=float(np.quantile(x,.90)),p95=float(np.quantile(x,.95)),
        p99=float(np.quantile(x,.99)),max=float(x.max()))

def go():
    ap=argparse.ArgumentParser();ap.add_argument('--output',required=True)
    args=ap.parse_args();out=Path(args.output)
    out.mkdir(parents=True,exist_ok=False)
    frequencies=np.load(ROOT/'freqs_hz.npy')
    if frequencies.shape!=(257,) or np.any(np.diff(frequencies)<=0):
        raise ValueError("bad original frequency grid")
    df=float(frequencies[1]-frequencies[0])
    if not np.allclose(np.diff(frequencies),df,rtol=0,atol=.01):
        raise ValueError("nonuniform frequency grid")
    step=C0/(NFFT*df)
    summaries=[]
    for route,nexpected in ROUTES.items():
        case=f'{route}_aB_m0'
        with np.load(CELL/f'{route}_B0_10.npz',allow_pickle=False) as z:
            tr={k:z[k] for k in ('pose_id','t','h','H','Pprior','prior','mask')}
        ids=tr['pose_id'].astype(int)
        if len(ids)!=nexpected or len(set(ids))!=nexpected or np.any(np.diff(ids)<=0):
            raise RuntimeError("bad/missing evaluation pose IDs")
        f=np.load(ROOT/'FULL_RF'/f'H_{case}.npy',mmap_mode='r')
        l=np.load(ROOT/f'H_LoS_{case}.npy',mmap_mode='r')
        if len(f)<=ids.max() or len(l)<=ids.max():raise ValueError("RF array too short")
        ff=np.asarray(f[ids,:,:,0]);ll=np.asarray(l[ids,:,:,0])
        if ff.shape!=(nexpected,257,2) or ll.shape!=(nexpected,257,2):
            raise ValueError("CFR axes invalid")
        fc,fs,fp,nF=observe(ff)
        lc,_,_,nL=observe(ll)
        sF=polar(fc,nF);sL=polar(lc,nL)
        if not(np.isfinite(sF).all() and np.isfinite(sL).all()):
            raise ValueError("undefined port power")
        pred=np.asarray(tr['h'][:,0],float)
        Hr=tr['H'][:,0,:]
        var=np.einsum('ni,nij,nj->n',Hr,tr['Pprior'],Hr)
        if np.any(var< -1e-10):raise ValueError("negative predicted covariance")
        sigma=np.sqrt(np.maximum(var,0)+.20**2)
        nSel,status=choose(nF,fs,fp,pred,sigma,step)
        sSel=polar(fc,nSel)
        dr0=(nF-nL)*step;dr1=(nSel-nL)*step
        ds0=sF-sL;ds1=sSel-sL
        er0=np.abs(dr0);er1=np.abs(dr1)
        es0=np.abs(ds0);es1=np.abs(ds1)
        changed=nSel!=nF
        correct=nF==nL
        summary=dict(route=route,n=len(ids),seed=10,bias='B0',
            changed=int(changed.sum()),held=int((status==2).sum()),
            original_tap_matches_los=int(correct.sum()),
            selected_tap_matches_los=int((nSel==nL).sum()),
            wrong_to_correct=int((~correct&(nSel==nL)).sum()),
            correct_to_wrong=int((correct&(nSel!=nL)).sum()),
            closer_tap=int((er1<er0-1e-8).sum()),
            farther_tap=int((er1>er0+1e-8).sum()),
            original_range_abs_diff_to_los_m=stats(er0),
            selected_range_abs_diff_to_los_m=stats(er1),
            original_s_abs_diff_to_los=stats(es0),
            selected_s_abs_diff_to_los=stats(es1),
            changed_original_range_error_m=stats(er0[changed]),
            changed_selected_range_error_m=stats(er1[changed]),
            changed_original_s_error=stats(es0[changed]),
            changed_selected_s_error=stats(es1[changed]),
            abs_predicted_minus_los_detector_range_m=stats(np.abs(pred-nL*step)))
        summaries.append(summary)
        with (out/f'{route}_SELECTIONS.csv').open('w',newline='') as file:
            writer=csv.writer(file)
            writer.writerow(['pose_id','t_s','predicted_detector_range_m','pred_sigma_m',
                'baseline_tap','selected_tap','oracle_los_tap_EVAL_ONLY',
                'baseline_range_minus_los_m','selected_range_minus_los_m',
                'baseline_s_minus_los','selected_s_minus_los','changed','held'])
            for k in range(len(ids)):
                writer.writerow([int(ids[k]),float(tr['t'][k]),float(pred[k]),float(sigma[k]),
                    int(nF[k]),int(nSel[k]),int(nL[k]),float(dr0[k]),float(dr1[k]),
                    float(ds0[k]),float(ds1[k]),int(changed[k]),int(status[k]==2)])
        print('RESULT_ROUTE',json.dumps(summary,allow_nan=False),flush=True)
    nums=['n','changed','held','original_tap_matches_los','selected_tap_matches_los',
          'wrong_to_correct','correct_to_wrong','closer_tap','farther_tap']
    totals={k:sum(x[k] for x in summaries) for k in nums}
    result=dict(status='EXPLORATORY_PILOT_NOT_INDEPENDENT_SCIENCE_ACCEPT',
        scope='Existing clean complex RF + frozen full MB_VAR premeasurement priors; open-loop candidate selector only',
        dataset='R2/R4/R5 anchor B m0 B0 seed10 3136 prior pose IDs',
        source_sha='e38de517a21a43bb210c7e04c9fbd6517d8a95cf',
        step_m=step,noise='CLEAN_CFR_NOT_ORIGINAL_NOISY_PACKET',
        policy='strongest RX first 0.30 peak vs prior-aware 0.10 peak candidate, ±5 raw tap and ±2sigma, threshold 0.8, sigma floor 0.20m',
        no_gt_in_selector=True,
        limitation='LoS oracle is evaluation-only. Original prior learned from noisy Full, current H is clean. Not joint EKF feedback, R recalibration, new RF, or fresh holdout',
        totals=totals,routes=summaries)
    (out/'SUMMARY.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf8')
    print('RESULT_TOTAL',json.dumps(totals),flush=True)
    print('RESULT_SUMMARY',json.dumps(result,allow_nan=False),flush=True)

if __name__=='__main__':go()
