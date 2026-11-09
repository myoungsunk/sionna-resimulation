"""Offline calibration only: fixed R2/B first 120s, no evaluation selection.
Fits a zero-mean two-variance HMM at known development reference states. No
true state, true bias, LoS channel or fitted reference residual is an online input.
"""
import numpy as np
from scipy.special import logsumexp
RS=.0081

def fb(y,T,Rc,pi):
    E=-.5*(np.log(2*np.pi*np.array([RS,Rc]))[None,:]+y[:,None]**2/np.array([RS,Rc]))
    a=np.empty_like(E);a[0]=np.log(pi)+E[0];LT=np.log(T)
    for k in range(1,len(y)):a[k]=E[k]+logsumexp(a[k-1,:,None]+LT,axis=0)
    ll=float(logsumexp(a[-1]));b=np.zeros_like(E)
    for k in range(len(y)-2,-1,-1):b[k]=logsumexp(LT+E[k+1][None,:]+b[k+1][None,:],axis=1)
    g=np.exp(a+b-ll);g/=g.sum(1)[:,None]
    xi=np.exp(a[:-1,:,None]+LT[None,:,:]+E[1:,None,:]+b[1:,None,:]-ll)
    return ll,g,xi

def fit(y):
    y=np.asarray(y,float)
    solutions=[]
    for init in (.04,.16,.36):
        Rc=init;T=np.array([[.97,.03],[.12,.88]]);pi=np.array([.8,.2]);trace=[]
        for it in range(80):
            ll,g,xi=fb(y,T,Rc,pi);trace.append(ll)
            cnt=xi.sum(0)+.5;T=cnt/cnt.sum(1)[:,None]
            Rc=max(RS*1.01,float(np.sum(g[:,1]*y*y)/np.sum(g[:,1])))
            pi=np.array([T[1,0],T[0,1]]);pi/=pi.sum()
            if len(trace)>2 and abs(trace[-1]-trace[-2])<1e-8:break
        ll,g,xi=fb(y,T,Rc,pi)
        solutions.append(dict(init=init,Rc=Rc,T=T.tolist(),pi0=pi.tolist(),loglik=ll,iterations=it+1,
                              occupancy_C=float(g[:,1].mean()),trace=trace))
    best=max(solutions,key=lambda a:a['loglik']);ll,g,xi=fb(y,np.array(best['T']),best['Rc'],np.array(best['pi0']))
    best=dict(best,starts=solutions,normal_Rs=RS,variance_floor_hit=best['Rc']<=RS*1.0100001,
              calibration_frames=len(y),reference_residual_lag1=float(np.corrcoef(y[:-1],y[1:])[0,1]),
              calibration_definition='R2_B0_reference_state residual, first t<120 seconds; all levels share RF',
              inference_uses_reference=False,selection_rule='largest development marginal likelihood among fixed three starts')
    return best,g,xi
