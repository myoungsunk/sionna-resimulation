from pathlib import Path
import json,numpy as np
J=Path('/job');C=J/'BLOCK_C';f=np.load(C/'freqs_hz.npy');rows=[]
for case in json.loads((J/'PLAN.json').read_text())['RF']['cases']:
 z=np.load(C/case/'PATHS_LoS.npz');a=z['a'].astype(np.complex64);t=z['tau'].astype(np.float32);h=np.load(C/('H_LoS_'+case+'.npy'),mmap_mode='r');exact=0.;double=0.
 for fi,v in enumerate(f):
  rec=(a[:,fi,:,:,None]*np.exp(-2j*np.pi*v*t[:,fi,None])[:,None,None,:]).sum(-1)
  exact=max(exact,float(np.max(abs(rec-h[:,fi]))))
  mathematical=z['a'][:,fi]*np.exp(-2j*np.pi*v*z['tau'][:,fi])[:,None,None]
  double=max(double,float(np.max(abs(mathematical-h[:,fi]))))
 rows.append({'case':case,'max_exact_native_precision_reconstruction_difference':exact,'max_float64_reconstruction_difference':double,'passed_native_numeric_check':exact<1e-12})
 print(case,exact,double,flush=True)
out={'numpy':np.__version__,'method':'independent reconstruction; coefficients complex64 and delays float32 as returned by native paths; original scalar-frequency operation order and pinned NumPy retained','rows':rows,'all_passed':all(x['passed_native_numeric_check'] for x in rows),'scope':'arithmetic validation only; no new solver calls; float64 diagnostic is not used to alter stored H'}
(J/'NATIVE_NUMERIC_VERIFICATION.json').write_text(json.dumps(out,indent=2));assert out['all_passed'],out
