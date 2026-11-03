@'
from pathlib import Path
import sys,types,subprocess,importlib.util,json,math,hashlib
import numpy as np
repo=Path('/mnt/d/codex/MBVAR_PRR_001_20261103');base=repo/'research/MBVAR_PRR_001_20261103';orig=Path('/mnt/d/SLAM_bot/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/execution_33e9849');src=orig/'p2';cache=Path('/mnt/d/codex/MBVAR_PRR_001_20261103_inputs/S1_INPUTS/algorithm_input')
sys.path[:0]=[str(src/'research/FFD_P0P3_20261016'),str(src/'research/EKF4_RANGE_S_STAGED_20261014'),str(src/'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src')]
def load(n,p):
 sp=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(sp);sys.modules[n]=m;sp.loader.exec_module(m);return m
raw=subprocess.check_output(['git','-c','safe.directory='+str(repo),'-C',str(repo),'show','7e2855314de867e0481f8eb5ed1a07c48710f364:research/EKF4_RANGE_S_STAGED_20261014/core.py']);core=types.ModuleType('core');sys.modules['core']=core;exec(compile(raw,'canonical/core.py','exec'),core.__dict__)
import source_model
from qclean_uwb.drivesim import pattern_apply as PA
banks=[]
for pol in ['plus','minus']:
 with np.load(orig/f'LP_{pol}45_bank.npz') as z:banks.append(PA.Bank(dict(z)))
model=source_model.SourceFFD(banks=banks);online=load('s1_online_audit',base/'S1/online.py');recovery=load('s2_recovery_audit',base/'S2/recovery.py');spec=dict(anchor=(10.,0.,2.65),robot_z_m=.45,mount_deg=0.)
def pred(x,P,k,c):
 if not k:return x.copy(),P.copy()
 ds,gy,dt=[float(c[a][k]) for a in ['ds','gy','dt']];Q=np.diag([2e-5*abs(ds),np.deg2rad(.015)**2*dt,0.]);return core.predict(x,P,ds,gy,dt,Q)[:2]
def update(x,P,H,nu,R,yes):
 if not yes:return x.copy(),P.copy()
 K=P@H.T@np.linalg.inv(H@P@H.T+R);y=x+K@nu;y[2]=(y[2]+np.pi)%(2*np.pi)-np.pi;A=np.eye(4)-K@H;C=A@P@A.T+K@R@K.T;return y,(C+C.T)/2
maxdiff=0.;checked=0;packetchecks=0
for route in ['R4','R5']:
 for bias in ['B0','L2']:
  for channel in ['Full','Native_LoS']:
   key=f'{route}_aB_m0_{bias}_{channel}'
   with np.load(cache/(key+'.npz')) as z:pk=dict(z)
   with np.load(cache/f'{route}_aB_m0_{bias}_0.npz') as z:ct=dict(z)
   for arm,baseline in [('A','W0'),('B','W-d0-DS')]:
    target,_=recovery.replay(pk,ct,arm,core,model,spec,online,end=35)
    x=np.r_[ct['x0'],0.];P=pk['P0'].copy();sx=x.copy();SP=P.copy();xx=[];PP=[];masks=[]
    for k in range(35):
     sx,SP=pred(sx,SP,k,ct);sh,sH=model.batch(sx[None],spec);sh,sH=sh[0],sH[0];v=pk['z'][k]-sh-pk['muBASE'][k];R=pk['R'][k];S=sH@SP@sH.T+R;yes=bool(v@np.linalg.inv(S)@v<=9.210340371976184);sx,SP=update(sx,SP,sH,v,R,yes)
     rho=np.linalg.norm(x[:2]-np.array([10.,0.]));sig=np.interp(rho,[0,1.5,3,6,10],[.011,.020,.050,.120,.240]);xp,pr=pred(x,P,k,ct);h,H=model.batch(xp[None],spec);h,H=h[0],H[0];nu=pk['z'][k]-h-pk['muMB'][k];d=pk['z'][k,1]-h[1]
     wd=max(.25,min(1,.2/(abs(d)+1e-12))**2);wD=max(.25,min(1,.07138038868537433/(abs(pk['D'][k])+1e-12))**2);w=1 if arm=='A' else max(.25,wd*wD);R=R.copy();R[1,1]=(R[1,1]+sig**2)/w
     x,P=update(xp,pr,H,nu,R,yes);xx.append(x);PP.append(P);masks.append(yes)
    for name,expected in [('x',np.array(xx)),('P',np.array(PP))]:
     assert np.allclose(target[name],expected,atol=1e-10,rtol=1e-10);maxdiff=max(maxdiff,float(np.max(abs(target[name]-expected))))
    assert np.array_equal(target['mask'],masks)
    with np.load(base/'S1/runs/DEV_001'/f'{key}_0_{baseline}.npz') as old:
     for name in ['x','P','prior','Pprior','H','h','mu','Reff']:assert np.allclose(target[name],old[name][:35],atol=1e-10,rtol=1e-10)
     assert np.array_equal(target['mask'],old['mask'][:35])
    checked+=1;packetchecks+=35
   # Truth poison cannot affect target; future-suffix controls/observations cannot alter prefix.
   poisoned={k:v.copy() for k,v in pk.items()};poisoned['truth']=np.ones((len(pk['t']),4))*1e9;poisoned['z'][8:]+=10
   controls={k:v.copy() for k,v in ct.items()};controls['ds'][8:]+=1
   trial,_=recovery.replay(poisoned,controls,'B',core,model,spec,online,end=12)
   for name in ['x','P','mask','weight','sigma_b','information']:assert np.array_equal(trial[name][:8],target[name][:8])
print(json.dumps(dict(status='PASS',real_QA_arm_prefixes=checked,real_QA_independent_packet_checks=packetchecks,max_abs_state_or_P_difference=maxdiff,source_FFD_and_motion_model_shared=True,independent_gate_and_update_formula=True,all_eight_cells_S1_parity=True,truth_poison_future_suffix_tests=8,science_outcome_scores_generated=False)))
'@ | wsl -d Ubuntu-24.04 env PYTHONDONTWRITEBYTECODE=1 PYTHONHOME=/home/myoung-sun/.local/share/prr31117 LD_LIBRARY_PATH=/home/myoung-sun/.local/share/prr31117/lib OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /home/myoung-sun/.local/share/prr31117/bin/python3 -