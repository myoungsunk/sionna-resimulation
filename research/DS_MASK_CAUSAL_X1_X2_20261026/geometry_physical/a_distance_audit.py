from common import *
import geometry_model as GM
assert json.loads((ROOT/'A_GATE.json').read_text())['status']=='PASS'
_,model=models();rows=[]
def observed(H):
 cir=np.fft.ifft(H*model.window[None,:,None],n=4*model.nf,axis=1)*model.nf
 return GM.O.first_path_batch(cir,float(model.freqs[1]-model.freqs[0]))
for case in V.MANIFEST['cases']:
 for bias in ['B0','L2']:
  stem=f'{case["id"]}_{bias}';a=load(ROOT/'A'/f'{stem}.npz');z=load(E1/'E1'/f'{stem}.npz');ix,jx=np.unravel_index(np.argmax(abs(a['ds_r'])),a['ds_r'].shape);m=z['t_s']>=30;true=z['truth_scoring_only'][m][ix:ix+1];est=z['x'][m][ix:ix+1,jx];b,e,r=geometry(true,case);_,_,rh=geometry(est,case)
  model.explicit=None;H0,_,_,_,_,_=model.spectrum(true,case,gradient=False)
  model.explicit=(unitvec(b,e),rh);H1,_,_,_,_,_=model.spectrum(true,case,gradient=False);model.explicit=None
  amplitude=r/rh;phase=np.exp(-2j*np.pi*(model.freqs-model.freqs[0])[None,:]*(rh-r)[:,None]/GM.O.C0)
  equivalent_H=H0*amplitude[:,None,None]*phase[:,:,None]
  rel=float(np.linalg.norm(H1-equivalent_H)/np.linalg.norm(H1));assert rel<1e-10
  o0=observed(H0);o1=observed(H1);oa=observed(H0*amplitude[:,None,None]);op=observed(H0*phase[:,:,None])
  check('amplitude_cancels',oa['s'],o0['s'],1e-12);check('phase_explains_r',op['s'],o1['s'],1e-12)
  rows.append(dict(case=case['id'],bias=bias,alpha=float([0,.25,.5,.75,1][jx]),t_s=float(a['t_s'][ix]),true_r=float(r[0]),estimated_r=float(rh[0]),s_true=float(o0['s'][0]),s_range=float(o1['s'][0]),s_amplitude_only=float(oa['s'][0]),s_phase_only=float(op['s'][0]),tap_true=int(o0['index'][0]),tap_range=int(o1['index'][0]),spectrum_relative_residual=rel))
pd.DataFrame(rows).to_csv(ROOT/'A_DISTANCE_AUDIT.csv',index=False);write('A_DISTANCE_AUDIT_GATE.json',dict(status='PASS',conditions=14,selection='Maximum absolute delta_s_r sample per condition; explanatory examples, not a new aggregate test.'));print('Distance audit PASS')
