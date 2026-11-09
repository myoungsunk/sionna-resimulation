#!/usr/bin/env python3
"""Reconstruct and audit B-MCG case evidence from immutable published traces.

No RF propagation or filter replay. Evaluator truth only used for retrospective labels.
Recover original yaw gyro and odom distance increments from the exact archived
core.transition predictor and independently replayed OFF/ON streams.
"""
from __future__ import annotations
import argparse, csv, io, json, hashlib, zipfile, math
from collections import defaultdict,Counter
from pathlib import Path
import numpy as np
import pandas as pd

ROUTES=('R2','R4','R5');STRATA=('B_FROZEN','B_BIAS_COV');MODES=('OFF','ACTIVE_RS')
STEP=299792458/(1028*1950000)
wrap=lambda x:(np.asarray(x)+np.pi)%(2*np.pi)-np.pi

def read_archive(root,route,stratum,mode):
    name=f'{route}/active/{stratum}/{mode}/{route}_{mode}.npz'
    with root.open('rb') as f:
        with zipfile.ZipFile(f) as z:
            with np.load(io.BytesIO(z.read(name)),allow_pickle=False) as a:
                return {k:a[k] for k in a.files}

def recover_motion(tr):
    # Original source core.transition: a=gyro_angle-bg_prev*dt; yaw_prior=wrap(yaw_prev+a)
    t=tr['t'];dt=np.diff(t)
    assert np.all(dt>0)
    a=wrap(tr['prior'][1:,2]-tr['x'][:-1,2])
    gyro=wrap(a+tr['x'][:-1,3]*dt)
    c=np.sinc(a/(2*np.pi))
    phi=tr['x'][:-1,2]+a/2
    u=np.stack([np.cos(phi),np.sin(phi)],axis=1)
    du=tr['prior'][1:,:2]-tr['x'][:-1,:2]
    ds=(du*u).sum(axis=1)/c
    residual=np.max(np.abs((du-u*(ds*c)[:,None])))
    return gyro,ds,residual

def loss(x,truth):
    err=x[:,:3]-truth
    err[:,2]=wrap(err[:,2]);
    return err[:,2]**2,(err[:,:2]**2).sum(axis=1)

def ungated_single_prior(tr):
    # Compare unattenuated original B update versus guard at EXACT SAME guard prior;
    # keeps the original shadow mask and observation intact.
    H=tr['H'];P=tr['Pprior'];R=tr['Rbase'];nu=tr['nu'];
    innovation=H@P@np.swapaxes(H,-1,-2)+R
    K=np.linalg.solve(innovation,H@P).swapaxes(-1,-2)
    xs=tr['prior']+np.einsum('nij,nj->ni',K,nu)
    xs[:,2]=wrap(xs[:,2])
    xs[~tr['mask']]=tr['prior'][~tr['mask']]
    return xs

def diag_nees(x,P,truth):
    e=x[:,:3]-truth;e[:,2]=wrap(e[:,2]);C=P[:,:3,:3]
    return np.einsum('ni,ni->n',e,np.linalg.solve(C,e[:,:,None])[:,:,0])

def select_diverse(df,metric,n=6,min_spacing=12,positives=True):
    z=df[df[metric].notna()].copy()
    z=z.sort_values(metric,ascending=not positives)
    out=[]
    for k in z.k:
        if any(abs(int(k)-i)<min_spacing for i in out):continue
        out.append(int(k))
        if len(out)>=n:break
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--archive',type=Path,default=Path('/mnt/data/B_MCG_v1_results_42600632209_verified.zip'))
    ap.add_argument('--primary',type=Path,default=Path('/mnt/data/b_mcg_case_study_inputs/PRIMARY_3136.csv'))
    ap.add_argument('--out',type=Path,default=Path('/mnt/data/B_MCG_CASE_GALLERY_20261109'))
    arg=ap.parse_args();arg.out.mkdir(parents=True,exist_ok=True)
    primary=pd.read_csv(arg.primary,encoding='utf-8-sig')
    assert len(primary)==3136 and set(primary.route)==set(ROUTES)
    extra=[]; wide_data={};audits={};cases={};
    for route in ROUTES:
        base=primary[primary.route==route].sort_values('k').reset_index(drop=True)
        n=len(base);assert np.array_equal(base.k,np.arange(n))
        assert np.max(abs(wrap(base.yaw_true_rad.to_numpy()-np.radians(base.heading_deg.to_numpy()))))<1e-7
        samples={}
        for st in STRATA:
            for mode in MODES: samples[(st,mode)]=read_archive(arg.archive,route,st,mode)
        controls=[]; dscontrols=[];residuals=[]
        for k,tr in samples.items():
            assert len(tr['x'])==n and np.max(abs(tr['t']-base.t_s))<1e-7
            assert np.array_equal(tr['pose_id'],base.pose_id)
            gyro,ds,r=recover_motion(tr);controls.append(gyro);dscontrols.append(ds);residuals.append(r)
            z=tr['nu']+tr['h']+tr['mu']; zp=np.c_[base.B_F*STEP,base.s_F]
            assert np.max(abs(z-zp))<1e-7,(route,st,mode,'B packet mismatch',np.max(abs(z-zp)))
            assert np.linalg.eigvalsh(tr['P']).min()>-1e-10
            if mode=='OFF':assert np.max(abs(tr['beta']-1))==0
        gyromax=max(float(np.max(abs(wrap(a-controls[0])))) for a in controls)
        dsmax=max(float(np.max(abs(a-dscontrols[0]))) for a in dscontrols)
        assert max(gyromax,dsmax,*residuals)<2e-11
        gyro=np.r_[0,controls[0]];ds=np.r_[0,dscontrols[0]];
        dyawtrue=np.r_[0,wrap(np.diff(base.yaw_true_rad.to_numpy()))]
        audits[route]={
          'n':n,'reconstruction':'Original yaw transition gyro_angle = wrap(prior_yaw - previous_posterior_yaw)+bg_previous*dt; ds projected via sinc_half midpoint',
          'gyro_stream_parity_max_rad':gyromax,'odom_stream_parity_max_m':dsmax,'position_forward_residual_max_m':max(residuals),
          't_step_median_s':float(np.median(np.diff(base.t_s))), 'gyro_rate_RMSE_vs_true_deg_s':float(np.sqrt(np.mean((np.degrees(gyro[1:]-dyawtrue[1:])/np.diff(base.t_s))**2))),
          'original_gyro_explicitly_downloaded':False,'gyro_derived_from_state_predictor_with_multi_arm_parity':True}
        base['gyro_increment_rad']=gyro;base['odom_distance_increment_m']=ds;base['true_yaw_increment_rad']=dyawtrue
        base['gyro_delta_minus_true_deg']=np.degrees(wrap(gyro-dyawtrue))
        for st in STRATA:
            off=samples[(st,'OFF')];on=samples[(st,'ACTIVE_RS')]
            truth=base[['x_true','y_true','yaw_true_rad']].to_numpy(float)
            expected=ungated_single_prior(on)
            ind=np.min(on['beta'],axis=1)<0.999999
            consistent=np.max(abs(wrap((expected-on['x'])[:,2][~ind]))) if (~ind).any() else 0
            err_other=float(np.max(abs(expected[~ind,:2]-on['x'][~ind,:2]))) if (~ind).any() else 0
            assert max(consistent,err_other)<1e-9,(route,st,'same prior correctness',consistent,err_other)
            ehg,exg=loss(on['x'],truth);ehu,exu=loss(expected,truth)
            ehp,exp=loss(on['prior'],truth);eho,exo=loss(off['x'],truth)
            neesg=diag_nees(on['x'],on['P'],truth);neeso=diag_nees(off['x'],off['P'],truth)
            df=base.copy()
            df['stratum']=st;df['monitor_state']=on['status'].astype(str);df['monitor_reason']=on['reason'].astype(str);
            for c in range(2):df[f'beta_{["r","s"][c]}']=on['beta'][:,c]
            df['legacy_accepted']=on['mask'];df['guard_damped']=ind & on['mask']
            df['score_r']=on['scores'][:,0];df['score_s']=on['scores'][:,1];df['score_joint']=on['scores'][:,2]
            df['yaw_off_deg']=np.degrees(off['x'][:,2]);df['yaw_on_deg']=np.degrees(on['x'][:,2]);df['yaw_prior_deg']=np.degrees(on['prior'][:,2])
            df['bias_off_deg_s']=np.degrees(off['x'][:,3]);df['bias_on_deg_s']=np.degrees(on['x'][:,3]);
            df['x_off_m']=off['x'][:,0];df['y_off_m']=off['x'][:,1];df['x_on_m']=on['x'][:,0];df['y_on_m']=on['x'][:,1]
            df['heading_error_off_deg']=np.degrees(wrap(off['x'][:,2]-truth[:,2]));df['heading_error_on_deg']=np.degrees(wrap(on['x'][:,2]-truth[:,2]));
            df['xy_error_off_cm']=100*np.linalg.norm(off['x'][:,:2]-truth[:,:2],axis=1)
            df['xy_error_on_cm']=100*np.linalg.norm(on['x'][:,:2]-truth[:,:2],axis=1)
            df['x_trial_unguarded_m']=expected[:,0];df['y_trial_unguarded_m']=expected[:,1];df['yaw_trial_unguarded_deg']=np.degrees(expected[:,2])
            df['guard_harm_heading_deg2']=(ehg-ehu)*((180/np.pi)**2)
            df['guard_harm_xy_cm2']=(exg-exu)*1e4
            df['B_update_harm_heading_deg2']=(ehu-ehp)*((180/np.pi)**2)
            df['B_update_harm_xy_cm2']=(exu-exp)*1e4
            df['B_unguarded_benefit_heading_deg2']=(ehp-ehu)*((180/np.pi)**2)
            df['B_unguarded_benefit_xy_cm2']=(exp-exu)*1e4
            df['heading_abs_error_prior_deg']=np.degrees(np.abs(wrap(on['prior'][:,2]-truth[:,2])))
            df['xy_error_prior_cm']=np.linalg.norm(on['prior'][:,:2]-truth[:,:2],axis=1)*100
            df['nees_off']=neeso;df['nees_on']=neesg
            df['nis_off']=off['nis'];df['nis_on']=on['nis']
            df['r_observed_m']=on['nu'][:,0]+on['h'][:,0]+on['mu'][:,0]
            df['s_observed']=on['nu'][:,1]+on['h'][:,1]+on['mu'][:,1]
            df['r_pred_off_m']=off['h'][:,0]+off['mu'][:,0];df['s_pred_off']=off['h'][:,1]+off['mu'][:,1]
            df['r_pred_on_m']=on['h'][:,0]+on['mu'][:,0];df['s_pred_on']=on['h'][:,1]+on['mu'][:,1]
            df['delta_update_yaw_off_deg']=np.degrees(wrap(off['x'][:,2]-off['prior'][:,2]))
            df['delta_update_yaw_on_deg']=np.degrees(wrap(on['x'][:,2]-on['prior'][:,2]))
            df['yaw_bias_corruption_deg_s']=np.degrees(on['x'][:,3]) # B0 true gyro bias=0, but no general claim
            # Monitor compatibility alone is NOT a correctness label.
            df['motion_rel_5s_deg']=[float(np.degrees(np.sum(gyro[max(1,k-25):k+1]))) for k in range(n)]
            df['filter_rel_5s_deg']=[float(np.degrees(wrap(off['x'][k,2]-off['x'][max(0,k-25),2]))) for k in range(n)]
            df['motion_filter_delta_5s_deg']=wrap(np.radians(df.motion_rel_5s_deg-df.filter_rel_5s_deg))*180/np.pi
            df['tap_changed_F_L']=df['B_F']!=df['B_L']
            extra.append(df)
            wide_data[(route,st)]=df
            cases[(route,st)]={'n':n, 'damped':int(df.guard_damped.sum()),'status':df.monitor_state.value_counts().to_dict(),
                         'damped_r':int((df.guard_damped & (df.beta_r<.999999)).sum()),'damped_s':int((df.guard_damped & (df.beta_s<.999999)).sum()),
                         'good_heading_immediate':int((df.guard_damped & (df.guard_harm_heading_deg2<0)).sum()),
                         'bad_heading_immediate':int((df.guard_damped & (df.guard_harm_heading_deg2>0)).sum()),
                         'good_xy_immediate':int((df.guard_damped & (df.guard_harm_xy_cm2<0)).sum()),
                         'bad_xy_immediate':int((df.guard_damped & (df.guard_harm_xy_cm2>0)).sum())}
    allx=pd.concat(extra,ignore_index=True)
    # Use only actual primary rows, exclude utility synthetic reference runs.
    assert len(allx)==3136*2
    # catalog unique (route,stratum,k) with multi-labels
    catalog={}
    def add(gr,st,ks,cat):
        df=wide_data[(gr,st)].set_index('k')
        for k in ks:
            k=int(k)
            rec=catalog.setdefault((gr,st,k),dict(route=gr,stratum=st,k=k,categories=[]))
            if cat not in rec['categories']:rec['categories'].append(cat)
    for gr in ROUTES:
      for st in STRATA:
        df=wide_data[(gr,st)].copy()
        add(gr,st,df.loc[df.guard_damped,'k'],'ACTIVE_ALL')
        # category candidates sorted, diverse in each group
        def choose(cat,mask,score,limit=8,spacing=14):
            sub=df[mask].copy()
            sub['ranking_score']=score[mask]
            add(gr,st,select_diverse(sub,'ranking_score',limit,spacing),cat)
        good=df.guard_damped & (df.guard_harm_heading_deg2<0) & (df.guard_harm_xy_cm2<0)
        bad=df.guard_damped & (df.guard_harm_heading_deg2>0) & (df.guard_harm_xy_cm2>0)
        mixed=df.guard_damped & ~good & ~bad
        choose('ACTIVE_BENEFIT_BOTH',good,-(df.guard_harm_heading_deg2.abs()+df.guard_harm_xy_cm2.abs()/200),12,1)
        choose('ACTIVE_HARM_BOTH',bad,df.guard_harm_heading_deg2.abs()+df.guard_harm_xy_cm2.abs()/200,12,1)
        choose('ACTIVE_TRADEOFF',mixed,df.guard_harm_heading_deg2.abs()+df.guard_harm_xy_cm2.abs()/200,15,1)
        # Compatible but has large physical distortion and current unguarded update makes heading worse.
        m=(df.monitor_state=='COMPATIBLE') & df.legacy_accepted
        choose('COMPATIBLE_HARM_HEADING',m & (df.B_update_harm_heading_deg2>0) & (df.e_s_mp.abs()>.03),df.B_update_harm_heading_deg2,10)
        choose('COMPATIBLE_HARM_XY',m & (df.B_update_harm_xy_cm2>0) & (df.e_s_mp.abs()>.03),df.B_update_harm_xy_cm2,10)
        choose('COMPATIBLE_CORRUPTED_S',m & (df.e_s_mp.abs()>.1),df.e_s_mp.abs(),9)
        choose('UNKNOWN_HARM_HEADING',(df.monitor_state=='UNKNOWN') & df.legacy_accepted & (df.B_update_harm_heading_deg2>0),df.B_update_harm_heading_deg2,8)
        choose('UNKNOWN_HARM_XY',(df.monitor_state=='UNKNOWN') & df.legacy_accepted & (df.B_update_harm_xy_cm2>0),df.B_update_harm_xy_cm2,8)
        choose('BENEFICIAL_FULL_HEADING',df.legacy_accepted & (df.B_update_harm_heading_deg2<0) & (df.B_unguarded_benefit_heading_deg2>0),df.B_unguarded_benefit_heading_deg2,7)
        choose('BENEFICIAL_FULL_XY',df.legacy_accepted & (df.B_update_harm_xy_cm2<0) & (df.B_unguarded_benefit_xy_cm2>0),df.B_unguarded_benefit_xy_cm2,7)
        choose('CLEAN_TAP_S_DISTORTED', (df.B_F==df.B_L) & (df.e_s_mp.abs()>.04), df.e_s_mp.abs(),7)
        choose('TAP_CHANGED_S_STABLE', (df.B_F!=df.B_L) & (df.e_s_mp.abs()<.025), (df.B_F-df.B_L).abs(),7)
        choose('LOW_NIS_HIGH_NEES', df.legacy_accepted & (df.nis_off<1) & (df.nees_off>20),df.nees_off,8)
        choose('GYRO_BIAS_EXTREME',df.k>=25,df.bias_off_deg_s.abs(),7,22)
        choose('HIGH_S_MP',df.k>=0,df.e_s_mp.abs(),7)
        choose('HIGH_R_MP',df.k>=0,df.e_r_mp_m.abs(),7)
        # transition examples - error falls from >0.1 to <0.03 within <=3 frames.
        arr=df.e_s_mp.abs().to_numpy()
        transitions=np.r_[False, (arr[1:]<.03) & (pd.Series(arr).shift(1).to_numpy()[1:]>.1)]
        choose('RF_SMALL_AFTER_LARGE',transitions,np.r_[0,arr[:-1]],5,5)
        # three 'representative' positions for each route stratum, independent of label
        add(gr,st,[max(2,int(.1*len(df))),int(.5*len(df)),min(len(df)-3,int(.9*len(df)))],'ROUTE_REFERENCE')
    selected=[]
    for i,(key,x) in enumerate(sorted(catalog.items(),key=lambda p:(p[0][0],p[0][1],p[0][2]))):
        df=wide_data[(key[0],key[1])];v=df.iloc[key[2]]
        cats=x['categories']
        primary_cat=next((s for s in ('ACTIVE_ALL','ACTIVE_HARM_BOTH','ACTIVE_TRADEOFF','ACTIVE_BENEFIT_BOTH','COMPATIBLE_HARM_HEADING','COMPATIBLE_HARM_XY','COMPATIBLE_CORRUPTED_S','UNKNOWN_HARM_HEADING','UNKNOWN_HARM_XY','LOW_NIS_HIGH_NEES','BENEFICIAL_FULL_HEADING','BENEFICIAL_FULL_XY','CLEAN_TAP_S_DISTORTED','TAP_CHANGED_S_STABLE','RF_SMALL_AFTER_LARGE','GYRO_BIAS_EXTREME','HIGH_S_MP','HIGH_R_MP','ROUTE_REFERENCE') if s in cats),'OTHER')
        selected.append({
           'id':f'{v.route}_{v.stratum}_k{int(v.k):04d}','route':v.route,'stratum':v.stratum,'k':int(v.k),'t_s':float(v.t_s),
           'categories':'|'.join(cats),'primary_category':primary_cat,'guard_status':v.monitor_state,'guard_reason':v.monitor_reason,
           'r_beta':float(v.beta_r),'s_beta':float(v.beta_s),'gate':bool(v.legacy_accepted),
           's_F':float(v.s_F),'s_L':float(v.s_L),'e_s_mp':float(v.e_s_mp),'e_r_mp_m':float(v.e_r_mp_m),
           'CIR_complex_distortion':float(v.local_complex_distortion),'full_tap':int(v.B_F),'clean_tap':int(v.B_L),
           'heading_true_deg':float(v.heading_deg),'x_true_m':float(v.x_m),'y_true_m':float(v.y_m),
           'heading_error_OFF_deg':float(v.heading_error_off_deg),'heading_error_ON_deg':float(v.heading_error_on_deg),
           'xy_error_OFF_cm':float(v.xy_error_off_cm),'xy_error_ON_cm':float(v.xy_error_on_cm),
           'gyro_increment_deg':float(np.degrees(v.gyro_increment_rad)),'true_yaw_increment_deg':float(np.degrees(v.true_yaw_increment_rad)),
           'gyro_bias_OFF_deg_s':float(v.bias_off_deg_s),
           'B_update_harm_heading_deg2':float(v.B_update_harm_heading_deg2),'B_update_harm_xy_cm2':float(v.B_update_harm_xy_cm2),
           'guard_harm_heading_deg2':float(v.guard_harm_heading_deg2),'guard_harm_xy_cm2':float(v.guard_harm_xy_cm2),
           'nees_OFF':float(v.nees_off),'nis_OFF':float(v.nis_off),
           'claim_note':'Harm of full B update is prior-vs-posterior association; does NOT prove RF is sole physical cause.'})
    listing=pd.DataFrame(selected)
    assert listing.id.is_unique
    # compact all-series data used by HTML JS: include retrospective truth separately labelled.
    important=['route','stratum','k','t_s','x_true','y_true','yaw_true_rad','x_off_m','y_off_m','x_on_m','y_on_m',
        'yaw_off_deg','yaw_on_deg','yaw_prior_deg','gyro_increment_rad','odom_distance_increment_m','true_yaw_increment_rad',
        'bias_off_deg_s','heading_error_off_deg','heading_error_on_deg','xy_error_off_cm','xy_error_on_cm',
        'B_update_harm_heading_deg2','B_update_harm_xy_cm2','guard_harm_heading_deg2','guard_harm_xy_cm2',
        'B_F','B_L','s_F','s_L','e_s_mp','e_r_mp_m','local_complex_distortion','full_peak_power0','full_peak_power1',
        'r_observed_m','s_observed','r_pred_off_m','s_pred_off','beta_r','beta_s','score_r','score_s',
        'legacy_accepted','monitor_state','monitor_reason','nis_off','nees_off','delta_update_yaw_off_deg','delta_update_yaw_on_deg']
    compact=allx[important].copy()
    listing.to_csv(arg.out/'CASE_CATALOG.csv',index=False,encoding='utf-8-sig')
    compact.to_csv(arg.out/'FULL_ENRICHED_6272.csv',index=False,encoding='utf-8-sig')
    for r in ROUTES:
       primary[primary.route==r].to_csv(arg.out/f'PRIMARY_{r}_RF_CIR_FEATURES.csv',index=False,encoding='utf-8-sig')
    def safe(v):
       if isinstance(v,(np.integer,)):return int(v)
       if isinstance(v,(np.floating,)):return float(v)
       raise TypeError(str(type(v)))
    result={
       'source_actions':42600632209,'n_trajectory_rows':3136,'two_strata_trajectory_rows':6272,
       'case_count':len(selected),'case_counts':listing.groupby(['route','stratum']).size().to_dict().__str__(),
       'guard_intervention_counts':{f'{r}|{st}':v for (r,st),v in cases.items()},'source_replay_archive_sha256':hashlib.sha256(arg.archive.read_bytes()).hexdigest(),
       'primary_csv_sha256':hashlib.sha256(arg.primary.read_bytes()).hexdigest(),
       'motion_reconstruction':audits,
       'do_not_conflate':['COMPATIBLE with clean','UNKNOWN with clean','full B update harm with RF-only causation',
                           'model-ideal recovery stress with measured clean CIR','raw gyro integrated aligned to GT with online ground truth'],
       'caveats':['The raw gy and ds come from inversion of the pinned predictor, not direct inspection of released online NPZ.',
                  'All 3136 rows originate from one exposed corridor B0 Full seed10; no independent noise scene evidence.',
                  'Online filter did not have access to evaluator true pose or clean s; these are retrospective plot layers.',
                  'B_MCG numerical trials in action are not policy adoption.']}
    (arg.out/'CASE_AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=safe)+'\n',encoding='utf-8')
    print('CASE_AUDIT',json.dumps({'selected':len(selected),'by_route_stratum':{f'{r}|{st}':int(v) for (r,st),v in listing.groupby(['route','stratum']).size().items()},'status':{f'{r}|{st}':v for (r,st),v in cases.items()},'motion_parity':audits},ensure_ascii=False,default=safe,indent=2))

if __name__=='__main__':main()
