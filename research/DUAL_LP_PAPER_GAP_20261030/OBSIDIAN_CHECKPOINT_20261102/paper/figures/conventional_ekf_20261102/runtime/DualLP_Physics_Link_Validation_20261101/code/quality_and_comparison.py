"""Independent-formula SELF_REVIEW, negative fixtures, comparison to prior evidence.
Does not claim reviewer independence or execute additional filter recursions.
"""
from __future__ import annotations
import unittest,time,hashlib
from bootstrap import *

def strict_packet_check(keys,t,z,expected_keys,expected_t,expected_z):
 if len(keys)==0 or len(keys)!=len(expected_keys):raise ValueError('EMPTY_OR_MISSING_ROWS')
 if len(np.unique(keys))!=len(keys):raise ValueError('DUPLICATE_KEYS')
 if not np.array_equal(keys,expected_keys):raise ValueError('KEY_ORDER_MISMATCH')
 if not np.array_equal(t,expected_t):raise ValueError('TIME_MISMATCH')
 if z.shape!=(len(keys),2) or not np.isfinite(z).all():raise ValueError('INVALID_OBSERVATION')
 if np.any(abs(z[:,1])>1):raise ValueError('SIGNED_RATIO_OUT_OF_DOMAIN')
 if not(np.allclose(z[:,0],expected_z[:,0],atol=1e-9,rtol=0) and np.allclose(z[:,1],expected_z[:,1],atol=1e-12,rtol=0)):raise ValueError('OBSERVER_PARITY_FAILED')
 return True

def negative_fixtures():
 D=read_data(CASES[0],'B0');keys=D['pose_id'][:8];t=D['t'][:8];z=D['z'][:8]
 def chk(k=keys,tt=t,zz=z):return strict_packet_check(k,tt,zz,keys,t,z)
 fixture=[]
 def reject(name,fn):
  try:fn()
  except (ValueError,AssertionError) as e:fixture.append(dict(test=name,expected='REJECT',status='PASS',reason=str(e)));return
  raise AssertionError('NEGATIVE_FIXTURE_NOT_REJECTED:'+name)
 assert chk();fixture.append(dict(test='unmodified_fixture',expected='ACCEPT',status='PASS'))
 reject('duplicate_pose_id',lambda:chk(k=np.r_[keys[0],keys[:-1]]))
 reject('missing_packet',lambda:chk(k=keys[:-1],tt=t[:-1],zz=z[:-1]))
 reject('time_shift_one_packet',lambda:chk(tt=t+.2))
 bad=z.copy();bad[:,1]*=-1;reject('port_swap_not_silently_accepted',lambda:chk(zz=bad))
 bad2=z.copy();bad2[0,0]+=.01;reject('range_observation_corruption',lambda:chk(zz=bad2))
 reject('zero_rows',lambda:chk(k=keys[:0],tt=t[:0],zz=z[:0]))
 bad3=z.copy();bad3[0,1]=1.2;reject('signed_s_out_of_domain',lambda:chk(zz=bad3))
 bad4=z.copy();bad4[0,0]=np.nan;reject('nonfinite_observation',lambda:chk(zz=bad4))
 path=INPUT/'rf/H_R2_aB_m0.npy';buf=bytearray(path.read_bytes());expected=hashlib.sha256(buf).hexdigest();buf[-1]^=1
 def bytecheck():
  if hashlib.sha256(buf).hexdigest()!=expected:raise ValueError('SHA256_MISMATCH')
 reject('RF_byte_mutation_hash_guard',bytecheck)
 from core import covariance
 reject('negative_covariance',lambda:covariance(np.diag([1.,-1.]),2,positive=True))
 sq=json.loads((RESULTS/'SHADOW_QA.json').read_text())
 for name,key in [('sigma_zero_shadow_identity','sigma_zero_identity_pass'),('muM_equal_muB_shadow_identity','copied_mean_identity_pass')]:
  assert sq[key];fixture.append(dict(test=name,expected='IDENTITY',status='PASS'))
 write_json(RESULTS/'NEGATIVE_FIXTURES.json',dict(fixtures=fixture,n=len(fixture),all_pass=True,scope='isolated fixtures and mathematical null interventions; no extra full recursive runs',audit='SELF_REVIEW_ONLY'))
 return len(fixture)

def inv2(a):
 det=a[:,0,0]*a[:,1,1]-a[:,0,1]*a[:,1,0]
 assert np.all(det>0)
 out=np.empty_like(a);out[:,0,0]=a[:,1,1];out[:,1,1]=a[:,0,0];out[:,0,1]=-a[:,0,1];out[:,1,0]=-a[:,1,0]
 return out/det[:,None,None]

def main():
 scores=pd.read_csv(TABLES/'RECURSIVE_144_LOGICAL_SCORES.csv');checks=[];first=[];index=[];oldchat=pd.read_csv(ROOT/'evidence/PREVIOUS_CHAT_REPORTED_12.csv')
 t0=time.time()
 for case in CASES:
  for bias in BIASES:
   D=read_data(case,bias);base=read_trace(case,bias,'BB_ORIG','self');fin=np.isfinite(D['z']).all(1);sm=D['t']>=30-1e-9
   for _,r in scores[(scores.case==case)&(scores.bias==bias)].iterrows():
    tr=read_trace(case,bias,r.arm,r.gate);u=tr['used'];P=tr['Pp'];J=tr['J'];S=tr['S'];v=tr['nu']
    # Different inverse formula from np.linalg.solve used by source.
    K=P@J.transpose(0,2,1)@inv2(S)
    y=tr['xp']+np.einsum('nij,nj->ni',K,v);y[:,2]=np.arctan2(np.sin(y[:,2]),np.cos(y[:,2]))
    e=y-tr['X'];e[:,2]=np.arctan2(np.sin(e[:,2]),np.cos(e[:,2]))
    xp_err=float(abs(e[u]).max())
    # Algebraically equivalent covariance contraction, not Joseph path.
    Pc=P-K@S@K.transpose(0,2,1);p_err=float(np.max(abs(Pc[u]-tr['PX'][u])))
    ep=np.arctan2(np.sin(tr['X'][:,2]-D['gt'][:,2]),np.cos(tr['X'][:,2]-D['gt'][:,2]));eh=float(np.sqrt(np.mean(ep[sm]**2))*180/np.pi)
    exy=float(np.sqrt(np.mean(np.sum((tr['X'][sm,:2]-D['gt'][sm,:2])**2,axis=1)))*100)
    sym=float(np.max(abs(tr['PX']-tr['PX'].transpose(0,2,1))));mineig=float(np.linalg.eigvalsh(tr['PX']).min())
    expected=u if False else ((tr['nis']<=DG.GATE)&fin if r.gate=='self' else D['acc']&fin)
    mask_ok=np.array_equal(u,expected)
    # all original fixed arms have exactly the same mask; no stable-FD selection enters them.
    checks.append(dict(case=case,bias=bias,arm=r.arm,gate=r.gate,head_rescore_abs=abs(eh-r.head_rmse),xy_rescore_abs_cm=abs(exy-r.xy_rmse_cm),state_update_reconstruction_abs=xp_err,covariance_contraction_abs=p_err,covariance_symmetry_abs=sym,min_P_eigenvalue=mineig,mask_pass=mask_ok))
    assert xp_err<1e-10 and p_err<1e-10 and abs(eh-r.head_rmse)<1e-10 and abs(exy-r.xy_rmse_cm)<1e-10 and mask_ok and mineig>0
    dx=tr['X']-base['X'];dx[:,2]=wrap(dx[:,2]);deviate=(abs(dx)>np.array([1e-8,1e-8,1e-10,1e-10])).any(1);ii=np.flatnonzero(deviate);flip=np.flatnonzero(tr['used']!=base['used'])
    first.append(dict(case=case,bias=bias,arm=r.arm,gate=r.gate,first_state_difference_pose_id=int(D['pose_id'][ii[0]]) if len(ii) else -1,first_state_difference_t_s=float(D['t'][ii[0]]) if len(ii) else np.nan,first_gate_difference_pose_id=int(D['pose_id'][flip[0]]) if len(flip) else -1,n_gate_flips=len(flip)))
    path=trace_path(case,bias,r.arm,'self' if r.arm=='BB_ORIG' and r.gate=='fixed' else r.gate)
    index.append(dict(case=case,bias=bias,arm=r.arm,gate=r.gate,path=path.relative_to(ROOT).as_posix(),sha256=digest(path),alias=(r.arm=='BB_ORIG' and r.gate=='fixed')))
 pd.DataFrame(checks).to_csv(TABLES/'INDEPENDENT_FORMULA_SELF_REVIEW.csv',index=False);pd.DataFrame(first).to_csv(TABLES/'FIRST_DIVERGENCE.csv',index=False);write_json(RESULTS/'FIXED_SELF_TRACE_INDEX.json',index)
 # Previous chat quoted 4 decimal values; authoritative historical CSV comparison is separate.
 chat=[]
 for _,r in oldchat.iterrows():
  got=scores[(scores.case==r.case)&(scores.bias==r.bias)&(scores.arm==r.arm)&(scores.gate==r.gate)].iloc[0]
  for col in ['head_rmse','xy_rmse_cm']:
   chat.append(dict(case=r.case,bias=r.bias,arm=r.arm,gate=r.gate,metric=col,previous_chat_value=r[col],new_value=got[col],new_rounded_4dec=round(got[col],4),abs_diff=abs(got[col]-r[col]),pass_display=round(got[col],4)==r[col],evidence_level='CHAT_TRANSCRIPTION_NO_OLD_TRACE'))
 ch=pd.DataFrame(chat);ch.to_csv(TABLES/'PREVIOUS_CHAT_VS_REBUILD_48_VALUES.csv',index=False)
 assert ch.pass_display.all()
 # Preserve the complete 12-condition table with original and combined, all self gate.
 primary=scores[(scores.gate=='self')&(scores.arm.isin(['BB_ORIG','MB_VAR']))].pivot(index=['case','bias'],columns='arm',values=['head_rmse','xy_rmse_cm']);primary.columns=['_'.join(x) for x in primary.columns];primary.reset_index().to_csv(TABLES/'LEGACY_PRESERVATION_12.csv',index=False,float_format='%.17g')
 contrast=[]
 for case in CASES:
  for bias in BIASES:
   for gate in ['fixed','self']:
    f=scores[(scores.case==case)&(scores.bias==bias)&(scores.gate==gate)].set_index('arm')
    d=dict(case=case,bias=bias,gate=gate,lookup_heading=f.loc['MB_VAR','head_rmse'],constant_heading=f.loc['MB_CONST','head_rmse'],lookup_xy_cm=f.loc['MB_VAR','xy_rmse_cm'],constant_xy_cm=f.loc['MB_CONST','xy_rmse_cm'],lookup_minus_constant_heading=f.loc['MB_VAR','head_rmse']-f.loc['MB_CONST','head_rmse'],lookup_minus_constant_xy_cm=f.loc['MB_VAR','xy_rmse_cm']-f.loc['MB_CONST','xy_rmse_cm'],BB_VAR_heading=f.loc['BB_VAR','head_rmse'],MB_ORIG_heading=f.loc['MB_ORIG','head_rmse'])
    contrast.append(d)
 cc=pd.DataFrame(contrast);cc.to_csv(TABLES/'MB_LOOKUP_VS_CONSTANT_24.csv',index=False,float_format='%.17g');cc[cc.gate=='self'].to_csv(TABLES/'MB_LOOKUP_VS_CONSTANT_12.csv',index=False,float_format='%.17g')
 mask=[]
 for (case,bias,arm),g in scores.groupby(['case','bias','arm']):
  f=g.set_index('gate');mask.append(dict(case=case,bias=bias,arm=arm,self_minus_fixed_heading=f.loc['self','head_rmse']-f.loc['fixed','head_rmse'],self_minus_fixed_xy_cm=f.loc['self','xy_rmse_cm']-f.loc['fixed','xy_rmse_cm'],self_n_used=int(f.loc['self','n_used']),fixed_n_used=int(f.loc['fixed','n_used'])))
 pd.DataFrame(mask).to_csv(TABLES/'MASK_POLICY_EFFECTS.csv',index=False)
 # Source input consistency across stored B0/L2, not a substitute for fresh ML inference.
 mrows=[]
 for c in CASES:
  ref=C.load_control(c,'B0')
  for b in ['B0','L2']:
   x=C.load_control(c,b);j=x['jb'];m=x['jm'];rj=ref['jb'];rm=ref['jm']
   for k,pid in enumerate(x['pose_id']):
    mrows.append(dict(case=c,bias=b,pose_id=int(pid),mu_B_r=float(x['mu'][k,j,0]),mu_M_r=float(x['mu'][k,m,0]),mu_s_difference=float(x['mu'][k,m,1]-x['mu'][k,j,1]),mu_B_vs_B0_max=float(np.max(abs(x['mu'][k,j]-ref['mu'][k,rj]))),mu_M_vs_B0_max=float(np.max(abs(x['mu'][k,m]-ref['mu'][k,rm]))),R_vs_B0_max=float(np.max(abs(x['R'][k,j]-ref['R'][k,rj])))))
 mm=pd.DataFrame(mrows);mm.to_csv(TABLES/'ARCHIVED_MEAN_CONSISTENCY_6272.csv.gz',index=False,float_format='%.17g')
 assert len(mm)==6272 and (mm[['mu_s_difference','mu_B_vs_B0_max','mu_M_vs_B0_max','R_vs_B0_max']].to_numpy()==0).all()
 fixtures=negative_fixtures();review=dict(logical_traces_reviewed=len(checks),actual_trace_files=132,score_and_update_and_masks_all_pass=True,chat_values_compared=len(ch),chat_display_matches=int(ch.pass_display.sum()),negative_fixture_tests=fixtures,archived_mean_rows=len(mm),archived_mean_consistency_pass=True,independent_auditor_status='NOT_AVAILABLE_SELF_REVIEW_ONLY',old_archive_byte_equality='NOT_VERIFIABLE_ORIGINAL_UNAVAILABLE',seconds=time.time()-t0)
 write_json(RESULTS/'COMPARISON_QA.json',review);print(review)
if __name__=='__main__':main()
