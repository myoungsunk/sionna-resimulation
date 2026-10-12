import numpy as np,pandas as pd
from pathlib import Path
S=Path('/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad')
D=S/'deliv/research/V01B_DATA_REQUEST_20261011/DELIVERY_A_20261012';P=S/'native5_paths'
NF=257;NFFT=4*NF;DF=1.95e6;TAP_S=1/(NFFT*DF);win=(1-np.cos(2*np.pi*np.arange(NF)/(NF-1)))/2
def td(H):return np.fft.ifft(H*win[None,:,None,None],n=NFFT,axis=1)*NF
out=[]
for c in ['R2_aB_m45','R4_aA_m45','R4_aB_m45','R5_aA_m45','R5_aB_m45']:
    L=np.load(D/f'H_{c}.npy');N=np.load(S/f'native5/H_{c}_native.npy');hL=td(L);hN=td(N)
    z=np.load(P/f'NATIVE_FULL__{c}__PATHS_CENTER_BIN.npz');tau=z['tau'].astype(float);valid=z['valid'];a=z['a'];inter=z['interactions'][:,:,0,:];obj=z['objects'][:,:,0,:]
    order=(inter!=0).sum(0)                                  # [pose,path] reflection/refraction count
    amp2=(np.abs(a)**2).sum((1,2))                           # [pose,path]
    tapp=tau/TAP_S                                           # path delay in tap units
    Ed=(np.abs(hN-hL)**2).sum((2,3));EL=(np.abs(hL)**2).sum((2,3));EN=(np.abs(hN)**2).sum((2,3))
    n=len(L);tot=np.zeros(5);diffw=np.zeros(5);cnt=np.zeros(5);dist=[];ratio=[];paired=0
    # baseline: energy share of each path order in the Native path list
    for p in range(n):
        v=valid[p]
        if not v.any():continue
        for o in range(4):tot[o]+=amp2[p][v&(order[p]==o)].sum()/amp2[p][v].sum()
        e=Ed[p].copy();pk=[]
        for _ in range(3):                                   # top-3 separated difference peaks
            i=int(e.argmax());
            if e[i]<=0.02*Ed[p].max():break
            pk.append(i);e[max(0,i-6):i+7]=0
        tp=tapp[p];ts=np.where(v,tp,np.inf)
        for i in pk:
            j=int(np.argmin(np.abs(ts-i)));d=abs(ts[j]-i)
            if d>3:continue                                   # no Native path within ~0.45 m: unattributed
            diffw[order[p,j]]+=Ed[p,i];cnt[order[p,j]]+=1;dist.append(d)
            ratio.append((np.abs(hL[p,i]).max()+1e-30)/(np.abs(hN[p,i]).max()+1e-30))
    base=tot[:4]/tot[:4].sum();att=cnt[:4]/cnt[:4].sum();wt=diffw[:4]/diffw[:4].sum()
    # how many top-difference peaks could not be attributed to any Native path?
    print(c,'| energy share by path order 0/1/2/3 in Native paths:',np.round(base,3),'| difference peaks attributed (count share):',np.round(att,3),'| diff-energy share:',np.round(wt,3),
          '| attributed peaks %d, median |tap offset| %.2f, median |h_L|/|h_N| at diff tap %.2f'%(cnt.sum(),np.median(dist),np.median(ratio)))
    # path count behaviour over frequency (Native, all bins)
    try:
        pc=np.load(P/f'NATIVE_FULL__{c}__PATH_COUNTS.npy');ch=(np.diff(pc,axis=1)!=0).sum(1)
        print('   Native path count per pose over 257 bins: min/median/max %d/%d/%d | poses whose count changes with frequency: %.2f | median #change points %d, max %d'%(pc.min(),np.median(pc),pc.max(),np.mean(ch>0),np.median(ch),ch.max()))
    except FileNotFoundError:print('   (path counts: completion-only for this case)')
