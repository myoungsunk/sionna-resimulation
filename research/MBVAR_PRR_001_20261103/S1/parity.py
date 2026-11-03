import hashlib,json,os,sys
from pathlib import Path
import numpy as np
s=Path(__file__).resolve().parent;sys.path.insert(0,str(s.parent/'A0_R3_REFIT'))
import check_base as b
import online
cache=b.cache/'S1_INPUTS'/'algorithm_input'
lock=json.loads((s/'MATERIALIZED_INPUTS.json').read_text())
spec=dict(anchor=(10.,0.,2.65),robot_z_m=.45,mount_deg=0.)
def read(key):
 p=cache/(key+'.npz');assert b.sha(p)==lock['algorithm_input/'+p.name]
 with np.load(p) as z:return dict(z)
def smoke():
 report={}
 for route in ('R4','R5'):
  for bias in ('B0','L2'):
   for ch in ('Full','Native_LoS'):
    key=f'{route}_aB_m0_{bias}_{ch}';pk=read(key);ct=read(f'{route}_aB_m0_{bias}_0')
    ref=np.load(s.parent/'A0_R3_REFIT/F64_REFERENCE'/(key+'.npz'))
    tr=online.replay(pk,ct,'W0',b.core,b.model,spec)
    pairs={'x':'x','P':'P','prior':'prior','Pprior':'Pprior','H':'H','h':'h','mu':'mu','Reff':'R'}
    delta={k:float(np.max(abs(tr[k]-ref[v]))) for k,v in pairs.items()}
    ok=np.array_equal(tr['mask'],ref['mask']) and all(np.allclose(tr[k],ref[v],atol=1e-10,rtol=1e-10) for k,v in pairs.items())
    report[key]=dict(passed=ok,delta=delta,mask_diff=int(np.count_nonzero(tr['mask']!=ref['mask'])))
    (s/'SELF_PARITY.json').write_text(json.dumps(report,indent=2))
    if not ok:raise RuntimeError(key)
if __name__=='__main__':smoke()
