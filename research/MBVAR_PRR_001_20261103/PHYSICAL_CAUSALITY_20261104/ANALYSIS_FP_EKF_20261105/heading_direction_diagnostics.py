#!/usr/bin/env python3
"""EXPLORATORY, read-only analysis of historical Full/LoS 4-state EKF B0 traces.

Data required (download exact historical GitHub Actions artifacts):
  /mnt/data/replay_r4/R4_aB_m0_{full,los}_B0_TRACE.npz
  /mnt/data/replay_r5/R5_aB_m0_{full,los}_B0_TRACE.npz
  /mnt/data/replay_r{4,5}/R{4,5}_aB_m0_full_B0_UPDATE_ORIGINS.csv.gz
  /mnt/data/c0a/c0a_outputs/C0A_AGGREGATE_TAP_DECOMPOSITION.csv
No new RT, no altered filter, no 4-state recursive counterfactual. 
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd

C2 = 3.841458820694124

def wrap_deg(a):
    return (np.asarray(a)+180)%360-180

def read(root, route, mode):
    with np.load(root/f'replay_{route.lower()}'/f'{route}_aB_m0_{mode}_B0_TRACE.npz',allow_pickle=False) as f:
        return {key:f[key] for key in f.files}

def signed_bins(heading):
    bins=np.arange(-180,181,15,dtype=float)
    labs=[f'[{bins[k]:g},{bins[k+1]:g})' for k in range(len(bins)-1)]
    h=np.asarray(wrap_deg(heading),float)
    inds=np.minimum(np.searchsorted(bins,h,side='right')-1,len(labs)-1)
    return np.array([labs[i] for i in inds])

def main():
    a=argparse.ArgumentParser();a.add_argument('--root',default='/mnt/data');a.add_argument('--out',default='/mnt/data/fp_ekf_verification');z=a.parse_args()
    root=Path(z.root);out=Path(z.out);out.mkdir(parents=True,exist_ok=True)
    c0=pd.read_csv(root/'c0a/c0a_outputs/C0A_AGGREGATE_TAP_DECOMPOSITION.csv')
    c0=c0[c0.route.isin(['R4','R5'])].set_index(['route','pose_id'],verify_integrity=True)
    trajectories=[];updates=[]
    for route in ['R4','R5']:
        alltrace={mode:read(root,route,mode) for mode in ['full','los']}
        orig=pd.read_csv(root/f'replay_{route.lower()}'/f'{route}_aB_m0_full_B0_UPDATE_ORIGINS.csv.gz')
        for mode,tr in alltrace.items():
            gt=np.asarray(tr['truth_scoring_only'][:,2],float)
            n=len(gt)
            assert np.max(np.abs(tr['t_s']-0.2*np.arange(n)))<1e-8
            assert np.array_equal(tr['pose_id'],np.arange(n))
            for arm in ['JOINT4','POWER1','POWER_DIAG']:
                j=list(tr['arms']).index(arm)
                state=np.asarray(tr['state'][:,j,2],float)
                err=wrap_deg(np.degrees(state-gt))
                sig=np.degrees(np.sqrt(tr['cov'][:,j,2,2]))
                assert np.all(sig>0)
                for k in range(n):
                    rf=c0.loc[(route,k)]
                    trajectories.append(dict(route=route,mode=mode,arm=arm,pose_id=k,t_s=float(tr['t_s'][k]),gt_heading_deg=float(wrap_deg(np.degrees(gt[k]))),posterior_heading_deg=float(wrap_deg(np.degrees(state[k]))),heading_error_deg=float(err[k]),heading_sigma_deg=float(sig[k]),heading_NEES=float((err[k]/sig[k])**2),heading95=bool((err[k]/sig[k])**2<=C2),NIS=float(tr['nis'][k,j]),accepted=bool(tr['accepted'][k,j]),x_GT_m=float(tr['truth_scoring_only'][k,0]),y_GT_m=float(tr['truth_scoring_only'][k,1]),s_FminusL=float(rf.physical_e_mp),s_same_tap=float(rf.same_los_tap_component),s_tap_selection=float(rf.tap_selection_component),delta_fp_tap=int(rf.delta_tap),delta_range_m=float(rf.delta_range_m)))
        # Origins are only at even 0.4s snapshots. Exact decomposition for accepted original updates.
        tr=alltrace['full'];arm_ix={str(name):j for j,name in enumerate(tr['arms'])}
        for row in orig.itertuples(index=False):
            if row.model != 'POWER1':continue  # JOINT4 UPDATE_ORIGINS NIS differs from stored TRACE; do not mix
            k=int(round(row.t_s/0.2)); assert abs(tr['t_s'][k]-row.t_s)<1e-8
            j=arm_ix[row.model];accepted=bool(tr['accepted'][k,j])
            assert accepted==bool(row.joint_accept)
            gt=float(wrap_deg(np.degrees(tr['truth_scoring_only'][k,2])))
            post=float(wrap_deg(np.degrees(tr['state'][k,j,2])))
            prev=float(wrap_deg(np.degrees(tr['state'][k-1,j,2]))) if k>0 else float('nan')
            upd_r=float(row.range_to_yaw_deg) if accepted else 0.
            upd_s=float(row.s_to_yaw_deg) if accepted else 0.
            prior=float(wrap_deg(post-upd_r-upd_s))
            assert abs(float(wrap_deg(prior+upd_r+upd_s-post)))<1e-7
            rf=c0.loc[(route,k)]
            Kr=float(row.range_to_yaw_deg/row.r_nu) if abs(float(row.r_nu))>1e-10 else float('nan')
            Ks=float(row.s_to_yaw_deg/row.s_nu) if abs(float(row.s_nu))>1e-10 else float('nan')
            cf_s=post-Ks*float(rf.physical_e_mp) if accepted else post
            cf_both=cf_s-Kr*float(rf.delta_range_m) if accepted else post
            updates.append(dict(route=route,arm=row.model,pose_id=k,t_s=float(row.t_s),x_GT_m=float(tr['truth_scoring_only'][k,0]),y_GT_m=float(tr['truth_scoring_only'][k,1]),GT_heading_deg=gt,previous_posterior_deg=prev,DR_prediction_deg=prior,DR_delta_from_previous_deg=float(wrap_deg(prior-prev)) if k>0 else float('nan'),innovation_range_m=float(row.r_nu),innovation_s=float(row.s_nu),Kpsi_r_deg_per_m=Kr,Kpsi_s_deg_per_s=Ks,range_heading_correction_deg=upd_r,s_heading_correction_deg=upd_s,prior_plus_s_component_deg=float(wrap_deg(prior+upd_s)),prior_plus_range_component_deg=float(wrap_deg(prior+upd_r)),posterior_heading_deg=post,heading_error_deg=float(wrap_deg(post-gt)),heading_sigma_deg=float(np.degrees(np.sqrt(tr['cov'][k,j,2,2]))),heading_NEES=float((wrap_deg(post-gt)/np.degrees(np.sqrt(tr['cov'][k,j,2,2])))**2),NIS=float(row.joint_nis),accepted=accepted,FP_shift_taps=int(rf.delta_tap),physical_s_FminusL=float(rf.physical_e_mp),same_tap_s_effect=float(rf.same_los_tap_component),tap_selection_s_effect=float(rf.tap_selection_component),range_FminusL_m=float(rf.delta_range_m),fixed_prior_s_LoS_posterior_deg=float(wrap_deg(cf_s)),fixed_prior_both_LoS_posterior_deg=float(wrap_deg(cf_both))))
    timeline=pd.DataFrame(trajectories);upd=pd.DataFrame(updates)
    assert len(timeline)==(742+1415)*2*3
    assert len(upd)==371+708
    assert max(abs(wrap_deg(upd.DR_prediction_deg+upd.range_heading_correction_deg+upd.s_heading_correction_deg-upd.posterior_heading_deg)))<1e-7
    timeline.to_csv(out/'HEADING_DIRECTION_ALL_STEPS.csv',index=False,float_format='%.12g')
    upd.to_csv(out/'HEADING_UPDATE_PRIOR_OBSERVATION_POSTERIOR.csv',index=False,float_format='%.12g')
    # t>=30: angle occupancy is not balanced; do not compare empty or tiny bins.
    a=timeline[(timeline.t_s>=30)&(timeline.arm.isin(['POWER1','JOINT4']))].copy()
    a['gt_angle_bin_15deg']=signed_bins(a.gt_heading_deg)
    key=['route','mode','arm','gt_angle_bin_15deg']
    g=a.groupby(key,observed=True).agg(n=('pose_id','size'),rmse_heading_deg=('heading_error_deg',lambda v:float(np.sqrt(np.mean(v*v)))),mean_abs_heading_deg=('heading_error_deg',lambda v:float(v.abs().mean())),signed_bias_deg=('heading_error_deg','mean'),heading_sigma_mean_deg=('heading_sigma_deg','mean'),heading95=('heading95','mean'),NEES_mean=('heading_NEES','mean'),FP_shift_share=('delta_fp_tap',lambda v:float(np.mean(v!=0))),eMP_s_rms=('s_FminusL',lambda v:float(np.sqrt(np.mean(v*v)))),GT_angle_mean_deg=('gt_heading_deg','mean')).reset_index()
    # Sort for reviewing route-specific direction of greatest errors, only n>=20.
    g['valid_n20']=g.n>=20
    g.to_csv(out/'HEADING_DIRECTION_15DEG_BINS.csv',index=False,float_format='%.10g')
    # Top error snapshots after the starting 30 seconds; all timesteps and update-matched subset.
    top=a[a['mode']=='full'].sort_values('heading_error_deg',key=lambda x:x.abs(),ascending=False).groupby(['route','arm']).head(15)
    top.to_csv(out/'HEADING_TOP_POST30_ERRORS.csv',index=False,float_format='%.12g')
    cases=[('R4','POWER1',0),('R4','POWER1',168),('R4','POWER1',190),('R4','POWER1',194),('R4','POWER1',298),('R4','POWER1',496),('R4','POWER1',500),('R5','POWER1',0),('R5','POWER1',162),('R5','POWER1',464),('R5','POWER1',524),('R5','POWER1',982)]
    cases=[(r,arm,k) for (r,arm,k) in cases if (r,arm,k) in upd.set_index(['route','arm','pose_id']).index]
    ss=upd.set_index(['route','arm','pose_id']).loc[cases].reset_index()
    ss.to_csv(out/'HEADING_EXAMPLE_UPDATES.csv',index=False,float_format='%.12g')
    qa={'source':'GitHub historical replay Actions 39376076166; C0A Actions 41783949902; no new simulation','source_types':'B0 Full and native LoS original traces, three filter arms, original 0.4s UPDATE_ORIGINS','timeline_rows':len(timeline),'update_rows':len(upd),'example_rows':len(ss),'max_identity_residual_deg':float(max(abs(wrap_deg(upd.DR_prediction_deg+upd.range_heading_correction_deg+upd.s_heading_correction_deg-upd.posterior_heading_deg)))),'excluded_initial_for_angle_score_s':30.0,'heading_convention':'radians in input, degrees displayed; 0° +X, CCW positive; wrap [-180,180)','caveats':['angle bins are observational: yaw confounded with route position/time','s-only projected angle is prior+Kalman-weighted innovation, not unique inverse s→yaw; other state and model matter','update origin archive only every two timesteps, actual full route traces every 0.2s','post t=30 analysis excludes startup but observations follow t=0 recursive history','counterfactual fixed prior does not replay future x,P,H,gate or noise','multiple time samples are serially correlated, not independent replications'],'status':'NONINDEPENDENT_EXPLORATORY_VERIFIED_RECOMPUTATION','update_origin_scope':'POWER1 only; JOINT4 UPDATE_ORIGINS differs from TRACE NIS and gate in some snapshots; JOINT4 directional errors from TRACE only'}
    (out/'HEADING_DIRECTION_QA.json').write_text(json.dumps(qa,indent=2,ensure_ascii=False),encoding='utf-8')
    # Plot charts (only if matplotlib available; data analysis remains usable without it).
    try:
        import matplotlib.pyplot as plt
        for route in ['R4','R5']:
            fig,ax=plt.subplots(figsize=(12,4.7))
            sub=g[(g.route==route)&(g['mode']=='full')&(g.arm.isin(['POWER1','JOINT4']))&(g.valid_n20)]
            if len(sub):
                for name,q in sub.groupby('arm'):
                    q=q.sort_values('GT_angle_mean_deg');ax.plot(q.GT_angle_mean_deg,q.rmse_heading_deg,'o-',label=name)
                ax.set_xlabel('Ground-truth heading (deg; 15° bins)')
                ax.set_ylabel('Heading RMSE (deg, t≥30 s)')
                ax.set_title(f'{route}-B: heading-error association by actual yaw (B0, Full)')
                ax.grid(True,alpha=.25);ax.legend();fig.tight_layout()
                fig.savefig(out/f'HEADING_DIRECTION_{route}_B0.png',dpi=165)
            plt.close(fig)
        fig,ax=plt.subplots(figsize=(11,4))
        sub=ss[((ss.route=='R4')&(ss.pose_id==190))|((ss.route=='R5')&(ss.pose_id==162))]
        for _,v in sub.iterrows():
            vals=[v.GT_heading_deg,v.previous_posterior_deg,v.DR_prediction_deg,v.prior_plus_s_component_deg,v.posterior_heading_deg]
            ax.plot(np.arange(len(vals)),vals,marker='o',label=f'{v.route} {v.arm} t={v.t_s:g}s')
        ax.set_xticks(range(5),['True','Previous','Prior (DR)','Prior + s contribution','Posterior'])
        ax.set_ylabel('Yaw (deg)');ax.set_title('Two failure events: prior and incremental RF update');ax.grid(True,alpha=.25);ax.legend();fig.tight_layout();fig.savefig(out/'HEADING_PRIOR_UPDATE_EXAMPLES.png',dpi=165);plt.close(fig)
    except ImportError:pass
    print(json.dumps(qa,indent=2,ensure_ascii=False))
    print('\nTOP POST-30 FULL ERRORS\n',top.groupby(['route','arm']).head(2)[['route','arm','pose_id','t_s','gt_heading_deg','posterior_heading_deg','heading_error_deg','heading_sigma_deg','heading_NEES','NIS','s_FminusL','delta_fp_tap']].to_string(index=False))
    print('\nSELECTED UPDATE CHAINS\n',ss[['route','arm','pose_id','t_s','GT_heading_deg','previous_posterior_deg','DR_prediction_deg','range_heading_correction_deg','s_heading_correction_deg','posterior_heading_deg','heading_error_deg','heading_sigma_deg','NIS','FP_shift_taps','physical_s_FminusL']].to_string(index=False))
    print('\nDIRECTION BINS n>=20\n',g[(g['mode']=='full')&(g.valid_n20)].sort_values(['route','arm','rmse_heading_deg'],ascending=[True,True,False]).to_string(index=False))

if __name__=='__main__':main()
