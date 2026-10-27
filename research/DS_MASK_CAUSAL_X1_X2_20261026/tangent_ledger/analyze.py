from pathlib import Path
import numpy as np,pandas as pd,json,hashlib
P=Path(__file__).resolve().parent;D=P.parent
E=D/'DS_NONLINEAR_E1_E4_20261027_01a1775b';C=D/'DS_GEOMETRY_PHYSICAL_20261027';T=D/'DS_COMPONENT_AZIMUTH_20261027'
manifest=D/'OFFICE_CORRIDOR_TRANSFER_FIX_20261026/execution_33e9849/p2/research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json'
cases={x['id']:x for x in json.loads(manifest.read_text())['cases']};primary=['R2_aA_m45','R4_aA_m0','R4_aB_m0'];inputs={};checks=[]
def check(name,a,b,tol=1e-10):
 err=float(np.max(np.abs(np.asarray(a)-b)));checks.append(dict(name=name,max_abs=err,tolerance=tol));assert err<=tol,(name,err)
def load(root,folder,c,b):
 p=root/folder/f'{c}_{b}.npz';h=hashlib.sha256(p.read_bytes()).hexdigest();m=json.loads((root/'OUTPUT_SHA256.json').read_text(encoding='utf-8-sig'));expected={x['path']:x['sha256'] for x in m['files']};assert h==expected[p.relative_to(root).as_posix()];inputs[str(p)]=h
 with np.load(p) as z:return {k:z[k] for k in z.files}
def wrap(x):return 180-(180-x)%360
def geom(z,c,field='x'):
 truth=z['truth_scoring_only'];x=z[field];a=np.array(cases[c]['anchor'])[:2];rad=truth[:,:2]-a;ur=rad/np.linalg.norm(rad,axis=1)[:,None];ut=np.c_[-ur[:,1],ur[:,0]];err=x[:,:,:2]-truth[:,None,:2]
 et=np.einsum('nji,ni->nj',err,ut);er=np.einsum('nji,ni->nj',err,ur);v=a-x[:,:,:2];v0=a-truth[:,:2];beta=wrap(np.degrees(np.arctan2(v[:,:,1],v[:,:,0])-np.arctan2(v0[:,1],v0[:,0])[:,None]));psi=wrap(np.degrees(x[:,:,2]-truth[:,None,2]));return et,er,beta,psi,ut,err
stats=[];gaps=[];ledger=[];summ=[]
for c in primary:
 for bias in ['B0','L2']:
  sources={'E1':load(E,'E1',c,bias),'C':load(C,'C',c,bias),'TRANSFER':load(T,'TRANSFER',c,bias)}
  ref=sources['E1'];m=ref['t_s']>=30
  for source,z in sources.items():
   check(c+bias+source+'time',z['t_s'],ref['t_s'],0);check(c+bias+source+'ids',z['pose_id'],ref['pose_id'],0)
   for field in ['x','prior']:
    et,er,be,ps,ut,err=geom(z,c,field)
    for j,name in enumerate(z['names']):
     stats.append(dict(case=c,bias=bias,source=source,state=field,arm=str(name),et_bias_cm=100*et[m,j].mean(),er_bias_cm=100*er[m,j].mean(),beta_bias_deg=be[m,j].mean(),heading_bias_deg=ps[m,j].mean()))
  for field in ['x','prior']:
   def stat(source,arm):return next(x for x in stats if x['case']==c and x['bias']==bias and x['source']==source and x['state']==field and x['arm']==arm)
   pairs=[('E1','E1','A0','A1'),('CUT_AZ','C','CUT_AZ_0','CUT_AZ_1'),('CUT_ALL','C','CUT_ALL_0','CUT_ALL_1'),('DONOR_BB','TRANSFER','R0_AZ_BB','R1_AZ_BB'),('DONOR_MB','TRANSFER','R0_AZ_MB','R1_AZ_MB'),('SELF_DONOR_DIAGONAL','TRANSFER','R0_AZ_BB','R1_AZ_MB')]
   base0=stat('E1','A0');base1=stat('E1','A1')
   for label,source,a0,a1 in pairs:
    q0,q1=stat(source,a0),stat(source,a1);row=dict(case=c,bias=bias,state=field,comparison=label)
    for key in ['et_bias_cm','er_bias_cm','beta_bias_deg','heading_bias_deg']:
     g=q1[key]-q0[key];g0=base1[key]-base0[key];row['delta_'+key]=g;row['f_magnitude_'+key]=1-abs(g)/abs(g0) if abs(g0)>=(.01 if 'deg' in key else 1e-10) else np.nan;row['sign_flip_'+key]=bool(g*g0<0)
    gaps.append(row)
  z=ref;et,er,be,ps,ut,err=geom(z,c);truth=z['truth_scoring_only'];K=z['K'][:,:,:2,:];nu=z['nu'];updates=K*nu[:,:,None,:]*z['acc'][:,:,None,None]
  check(c+bias+'actual_update',updates.sum(axis=-1),z['x'][:,:,:2]-z['prior'][:,:,:2])
  terms={}
  for j in [0,4]:
   prop=z['prior'][1:,j,:2]-z['x'][:-1,j,:2]-np.diff(truth[:,:2],axis=0)
   terms[j]=np.column_stack([np.einsum('ni,ni->n',ut[1:],prop),np.einsum('ni,ni->n',ut[1:],updates[1:,j,:,0]),np.einsum('ni,ni->n',ut[1:],updates[1:,j,:,1]),np.einsum('ni,ni->n',np.diff(ut,axis=0),err[:-1,j])])
   check(c+bias+str(j)+'local_three',terms[j][:,:3].sum(axis=1),np.einsum('ni,ni->n',ut[1:],np.diff(err[:,j],axis=0)))
   check(c+bias+str(j)+'rotating_four',terms[j].sum(axis=1),np.diff(et[:,j]))
  diff=terms[4]-terms[0];names=['propagation','range','polarization','basis_rotation'];cum=np.cumsum(diff,axis=0);gap=et[:,4]-et[:,0]
  check(c+bias+'cumulative',gap[0]+cum.sum(axis=1),gap[1:])
  # Full-history cumulative mean exactly reconstructs the t>=30 mean gap, including initial condition.
  fullcum=np.vstack([np.zeros((1,4)),cum]);contrib=fullcum[m].mean(axis=0)*100
  check(c+bias+'mean_gap',100*gap[0]+contrib.sum(),100*gap[m].mean())
  summ.append(dict(case=c,bias=bias,initial_gap_cm=100*gap[0],mean_et_gap_cm=100*gap[m].mean(),**{n+'_mean_cumulative_cm':v for n,v in zip(names,contrib)},**{n+'_final_cumulative_cm':v for n,v in zip(names,cum[-1]*100)}))
  for k in range(1,len(gap)):
   ledger.append(dict(case=c,bias=bias,k=k,t_s=z['t_s'][k],pose_id=int(z['pose_id'][k]),scoring=bool(m[k]),et_gap_cm=gap[k]*100,**{n+'_delta_cm':v for n,v in zip(names,diff[k-1]*100)},**{n+'_cumulative_cm':v for n,v in zip(names,cum[k-1]*100)}))
for name,data in [('STEP0_STATS',stats),('STEP0_GAPS',gaps),('STEP1_LEDGER',ledger),('STEP1_SUMMARY',summ)]:pd.DataFrame(data).to_csv(P/(name+'.csv'),index=False)
(P/'CHECKS.json').write_text(json.dumps(dict(status='PASS',checks=checks),indent=2))
(P/'INPUT_LOCK.json').write_text(json.dumps(dict(files=inputs,manifest=str(manifest),manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest()),indent=2))
print(pd.DataFrame(gaps).query("state=='x' and comparison in ['E1','CUT_AZ','CUT_ALL']")[['case','bias','comparison','delta_et_bias_cm','delta_beta_bias_deg','f_magnitude_beta_bias_deg']].to_string(index=False))
print(pd.DataFrame(summ).to_string(index=False));print('CHECKS PASS',len(checks))
