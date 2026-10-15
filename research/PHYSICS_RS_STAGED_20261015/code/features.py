"""Pure measured-packet feature extraction. No pose, truth or channel labels.
Original observation: Hann, 4N IFFT*N, stronger-RX 30% leading edge,
shared first tap. Features use an explicitly fixed FP:FP+80 tap window.
"""
from __future__ import annotations
import numpy as np
C0=299792458.0
G0=['range_m','log_fp_power','abs_s_fp']
G1=['early4','early8','early16','delay_rms_ns','peak_diff_ns']
G2=['eta_fp_win80','s_diff4','s_diff8','s_diff16','tap_pol_var80']
G3=['jones_diversity','freq_s_var']
G4=['detector_s_span','detector_delay_span_ns']
GROUPS={'G0':G0,'G1':G0+G1,'G2':G0+G2,'G3':G0+G3,'G4':G0+G4,
        'G5':G0+G1+G2+G3+G4}
FEATURES=list(dict.fromkeys(sum(GROUPS.values(),[])))

def extract(h: np.ndarray, f: np.ndarray)->dict[str,np.ndarray]:
    h=np.asarray(h,dtype=np.complex128);f=np.asarray(f,dtype=np.float64)
    if h.ndim!=3 or h.shape[1:]!=(len(f),2):raise ValueError('H must be N,F,2 RX')
    if len(f)!=257 or not np.isfinite(h).all() or not np.isfinite(f).all():raise ValueError('nonfinite or non257')
    if f[1]<=f[0] or not np.allclose(np.diff(f),f[1]-f[0],rtol=1e-10,atol=1e-5):raise ValueError('frequency grid')
    n,nf,_=h.shape;nt=4*nf;dt=1/(nt*(f[1]-f[0]));ii=np.arange(n)
    window=.5-.5*np.cos(2*np.pi*np.arange(nf)/(nf-1))
    cir=np.fft.ifft(h*window[None,:,None],n=nt,axis=1)*nf
    amp=np.abs(cir);power=amp**2
    branch=amp.max(axis=1).argmax(axis=1)
    strong=amp[ii,:,branch];peaks=strong.max(axis=1)
    detected=peaks>0
    tap=(strong>=.3*peaks[:,None]).argmax(axis=1)
    valid=detected&(tap+80<=nt)
    fp=power[ii,tap,:];den=fp.sum(axis=1)
    # Relative regularization preserves amplitude-scale invariance; null flags remain explicit.
    tiny=np.finfo(float).tiny
    sfp=np.divide(fp[:,0]-fp[:,1],den,out=np.full(n,np.nan),where=den>tiny)
    winidx=np.minimum(tap[:,None]+np.arange(80),nt-1)
    pw=power[ii[:,None],winidx,:];ps=pw.sum(axis=2);energy=ps.sum(axis=1)
    w=np.divide(ps,energy[:,None],out=np.zeros_like(ps),where=energy[:,None]>tiny)
    tk=np.arange(80)*dt*1e9;mt=(w*tk).sum(axis=1)
    rms=np.sqrt(np.maximum(0,(w*(tk-mt[:,None])**2).sum(axis=1)))
    r=np.divide(pw[:,:,0]-pw[:,:,1],ps,out=np.zeros_like(ps),where=ps>tiny)
    rbar=(w*r).sum(axis=1);vpol=(w*(r-rbar[:,None])**2).sum(axis=1)
    eports=pw.sum(axis=1);eps=np.maximum(energy*1e-12,tiny)
    eps_fp=np.maximum(den*1e-12,tiny)
    eta=.5*np.abs(np.log((fp[:,0]+eps_fp)/(fp[:,1]+eps_fp))-np.log((eports[:,0]+eps)/(eports[:,1]+eps)))
    out={'s_fp':sfp,'range_m':tap*dt*C0,'tap':tap,'branch':branch,'valid':valid,
         'log_fp_power':np.log10(np.maximum(den,tiny)),'abs_s_fp':abs(sfp),
         'delay_rms_ns':rms,'peak_diff_ns':abs(pw[:,:,0].argmax(axis=1)-pw[:,:,1].argmax(axis=1))*dt*1e9,
         'eta_fp_win80':eta,'tap_pol_var80':vpol,
         'weak_port_fp':(fp.min(axis=1)<=den*1e-10),'window_truncated':~(tap+80<=nt)}
    for L in (4,8,16):
        el=pw[:,:L,:].sum(axis=1);dl=el.sum(axis=1)
        sl=np.divide(el[:,0]-el[:,1],dl,out=np.full(n,np.nan),where=dl>tiny)
        out[f'early{L}']=w[:,:L].sum(axis=1)
        out[f's_diff{L}']=abs(sfp-sl)
    # Scale each packet before second moment to prevent under/overflow.
    scale=np.max(np.abs(h),axis=(1,2));hn=np.divide(h,scale[:,None,None],out=np.zeros_like(h),where=scale[:,None,None]>tiny)
    ch=np.einsum('nfi,nfj->nij',hn,hn.conj());ch=(ch+ch.conj().transpose(0,2,1))/2
    ev=np.linalg.eigvalsh(ch);tr=ev.sum(axis=1)
    if np.any(ev[:,0]<-1e-12*np.maximum(tr,1)):raise RuntimeError('Jones moment not PSD')
    out['jones_diversity']=np.divide(np.maximum(ev[:,0],0),tr,out=np.full(n,np.nan),where=tr>tiny)
    pf=abs(hn)**2;df=pf.sum(axis=2);wf=np.divide(df,df.sum(axis=1)[:,None],out=np.zeros_like(df),where=df.sum(axis=1)[:,None]>tiny)
    rs=np.divide(pf[:,:,0]-pf[:,:,1],df,out=np.zeros_like(df),where=df>tiny);mr=(wf*rs).sum(axis=1)
    out['freq_s_var']=(wf*(rs-mr[:,None])**2).sum(axis=1)
    ss=[];tt=[]
    for q in (.2,.3,.4):
        tq=(strong>=q*peaks[:,None]).argmax(axis=1);fq=power[ii,tq,:];dq=fq.sum(axis=1)
        sq=np.divide(fq[:,0]-fq[:,1],dq,out=np.full(n,np.nan),where=dq>tiny)
        ss.append(sq);tt.append(tq)
    out['detector_s_span']=np.max(abs(np.stack(ss)-sfp),axis=0)
    out['detector_delay_span_ns']=np.ptp(np.stack(tt),axis=0)*dt*1e9
    for key in FEATURES:
        out[key]=np.asarray(out[key],float)
        out[key][~valid]=np.nan
    return out
