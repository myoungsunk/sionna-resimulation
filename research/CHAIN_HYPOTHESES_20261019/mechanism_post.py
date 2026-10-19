"""Offline causal diagnostics from completed inference, never a new GT-driven policy."""
from pathlib import Path
import argparse,json,hashlib
import numpy as np
import pandas as pd

def w(x):return np.arctan2(np.sin(x),np.cos(x))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--delivery',required=True);ap.add_argument('--model',required=True);ap.add_argument('--out',required=True);args=ap.parse_args()
    delivery=Path(args.delivery);model=Path(args.model);out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    onset=[];events=[];attribution=[];gate=[];qa=[];local=[];tfits=[]
    rawdensity=pd.read_csv(model/'DENSITY_DIAGNOSTICS.csv');rawdensity.to_csv(out/'STATIC_DENSITY_AND_SERIAL_ERROR.csv',index=False)
    for p in delivery.rglob('*_TRACE.npz'):
        fields=p.stem.split('_');cid='_'.join(fields[:3]);level=fields[3]
        with np.load(p,allow_pickle=False) as z:a={k:z[k] for k in z.files}
        with np.load(model/(cid+'_full.npz'),allow_pickle=False) as z:d={k:z[k] for k in z.files}
        if not np.array_equal(a['pose_id'],d['pose_id']):raise ValueError('Pose ID mismatch')
        t=a['t'];truth=a['truth_offline'];arms=a['arms'].tolist();n=len(t)
        event=json.loads((p.parent/(level+'_EVENT.json')).read_text());first,last=event['start'],event['end']
        cfg=json.loads((p.parent/'TRAIN_TEMPORAL_ACTUAL_CLOCK.json').read_text())
        if level=='B0':
            tp=cfg['temporal'];tfits.append({'case':cid,'a_ref':tp['a_ref'],'fraction':tp['f'],'dt_s':tp['dt_ref'],'tau_seconds':float(-tp['dt_ref']/np.log(tp['a_ref'])),'training_rho1_range':tp['rho1_whitened'][0],'training_rho1_s':tp['rho1_whitened'][1]})
        for j,arm in enumerate(arms):
            err=np.rad2deg(w(a['state'][:,j,2]-truth[:,2]));prior=np.rad2deg(w(a['prior_state'][:,j,2]-truth[:,2]));sigma=np.rad2deg(np.sqrt(a['cov'][:,j,2,2]));proposed=prior+np.rad2deg(a['proposal'][:,j,2]);acc=a['accepted'][:,j]
            # Nonlinear sequential/iterated proposals in stored diagnostics are NOT total updates.
            exact=arm not in ['POWER_SR4','POWER_IEKF']
            if exact:
                afterproposal=np.rad2deg(w(np.radians(proposed)));losschange=afterproposal**2-prior**2
                gate.append({'case':cid,'bias':level,'arm':arm,'rejected_fraction':float((~acc[t>=30]).mean()),'accepted_harmful_fraction':float((acc[t>=30]&(losschange[t>=30]>1e-10)).mean()),'rejected_helpful_fraction':float(((~acc[t>=30])&(losschange[t>=30]<-1e-10)).mean()),'mean_loss_change_if_all_accepted':float(losschange[t>=30].mean()),'recovery_count':int(a['recovery'][:,j].sum())})
            if arm in ['JOINT4','POWER1','MEM_RS','MEM_R','MEM_S','POWER_RECOVERY']:
                flag=(abs(err)>2)&(abs(err)>1.95996398454*sigma)
                starts=np.flatnonzero(flag&~np.r_[False,flag[:-1]]);ends=np.flatnonzero(flag&~np.r_[flag[1:],False])+1
                found=[(u,v) for u,v in zip(starts,ends) if v-u>=5]
                for ix,(u,v) in enumerate(found):
                    onset.append({'case':cid,'bias':level,'arm':arm,'episode':ix,'start_frame':int(u),'end_frame':int(v),'x':float(truth[u,0]),'y':float(truth[u,1]),'heading_deg':float(np.rad2deg(truth[u,2])),'distance':float(d['feature_distance'][u]),'relative_yaw_deg':float(np.rad2deg(d['feature_relative_yaw'][u])),'gpsi':float(d['feature_gpsi'][u]),'detector_s_span':float(d['feature_detector_s_span'][u]),'delta_r':float(d['z'][u,0]-d['z_los'][u,0]),'delta_s':float(d['z'][u,1]-d['z_los'][u,1]),'prior_error_deg':float(prior[u]),'post_error_deg':float(err[u]),'sigma_deg':float(sigma[u]),'peak_error_deg':float(abs(err[u:v]).max()),'frames':int(v-u),'starts_before_local_event':bool(u<first),'time_is_index_only':float(t[u])})
                beta=np.einsum('nij,nj->ni',a['B'][:,j],a['prior_state'][:,j,4:])
                hnav=a['h_pred'][:,j]-beta
                components={'multipath':d['z']-d['z_los'],'los_model':d['z_los']-d['h_truth'],'mean_correction':-a['mu'][:,j],'prior_error':d['h_truth']-hnav,'memory':-beta}
                closure=np.max(abs(sum(components.values())-a['innovation'][:,j]));qa.append({'case':cid,'bias':level,'arm':arm,'innovation_closure_max':float(closure)})
                masks={'evaluation':t>=30}
                if first<n:masks.update(event=(np.arange(n)>=first)&(np.arange(n)<last),after=np.arange(n)>=last)
                for scope,m in masks.items():
                    if not m.any():continue
                    for part,v in components.items():
                        term=np.rad2deg(a['K'][:,j,2,:]*v)*acc[:,None]
                        attribution.append({'case':cid,'bias':level,'arm':arm,'scope':scope,'component':part,'range_heading_sum_deg':float(term[m,0].sum()),'s_heading_sum_deg':float(term[m,1].sum()),'rms_heading_step_deg':float(np.sqrt(np.mean(term[m].sum(1)**2))),'scope_count':int(m.sum()),'note':'exact realized-update decomposition, not additive counterfactual total-effect shares'})
            if first<n and arm in ['POWER1','LOCAL_MEM_KEEP','LOCAL_MEM_DROP','LOCAL_RICH','LOCAL_PLACEBO']:
                events.append({'case':cid,'bias':level,'arm':arm,'start_frame':first,'end_frame':last,'frames':last-first,'duration_s':float(t[min(last,n-1)]-t[first]),'x_start':float(truth[first,0]),'y_start':float(truth[first,1]),'relative_angle_start_deg':float(np.rad2deg(d['feature_relative_yaw'][first])),'distance_start':float(d['feature_distance'][first]),'gpsi_start':float(d['feature_gpsi'][first]),'prior_heading_error_deg':float(prior[first]),'posterior_at_event_end_deg':float(err[last-1]),'sigma_at_event_end_deg':float(sigma[last-1]),'next_heading_correction_deg':float(np.rad2deg(a['proposal'][last,j,2])) if last<n else None,'after_rmse_deg':float(np.sqrt(np.mean(err[last:]**2))) if last<n else None,'gate_changes_during_event_vs_POWER':int(np.sum(acc[first:last]!=a['accepted'][first:last,arms.index('POWER1')])),'gate_changes_after_vs_POWER':int(np.sum(acc[last:]!=a['accepted'][last:,arms.index('POWER1')]))})
        baseline=arms.index('POWER1');white=arms.index('MEM_WHITE')
        xa=a['state'][:,baseline,:4]-a['state'][:,white,:4];xa[:,2]=w(xa[:,2])
        qa.append({'case':cid,'bias':level,'arm':'WHITE_PATH_EQUIVALENCE','state_max':float(abs(xa).max()),'cov_max':float(abs(a['cov'][:,baseline,:4,:4]-a['cov'][:,white,:4,:4]).max()),'gate_differences':int(np.sum(a['accepted'][:,baseline]!=a['accepted'][:,white]))})
    pd.DataFrame(onset).to_csv(out/'ERROR_ONSET_PHYSICAL_CONDITIONS.csv',index=False)
    pd.DataFrame(events).to_csv(out/'LOCAL_EVENT_CHAIN.csv',index=False)
    pd.DataFrame(attribution).to_csv(out/'REALIZED_HEADING_CHAIN_COMPONENTS.csv',index=False)
    pd.DataFrame(gate).to_csv(out/'GATE_USEFULNESS_OFFLINE.csv',index=False)
    pd.DataFrame(tfits).to_csv(out/'ACTUAL_CLOCK_TEMPORAL_PARAMETERS.csv',index=False)
    (out/'MECHANISM_QA.json').write_text(json.dumps(qa,indent=2))
    ev=pd.DataFrame(events);on=pd.DataFrame(onset)
    print('TEMPORAL_PARAMETERS',json.dumps(tfits),flush=True)
    print('EVENT_CHAIN_B0',ev[(ev.bias=='B0')&ev.arm.isin(['POWER1','LOCAL_MEM_DROP','LOCAL_RICH'])].to_json(orient='records'),flush=True)
    if len(on):print('FIRST_ERROR_B0',on[(on.bias=='B0')&(on.episode==0)&on.arm.isin(['JOINT4','POWER1','MEM_RS'])].to_json(orient='records'),flush=True)
    selected=pd.read_csv(delivery/'analysis/EVALUATION_SCORES.csv')
    print('P4_AND_SENSITIVITY_B0',selected[(selected.bias=='B0')&selected.arm.isin(['MEM_SHORT','MEM_LONG','MEM_NO_CROSS','P4_HARD_MEAN','P4_HARD_COV','P4_SOFT','POWER_NO_GATE','POWER_FREEZE_BG'])][['case','arm','heading_rmse_deg','heading95','gyro_bias_rmse_dps','max_heading_latent_correlation']].to_json(orient='records'),flush=True)
    print('DENSITY_FULL',rawdensity[rawdensity.channel=='full'].to_json(orient='records'),flush=True)
    qdf=pd.DataFrame(qa);print('QA_MAXIMA',qdf.select_dtypes(include='number').max().to_json(),flush=True)
    # Inspect actual leaf-level state/covariance accounting; no time series is an independent scene.
    print('COUNTS',json.dumps({'onset_episodes':len(onset),'local_condition_rows':len(events),'component_rows':len(attribution),'gate_rows':len(gate)}),flush=True)

if __name__=='__main__':main()
