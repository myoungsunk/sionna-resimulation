from common import *
from frozen_cut import cut_predict
PRIMARY=['R2_aA_m45','R4_aA_m0','R4_aB_m0'];rows=[];packets=[];align=[];locked=[]
def verified(root,sub,c,b):
 p=root/sub/f'{c}_{b}.npz';m=json.loads((root/'OUTPUT_SHA256.json').read_text());lookup={x['path']:x['sha256'] for x in m['files']};assert S.sha(p)==lookup[p.relative_to(root).as_posix()];locked.append(dict(path=str(p),sha256=S.sha(p)));return load(p)
for case in V.MANIFEST['cases']:
 if case['id'] not in PRIMARY:continue
 cid=case['id']
 for bias in ['B0','L2']:
  z=verified(E1,'E1',cid,bias);o=verified(ROOT.parent/'DS_CUT_ODO_20261027','CUT_ODO',cid,bias)
  t=z['t_s'];truth=z['truth_scoring_only'];a=np.array(case['anchor'])[:2];rad=truth[:,:2]-a;ur=rad/np.linalg.norm(rad,axis=1)[:,None];ut=np.c_[-ur[:,1],ur[:,0]];m=t>=30
  check('odo_ids',o['pose_id'],z['pose_id'],0);check('odo_times',o['t_s'],t,0);check('odo_truth',o['truth_scoring_only'],truth,0)
  contributions=[]
  for j in [0,4]:
   err=z['x'][:,j,:2]-truth[:,:2];u=z['K'][:,j,:2,:]*z['nu'][:,j,None,:]*z['acc'][:,j,None,None]
   check('actual_update',u.sum(axis=2),z['x'][:,j,:2]-z['prior'][:,j,:2])
   prop=np.zeros_like(err);prop[1:]=z['prior'][1:,j,:2]-z['x'][:-1,j,:2]-np.diff(truth[:,:2],axis=0)
   r=u[:,:,0].copy();s=u[:,:,1].copy();r[0]=0;s[0]=0
   rr=ur*np.einsum('ni,ni->n',ur,r)[:,None];rt=ut*np.einsum('ni,ni->n',ut,r)[:,None];check('range_split',rr+rt,r)
   worlds={'initial':np.broadcast_to(err[0],err.shape),'prop':np.cumsum(prop,axis=0),'range_radial':np.cumsum(rr,axis=0),'range_tangent':np.cumsum(rt,axis=0),'pol':np.cumsum(s,axis=0)}
   check('world_reconstruction',sum(worlds.values()),err)
   projected={k:np.einsum('ni,ni->n',ut,v)*100 for k,v in worlds.items()};check('tangent_reconstruction_cm',sum(projected.values()),np.einsum('ni,ni->n',ut,err)*100)
   contributions.append(projected)
  dif={k:contributions[1][k]-contributions[0][k] for k in contributions[0]};gap=np.einsum('ni,ni->n',ut,z['x'][:,4,:2]-z['x'][:,0,:2])*100;check('gap_cm',sum(dif.values()),gap)
  row=dict(case=cid,bias=bias,gap_cm=float(gap[m].mean()),**{k+'_cm':float(v[m].mean()) for k,v in dif.items()});row['range_total_cm']=row['range_radial_cm']+row['range_tangent_cm'];rows.append(row)
  for k in range(len(t)):packets.append(dict(case=cid,bias=bias,pose_id=int(z['pose_id'][k]),t_s=t[k],scoring=bool(m[k]),gap_cm=gap[k],**{n+'_cm':v[k] for n,v in dif.items()}))
  controls,x0=V.build_positive_bias_controls(t,truth[:,:3],bias)
  # Independent audit keyed by recorded current/previous packet, not proxy counter.
  for k in range(1,len(t)):
   for j in range(2):
    yy,pp,*_=cut_predict(o['x'][k-1,j],o['P'][k-1,j],float(controls['ds_odom'][k]),float(controls['dtheta_gyro'][k]),float(controls['dt_s'][k]),float(truth[k-1,2]))
    dx=float(abs(yy-o['prior'][k,j]).max());dp=float(abs(pp-o['Pprior'][k,j]).max());assert dx<=1e-10 and dp<=1e-10,(cid,bias,k,j,dx,dp)
    align.append(dict(case=cid,bias=bias,arm=str(o['names'][j]),current_pose_id=int(o['pose_id'][k]),previous_posterior_pose_id=int(o['pose_id'][k-1]),GT_source_pose_id=int(z['pose_id'][k-1]),current_time=t[k],GT_source_time=t[k-1],GT_psi_rad=truth[k-1,2],prior_max_abs=dx,Pprior_max_abs=dp))
  S.event('CASE_PASS',case=cid,bias=bias)
pd.DataFrame(rows).to_csv(ROOT/'WORLD_SUMMARY.csv',index=False);pd.DataFrame(packets).to_csv(ROOT/'WORLD_PACKETS.csv',index=False);pd.DataFrame(align).to_csv(ROOT/'ODO_ALIGNMENT.csv',index=False)
write('CHECKS.json',S.checks);write('ALIGNMENT_GATE.json',dict(status='PASS',calls=len(align),prior_max_abs=max(x['prior_max_abs'] for x in align),Pprior_max_abs=max(x['Pprior_max_abs'] for x in align),meaning='Saved prior/Pprior reconstructed independently from previous packet GT heading; not an original runtime call log.'))
write('INPUT_LOCK.json',dict(files=locked));print(pd.DataFrame(rows).to_string(index=False));print('alignment',len(align))
