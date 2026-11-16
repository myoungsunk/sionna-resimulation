import sys, numpy as np
sys.path.insert(0,'/home/claude/audit/m45')
from ffd import load
B='/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/'
sys.path.insert(0,B+'INTEGRITY_DIAG_001/continuation_d2_d3')
from d3 import decompose
CFG=dict(half_seconds=5., half_distance_m=.25, half_yaw_deg=5., min_window_packets=10)
EDGES=np.array([1.5,3.,6.,10.])
m=load()
W=lambda v: np.angle(np.exp(1j*v))
def data(route,mount):
    if mount==0:
        on=np.load(f'/home/claude/rel/{route}_B0_Full_10__online.npz'); ev=np.load(f'/home/claude/rel/{route}_B0_Full_10__evaluator.npz')
        tr_=np.load(B+f'INTEGRITY_DIAG_001/attempt_02/d0/B_B0_{route}.npz')
    else:
        M=B+'MOUNT45_B0_20261116/'
        on=np.load(M+f'{route}_aB_m45_B0_Full_10__online.npz'); ev=np.load(M+f'{route}_aB_m45_B0_Full_10__evaluator.npz')
        tr_=np.load(M+f'{route}_aB_m45_B0_Full_10__e0_trace.npz')
    truth=ev['truth']; case={'anchor':(10.,0.,2.65),'robot_z_m':.45,'mount_deg':float(mount)}
    st=np.c_[truth,np.zeros(len(truth))]
    h,H=m.batch(st,case)
    eps=on['z']-h-on['muMB']
    g=np.abs(H[:,1,2]); d=np.hypot(truth[:,0]-10,truth[:,1])
    arc=np.r_[0,np.cumsum(np.abs(on['ds'][1:]))]; yaw=np.r_[0,np.cumsum(np.abs(W(np.diff(truth[:,2]))))]
    t=on['t']; R=on['R'][:,1,1]
    mask=tr_['mask'] if 'mask' in tr_.files else np.ones(len(t),bool)
    parts=decompose(eps,t,arc,yaw,CFG)
    return dict(eps=eps,g=g,d=d,t=t,R=R,mask=mask,parts=parts,bins=np.searchsorted(EDGES,d,side='right')-1)
rows={}
for route in ('R2','R4','R5'):
    for mount in (0,45):
        D=data(route,mount); rows[(route,mount)]=D
        el=D['parts']['support']
        out=[]
        for b,(lo,hi) in enumerate(((1.5,3),(3,6),(6,10))):
            for usemask in (True,False):
                idx=np.flatnonzero(el&(D['bins']==b)&(D['mask'] if usemask else True))
                sv=np.var(D['parts']['slow'][idx,1]) if len(idx) else np.nan
                if usemask: sv_m=sv
            idx=np.flatnonzero(el&(D['bins']==b))
            e=D['eps'][D['bins']==b,1]; Rb=D['R'][D['bins']==b]
            hi_g=idx[D['g'][idx]>=2.0]
            win=np.unique(np.floor((D['t'][hi_g]-D['t'][0])/20)).size
            out.append(f'{lo}-{hi}m: slowVar(mask) {sv_m:.5f} (all) {sv:.5f} | eps_s mean {e.mean():+.4f} sd {e.std():.4f} z_sd {np.std(e/np.sqrt(Rb)):.2f} | g med {np.median(D["g"][D["bins"]==b]):.2f} | g>=2 supported n {len(hi_g)} win20s {win}')
        print(f'== {route} m{mount} accept {D["mask"].mean():.3f} eps_r mean {D["eps"][:,0].mean():+.3f} sd {D["eps"][:,0].std():.3f}')
        for o in out: print('   ',o)
np.savez('/home/claude/audit/m45/rows.npz', **{f'{r}_{mm}_{k}':v for (r,mm),D in rows.items() for k,v in D.items() if k!='parts'}, **{f'{r}_{mm}_slow':D['parts']['slow'] for (r,mm),D in rows.items()}, **{f'{r}_{mm}_support':D['parts']['support'] for (r,mm),D in rows.items()})
