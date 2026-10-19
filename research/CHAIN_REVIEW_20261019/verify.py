"""Independent post-run scorer and targeted hypothesis review.
Does not load the inference engine. Physical truth used only for scoring.
"""
from pathlib import Path
import json,hashlib,zipfile,io,sys
import numpy as np,pandas as pd
from scipy.spatial import cKDTree
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import roc_auc_score
ROOT=Path(sys.argv[1]);OUT=ROOT/'review';OUT.mkdir(exist_ok=True)
def wrap(x):return np.arctan2(np.sin(x),np.cos(x))
def write(n,rows):pd.DataFrame(rows).to_csv(OUT/n,index=False)
def c(a,b):
    return float(np.corrcoef(a,b)[0,1]) if len(a)>3 and np.std(a)>1e-10 and np.std(b)>1e-10 else None
refs={('R2_aA_m0',0.,'POWER1'):1.7989100455630698,('R2_aA_m0',0.,'JOINT4'):7.930101308687917,('R2_aA_m45',0.,'POWER1'):0.9826339362129952,('R2_aA_m45',0.,'JOINT4'):1.006306679285617,('R2_aA_m0',.05,'POWER1'):1.7950025124097089,('R2_aA_m0',.05,'POWER_SR4'):1.7068653544117791,('R5_aA_m0',0.,'POWER1'):4.556146,('R5_aB_m0',0.,'POWER1'):1.056234,('R4_aA_m0',0.,'POWER1'):.658932,('R4_aB_m0',0.,'POWER1'):1.508341}
score=pd.read_csv(ROOT/'EVALUATION_METRICS.csv');params=pd.read_csv(ROOT/'OOF_PARAMETERS.csv.gz');events={x['case']:x['index_range'] for x in json.loads((ROOT/'EVENTS.json').read_text())}
qa=[];baseline=[];effects=[];p4=[];conditional=[];geometry=[];onsets=[]
levels={'B0':0.,'L0':.01,'L1':.05,'L2':.20}
for f in sorted((ROOT/'traces').glob('*.npz')):
    cid,label=f.stem.rsplit('_',1);bias=levels[label]
    with np.load(f,allow_pickle=False) as v:a={k:v[k] for k in v.files}
    t=a['t'];truth=a['truth_for_offline_scoring_only'];names=list(a['names']);mask=t>=30
    e=wrap(a['state'][:,:,2]-truth[:,None,2]);sigma=np.sqrt(a['cov'][:,:,2,2]);z=e/sigma
    for j,name in enumerate(names):
        ref=score[(score['case']==cid)&(np.isclose(score.bias_dps,bias))&(score.method==name)].iloc[0]
        vals={'heading_rmse_deg':float(np.degrees(np.sqrt(np.mean(e[mask,j]**2)))),'heading_nees':float(np.mean(z[mask,j]**2)),'heading95':float(np.mean(abs(z[mask,j])<=1.959963984540054)),'signed_heading_deg':float(np.degrees(e[mask,j].mean()))}
        err=max(abs(vals[k]-float(ref[k])) for k in vals)
        qa.append(dict(file=f.name,method=name,score_max_error=err,min_eigenvalue=float(np.linalg.eigvalsh(a['cov'][:,j]).min())))
        key=(cid,bias,str(name))
        if key in refs:baseline.append(dict(case=cid,bias=bias,method=name,previous=refs[key],now=vals['heading_rmse_deg'],abs_difference=abs(refs[key]-vals['heading_rmse_deg'])))
    j=names.index('POWER1');jf=names.index('POWER_MEMORY');event=events[cid]
    if event is not None:
        start,end=event
        for base,prefix in [('POWER1','POWER'),('JOINT4','JOINT4')]:
            j0=names.index(base)
            for suffix in ['LOCAL_DROP','LOCAL_KEEP']:
                key=prefix+'_'+suffix
                if key not in names:continue
                k=names.index(key);post=np.arange(len(t))>=end
                effects.append(dict(case=cid,bias=bias,method=key,start=start,end=end,t_start=float(t[start]),t_end=float(t[min(end,len(t)-1)]),identical_prefix_state_max=float(np.max(abs(a['state'][:start,k,:4]-a['state'][:start,j0,:4]))) if start else 0.,identical_prefix_cov_max=float(np.max(abs(a['cov'][:start,k,:4,:4]-a['cov'][:start,j0,:4,:4]))) if start else 0.,after_rmse_base=float(np.degrees(np.sqrt(np.mean(e[post,j0]**2)))) if post.any() else None,after_rmse_new=float(np.degrees(np.sqrt(np.mean(e[post,k]**2)))) if post.any() else None,after_heading95_base=float(np.mean(abs(z[post,j0])<=1.95996398454)) if post.any() else None,after_heading95_new=float(np.mean(abs(z[post,k])<=1.95996398454)) if post.any() else None))
    frame=params[(params['case']==cid)&(params.channel=='full')].set_index('pose_id').loc[a['pose_id']]
    if label=='B0':
        # Four action policies, exactly same POWER prior, H, raw packet and quality score.
        X=a['prior'][:,j,:4];P=a['prior_cov'][:,j,:4,:4];H=a['H'][:,j,:,:4];h=a['h'][:,j];raw=a['observations'];mu=frame[['mu_r','mu_s']].to_numpy()
        C=np.zeros((len(t),2,2));C[:,0,0]=frame.C00;C[:,1,1]=frame.C11;C[:,0,1]=C[:,1,0]=frame.C01
        R0=np.repeat(np.diag([.0068578637,.0081])[None],len(t),axis=0);ep=wrap(X[:,2]-truth[:,2]);loss={};allow={}
        for act,mean,R in [('JOINT4',np.zeros_like(mu),R0),('MEAN_ONLY',mu,R0),('COV_ONLY',np.zeros_like(mu),C),('POWER1',mu,C)]:
            nu=raw-mean-h;S=H@P@H.transpose(0,2,1)+R;K=np.linalg.solve(S,H@P).transpose(0,2,1);N=np.einsum('ni,ni->n',nu,np.linalg.solve(S,nu[...,None])[...,0]);ok=N<=9.210340371976184
            delta=np.einsum('nij,nj->ni',K,nu)[:,2];post=wrap(ep+np.where(ok,delta,0.));loss[act]=post**2;allow[act]=ok
        risk=frame.risk.to_numpy();choose_power=risk>=.5;power_better=loss['POWER1']<loss['JOINT4'];Nmask=mask&(~choose_power)
        p4.append(dict(case=cid,n=int(mask.sum()),low_risk=int(Nmask.sum()),low_risk_but_power_better=int(np.sum(Nmask&power_better)),high_risk_but_base_better=int(np.sum(mask&choose_power&(~power_better))),same_prior_power_rmse=float(np.degrees(np.sqrt(loss['POWER1'][mask].mean()))),same_prior_hard_rmse=float(np.degrees(np.sqrt(np.where(choose_power,loss['POWER1'],loss['JOINT4'])[mask].mean()))),risk_auc_for_power_utility=float(roc_auc_score(power_better[mask],risk[mask])) if len(np.unique(power_better[mask]))>1 else None))
        # Posterior correlation diagnoses confounding, not proof of structural observability.
        Pm=a['cov'][:,jf];rho_pb=Pm[:,2,4:]/np.sqrt(Pm[:,2,2,None]*np.diagonal(Pm[:,4:,4:],axis1=1,axis2=2));rho_gb=Pm[:,3,4:]/np.sqrt(Pm[:,3,3,None]*np.diagonal(Pm[:,4:,4:],axis1=1,axis2=2))
        geometry.append(dict(case=cid,max_abs_heading_RFbias_correlation=float(abs(rho_pb[mask]).max()),median_max_abs_heading_RFbias_correlation=float(np.median(abs(rho_pb[mask]).max(axis=1))),max_abs_gyro_RFbias_correlation=float(abs(rho_gb[mask]).max())))
        for method in ['JOINT4','POWER1','POWER_MEMORY']:
            jj=names.index(method);ee=np.degrees(e[:,jj]);pred=wrap(a['prior'][:,jj,2]-truth[:,2]);d=np.degrees(a['proposal_dpsi'][:,jj]);used=a['accepted'][:,jj]
            dt=a['controls_dt'];dy=a['controls_dyaw'];phys=np.hypot(truth[:,0]-float(frame.anchor_x_feature.iloc[0]*10),truth[:,1])
            sectors=np.floor((np.degrees(truth[:,2])+45*frame.mount_feature.iloc[0]+180)%360/45).astype(int);rad=np.digitize(phys,[1,3,6,10])
            for r in np.unique(rad):
                for sec in np.unique(sectors):
                    use=mask&(rad==r)&(sectors==sec)
                    if use.sum()<10:continue
                    onsets.append(dict(case=cid,method=method,rho_bin=int(r),antenna_sector45=int(sec),n=int(use.sum()),signed_deg=float(ee[use].mean()),rmse_deg=float(np.sqrt(np.mean(ee[use]**2))),heading95=float(np.mean(abs(z[use,jj])<1.95996398454)),accepted_fraction=float(used[use].mean()),accepted_heading_increment_rms_deg=float(np.sqrt(np.mean(np.where(used,d,0)[use]**2))),gyro_increment_rms_deg=float(np.degrees(np.sqrt(np.mean(dy[use]**2))))))
# Training-only richer instantaneous means versus original one-feature POWER mean.
full=params[params.channel=='full'].copy();features=['log_fp_power','early4','early8','early16','delay_rms_ns','peak_diff_ns','eta_fp_win80','s_diff4','s_diff8','s_diff16','tap_pol_var80','jones_diversity','freq_s_var','detector_s_span','detector_delay_span_ns','mount_feature','anchor_x_feature']
for held in ['R2','R4','R5']:
    te=full.route==held;test=full.loc[te].copy();train=full.loc[~te].copy();dd=cKDTree(test[['x_eval','y_eval']]).query(train[['x_eval','y_eval']])[0];train=train.loc[dd>1e-4]
    predicted=[]
    for target in ['e_r','e_s']:
        model=HistGradientBoostingRegressor(max_iter=120,max_leaf_nodes=15,l2_regularization=1.,learning_rate=.05,random_state=42)
        model.fit(train[features],train[target]);predicted.append(model.predict(test[features]))
    for k,(target,base) in enumerate([('e_r','mu_r'),('e_s','mu_s')]):
        r0=test[target].to_numpy()-test[base].to_numpy();r1=test[target].to_numpy()-predicted[k]
        for cid,idx in test.groupby('case').indices.items():
            old=r0[idx];new=r1[idx]
            conditional.append(dict(case=cid,target=target,n=len(idx),old_rmse=float(np.sqrt(np.mean(old**2))),expanded_feature_rmse=float(np.sqrt(np.mean(new**2))),old_lag1=c(old[:-1],old[1:]),expanded_lag1=c(new[:-1],new[1:]),test='observation residual only, NOT recursive performance; measured features no GT inputs'))
write('INDEPENDENT_SCORE_QA.csv',qa);write('HISTORICAL_BASELINE_PARITY.csv',baseline);write('LOCAL_CAUSAL_EFFECTS.csv',effects);write('P4_TARGET_ACTION_MISMATCH.csv',p4);write('RFBIAS_STATE_COUPLING.csv',geometry);write('PHYSICAL_SECTOR_HEADING.csv',onsets);write('RICHER_INSTANTANEOUS_MEAN_TEST.csv',conditional)
summary={'scored_trace_files':len(list((ROOT/'traces').glob('*.npz'))),'scored_method_rows':len(qa),'max_score_error':max(x['score_max_error'] for x in qa),'minimum_cov_eigenvalue':min(x['min_eigenvalue'] for x in qa),'max_historical_heading_difference':max(x['abs_difference'] for x in baseline),'local_identical_prefix_state_max':max((x['identical_prefix_state_max'] for x in effects),default=0),'local_identical_prefix_cov_max':max((x['identical_prefix_cov_max'] for x in effects),default=0),'P4_policy_results':p4,'richer_mean_results':conditional,'coupling':geometry}
(OUT/'REVIEW_SUMMARY.json').write_text(json.dumps(summary,indent=2));print('REVIEW_SUMMARY',json.dumps(summary),flush=True)
print('LOCAL_EFFECTS',json.dumps(effects),flush=True)
# Compact main B0 comparison for in-chat evidence and review.
keep=['JOINT4','POWER1','POWER_INDEPENDENT','POWER_MEMORY','POWER_MEMORY_NO_CROSS','POWER_ITERATED','P4_HARD_RECONSTRUCTED','P4_MEAN_SWITCH_ONLY','P4_COV_SWITCH_ONLY','POWER_SR4']
v=score[(score.bias_dps==0)&score.method.isin(keep)][['case','method','signed_heading_deg','heading_rmse_deg','heading_sigma_rms_deg','heading95','heading_nees','bias_rmse_dps']]
v.to_csv(OUT/'KEY_B0_RESULTS.csv',index=False);print('KEY_B0_RESULTS',v.to_json(orient='records'),flush=True)
print('MODEL_COMPARISON',pd.read_csv(ROOT/'MODEL_COMPARISON.csv').to_json(orient='records'),flush=True)
