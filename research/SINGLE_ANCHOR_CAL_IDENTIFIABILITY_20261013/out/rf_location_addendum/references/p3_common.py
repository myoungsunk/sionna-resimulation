"""Shared P3/P4/P5 detector candidates. Features and predictions use ONLY the complex H (as a receiver would have it), the mount and the frozen observer; labels never enter this module."""
import sys,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];OBS_SRC=ROOT/'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src'
sys.path.insert(0,str(OBS_SRC));from qclean_uwb.drivesim import observation as O
C0=299792458.0;B_OLD=-0.5315983906250129;LEAD=O.LEADING_EDGE
def tap_m(freq):return C0/(4*len(freq)*float(freq[1]-freq[0]))
def cir_mag(H,noise_var=None,rng=None):
    """H (B,bin,rx,tx) -> strongest-RX |CIR| (B,n_tap), observer-identical selection, plus observer outputs"""
    h=np.asarray(H)[...,0]
    if noise_var:
        s=np.sqrt(noise_var/2.0);h=h+s*(rng.standard_normal(h.shape)+1j*rng.standard_normal(h.shape))
    cir=O.cir_batch(h);mag=np.abs(cir);rx=mag.max(axis=1).argmax(axis=1);st=np.take_along_axis(mag,rx[:,None,None],axis=2)[:,:,0]
    return st,cir
def detect(st,tm,threshold=None):
    peak=st.max(axis=1);hits=st>=LEAD*peak[:,None];i1=hits.argmax(axis=1)
    if threshold is not None:det=peak>=threshold
    else:det=np.ones(len(peak),bool)
    # D1: fractional crossing of LEAD*peak between taps i1-1 and i1
    thr=LEAD*peak;r=np.arange(len(st));m1=st[r,i1];m0=np.where(i1>0,st[r,np.maximum(i1-1,0)],0.0)
    t=np.where(m1>m0,(thr-m0)/np.maximum(m1-m0,1e-300),1.0);pos=np.where(i1>0,i1-1+np.clip(t,0,1),0.0)
    return dict(peak=peak,i1=i1,peak_idx=st.argmax(axis=1),first_mag=m1,r_b=i1*tm,r_d1=pos*tm,pos_d1=pos,detected=det)
def e1_features(det,mount,tm):
    """Online-observable features only: raw range, peak, first-tap-to-peak distance, first-lobe amplitude ratio, mount."""
    rb=det['r_b'];dpk=(det['peak_idx']-det['i1'])*tm;lp=np.log(np.maximum(det['peak'],1e-300));fr=det['first_mag']/np.maximum(det['peak'],1e-300)
    return np.stack([np.ones_like(rb),rb,rb**2,dpk,dpk*rb,lp,fr,(mount==45).astype(float)],axis=1)
E1_FEATURES=['1','r_raw','r_raw^2','peak_minus_first_tap_m','that*r_raw','log_peak','first_over_peak','mount==45']
def ridge(X,y,lam=1.0):
    mu=X[:,1:].mean(0);sd=X[:,1:].std(0)+1e-12;Z=np.c_[X[:,:1],(X[:,1:]-mu)/sd];I=np.eye(Z.shape[1]);I[0,0]=0
    w=np.linalg.solve(Z.T@Z+lam*I,Z.T@y);return dict(w=w.tolist(),mu=mu.tolist(),sd=sd.tolist(),lam=lam)
def ridge_pred(m,X):
    mu=np.array(m['mu']);sd=np.array(m['sd']);Z=np.c_[X[:,:1],(X[:,1:]-mu)/sd];return Z@np.array(m['w'])
U_GRID=np.arange(-6.0,6.0001,0.25)
def build_template(st_los,pos_true):
    """training-only: mean peak-normalised LoS lobe sampled at true position + u (taps)"""
    n=st_los.shape[1];acc=np.zeros(len(U_GRID));cnt=0
    for m,p in zip(st_los,pos_true):
        x=p+U_GRID
        if x.min()<0 or x.max()>n-1:continue
        v=np.interp(x,np.arange(n),m);mx=v.max()
        if mx<=0:continue
        acc+=v/mx;cnt+=1
    T=acc/cnt;return T/T.max()
def d2_fit(st,det,T,span=4.0,step=0.05):
    """template-matching delay estimate (taps): argmin_p sum_u (obs(p+u)/win_max - T(u))^2 over p in [p0-span,p0+span]; no label used"""
    n=st.shape[1];p0=det['pos_d1'];cand=np.arange(-span,span+1e-9,step);out=np.zeros(len(st));idx=np.arange(n)
    for k in range(len(st)):
        centers=p0[k]+cand;x=centers[:,None]+U_GRID[None,:];ok=(x.min(axis=1)>=0)&(x.max(axis=1)<=n-1);v=np.interp(x.ravel(),idx,st[k]).reshape(x.shape)
        win=np.interp(np.arange(max(0,p0[k]-6),min(n-1,p0[k]+6)),idx,st[k]).max()
        err=((v/max(win,1e-300)-T[None,:])**2).sum(axis=1);err[~ok]=np.inf;out[k]=centers[int(np.argmin(err))] if np.isfinite(err).any() else p0[k]
    return out

def predict(H,mount,freq,frozen,noise_var=None,rng=None,threshold=None):
    """Frozen-model prediction from the complex channel only. Returns dict of ranges (B baseline and the chosen model) and detection flags. No label arguments exist."""
    tm=tap_m(freq);st,_=cir_mag(H,noise_var,rng);det=detect(st,tm,threshold);rb=det['r_b']-B_OLD;res=dict(B_old=rb,detected=det['detected'],tap=det['i1'])
    if frozen['chosen']=='E1_on_B':
        X=e1_features(det,np.broadcast_to(np.asarray(mount),det['r_b'].shape),tm);res['chosen']=rb-ridge_pred(frozen['params']['E1'],X)
    elif frozen['chosen']=='B_old':res['chosen']=rb
    else:raise NotImplementedError(frozen['chosen'])
    return res
