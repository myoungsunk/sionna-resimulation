import sys,math,json,time
from pathlib import Path
S=Path('/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad')
sys.path[:0]=[str(S/'g7/job/source/src'),str(S/'abc/research/P0_RESTORE_20261011')]
import numpy as np
import qclean_uwb.drivesim.rf_store as RS
from qclean_uwb.drivesim import rf_store
from qclean_uwb.drivesim.hs_lut import HsLut,s_model
from pole_safe_model_v2 import PoleSafeModelV2
import hashlib
RS.ROOT=S/'rtroot'                       # banks + manifest layout used by load_banks defaults
RS.BANK_MANIFEST=S/'rtroot/results/SIONNA_G2_FFD_NOFLIP_20260924_01a0d30b/bank/BANK_MANIFEST.json'
banks=RS.load_banks(S/'rtroot')
meta=json.loads((S/'g7/lut/hs_lut_meta.json').read_text())['meta']
lut=HsLut(dict(theta_deg=meta['theta_deg'],phi_deg=np.arange(meta['phi_deg'][0],meta['phi_deg'][1]+.01,meta['phi_deg'][2]),s=np.load(S/'g7/lut/hs_lut_2deg.npy')))
t0=time.time();pm=PoleSafeModelV2(lut,banks);print('model built %.1fs'%(time.time()-t0),pm.model_version)
anchor=(4.0,0.0,2.65);z=0.45
for rho in (0.02,0.05,0.10,0.115,0.15,0.3,0.52,1.0,3.0):
    x=4.0+rho;y=0.0
    for psi in (0.3,):
        a,Ja=s_model(lut,anchor,z,x,y,psi,0.,with_jac=True);b,Jb=pm(anchor,z,x,y,psi,0.,with_jac=True)
        print('rho %.3f theta %.1f | LUT s %.4f |J| %.3f | polesafe s %.4f |J| %.3f'%(rho,math.degrees(math.atan2(rho,2.2)),a,np.linalg.norm(Ja),b,np.linalg.norm(Jb)))
print('--- Jacobian along the actual R2 / R5 routes (anchor A / B) ---')
rows=[]
for route,ax,case in (('R2',4.0,'R2_aA_m0'),('R5',4.0,'R5_aA_m0'),('R5',10.0,'R5_aB_m0')):
    P=np.load(S/f'g7/job_pub/OUTPUT/MOTION_{route}_legacy-euler.npz')['pose'];an=(ax,0.,2.65)
    J=np.array([s_model(lut,an,z,p[0],p[1],p[2],0.,with_jac=True)[1] for p in P]);Jp=np.array([pm(an,z,p[0],p[1],p[2],0.,with_jac=True)[1] for p in P])
    rho=np.hypot(P[:,0]-ax,P[:,1])
    for lo,hi in ((0,0.115),(0.115,0.3),(0.3,0.7),(0.7,1.5),(1.5,5),(5,30)):
        m=(rho>=lo)&(rho<hi)
        if m.any():print(case,'rho[%.3f,%.3f) n=%4d  |dS/dxy| med %.2f max %.2f | |dS/dyaw| med %.2f max %.2f | polesafe |dxy| max %.2f'%(lo,hi,m.sum(),np.median(np.hypot(J[m,0],J[m,1])),np.hypot(J[m,0],J[m,1]).max(),np.median(abs(J[m,2])),abs(J[m,2]).max(),np.hypot(Jp[m,0],Jp[m,1]).max()))
