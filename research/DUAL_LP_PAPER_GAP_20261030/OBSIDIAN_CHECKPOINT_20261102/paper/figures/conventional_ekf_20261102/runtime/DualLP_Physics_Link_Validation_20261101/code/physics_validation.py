"""V1: locked channel→observer, source derivatives, scalar/port invariants.
No RT; never changes the filter's eligibility mask.
"""
from __future__ import annotations
import time
from bootstrap import *

def obs(h,model):
 from qclean_uwb.drivesim import observation as O
 cir=O.cir_batch(h);o=O.first_path_batch(cir,float(model.freqs[1]-model.freqs[0]));mag=np.abs(cir);branch=mag.max(1).argmax(1)
 strong=mag[np.arange(len(cir)),:,branch];threshold=.3*strong.max(1);i=o['index'];ix=np.arange(len(i))
 margin=np.minimum(strong[ix,i]-threshold,threshold-np.where(i>0,strong[ix,np.maximum(i-1,0)],0))/np.maximum(strong.max(1),np.finfo(float).tiny)
 return dict(**o,cir=cir,strong_port=branch,margin=margin)

def same_branch(a,b):
 return (a['tap']==b['tap'])&(a['strong_port']==b['strong_port'])&np.all(a['cells']==b['cells'],axis=1)

def main():
 start=time.time();model=C.base_model();rows=[];fds=[];inv=[];qa=[];branches=[];source_decomp=[]
 for case in CASES:
  D=read_data(case,'B0');ref=C.load_control(case,'B0');Hf,Hl,samples=C.load_rf(case);idx_by_id={int(s['pose_id']):i for i,s in enumerate(samples)}
  assert len(idx_by_id)==len(samples)
  idx=np.array([idx_by_id[int(i)] for i in D['pose_id']]);spec=D['spec'];gt=D['gt'];n=len(idx)
  sample_xyz=np.array([[samples[i]['x'],samples[i]['y']] for i in idx]); sample_yaw=np.radians([samples[i]['yaw_body_deg'] for i in idx])
  pose_xy_diff=float(np.max(abs(sample_xyz-gt[:,:2])));pose_yaw_diff=float(np.max(abs(wrap(sample_yaw-gt[:,2]))))
  assert pose_xy_diff<=5.0001e-7 and pose_yaw_diff<=math.radians(5.0001e-7)
  maxr=maxs=0.;native_diff=[];native_H_rel=[];n_inv=0;n_inv_fail=0;stable_count=0;fd_fails=0
  for st in range(0,n,64):
   en=min(n,st+64);m=en-st;x=gt[st:en].copy();x[:,3]=0
   pred,J,diag=model.batch(x,spec,return_diagnostics=True)
   sp,dsp,dist,dr,cells,rho=model.spectrum(x,spec,gradient=True)
   srcphys=sp*np.exp(-2j*np.pi*model.freqs[0]*dist/299792458.)[:,None,None]
   chans={'Full':np.asarray(Hf[idx[st:en],:,:,0]),'LoS':np.asarray(Hl[idx[st:en],:,:,0]),'SourceFFD':sp}
   obs_all={name:obs(h,model) for name,h in chans.items()}
   full,los,source=[obs_all[name] for name in ('Full','LoS','SourceFFD')]
   znew=np.c_[full['range_m'],full['s']];maxr=max(maxr,float(np.max(abs(znew[:,0]-D['z'][st:en,0]))));maxs=max(maxs,float(np.max(abs(znew[:,1]-D['z'][st:en,1]))))
   native_diff.extend(los['s']-pred[:,1]); native_H_rel.extend(np.linalg.norm((srcphys-chans['LoS']).reshape(m,-1),axis=1)/np.linalg.norm(chans['LoS'].reshape(m,-1),axis=1))
   # Both own-tap and common-full-tap differences, kept separate.
   los_at_full=np.abs(los['cir'][np.arange(m),full['index']])**2
   los_s_at_full=(los_at_full[:,0]-los_at_full[:,1])/los_at_full.sum(1)
   for j in range(m):
    k=st+j;eps=D['z'][k]-pred[j]-D['mu']['MB'][k]
    row=dict(case=case,pose_id=int(D['pose_id'][k]),t_s=float(D['t'][k]),x_truth_offline_m=float(x[j,0]),y_truth_offline_m=float(x[j,1]),yaw_truth_offline_rad=float(x[j,2]),rho_true_m=float(rho[j]),bearing_rad=float(math.atan2(x[j,1]-spec['anchor'][1],x[j,0]-spec['anchor'][0])),relative_yaw_rad=float(wrap(math.atan2(spec['anchor'][1]-x[j,1],spec['anchor'][0]-x[j,0])-x[j,2])),h_r=float(pred[j,0]),h_s=float(pred[j,1]),J_sx=float(J[j,1,0]),J_sy=float(J[j,1,1]),J_spsi_per_rad=float(J[j,1,2]),eps_r_MB=float(eps[0]),eps_s_MB=float(eps[1]),full_minus_los_own_tap_s=float(full['s'][j]-los['s'][j]),full_minus_los_full_common_tap_s=float(full['s'][j]-los_s_at_full[j]),los_minus_source_s=float(los['s'][j]-pred[j,1]),source_fp_margin=float(diag['fp_margin'][j]),equivalent_yaw_rad=float(eps[1]/J[j,1,2]) if abs(J[j,1,2])>=.05 else np.nan,role_of_truth='OFFLINE_DIAGNOSTIC_NOT_FILTER_INPUT')
    for name,o in obs_all.items():
     row.update({name+'_s':float(o['s'][j]),name+'_r_m':float(o['range_m'][j]),name+'_tap':int(o['index'][j]),name+'_port':int(o['strong_port'][j]),name+'_Pplus':float(o['power'][j,0]),name+'_Pminus':float(o['power'][j,1]),name+'_Ptotal':float(o['power'][j].sum()),name+'_fp_margin':float(o['margin'][j])})
    for q,c in enumerate(diag['cells'][j]):row['source_cell_'+str(q)]=int(c)
    rows.append(row)
   # Frequency-independent common complex multipliers and port swap.
   for name,h in chans.items():
    base=obs_all[name]
    for no,t in enumerate(CONFIG['common_scalar_tests']):
     cc=t['amplitude']*np.exp(1j*t['phase_rad']);new=obs(cc*h,model)
     errs=abs(new['s']-base['s']);passmask=(errs<=1e-12)&(new['index']==base['index'])&(new['strong_port']==base['strong_port'])
     for j in range(m):inv.append(dict(case=case,pose_id=int(D['pose_id'][st+j]),channel=name,test='scalar_'+str(no),s_abs_error=float(errs[j]),tap_equal=bool(new['index'][j]==base['index'][j]),pass_test=bool(passmask[j])))
    new=obs(h[:,:,::-1],model);errs=abs(new['s']+base['s']);passmask=(errs<=1e-12)&(new['index']==base['index'])&(new['strong_port']==1-base['strong_port'])
    for j in range(m):inv.append(dict(case=case,pose_id=int(D['pose_id'][st+j]),channel=name,test='port_swap',s_abs_error=float(errs[j]),tap_equal=bool(new['index'][j]==base['index'][j]),pass_test=bool(passmask[j])))
   # Analytic derivative vs central FD and half-step, classify active branch first.
   for u,step in enumerate([1e-4,1e-4,1e-5]):
    pp=[];di=[]
    for delta in (step,-step,step/2,-step/2):
     xx=x.copy();xx[:,u]+=delta
     h,_,d=model.batch(xx,spec,gradient=False,return_diagnostics=True);pp.append(h);di.append(d)
    fd=(pp[0]-pp[1])/(2*step);fd2=(pp[2]-pp[3])/step
    stable=np.logical_and.reduce([same_branch(diag,d) for d in di])
    atol=CONFIG['fd_steps']['stable_branch_atol'];rtol=CONFIG['fd_steps']['stable_branch_rtol']
    ok=(abs(fd-J[:,:,u])<=atol+rtol*abs(J[:,:,u])).all(1)&(abs(fd2-J[:,:,u])<=atol+rtol*abs(J[:,:,u])).all(1)&(abs(fd-fd2)<=atol+rtol*abs(fd2)).all(1)
    stable_count+=int(stable.sum());fd_fails+=int((stable&~ok).sum())
    for j in range(m):
     r=dict(case=case,pose_id=int(D['pose_id'][st+j]),t_s=float(D['t'][st+j]),axis=('x','y','psi')[u],step=step,stable_branch=bool(stable[j]),J_r=float(J[j,0,u]),fd_r=float(fd[j,0]),half_fd_r=float(fd2[j,0]),J_s=float(J[j,1,u]),fd_s=float(fd[j,1]),half_fd_s=float(fd2[j,1]),abs_s_error=float(abs(fd[j,1]-J[j,1,u])),numeric_pass=bool(ok[j]),status='PASS' if stable[j] and ok[j] else 'FAIL_STABLE_FD' if stable[j] else 'BRANCH_TRANSITION_NOT_FILTER_EXCLUDED')
     fds.append(r)
     if not stable[j]:branches.append(r)
  qa.append(dict(case=case,n=n,pose_xy_metadata_error_m=pose_xy_diff,pose_yaw_metadata_error_rad=pose_yaw_diff,full_to_CONTROL_range_max_m=maxr,full_to_CONTROL_s_max=maxs,raw_observer_pass=maxr<=1e-9 and maxs<=1e-12,stable_derivatives=stable_count,stable_derivative_failures=fd_fails,native_los_source_s_rmse=float(np.sqrt(np.mean(np.array(native_diff)**2))),native_los_source_s_max=float(np.max(abs(np.array(native_diff)))),physical_spectrum_relative_l2_max=float(np.max(native_H_rel))))
  print('PHYSICS',qa[-1],flush=True)
 pd.DataFrame(rows).to_csv(RESULTS/'PHYSICS_PACKET_LEDGER.csv.gz',index=False,float_format='%.17g')
 pd.DataFrame(fds).to_csv(TABLES/'FFD_FD_CHECKS.csv',index=False,float_format='%.17g')
 pd.DataFrame(branches).to_csv(TABLES/'BRANCH_TRANSITION_LEDGER.csv',index=False,float_format='%.17g')
 inv=pd.DataFrame(inv);inv.to_csv(TABLES/'SCALAR_PORT_INVARIANTS.csv.gz',index=False,float_format='%.17g')
 result=dict(cases=qa,unique_RF_rows=len(rows),derivative_total=len(fds),stable_derivatives=sum(x['stable_derivatives'] for x in qa),transition_derivatives=len(branches),stable_derivative_failures=sum(x['stable_derivative_failures'] for x in qa),invariance_tests=len(inv),invariance_failures=int((~inv.pass_test).sum()),source_mean_native_los_not_assumed_exact=True,all_raw_observers_pass=all(x['raw_observer_pass'] for x in qa),seconds=time.time()-start,audit='SELF_REVIEW_ONLY')
 write_json(RESULTS/'PHYSICS_QA.json',result);print('PHYSICS_QA',result,flush=True)
 assert result['all_raw_observers_pass'] and result['stable_derivative_failures']==0 and result['invariance_failures']==0
if __name__=='__main__':main()
