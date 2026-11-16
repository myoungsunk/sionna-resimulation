import sys, numpy as np
sys.path.insert(0,'/home/claude/audit/m45')
import ffd  # sets sys.path
from qclean_uwb.drivesim import observation as O
B='/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/'
Z=np.load('/home/claude/audit/m45/rows.npz')
def files(r,m):
    if m==0: return np.load(f'/home/claude/rel/{r}_B0_Full_10__online.npz'), np.load(f'/home/claude/rel/{r}_B0_Full_10__evaluator.npz')
    M=B+'MOUNT45_B0_20261116/'; return np.load(M+f'{r}_aB_m45_B0_Full_10__online.npz'), np.load(M+f'{r}_aB_m45_B0_Full_10__evaluator.npz')
def feats(H):
    out={k:[] for k in ('idx','peakgap','fpratio','s_fp','s_pk')}
    for a in range(0,len(H),256):
        cir=O.cir_batch(np.asarray(H[a:a+256])[...,0] if np.asarray(H).ndim==4 else np.asarray(H[a:a+256]))
        mag=np.abs(cir); rx=mag.max(axis=1).argmax(axis=1); st=np.take_along_axis(mag,rx[:,None,None],axis=2)[:,:,0]
        pk=st.argmax(axis=1); peak=st.max(axis=1); idx=(st>=0.3*peak[:,None]).argmax(axis=1)
        ii=np.arange(len(st)); out['idx'].append(idx); out['peakgap'].append(pk-idx); out['fpratio'].append(st[ii,idx]/peak)
        p=np.abs(cir[ii,idx,:])**2; out['s_fp'].append((p[:,0]-p[:,1])/p.sum(1)); q=np.abs(cir[ii,pk,:])**2; out['s_pk'].append((q[:,0]-q[:,1])/q.sum(1))
    return {k:np.concatenate(v) for k,v in out.items()}
for r,m in (('R2',0),('R4',0),('R5',0),('R2',45),('R5',45),('R4',45)):
    on,ev=files(r,m)
    Hf=on['Hrf']; Hl=ev['clean_H']
    print(r,m,'shapes',Hf.shape,Hl.shape) if r=='R2' and m==0 else None
    F=feats(Hf); L=feats(Hl)
    dtap=F['idx']-L['idx']
    sup=Z[f'{r}_{m}_support']; bins=Z[f'{r}_{m}_bins']; slow=Z[f'{r}_{m}_slow'][:,1]
    res=[]
    for b in range(3):
        idx=np.flatnonzero(sup&(bins==b)); s=slow[idx]-slow[idx].mean()
        late=dtap[idx]>=2
        gap=F['peakgap'][idx]; fr=F['fpratio'][idx]; dsp=np.abs(F['s_fp'][idx]-F['s_pk'][idx])
        rho=lambda x: np.corrcoef(x, s**2)[0,1]
        res.append(f'b{b}: slowVar {np.var(s):.5f} late(dtap>=2) {late.mean():.2f} slowVar|noLate {np.var(s[~late]) if (~late).sum()>5 else np.nan:.5f} | gap med {np.median(gap):.0f} fpratio med {np.median(fr):.2f} |s_fp-s_pk| med {np.median(dsp):.3f}')
    print(f'== {r} m{m}'); [print('   ',x) for x in res]
    np.savez(f'/home/claude/audit/m45/cir_{r}_{m}.npz', dtap=dtap, **{f'F_{k}':v for k,v in F.items()})
