#!/usr/bin/env python3
"""Partial 4-state EKF C1 counterfactual: exact recorded yaw projection, inferred S.

No recursive intervention; no online oracle correction claim. Original historical
POWER1 [B0, full] archived posterior+innovation contributions+conditional NIS.
Recover S roots from 2D innovation normalized marginals and NIS; discard roots
inconsistent with S-R = H Pprior H' >= 0. In ambiguous cases report all roots.
Recover Pprior(psi,psi) from Ppost + K_psi S K_psi^T for accepted baseline.
No Pprior for rejected necessary because original stored Ppost=Pprior.
"""
from __future__ import annotations
from pathlib import Path
import argparse,math,json,hashlib
import numpy as np,pandas as pd
D=Path('/mnt/data');O=D/'fp_ekf_verification';O.mkdir(exist_ok=True)
G2=9.210340371976184

def wrap(d):return (d+math.pi)%(2*math.pi)-math.pi

def ss_candidates(orig,noise):
    a=math.copysign(math.sqrt(float(orig.marginal_nis_r)),float(orig.r_nu))
    b=math.copysign(math.sqrt(float(orig.marginal_nis_s)),float(orig.s_nu))
    N=float(orig.joint_nis)
    ssr=float(orig.r_nu)**2/float(orig.marginal_nis_r)
    sss=float(orig.s_nu)**2/float(orig.marginal_nis_s)
    discriminant=(a*b)**2-N*(a*a+b*b-N)
    assert discriminant>-1e-8,(orig,discriminant)
    candidates=[]
    for rho in [(a*b+math.sqrt(max(0,discriminant)))/N,(a*b-math.sqrt(max(0,discriminant)))/N]:
        if abs(rho)>=1:continue
        S=np.array([[ssr,rho*math.sqrt(ssr*sss)],[rho*math.sqrt(ssr*sss),sss]])
        eig=np.linalg.eigvalsh(S-noise)
        if eig[0]>-1e-8 and not any(np.max(abs(S-y))<1e-13 for y in candidates): candidates.append(S)
    assert candidates,('no_feasible_S',orig,noise)
    nu=np.array([orig.r_nu,orig.s_nu],float)
    assert max(abs(float(nu@np.linalg.solve(x,nu))-N) for x in candidates)<1e-7
    return candidates

def load_old(route):
    tr=np.load(D/f'replay_{route.lower()}/{route}_aB_m0_full_B0_TRACE.npz',allow_pickle=False)
    j=list(tr['arms']).index('POWER1')
    ori=pd.read_csv(D/f'replay_{route.lower()}/{route}_aB_m0_full_B0_UPDATE_ORIGINS.csv.gz')
    ori=ori[ori.model=='POWER1'].copy()
    assert len(ori)==sum(np.arange(len(tr['t_s']))%2==0)
    return tr,j,ori

def run():
  old=pd.read_csv(D/'c0a/c0a_outputs/C0A_AGGREGATE_TAP_DECOMPOSITION.csv')
  new=pd.read_csv(O/'PR36_FP_ALL_NEW154_PAIRED.csv')
  reference=old[old.route.isin(['R4','R5'])].set_index(['route','pose_id'],verify_integrity=True)
  fresh=set(zip(new.route,new.pose_id))
  all_rows=[];amb_rows=[];baselines=[]
  for route in ['R4','R5']:
    tr,j,origins=load_old(route)
    for ori in origins.itertuples(index=False):
      k=int(round(float(ori.t_s)/.2))
      assert abs(float(tr['t_s'][k])-float(ori.t_s))<1e-8
      assert k%2==0
      rf=reference.loc[(route,int(tr['pose_id'][k]))]
      assert abs(rf.t_s-ori.t_s)<1e-8
      accepted=bool(ori.joint_accept)
      assert accepted==bool(tr['accepted'][k,j])
      noise=tr['R'][k,j]
      C=ss_candidates(ori,noise)
      nu=np.array([float(ori.r_nu),float(ori.s_nu)])
      # K_psi in radians per meter, radians per signed-s
      kp=np.radians(np.array([float(ori.range_to_yaw_deg)/nu[0],float(ori.s_to_yaw_deg)/nu[1]]))
      real_psi=float(tr['state'][k,j,2]);gt_psi=float(tr['truth_scoring_only'][k,2]);Ppost=float(tr['cov'][k,j,2,2]);orig_err=wrap(real_psi-gt_psi)
      assert Ppost>0 and np.isfinite(kp).all()
      arms={
       'FF_original':(0.,0.),
       'FL_s_LoS':(0.,-float(rf.physical_e_mp)),
       'LF_r_LoS':(-float(rf.delta_range_m),0.),
       'LL_both_LoS':(-float(rf.delta_range_m),-float(rf.physical_e_mp)),
       'FP_tap_s_only':(0.,-float(rf.tap_selection_component)),
       'FP_tap_and_range':(-float(rf.delta_range_m),-float(rf.tap_selection_component)),
      }
      for root,S in enumerate(C):
        prior_psi=wrap(real_psi-(kp@nu if accepted else 0.))
        Pprior=Ppost+(float(kp@S@kp) if accepted else 0.)
        assert Pprior>=Ppost-1e-13
        assert abs(float(nu@np.linalg.solve(S,nu))-float(ori.joint_nis))<1e-7
        if k==0:
          # fixed initial standard deviation in original implementation 5 deg
          assert abs(np.degrees(math.sqrt(Pprior))-5.)<5e-6,(route,Pprior,S,kp)
        b=dict(route=route,pose_id=k,t_s=ori.t_s,S_candidate=root,n_S_candidates=len(C),fresh_pr36=(route,k) in fresh,original_accepted=accepted,original_NIS=ori.joint_nis,heading_prior_err_deg=math.degrees(wrap(prior_psi-gt_psi)),heading_full_err_deg=math.degrees(orig_err),Pprior_psi_deg2=math.degrees(math.sqrt(Pprior))**2,Ppost_full_deg2=math.degrees(math.sqrt(Ppost))**2,Kpsi_r_deg_per_m=math.degrees(kp[0]),Kpsi_s_deg_per_s=math.degrees(kp[1]),delta_tap=rf.delta_tap,ds_total=rf.physical_e_mp,ds_selection=rf.tap_selection_component,dr_total=rf.delta_range_m)
        baselines.append(b)
        for arm,(dr,ds) in arms.items():
          dnu=np.array([dr,ds])
          nn=nu+dnu
          nis=float(nn@np.linalg.solve(S,nn))
          if arm=='FF_original':assert abs(nis-float(ori.joint_nis))<1e-7
          # Common fixed BASE gate decision, as well as recomputed local gate
          for policy in ['frozen_gate','self_gate']:
            yes=accepted if policy=='frozen_gate' else nis<=G2
            post=wrap(prior_psi+(kp@nn if yes else 0.))
            var=Ppost if yes else Pprior
            err=math.degrees(wrap(post-gt_psi))
            sig=math.degrees(math.sqrt(var))
            all_rows.append({**b,'arm':arm,'gate_policy':policy,'accepted':yes,'NIS_cf':nis,'heading_error_cf_deg':err,'sigma_cf_deg':sig,'heading_nees_cf':(err/sig)**2,'delta_heading_cf_deg':err-math.degrees(orig_err),'prior_to_post_var_ratio':var/Pprior})
      if len(C)>1:amb_rows.append((route,k,float(ori.t_s),len(C)))
  all_df=pd.DataFrame(all_rows);base_df=pd.DataFrame(baselines)
  # Verify each original same-prior arm gets byte-equivalent archived posterior heading and Ppsi
  orig=all_df[(all_df.arm=='FF_original') & (all_df.gate_policy=='self_gate')]
  assert np.max(abs(orig.heading_error_cf_deg-orig.heading_full_err_deg))<1e-11
  assert np.max(abs(orig.sigma_cf_deg-np.sqrt(orig.Ppost_full_deg2)))<1e-9
  # Ambiguous S candidates: any differing gate decisions? Show and filter them, do not silently select.
  ambiguity=all_df.groupby(['route','pose_id','arm','gate_policy']).agg(n=('NIS_cf','size'),gate_unique=('accepted','nunique'),error_span=('heading_error_cf_deg',lambda x:x.max()-x.min()),nis_span=('NIS_cf',lambda x:x.max()-x.min())).reset_index()
  amb_diff=ambiguity[(ambiguity.n>1)&(ambiguity.gate_unique>1)]
  # Canonical unique rows: use only unambiguous or consensus-gate rows;
  # when both solutions yield same gate but differ in NIS, report intervals.
  one=all_df[all_df.S_candidate==0].copy()
  one['gate_robust']=one.set_index(['route','pose_id','arm','gate_policy']).index.isin(ambiguity[ambiguity.gate_unique==1].set_index(['route','pose_id','arm','gate_policy']).index)
  assert one.gate_robust.mean()>.99
  one.to_csv(O/'C1_ALL_P0_B0_EVEN_FROZEN_AND_SELFGATE.csv',index=False)
  all_df.to_csv(O/'C1_ALL_S_ROOT_CANDIDATES.csv',index=False)
  base_df.to_csv(O/'C1_PRIOR_VARIANCE_RECOVERY.csv',index=False)
  key=['route','arm','gate_policy']
  x=one[one.gate_robust]
  sm=x.groupby(key).agg(n=('NIS_cf','count'),accepted=('accepted','sum'),mean_NIS=('NIS_cf','mean'),heading_abs_error_mean=('heading_error_cf_deg',lambda a:a.abs().mean()),heading_RMSE=('heading_error_cf_deg',lambda a:np.sqrt(np.mean(a*a))),heading_NEES_mean=('heading_nees_cf','mean'),heading_95=('heading_nees_cf',lambda a:np.mean(a<=3.841458820694124)),orig_sigma_mean_deg=('sigma_cf_deg','mean'),fresh_pr36_n=('fresh_pr36','sum')).reset_index()
  sm.to_csv(O/'C1_GATE_AND_HEADING_SUMMARY.csv',index=False)
  # Compare causal contrast with original at the exact same time, only for accepted base & validated roots
  comp=[]
  for (route,arm,policy),g in x.groupby(key):
    g=g.merge(x[(x.route==route)&(x.arm=='FF_original')&(x.gate_policy=='self_gate')][['pose_id','heading_error_cf_deg','heading_nees_cf']],on='pose_id',suffixes=('','_ff'),validate='one_to_one')
    g30=g[g.t_s>=30];comp.append({'route':route,'arm':arm,'policy':policy,'n_total':len(g),'n_t_ge_30':len(g30),'heading_NEES_change_ge30':float((g30.heading_nees_cf-g30.heading_nees_cf_ff).mean()) if len(g30) else np.nan,'improve_abs_error_count':int((g.heading_error_cf_deg.abs()<g.heading_error_cf_deg_ff.abs()-1e-9).sum()),'worsen_abs_error_count':int((g.heading_error_cf_deg.abs()>g.heading_error_cf_deg_ff.abs()+1e-9).sum())})
  pd.DataFrame(comp).to_csv(O/'C1_PAIRED_CONTRASTS.csv',index=False)
  qa={'data_source':'C0A 3136 full/los original composite; original #39376076166 POWER1 Full B0 every 2 frames','original_snapshots':len(orig),'new_raw_154_overlap':int(orig.fresh_pr36.sum()),'S_ambiguous_timestamps':amb_rows,'S_unique_snapshots':1079-len(amb_rows),'selfgate_ambiguous_different_gate_rows':amb_diff.to_dict(orient='records'),'root_candidate_rows':len(base_df),'baseline_exact_recovery_heading_max_deg':float((orig.heading_error_cf_deg-orig.heading_full_err_deg).abs().max()),'baseline_exact_recovery_sigma_max_deg':float((orig.sigma_cf_deg-np.sqrt(orig.Ppost_full_deg2)).abs().max()),'initial_Pprior_deg_expected':5.,'label':'NONINDEPENDENT_EXPLORATORY_PARTIAL_C1_1D_YAW_PROJECTION_NOT_4D_RECURSION'}
  (O/'C1_GATE_QA.json').write_text(json.dumps(qa,indent=2,ensure_ascii=False,allow_nan=False))
  print('S QA',json.dumps(qa,indent=1)[:5000]);print('RESULT summary',sm.to_string(index=False)[:10500]);print('COMP',pd.DataFrame(comp).to_string(index=False)[:6500])
if __name__=='__main__':run()
