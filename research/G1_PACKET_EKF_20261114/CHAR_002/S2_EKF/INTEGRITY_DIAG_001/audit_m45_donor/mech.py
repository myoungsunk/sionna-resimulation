import sys, numpy as np
sys.path.insert(0,'/home/claude/audit/m45')
from ffd import load
B='/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/'
W=lambda v: np.angle(np.exp(1j*v))
Z=np.load('/home/claude/audit/m45/rows.npz'); m=load()
case={'anchor':(10.,0.,2.65),'robot_z_m':.45,'mount_deg':0.}
for r in ('R2','R4','R5'):
    tr=np.load(f'/home/claude/rel/{r}_B0_Full_10__evaluator.npz')['truth']; L=np.load(B+f'attempt_02/d5/B_B0_{r}.npz')
    _,H=m.batch(np.c_[tr,np.zeros(len(tr))],case); Hpsi=H[:,1,2]
    slow=Z[f'{r}_0_slow'][:,1]; sup=Z[f'{r}_0_support']; t=L['t']-L['t'][0]
    eh=W(L['x'][:,2]-tr[:,2]); sd=np.sqrt(L['P'][:,2,2]); z2=(eh/sd)**2
    R=L['Reff'][:,1,1]; info=Hpsi**2/R
    hi=np.abs(Hpsi)>=1.5
    # dwell: fraction of last 10 s with high g
    dwell=np.array([hi[(t>=ti-10)&(t<=ti)].mean() for ti in t])
    theta=np.where(np.abs(Hpsi)>0.3, slow/np.where(Hpsi==0,np.nan,Hpsi), np.nan)
    ok=sup&hi&np.isfinite(theta)
    c=np.corrcoef(theta[ok],eh[ok])[0,1] if ok.sum()>20 else np.nan
    # white-assumption info over 10 s vs effective: count accepted high-g packets in 10 s
    n10=np.array([((t>=ti-10)&(t<=ti)&hi&L['mask']).sum() for ti in t])
    print(f'== {r}: high-g frac {hi.mean():.2f}')
    print(f'   per-packet heading info g^2/R median: high {np.median(info[hi]) if hi.any() else np.nan:.0f}, low {np.median(info[~hi]):.0f} rad^-2 | sd_psi median high {np.rad2deg(np.median(sd[hi])) if hi.any() else np.nan:.2f} low {np.rad2deg(np.median(sd[~hi])):.2f} deg')
    print(f'   slow-equivalent heading bias |slow_s/Hpsi| (high-g, supported) median {np.rad2deg(np.nanmedian(np.abs(theta[ok]))) if ok.any() else np.nan:.2f} deg; corr(theta, heading err) {c:.2f}; RMS heading err there {np.rad2deg(np.sqrt(np.mean(eh[ok]**2))) if ok.any() else np.nan:.2f} deg')
    for lo,hi_ in ((0,.2),(.2,.6),(.6,1.01)):
        q=(dwell>=lo)&(dwell<hi_)
        if q.sum(): print(f'   dwell {lo}-{hi_}: n={q.sum()} mean z^2 {z2[q].mean():.1f} h95 {np.mean(z2[q]<3.84):.2f} sd_psi {np.rad2deg(np.median(sd[q])):.2f} deg')
    ac=[np.corrcoef(eh[:-k],eh[k:])[0,1] for k in (5,25,50,100)]
    print('   heading-error autocorr at lag 1/5/10/20 s:',[round(a,2) for a in ac])
