from common import *
from decompose import arrays,metric_rows
assert json.loads((ROOT/'B_GATE.json').read_text())['status']=='PASS'
metrics=pd.read_csv(ROOT/'B_DECOMPOSITION.csv');old=pd.read_csv(PREVIOUS/'A_METRICS.csv');old=old[list(metrics.columns)].copy();old['arm']=['FULL_'+str(a) for a in old.alpha]
unified=pd.concat([metrics[~metrics.arm.str.startswith('FULL')],old],ignore_index=True)
assert len(unified)==210 and not unified.duplicated(['case','bias','arm','alpha']).any()
unified.to_csv(ROOT/'B_ALL_ARMS_DECOMPOSITION.csv',index=False);rows=[]
for case in V.MANIFEST['cases']:
 for bias in ['B0','L2']:
  stem=f'{case["id"]}_{bias}';ref=load(E1/'E1'/f'{stem}.npz');m=ref['t_s']>=30;truth=ref['truth_scoring_only'][m];vec=truth[:,:2]-np.array(case['anchor'])[:2];ur=vec/np.linalg.norm(vec,axis=1)[:,None];ut=np.column_stack([-ur[:,1],ur[:,0]])
  baseline=ref['x'][m,0,:2];g=unified[(unified.case==case['id'])&(unified.bias==bias)];bb=g[(g.arm.str.startswith('FULL'))&(g.alpha==0)].iloc[0]
  fullchange={a:float(g[(g.arm.str.startswith('FULL'))&(g.alpha==a)].iloc[0].et_bias-bb.et_bias) for a in [0,.25,.5,.75,1]}
  for mode in ['CONST','VAR','FULL']:
   trace=ref if mode=='FULL' else load(ROOT/('B_'+mode)/f'{stem}.npz')
   for j,alpha in enumerate([0,.25,.5,.75,1]):
    row=g[(g.arm.str.startswith(mode))&(g.alpha==alpha)].iloc[0];delta=trace['x'][m,j,:2]-baseline
    tang=float(np.mean(np.einsum('ni,ni->n',delta,ut))*100);rad=float(np.mean(np.einsum('ni,ni->n',delta,ur))*100)
    check('tangent_direct_projection',tang,float(row.et_bias-bb.et_bias),1e-10);check('radial_direct_projection',rad,float(row.er_bias-bb.er_bias),1e-10)
    denom=fullchange[alpha]
    rows.append(dict(case=case['id'],bias=bias,arm=mode,alpha=alpha,delta_tangential_cm=tang,delta_radial_cm=rad,delta_beta_deg=float(row.beta_bias-bb.beta_bias),delta_phi_deg=float(row.phi_bias-bb.phi_bias),delta_heading_deg=float(row.psi_bias-bb.psi_bias),FULL_tangential_cm=denom,tangential_fraction=tang/denom if abs(denom)>=1e-6 else None))
pd.DataFrame(rows).to_csv(ROOT/'B_POSITION_MOVEMENT.csv',index=False);write('B_MOVEMENT_CHECKS.json',S.checks);write('B_ANALYSIS_GATE.json',dict(status='PASS',rows=210,definition='GT-axis mean signed displacement from E1 BB; direct projection verified.'));print('B movement analysis PASS')
