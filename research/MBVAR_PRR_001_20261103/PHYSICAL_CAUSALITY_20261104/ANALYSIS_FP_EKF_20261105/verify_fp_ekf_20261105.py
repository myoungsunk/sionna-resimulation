#!/usr/bin/env python3
"""Nonindependent explanatory audit: PR36 original per-pose FP/CIR and historical POWER1 traces.

Inputs: locally extracted GitHub Actions artifacts
  PR36 #41958274374 shard-0 / shard-2 (selected_pr36/output_0,output_2),
  C0-A #41783949902, original separate-rs replay #39376076166 (R4/R5).
Does not perform Sionna-RT nor refit the source model; no optimizer or GT online.
"""
from pathlib import Path
import argparse, json, hashlib, math
import numpy as np
import pandas as pd

C=299792458.0

def signed_s(cir, tap):
    p=np.abs(cir[int(tap),:])**2
    return float((p[0]-p[1])/(p[0]+p[1]))

def original_fp(H, freq):
    n=len(freq); w=.5-.5*np.cos(2*np.pi*np.arange(n)/(n-1))
    pad=np.zeros((n*4,2),np.complex128); pad[:n,:]=H[:,:,0]*w[:,None]
    cir=np.fft.ifft(pad,axis=0)*n
    m=np.abs(cir); ch=np.argmax(m.max(axis=0)); peak=m[:,ch].max()
    tap=int(np.argmax(m[:,ch]>=.3*peak))
    df=float(freq[1]-freq[0]);rng=tap/(n*4*df)*C
    return cir,tap,signed_s(cir,tap),rng

def calc_fp(root, df_ref):
    root=Path(root)
    paths={}
    for p in root.rglob('FIRST_PATH.npz'):
        name=p.parent.name
        for suff in ('_Full','_LoS'):
            if name.endswith(suff):
                key=name[:-len(suff)]; paths.setdefault(key,{})[suff[1:]]=p
    out=[];check={'pairs':0,'max_h_to_cir':0.,'max_s_receipt':0.,'max_range_receipt_m':0.,'max_algebra_residual':0.,'max_abs_full_orig_s':0.,'max_abs_los_orig_s':0.,'max_abs_full_orig_range_m':0.,'max_abs_los_orig_range_m':0.,'orig_index_mismatch':0}
    old={(v.route,int(v.pose_id)):v for v in df_ref.itertuples(index=False)}
    for key,mp in paths.items():
        if set(mp)!={'Full','LoS'}: continue
        route=key[:2];pose=int(key.split('_')[-1]); r=old[(route,pose)]
        d={}
        for mode,p in mp.items():
            z=np.load(p,allow_pickle=False);raw=np.load(p.with_name('RAW_H.npz'),allow_pickle=False)
            cir,tap,s,rng=original_fp(raw['H'],raw['frequency'])
            check['max_h_to_cir']=max(check['max_h_to_cir'],float(np.max(abs(cir-raw['cir'][0]))))
            check['max_s_receipt']=max(check['max_s_receipt'],abs(s-float(z['observed_s'][0])))
            check['max_range_receipt_m']=max(check['max_range_receipt_m'],abs(rng-float(z['observed_range_m'][0])))
            assert tap==int(z['observed_index'][0]),(key,mode,tap,z['observed_index'][0])
            d[mode]={'cir':cir,'tap':tap,'s':s,'r':rng}
        f,l=d['Full'],d['LoS'];same=signed_s(f['cir'],l['tap'])-l['s'];selection=f['s']-signed_s(f['cir'],l['tap']);total=f['s']-l['s'];res=abs(total-same-selection)
        check['max_algebra_residual']=max(check['max_algebra_residual'],res)
        check['max_abs_full_orig_s']=max(check['max_abs_full_orig_s'],abs(f['s']-float(r.s_full)))
        check['max_abs_los_orig_s']=max(check['max_abs_los_orig_s'],abs(l['s']-float(r.s_los)))
        check['max_abs_full_orig_range_m']=max(check['max_abs_full_orig_range_m'],abs(f['r']-float(r.range_full_m)))
        check['max_abs_los_orig_range_m']=max(check['max_abs_los_orig_range_m'],abs(l['r']-float(r.range_los_m)))
        check['orig_index_mismatch']+=int(f['tap']!=int(r.fp_full) or l['tap']!=int(r.fp_los))
        out.append({'key':key,'route':route,'pose_id':pose,'t_s':float(r.t_s),'tap_full':f['tap'],'tap_los':l['tap'],'delta_tap':f['tap']-l['tap'],'s_full':f['s'],'s_los':l['s'],'s_full_at_los_tap':signed_s(f['cir'],l['tap']),'total_delta_s':total,'same_tap_delta_s':same,'tap_selection_delta_s':selection,'range_full_m':f['r'],'range_los_m':l['r'],'delta_range_m':f['r']-l['r'],'s_original_delta':f['s']-float(r.s_full),'s_los_original_delta':l['s']-float(r.s_los),'fp_original_same':bool(f['tap']==int(r.fp_full) and l['tap']==int(r.fp_los))})
        check['pairs']+=1
    x=pd.DataFrame(out).sort_values(['route','pose_id']).reset_index(drop=True)
    assert check['pairs']>0 and check['max_algebra_residual']<1e-12
    assert check['max_s_receipt']<1e-12 and check['max_range_receipt_m']<1e-9
    assert check['orig_index_mismatch']==0
    return x,check

def e_deg(z,gt):return float(np.degrees((z-gt+np.pi)%(2*np.pi)-np.pi))

def ekf_trace(replay_dir, route, selected):
    root=Path(replay_dir)
    out=[];one=[];summaries=[]
    oldorig=sorted(root.glob(f'{route}_aB_m0_full_B0_UPDATE_ORIGINS.csv.gz'))
    assert len(oldorig)==1
    diag=pd.read_csv(oldorig[0]);
    for mode in ['full','los']:
        tr=np.load(root/f'{route}_aB_m0_{mode}_B0_TRACE.npz',allow_pickle=False)
        arms={str(a):i for i,a in enumerate(tr['arms'])}
        for arm in ['JOINT4','POWER1','POWER_DIAG']:
            j=arms[arm];truth=tr['truth_scoring_only'][:,2]
            e=(tr['state'][:,j,2]-truth+np.pi)%(2*np.pi)-np.pi
            sig=np.sqrt(tr['cov'][:,j,2,2]);nis=tr['nis'][:,j]
            mask=tr['t_s']>=30
            summaries.append({'route':route,'mode':mode,'arm':arm,'n_scored':int(mask.sum()),'heading_rmse_deg':float(np.degrees(np.sqrt(np.mean(e[mask]**2)))),'heading_sigma_mean_deg':float(np.degrees(sig[mask]).mean()),'heading95':float(np.mean((e[mask]/sig[mask])**2<=3.841458820694124)),'heading_nees_mean':float(np.mean((e[mask]/sig[mask])**2)),'accepted_fraction':float(tr['accepted'][mask,j].mean())})
            for k in selected:
                if k >=len(tr['t_s']):continue
                out.append({'route':route,'mode':mode,'arm':arm,'pose_id':k,'t_s':float(tr['t_s'][k]),'accepted':bool(tr['accepted'][k,j]),'nis':float(nis[k]),'heading_error_deg':e_deg(tr['state'][k,j,2],truth[k]),'sigma_deg':float(np.degrees(sig[k])),'nees_heading':float((e[k]/sig[k])**2)})
    full=np.load(root/f'{route}_aB_m0_full_B0_TRACE.npz',allow_pickle=False);j=list(full['arms']).index('POWER1')
    for row in selected:
        if row>=len(full['t_s']):continue
        hit=diag[(diag.model=='POWER1') & np.isclose(diag.t_s,full['t_s'][row],rtol=0,atol=1e-8)]
        if len(hit)!=1: continue
        e=hit.iloc[0]
        kr=float(e.range_to_yaw_deg/e.r_nu) if abs(e.r_nu)>1e-9 else np.nan
        ks=float(e.s_to_yaw_deg/e.s_nu) if abs(e.s_nu)>1e-9 else np.nan
        assert bool(e.joint_accept)==bool(full['accepted'][row,j]),(route,row)
        one.append({'route':route,'pose_id':row,'t_s':float(e.t_s),'joint_accept':bool(e.joint_accept),'nis':float(e.joint_nis),'K_psi_r_deg_per_m':kr,'K_psi_s_deg_per_s':ks,'nu_r':float(e.r_nu),'nu_s':float(e.s_nu),'contribution_r_deg':float(e.range_to_yaw_deg),'contribution_s_deg':float(e.s_to_yaw_deg),'heading_error_full_deg':e_deg(full['state'][row,j,2],full['truth_scoring_only'][row,2]),'sigma_full_deg':float(np.degrees(np.sqrt(full['cov'][row,j,2,2])))})
    return pd.DataFrame(out),pd.DataFrame(one),pd.DataFrame(summaries)

def main():
    p=argparse.ArgumentParser();p.add_argument('--data',default='/mnt/data');p.add_argument('--out',default='/mnt/data/fp_ekf_verification');a=p.parse_args()
    root=Path(a.data);dest=Path(a.out);dest.mkdir(parents=True,exist_ok=True)
    ref=pd.read_csv(root/'c0a/c0a_outputs/C0A_AGGREGATE_TAP_DECOMPOSITION.csv')
    fp,qa=calc_fp(root/'selected_pr36',ref)
    fp.to_csv(dest/'PR36_FP_77_PAIRED.csv',index=False,float_format='%.15g')
    summaries=[];one=[];traces=[]
    for route in ['R4','R5']:
        ids=fp[fp.route==route].pose_id.to_list()
        df,oo,summary=ekf_trace(root/f'replay_{route.lower()}',route,ids)
        traces.append(df);one.append(oo);summaries.append(summary)
    e=pd.concat(traces,ignore_index=True);e.to_csv(dest/'HISTORICAL_EKF_TRACE_AT_PR36_POSES.csv',index=False,float_format='%.15g')
    o=pd.concat(one,ignore_index=True);o.to_csv(dest/'PR36_FIXED_PRIOR_POWER1_UPDATE.csv',index=False,float_format='%.15g')
    summ=pd.concat(summaries,ignore_index=True);summ.to_csv(dest/'HISTORICAL_EKF_SUMMARY.csv',index=False,float_format='%.15g')
    joined=fp.merge(o,on=['route','pose_id','t_s'],how='inner',validate='one_to_one')
    for label,key,value in [('tap_fixed','K_psi_s_deg_per_s','tap_selection_delta_s'),('s_los','K_psi_s_deg_per_s','total_delta_s'),('r_los','K_psi_r_deg_per_m','delta_range_m')]:
        joined['delta_heading_'+label+'_deg']=-joined[key]*joined[value]
    joined['delta_heading_both_los_deg']=joined['delta_heading_s_los_deg']+joined['delta_heading_r_los_deg']
    # A detector tap relocation changes BOTH s sampled at the tap and FP-derived range.
    # Keep the tap-only-s arm separate as a preprocessing diagnostic.
    joined['delta_heading_tap_and_range_deg']=joined['delta_heading_tap_fixed_deg']+joined['delta_heading_r_los_deg']
    joined['estimated_error_tap_and_range_deg']=joined['heading_error_full_deg']+joined['delta_heading_tap_and_range_deg']*joined['joint_accept'].astype(float)
    for label in ['tap_fixed','s_los','r_los','both_los']:
        joined['estimated_error_'+label+'_deg']=joined['heading_error_full_deg']+joined['delta_heading_'+label+'_deg']*joined['joint_accept'].astype(float)
    joined['heading_nees_full']=np.square(joined['heading_error_full_deg']/joined['sigma_full_deg'])
    joined['heading_nees_both_los_frozen_gain']=np.square(joined['estimated_error_both_los_deg']/joined['sigma_full_deg'])
    # Fixed-K update: P remains constant for accepted arms by Joseph algebra. Not a self-gated or recursive contrast.
    joined.to_csv(dest/'PR36_C1_FROZEN_K_YAW_EFFECT.csv',index=False,float_format='%.15g')
    pairs=fp.groupby('route').apply(lambda d:pd.Series({'n_pairs':len(d),'changed_tap':int((d.delta_tap!=0).sum()),'large_abs_s_gt_0p10':int((d.total_delta_s.abs()>.1).sum()),'changed_and_large':int(((d.delta_tap!=0)&(d.total_delta_s.abs()>.1)).sum()),'nochange_and_large':int(((d.delta_tap==0)&(d.total_delta_s.abs()>.1)).sum()),'rms_total_delta_s':float(np.sqrt(np.mean(d.total_delta_s**2))),'rms_selection':float(np.sqrt(np.mean(d.tap_selection_delta_s**2))),'max_abs_total_delta_s':float(d.total_delta_s.abs().max())}),include_groups=False).reset_index()
    pairs.to_csv(dest/'PR36_FP_SUMMARY.csv',index=False,float_format='%.15g')
    met={'source':'#41958274374 PR36 shards 0 and 2; C0A #41783949902; historical #39376076166 POWER1/B0','c0':qa,'counts_by_route':pairs.to_dict(orient='records'),'fixed_prior_overlap':{'n':len(joined),'accepted':int(joined.joint_accept.sum()),'r4_0':joined[(joined.route=='R4')&(joined.pose_id==0)].to_dict(orient='records'),'r4_497':joined[(joined.route=='R4')&(joined.pose_id==497)].to_dict(orient='records'),'r5_674':joined[(joined.route=='R5')&(joined.pose_id==674)].to_dict(orient='records')},'status':'EXPLORATORY_REANALYSIS_NOT_FULL_C1_C2_VALIDATION','limits':['77 paired samples from shards 0/2 only, not the full 190 poses or full 400 tasks','Historical POWER1/B0 EKF uses original composite H and different physical solver precision than new per-ray reconstruction. Frozen K difference is local linearized perturbation; not a new EKF replay','Samples preselected from time windows; not independent holdout','Natural Full and LoS traces have distinct recursive priors; difference not a controlled single-event causal estimate','FP shift vs LoS detector is a proxy for changed detector choice, not proof of an incorrect physical direct-path pick']}
    (dest/'QA_SUMMARY.json').write_text(json.dumps(met,indent=2,ensure_ascii=False,allow_nan=False))
    print('C0 QA',qa)
    print('\nSUMMARY:\n',pairs.to_string(index=False))
    print('\nFIXED PRIOR SELECTED:\n',joined.loc[((joined.route=='R4')&(joined.pose_id.isin([0,520])))|((joined.route=='R5')&(joined.pose_id==674)),['route','pose_id','delta_tap','total_delta_s','same_tap_delta_s','tap_selection_delta_s','K_psi_s_deg_per_s','K_psi_r_deg_per_m','delta_heading_tap_fixed_deg','delta_heading_s_los_deg','delta_heading_r_los_deg','delta_heading_both_los_deg','heading_error_full_deg','estimated_error_both_los_deg','sigma_full_deg','joint_accept']].to_string(index=False))
    print('\nTOP FP SHIFT:\n',joined.loc[joined.delta_tap!=0].sort_values('delta_heading_tap_fixed_deg',key=lambda s:s.abs(),ascending=False)[['route','pose_id','t_s','delta_tap','tap_selection_delta_s','K_psi_s_deg_per_s','delta_heading_tap_fixed_deg','joint_accept']].head(12).to_string(index=False))
    print('\nHISTORICAL SUMMARY:\n',summ.to_string(index=False))

if __name__=='__main__':main()
