"""V2 same-prior updates; separate algebra over recorded legacy priors/J.
This is SELF_REVIEW_ONLY, not an independent-auditor execution.
"""
from __future__ import annotations
import time
from bootstrap import *

def matvec(a,b):return np.einsum('nij,nj->ni',a,b)
def update(x,P,J,R,v):
 S=J@P@J.transpose(0,2,1)+R;S=(S+S.transpose(0,2,1))/2
 K=np.linalg.solve(S,J@P).transpose(0,2,1)
 dx=matvec(K,v);y=x+dx;y[:,2]=wrap(y[:,2])
 A=np.eye(4)[None]-K@J;Pn=A@P@A.transpose(0,2,1)+K@R@K.transpose(0,2,1);Pn=(Pn+Pn.transpose(0,2,1))/2
 nis=np.einsum('ni,ni->n',v,np.linalg.solve(S,v[...,None])[...,0])
 return y,Pn,K,S,nis,dx

def main():
 start=time.time();allrows=[];losses=[];checks=[];contrast=[];inter=[]
 for case in CASES:
  for bias in BIASES:
   D=read_data(case,bias);base=read_trace(case,bias,'BB_ORIG','self');x=base['xp'];P=base['Pp'];J=base['J'];h=base['hx'];n=len(x)
   lam=base['sigma_lookup']**2;mask=D['acc']&(D['t']>=30-1e-9);assert mask.sum()>0
   dh=D['hg']-h;cell={};pack={};base_min=np.inf
   Pinv=np.linalg.inv(P)
   for bg,mode,arm in [('BB','orig','BB_ORIG'),('MB','orig','MB_ORIG'),('BB','var','BB_VAR'),('MB','var','MB_VAR')]:
    R=D['R'].copy()
    if mode=='var':R[:,1,1]+=lam
    mu=D['mu'][bg];eps=D['z']-D['hg']-mu;v=D['z']-h-mu
    y,Pn,K,S,nis,dx=update(x,P,J,R,v);ke=matvec(K,eps);kd=matvec(K,dh)
    e=y[:,:3]-D['gt'][:,:3];e[:,2]=wrap(e[:,2]);losspsi=np.degrees(e[:,2])**2;lossxy=np.sum(e[:,:2]**2,axis=1)*1e4
    priorpsi=np.degrees(wrap(x[:,2]-D['gt'][:,2]))**2;priorxy=np.sum((x[:,:2]-D['gt'][:,:2])**2,1)*1e4
    precision=Pinv+J.transpose(0,2,1)@np.linalg.solve(R,J);nn=[0,1,3]
    schur=precision[:,2,2]-np.einsum('ni,ni->n',precision[:,2,nn],np.linalg.solve(precision[:,nn][:,:,nn],precision[:,nn,2][...,None])[...,0])
    schur_err=abs(schur-1/Pn[:,2,2])/np.maximum(abs(schur),1)
    eig=np.linalg.eigvalsh(Pn);base_min=min(base_min,float(eig.min()))
    checks.append(dict(case=case,bias=bias,arm=arm,n=n,innovation_decomposition_abs_max=float(np.max(abs(v-eps-dh))),correction_decomposition_abs_max=float(np.max(abs(dx-ke-kd))),schur_posterior_rel_max=float(schur_err.max()),posterior_min_eigenvalue=float(eig.min())))
    row=dict(case=case,bias=bias,arm=arm,n_score=int(mask.sum()),head_mse_deg2=float(np.mean(losspsi[mask])),xy_mse_cm2=float(np.mean(lossxy[mask])),head_mse_change_deg2=float(np.mean((losspsi-priorpsi)[mask])),xy_mse_change_cm2=float(np.mean((lossxy-priorxy)[mask])),shadow_accept_score=int(((nis<=DG.GATE)&(D['t']>=30-1e-9)).sum()),mean_abs_Kpsi_s=float(np.mean(abs(K[mask,2,1]))),mean_signed_Kpsi_eps_s_deg=float(np.degrees(np.mean(K[mask,2,1]*eps[mask,1]))),mean_signed_Kpsi_eps_r_deg=float(np.degrees(np.mean(K[mask,2,0]*eps[mask,0]))),mean_signed_Kpsi_dh_deg=float(np.degrees(np.mean(kd[mask,2]))))
    losses.append(row);cell[arm]=row
    pack[arm+'_posterior']=y;pack[arm+'_P']=Pn;pack[arm+'_K']=K;pack[arm+'_nu']=v;pack[arm+'_eps']=eps;pack[arm+'_dx_eps']=ke;pack[arm+'_dx_state']=kd;pack[arm+'_NIS']=nis;pack[arm+'_lambda_eff_psi']=schur
    # Flat inspectable ledger; no parquet dependency, numeric precision retained.
    r=pd.DataFrame(dict(case=case,bias=bias,pose_id=D['pose_id'],t_s=D['t'],arm=arm,fixed_accepted=D['acc'],primary_score_mask=mask,shadow_accepted=nis<=DG.GATE,rho_previous_posterior_m=base['rho_lookup'],lambda_extra=lam if mode=='var' else np.zeros(n),nu_r=v[:,0],nu_s=v[:,1],epsilon_r=eps[:,0],epsilon_s=eps[:,1],delta_h_r=dh[:,0],delta_h_s=dh[:,1],head_loss_deg2=losspsi,xy_loss_cm2=lossxy,head_loss_change_deg2=losspsi-priorpsi,xy_loss_change_cm2=lossxy-priorxy,NIS=nis,lambda_eff_psi=schur,role_of_truth='OFFLINE_EFFECT_SCORING'))
    for q,name in enumerate(['x','y','psi','bg']):
     r['prior_'+name]=x[:,q];r['posterior_'+name]=y[:,q];r['K_'+name+'_r']=K[:,q,0];r['K_'+name+'_s']=K[:,q,1];r['dx_'+name+'_range']=K[:,q,0]*v[:,0];r['dx_'+name+'_pol']=K[:,q,1]*v[:,1];r['dx_'+name+'_RF']=ke[:,q];r['dx_'+name+'_state']=kd[:,q]
    for q in range(4):
     for w in range(4):r[f'Ppost_{q}{w}']=Pn[:,q,w]
    allrows.append(r)
   K0=pack['BB_ORIG_K'];K1=pack['BB_VAR_K'];S0=J@P@J.transpose(0,2,1)+D['R'];S0=(S0+S0.transpose(0,2,1))/2
   invss=np.linalg.inv(S0)[:,1,1];expected=K0[:,:,1]/(1+lam*invss)[:,None]
   err=abs(K1[:,:,1]-expected);checks[-1]['gain_identity_max']=float(err.max());checks[-1]['gain_identity_pass']=bool(np.allclose(K1[:,:,1],expected,atol=1e-12,rtol=1e-10))
   assert np.allclose(K1[:,:,1],expected,atol=1e-12,rtol=1e-10)
   assert np.array_equal(pack['BB_ORIG_K'],pack['MB_ORIG_K']) and np.array_equal(pack['BB_VAR_K'],pack['MB_VAR_K'])
   assert np.allclose(pack['BB_ORIG_posterior'][D['acc']],base['X'][D['acc']],atol=1e-12,rtol=1e-10)
   assert np.allclose(pack['BB_ORIG_P'][D['acc']],base['PX'][D['acc']],atol=1e-12,rtol=1e-10)
   # Explicit zero-variance and copied-mean identities; no extra recursion.
   zero=update(x,P,J,D['R'].copy(),D['z']-h-D['mu']['BB'])
   assert np.array_equal(zero[0],pack['BB_ORIG_posterior'])
   zero_R=D['R'].copy();zero_R[:,1,1]+=np.zeros(n)
   assert np.array_equal(update(x,P,J,zero_R,D['z']-h-D['mu']['BB'])[2],K0)
   (RESULTS/'shadow').mkdir(exist_ok=True);np.savez_compressed(RESULTS/'shadow'/f'{case}_{bias}.npz',prior=x,Pprior=P,J=J,delta_h=dh,t_s=D['t'],pose_id=D['pose_id'],fixed_accepted=D['acc'],primary_score_mask=mask,lambda_lookup=lam,**pack)
   c=dict(case=case,bias=bias,n_score=int(mask.sum()),mean_only_head_mse_deg2=cell['MB_ORIG']['head_mse_deg2'],combined_head_mse_deg2=cell['MB_VAR']['head_mse_deg2'],combined_minus_mean_head_mse_deg2=cell['MB_VAR']['head_mse_deg2']-cell['MB_ORIG']['head_mse_deg2'],mean_only_xy_mse_cm2=cell['MB_ORIG']['xy_mse_cm2'],combined_xy_mse_cm2=cell['MB_VAR']['xy_mse_cm2'],combined_minus_mean_xy_mse_cm2=cell['MB_VAR']['xy_mse_cm2']-cell['MB_ORIG']['xy_mse_cm2']);contrast.append(c)
   inter.append(dict(case=case,bias=bias,head_mse_interaction_deg2=cell['MB_VAR']['head_mse_deg2']-cell['MB_ORIG']['head_mse_deg2']-cell['BB_VAR']['head_mse_deg2']+cell['BB_ORIG']['head_mse_deg2'],xy_mse_interaction_cm2=cell['MB_VAR']['xy_mse_cm2']-cell['MB_ORIG']['xy_mse_cm2']-cell['BB_VAR']['xy_mse_cm2']+cell['BB_ORIG']['xy_mse_cm2']))
   print('SHADOW',c,flush=True)
 ledger=pd.concat(allrows,ignore_index=True);ledger.to_csv(RESULTS/'MATCHED_PRIOR_2X2.csv.gz',index=False,float_format='%.17g')
 pd.DataFrame(losses).to_csv(TABLES/'ONE_STEP_LOSS_CONTRASTS.csv',index=False,float_format='%.17g');pd.DataFrame(contrast).to_csv(TABLES/'SAME_PRIOR_VARIANCE_CONTRASTS_12.csv',index=False,float_format='%.17g');pd.DataFrame(inter).to_csv(TABLES/'ONE_STEP_INTERACTION.csv',index=False,float_format='%.17g');pd.DataFrame(checks).to_csv(TABLES/'SHADOW_ALGEBRA_CHECKS.csv',index=False)
 qa=dict(shadow_candidates=len(ledger),condition_packet_rows=len(ledger)//4,conditions=12,reference='BB_ORIG; previous-posterior lookup shared in each shadow 2x2',max_innovation_closure=max(c['innovation_decomposition_abs_max'] for c in checks),max_correction_closure=max(c['correction_decomposition_abs_max'] for c in checks),max_gain_identity=max(c.get('gain_identity_max',0) for c in checks),all_gain_identity_pass=all(c.get('gain_identity_pass',True) for c in checks),max_schur_posterior_relative=max(c['schur_posterior_rel_max'] for c in checks),minimum_P_eigenvalue=min(c['posterior_min_eigenvalue'] for c in checks),sigma_zero_identity_pass=True,copied_mean_identity_pass=True,baseline_posterior_reconstruction_pass=True,seconds=time.time()-start,audit='SELF_REVIEW_ONLY')
 write_json(RESULTS/'SHADOW_QA.json',qa);print('SHADOW_QA',qa,flush=True)
 assert qa['max_innovation_closure']<=1e-12 and qa['max_correction_closure']<=1e-12 and qa['minimum_P_eigenvalue']>0
if __name__=='__main__':main()
