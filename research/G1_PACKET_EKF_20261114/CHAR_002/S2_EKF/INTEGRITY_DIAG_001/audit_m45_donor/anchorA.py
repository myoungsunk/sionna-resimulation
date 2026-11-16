import sys, numpy as np
sys.path.insert(0,'/home/claude/audit/m45')
from ffd import load
B='/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/'
sys.path.insert(0,B+'continuation_d2_d3')
from d3 import decompose
CFG=dict(half_seconds=5., half_distance_m=.25, half_yaw_deg=5., min_window_packets=10)
W=lambda v: np.angle(np.exp(1j*v))
m=load()
L=np.load(B+'attempt_02/d5/A_B0_R4.npz')
for ax in (4.,):
    case={'anchor':(ax,0.,2.65),'robot_z_m':.45,'mount_deg':0.}
    h,H=m.batch(L['prior'][:40],case); print('anchor A parity at x=%.0f:'%ax, np.abs(h-L['h'][:40]).max(), np.abs(H-L['H'][:40]).max())
case={'anchor':(4.,0.,2.65),'robot_z_m':.45,'mount_deg':0.}
P=B+'continuation_ks/replay_inputs/packets/A_B0/'
ref_R4B=None
for r in ('R2','R4','R5'):
    on=np.load(P+f'{r}_aA_m0_B0_Full_10__online.npz'); ev=np.load(P+f'{r}_aA_m0_B0_Full_10__evaluator.npz'); tr=ev['truth']
    h,H=m.batch(np.c_[tr,np.zeros(len(tr))],case); eps=on['z']-h-on['muMB']; g=np.abs(H[:,1,2]); d=np.hypot(tr[:,0]-4,tr[:,1])
    arc=np.r_[0,np.cumsum(np.abs(on['ds'][1:]))]; yaw=np.r_[0,np.cumsum(np.abs(W(np.diff(tr[:,2]))))]; t=on['t']
    parts=decompose(eps,t,arc,yaw,CFG); sup=parts['support']; bins=np.searchsorted([1.5,3,6,10],d,side='right')-1
    out=[]
    for b,(lo,hi) in enumerate(((1.5,3),(3,6),(6,10))):
        idx=np.flatnonzero(sup&(bins==b)); s=parts['slow'][idx,1]
        hg=idx[g[idx]>=2.0]; win=np.unique(np.floor((t[hg]-t[0])/20)).size; wall=np.unique(np.floor((t[idx]-t[0])/20)).size
        out.append(f'{lo}-{hi}m n={len(idx)} win={wall} slowVar={np.var(s):.5f} g med {np.median(g[idx]):.2f} | g>=2 n={len(hg)} win={win}')
    print(f'anchor A {r} m0:', ' | '.join(out))
