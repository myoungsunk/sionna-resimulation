"""Post-hoc read-only R5 diagnosis; no filter replay or parameter modification."""
from pathlib import Path
import sys,json,hashlib,datetime
import numpy as np
import pandas as pd
OUT=Path(__file__).resolve().parent
RUN=OUT.parent
sys.path.insert(0,str(RUN))
import replay_observer_swap as A
DG=A.DG
model=DG.C.base_model();lut=A.LutBatch();spec=DG.C.CASES['R5_aB_m0']
inputs=[RUN/'CONTRACT.json',RUN/'RESULT_CHECKS.json',Path(A.__file__),Path(DG.__file__),Path(__file__)]
inputs += [Path(p) for p in json.loads((RUN/'CONTRACT.json').read_text())['input_hashes'] if str(p).endswith(('.py','.npy','.json','.md'))]
for b in A.BIASES:
    for st in A.STAGES:
        inputs += [RUN/f'R5_aB_m0_{b}_{st}_LUT.npz',A.refpath('R5_aB_m0',b,st)]
hashes={str(p):A.sha(p) for p in set(inputs)}
contract=dict(question_id='DLP-R5-LUT-NEES-CAUSE-20261102',parent_question='DLP-ANCHORB-LUT-OBSERVER-SWAP-20261102',role='AUDITOR self-check; not independent',scope='Read-only saved-trace diagnosis; same-state h/H evaluations, algebraic covariance and error substitutions; no recursive rerun, tuning or manuscript changes',source_identity=json.loads((RUN/'CONTRACT.json').read_text())['checkout_status'],competitors=['larger heading error','smaller/correlated covariance','LUT Jacobian change','gate rejection or different R','near-pole interpolation behavior'],score='all t>=30s; heading1/XY2/pose3 NEES; four biases and all three stages for R5',input_hashes=hashes,started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
(OUT/'CONTRACT.json').write_text(json.dumps(contract,ensure_ascii=False,indent=2),encoding='utf-8')

def nees(e,p):return np.einsum('ni,ni->n',e,np.linalg.solve(p,e[...,None])[...,0])
def cov_update(p,h,r):
    s=h@p@h.transpose(0,2,1)+r;k=np.linalg.solve(s,h@p).transpose(0,2,1)
    a=np.eye(4)[None]-k@h
    return a@p@a.transpose(0,2,1)+k@r@k.transpose(0,2,1)
def measures(z):
    e=z['gt'][:,:3]-z['X'][:,:3];e[:,2]=DG.wrap(e[:,2]);p=z['PX'][:,:3,:3]
    xy=nees(e[:,:2],p[:,:2,:2]);heading=e[:,2]**2/p[:,2,2]
    beta=np.linalg.solve(p[:,:2,:2],p[:,:2,2,None])[...,0]
    vc=p[:,2,2]-np.einsum('ni,ni->n',p[:,2,:2],beta)
    ec=e[:,2]-np.einsum('ni,ni->n',beta,e[:,:2])
    joint=nees(e,p);cond=ec**2/vc
    assert np.allclose(joint,xy+cond,rtol=1e-7,atol=1e-7)
    return e,p,xy,heading,joint,vc,ec

rows=[];packets=[];cross=[];events=[];fdrows=[];checks=[]
for b in A.BIASES:
 for st in A.STAGES:
    ll=dict(np.load(RUN/f'R5_aB_m0_{b}_{st}_LUT.npz'))
    ss=dict(np.load(A.refpath('R5_aB_m0',b,st)))
    for k in ['t','gt','z','mu']:
        if k not in ss:ss[k]=ll[k]
    t=ll['t'];m=t>=30-1e-9;n=len(t)
    states={'SourceFFD':ss,'LUT':ll}; mm={}
    # Evaluate BOTH functions at EACH saved prior to isolate model vs trajectory.
    hs,js=model.batch(ss['xp'],spec);hl,jl=lut.batch(ll['xp'],spec)
    hls,jls=lut.batch(ss['xp'],spec);hsl,jsl=model.batch(ll['xp'],spec)
    assert np.allclose(hs,ss['hx'],atol=1e-10) and np.allclose(hl,ll['hx'],atol=1e-10)
    if 'J' in ss:assert np.allclose(js,ss['J'],atol=1e-8)
    for ob,z,h,j,otherh,otherj in [('SourceFFD',ss,hs,js,hls,jls),('LUT',ll,hl,jl,hsl,jsl)]:
        e,p,xy,heading,joint,vc,ec=measures(z);mm[ob]=(e,p,joint)
        assert np.allclose(j@z['Pp']@j.transpose(0,2,1),z['HPH'],atol=1e-9,rtol=1e-8)
        assert np.array_equal(z['nis']<=DG.GATE,z['used'])
        assert np.allclose(z['S'],z['HPH']+z['Ru'],atol=1e-12)
        recompute=cov_update(z['Pp'],j,z['Ru']);used=z['used']
        assert np.allclose(recompute[used],z['PX'][used],rtol=1e-7,atol=1e-10)
        assert np.allclose(z['Pp'][~used],z['PX'][~used],atol=1e-10)
        alt=cov_update(z['Pp'],otherj,z['Ru'])
        rho=np.linalg.norm(z['xp'][:,:2]-np.asarray(spec['anchor'][:2]),axis=1)
        theta=np.degrees(np.arctan2(rho,spec['anchor'][2]-spec['robot_z_m']))
        eig=np.linalg.eigvalsh(p)
        corr=p/np.sqrt(np.diagonal(p,axis1=1,axis2=2)[:,:,None]*np.diagonal(p,axis1=1,axis2=2)[:,None,:])
        df=pd.DataFrame(dict(bias=b,stage=st,observer=ob,k=np.arange(n),t_s=t,scored=m,
          ex_cm=e[:,0]*100,ey_cm=e[:,1]*100,eheading_deg=np.degrees(e[:,2]),xy_error_cm=100*np.linalg.norm(e[:,:2],axis=1),
          sigma_x_cm=100*np.sqrt(p[:,0,0]),sigma_y_cm=100*np.sqrt(p[:,1,1]),sigma_heading_deg=np.degrees(np.sqrt(p[:,2,2])),
          conditional_heading_error_deg=np.degrees(ec),conditional_sigma_heading_deg=np.degrees(np.sqrt(vc)),
          nees_xy=xy,nees_heading=heading,nees_pose=joint,conditional_heading_nees=joint-xy,
          min_eigenvalue_mixed_units=eig[:,0],cov_condition_mixed_units=eig[:,-1]/eig[:,0],
          corr_x_heading=corr[:,0,2],corr_y_heading=corr[:,1,2],rho_prior_m=rho,theta_prior_deg=theta,
          J_sx=j[:,1,0],J_sy=j[:,1,1],J_spsi=j[:,1,2],J_sxy_norm=np.linalg.norm(j[:,1,:2],axis=1),
          other_model_same_prior_J_sx=otherj[:,1,0],other_model_same_prior_J_sy=otherj[:,1,1],other_model_same_prior_J_spsi=otherj[:,1,2],
          s=h[:,1],other_model_same_prior_s=otherh[:,1],nu_r=z['nu'][:,0],nu_s=z['nu'][:,1],Rss=z['Ru'][:,1,1],
          Sss=z['S'][:,1,1],HPHss=z['HPH'][:,1,1],nis=z['nis'],used=used,
          update_Px_ratio=recompute[:,0,0]/z['Pp'][:,0,0],update_Py_ratio=recompute[:,1,1]/z['Pp'][:,1,1],
          other_H_same_prior_Px_ratio=alt[:,0,0]/z['Pp'][:,0,0],other_H_same_prior_Py_ratio=alt[:,1,1]/z['Pp'][:,1,1]))
        packets.append(df)
        top=np.sort(joint[m]);top1=max(1,int(np.ceil(m.sum()*.01)))
        r=dict(bias=b,stage=st,observer=ob,n_score=int(m.sum()),heading_rmse_deg=np.sqrt(np.mean(np.degrees(e[m,2])**2)),xy_rmse_cm=np.sqrt(np.mean(np.sum(e[m,:2]**2,axis=1)))*100,
          nees_heading=heading[m].mean(),nees_xy=xy[m].mean(),nees_pose=joint[m].mean(),conditional_heading_nees=(joint-xy)[m].mean(),
          rms_sigma_x_cm=np.sqrt(np.mean(p[m,0,0]))*100,rms_sigma_y_cm=np.sqrt(np.mean(p[m,1,1]))*100,
          rms_sigma_heading_deg=np.degrees(np.sqrt(np.mean(p[m,2,2]))),rms_conditional_sigma_heading_deg=np.degrees(np.sqrt(np.mean(vc[m]))),
          nees_pose_max=top[-1],nees_pose_p99=np.quantile(top,.99),top1pct_NEES_sum_share=top[-top1:].sum()/top.sum(),
          used_all=int(used.sum()),used_score=int(used[m].sum()),J_sxy_max=np.linalg.norm(j[:,1,:2],axis=1).max(),J_spsi_abs_max=abs(j[:,1,2]).max(),
          Rss_mean=z['Ru'][m,1,1].mean(),near_pole_lt2deg=int((theta<2).sum()),min_rho=rho.min())
        rows.append(r)
        for k in np.unique(np.r_[np.argsort(joint*m)[-5:],np.argsort(np.linalg.norm(j[:,1,:2],axis=1))[-5:]]):
            events.append(df.iloc[k].to_dict())
        if st=='PROPOSED_MB_VAR' and ob=='LUT':
            # Central differences at the largest spatial-gradient priors, no filter replay.
            for k in np.argsort(np.linalg.norm(j[:,1,:2],axis=1))[-3:]:
                for a in range(3):
                    eps=1e-7;xp=z['xp'][k].copy();xm=xp.copy();xp[a]+=eps;xm[a]-=eps
                    val=(lut.batch(xp[None],spec)[0][0,1]-lut.batch(xm[None],spec)[0][0,1])/(2*eps)
                    fdrows.append(dict(bias=b,k=int(k),axis=a,analytic=j[k,1,a],fd=val,error=val-j[k,1,a]))
    es,ps,ns=mm['SourceFFD'];el,pl,nl=mm['LUT']
    cross.append(dict(bias=b,stage=st,NEES_eS_PS=ns[m].mean(),NEES_eL_PS=nees(el,ps)[m].mean(),NEES_eS_PL=nees(es,pl)[m].mean(),NEES_eL_PL=nl[m].mean(),
      gate_flips_all=int(np.count_nonzero(ll['used']!=ss['used'])),gate_flips_score=int(np.count_nonzero((ll['used']!=ss['used'])&m)),
      first_gate_flip_s=float(t[np.flatnonzero(ll['used']!=ss['used'])[0]]) if np.any(ll['used']!=ss['used']) else None,
      Rss_max_abs_difference=np.max(abs(ll['Ru'][:,1,1]-ss['Ru'][:,1,1]))))
    checks.append(dict(bias=b,stage=st,stored_h_HPH_gate_Joseph_verified=True))
    np.savez_compressed(OUT/f'{b}_{st}_JACOBIAN_SAME_PRIOR.npz',t=t,J_Source_at_Source=js,J_LUT_at_Source=jls,J_LUT_at_LUT=jl,J_Source_at_LUT=jsl,h_Source_at_Source=hs,h_LUT_at_Source=hls,h_LUT_at_LUT=hl,h_Source_at_LUT=hsl)
    print('DIAG_DONE',b,st,flush=True)
pd.DataFrame(rows).to_csv(OUT/'SUMMARY_24.csv',index=False)
pd.DataFrame(cross).to_csv(OUT/'CROSS_ERROR_COV_AND_GATE.csv',index=False)
pd.DataFrame(events).to_csv(OUT/'TOP_EVENTS.csv',index=False)
pd.DataFrame(fdrows).to_csv(OUT/'LARGE_J_FINITE_DIFFERENCE.csv',index=False)
pd.concat(packets,ignore_index=True).to_csv(OUT/'PACKET_DIAGNOSTICS.csv.gz',index=False)
assert all(A.sha(p)==h for p,h in hashes.items())
(OUT/'CHECKS.json').write_text(json.dumps(dict(status='TRACE_DIAGNOSIS_COMPLETED',filter_rerun=False,inputs_unchanged=True,checks=checks,finite_difference_max_abs=float(abs(pd.DataFrame(fdrows).error).max()),finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()),indent=2),encoding='utf-8')
print(pd.DataFrame(rows).query("stage=='PROPOSED_MB_VAR'").to_string(index=False))
print(pd.DataFrame(cross).query("stage=='PROPOSED_MB_VAR'").to_string(index=False))
