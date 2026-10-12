import numpy as np,pandas as pd
from pathlib import Path
S=Path('/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad')
D=S/'deliv/research/V01B_DATA_REQUEST_20261011/DELIVERY_A_20261012'
NF=257;NFFT=4*NF;win=(1-np.cos(2*np.pi*np.arange(NF)/(NF-1)))/2
STEP=299792458./(NFFT*1.95e6)   # metres per tap
EDGES=[-10**9,-2,2,6,12,24,48,96,10**9]   # excess delay windows in taps relative to first arrival (tap~0.15 m)
LAB=['<-2','[-2,2)','[2,6)','[6,12)','[12,24)','[24,48)','[48,96)','>=96']
def td(H):
    return np.fft.ifft(H*win[None,:,None,None],n=NFFT,axis=1)*NF     # [pose,tap,rx,tx]
def fp(h):                      # first arrival: 30% of strongest-RX amplitude peak, as in the observer
    amp=np.abs(h).max(axis=(2,3))                      # [pose,tap]
    pk=amp.max(1,keepdims=True);return (amp>=.3*pk).argmax(1)
rows=[]
for c in ['R2_aB_m45','R4_aA_m45','R4_aB_m45','R5_aA_m45','R5_aB_m45']:
    L=np.load(D/f'H_{c}.npy');N=np.load(S/f'native5/H_{c}_native.npy');hL=td(L);hN=td(N)
    t0=fp(hL);n=len(L);E_L=(np.abs(hL)**2).sum((2,3));E_N=(np.abs(hN)**2).sum((2,3));E_d=(np.abs(hN-hL)**2).sum((2,3))
    idx=np.arange(NFFT)[None,:]-t0[:,None]
    tot=E_L.sum(1)
    res={'case':c}
    for k,(lo,hi) in enumerate(zip(EDGES[:-1],EDGES[1:])):
        m=(idx>=lo)&(idx<hi)
        res['L '+LAB[k]]=float(np.median((E_L*m).sum(1)/tot));res['N-L '+LAB[k]]=float(np.median((E_d*m).sum(1)/tot))
        res['dE '+LAB[k]]=float(np.median(((E_N-E_L)*m).sum(1)/tot))
    rows.append(res)
    # per-pose: where is the single largest difference tap relative to first arrival (in metres)?
    ix=E_d.argmax(1);off=(ix-t0);off=np.where(off>NFFT//2,off-NFFT,off)
    print(c,'| largest-difference tap offset from first arrival: median %.0f taps (%.1f m), frac within +-2 taps: %.2f, frac later than +12 taps: %.2f'%(np.median(off),np.median(off)*STEP,np.mean(abs(off)<=2),np.mean(off>12)))
df=pd.DataFrame(rows).set_index('case')
pd.set_option('display.width',260)
print('\nShare of the pose energy (median over poses) by excess delay window relative to first arrival (tap = %.3f m)'%STEP)
print('legacy energy L:');print(df[[c for c in df if c.startswith('L ')]].round(4).to_string())
print('difference energy |N-L|^2:');print(df[[c for c in df if c.startswith('N-L')]].round(5).to_string())
print('signed energy N minus L:');print(df[[c for c in df if c.startswith('dE')]].round(5).to_string())
df.to_csv(S/'delay_decomp.csv')
