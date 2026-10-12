import sys,json,collections
import numpy as np
from pathlib import Path
S=Path('/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad')
sys.path.insert(0,str(S/'abc_src/src'))
from qclean_uwb.features.reflection_attribution import image_delays
from qclean_uwb.scenarios.corridor import CorridorSetup
D=S/'deliv/research/V01B_DATA_REQUEST_20261011/DELIVERY_A_20261012';P=S/'native5_paths'
poses={r:json.load(open(S/'matrix.json')) for r in ()}  # placeholder
NF=257;NFFT=4*NF;TAP_S=1/(NFFT*1.95e6);win=(1-np.cos(2*np.pi*np.arange(NF)/(NF-1)))/2;TIE=1e-13
td=lambda H:np.fft.ifft(H*win[None,:,None,None],n=NFFT,axis=1)*NF
ANCH={'aA':4.0,'aB':10.0}
def classes(table):
    seqs=list(table);d=np.array([table[s] for s in seqs]);order=np.argsort(d,kind='stable');cd=[];cn=[];cnt=[]
    for i in order:
        if cd and d[i]-cd[-1]<=TIE:
            cnt[-1]+=1
            if (len(seqs[i]),seqs[i])<cn[-1]:cn[-1]=(len(seqs[i]),seqs[i])
        else:cd.append(d[i]);cn.append((len(seqs[i]),seqs[i]));cnt.append(1)
    return np.array(cd),['LOS' if not n[1] else '>'.join(n[1]) for n in cn],np.array(cnt)
# poses (x,y) per route from the repo copy (R4 extracted earlier; R2/R5 from the abc tree via git)
import subprocess
B='origin/codex/abc-gated-resume-20261011'
def load_poses(r):
    raw=subprocess.check_output(['git','-C','/home/user/sionna-resimulation','show',f'{B}:results/DRIVE_SIM_20261007/S1/routes/rf_poses_{r}.json']);return json.loads(raw)
for c in ['R4_aB_m45','R4_aA_m45','R2_aB_m45','R5_aA_m45','R5_aB_m45']:
    r=c[:2];anc=ANCH[c[3:5]];ps=load_poses(r);setup=CorridorSetup(anchor_x_m=anc)
    L=np.load(D/f'H_{c}.npy');N=np.load(S/f'native5/H_{c}_native.npy');hL=td(L);hN=td(N)
    z=np.load(P/f'NATIVE_FULL__{c}__PATHS_CENTER_BIN.npz');tau=z['tau'].astype(float);valid=z['valid'];amp2=(np.abs(z['a'])**2).sum((1,2));inter=z['interactions'][:,:,0,:];order=(inter!=0).sum(0)
    Ed=(np.abs(hN-hL)**2).sum((2,3));base=collections.Counter();dif=collections.Counter();cntp=collections.Counter();multi_b=0.;multi_d=0.;tb=0.;td_=0.;unm=0;tot_paths=0;cls_stats={}
    tx=setup.anchor_position
    for p in range(len(L)):
        rx=setup.robot_position(ps[p]['x'],ps[p]['y']);cd,names,mult=classes(image_delays(tx,rx,setup.length_m,setup.y_half,setup.height_m))
        v=valid[p];idx=np.flatnonzero(v)
        res=np.abs(tau[p,idx,None]-cd[None,:]);pick=res.argmin(1);ok=res[np.arange(len(idx)),pick]<=5e-14;unm+=int((~ok).sum());tot_paths+=len(idx)
        cls=np.full(valid.shape[1],-1);cls[idx[ok]]=pick[ok]
        for k,j in enumerate(idx):
            if cls[j]<0:continue
            tb+=amp2[p,j]
            if mult[cls[j]]>1:multi_b+=amp2[p,j]
        e=Ed[p].copy();ts=np.where(v,tau[p]/TAP_S,np.inf)
        for _ in range(3):
            i=int(e.argmax())
            if e[i]<=0.02*Ed[p].max():break
            e[max(0,i-6):i+7]=0;j=int(np.argmin(np.abs(ts-i)))
            if abs(ts[j]-i)>3 or cls[j]<0:continue
            td_+=Ed[p,i];dif[names[cls[j]]]+=Ed[p,i];cntp[names[cls[j]]]+=1
            if mult[cls[j]]>1:multi_d+=Ed[p,i]
        for j in idx:
            if cls[j]>=0:base[names[cls[j]]]+=amp2[p,j]
    print(c,'| Native paths matched to image classes (|res|<=5e-14 s): %.1f%% (unmatched %d of %d)'%(100*(1-unm/tot_paths),unm,tot_paths),
          '| path-energy in DEGENERATE classes (>1 sequence share an image): %.1f%% | share of difference energy in degenerate classes: %.1f%%'%(100*multi_b/tb,100*multi_d/td_))
    print('   top difference classes (name | share of attributed diff energy | share of path energy | peaks):')
    for k,v in sorted(dif.items(),key=lambda kv:-kv[1])[:5]:print('     %-44s %5.1f%% | %5.2f%% | %d'%(k,100*v/td_,100*base[k]/tb,cntp[k]))
