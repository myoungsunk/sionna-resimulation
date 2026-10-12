import sys,json,hashlib,importlib.util,itertools
import numpy as np
from pathlib import Path
S=Path('/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad');R=S/'rfroot'
sys.path.insert(0,str(R/'src'))
M=json.load(open(S/'matrix.json'));DL=S/'deliv/research/V01B_DATA_REQUEST_20261011/DELIVERY_A_20261012'
FQ=np.load('/home/user/sionna-resimulation/results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/freqs_hz.npy')
FR=Path('/home/user/sionna-resimulation/results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C')
print('== G2: rf_poses SHA per route vs matrix (R2/R5 read from branch files, R4 already matched)')
import subprocess
for r in ('R2','R4','R5'):
    raw=subprocess.check_output(['git','-C','/home/user/sionna-resimulation','show',f'origin/codex/abc-gated-resume-20261011:results/DRIVE_SIM_20261007/S1/routes/rf_poses_{r}.json'])
    exp={c['rf_pose_sha256'] for c in M if c['case'].startswith(r)};print(r,hashlib.sha256(raw).hexdigest()==list(exp)[0],len(exp),'sha value(s) in matrix')
print('\n== G4: observer parity on the 5 NEW H (frozen Sensor-v2 observer vs current native observer, same input, noise off/30/10 dB)')
def load(n,p):
    sp=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(sp);sys.modules[n]=m;sp.loader.exec_module(m);return m
old=load('obs_old',str(S/'obs_frozen.py'));new=load('obs_new',str(S/'abc_src/src/qclean_uwb/drivesim/observation.py'))
worst=0.;tapok=True;n=0
for c in ('R2_aB_m45','R4_aA_m45','R4_aB_m45','R5_aA_m45','R5_aB_m45'):
    H=np.load(DL/f'H_{c}.npy',mmap_mode='r');H=np.asarray(H[np.unique(np.linspace(0,len(H)-1,96).astype(int))])
    for snr in (None,30.,10.):
        nv=None if snr is None else old.noise_var_from_snr(snr)
        a=old.observe(H,FQ,nv,np.random.default_rng(7),return_h=True);b=new.observe(H,FQ,nv,np.random.default_rng(7),return_h=True)
        det=np.asarray(a['detected'])
        worst=max(worst,float(np.nanmax(abs(a['s'][det]-b['s'][det]))) if det.any() else 0.);tapok&=bool(np.array_equal(a['index'],b['index']) and np.array_equal(a['detected'],b['detected']));n+=1
print('conditions',n,'| max |Δs| between observers %.1e | FP tap + detection identical:'%worst,tapok)
