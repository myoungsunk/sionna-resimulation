"""Offline scoring only. Ground truth is never sent to engine.replay."""
import numpy as np
from colored_math import wrap


def scores(result,t,truth,bias,arms,event):
    rows=[]
    masks={'evaluation':t>=30}
    if event['start']<len(t):
        masks['event']=(np.arange(len(t))>=event['start'])&(np.arange(len(t))<event['end'])
        masks['after_event']=np.arange(len(t))>=event['end']
    for scope,mask in masks.items():
        if not np.any(mask):continue
        for j,arm in enumerate(arms):
            x=result['state'][mask,j];P=result['cov'][mask,j]
            e=wrap(x[:,2]-truth[mask,2]);v=P[:,2,2];d=np.degrees(e);b=np.degrees(x[:,3])-bias
            ne=e*e/v;prior=result['prior_state'][mask,j];ep=wrap(prior[:,2]-truth[mask,2]);proposal=result['proposal'][mask,j,2]
            ec=wrap(ep+proposal);accept=result['accepted'][mask,j]
            useful=(ec*ec<ep*ep-1e-14);rej=~accept
            cross=np.abs(P[:,2,4:])/np.sqrt(np.maximum(P[:,2,2,None]*np.diagonal(P[:,4:,4:],axis1=1,axis2=2),1e-30))
            rows.append({'scope':scope,'arm':arm,'n':int(mask.sum()),'signed_mean_deg':float(d.mean()),'heading_rmse_deg':float(np.sqrt(np.mean(d*d))),'heading_nees':float(ne.mean()),'heading95':float(np.mean(ne<=3.841458820694124)),'sigma_rms_deg':float(np.degrees(np.sqrt(v.mean()))),'interval95_mean_width_deg':float(np.degrees(3.919927969*np.sqrt(v)).mean()),'heading_nll_rad':float(np.mean(.5*(np.log(2*np.pi*v)+ne))),'xy_rmse_m':float(np.sqrt(np.mean(np.sum((x[:,:2]-truth[mask,:2])**2,axis=1)))),'gyro_bias_rmse_dps':float(np.sqrt(np.mean(b*b))),'gyro_final_dps':float(np.degrees(result['state'][-1,j,3])),'over1deg_overconfident_fraction':float(np.mean((abs(d)>1)&(ne>3.841458820694124))),'over5deg_overconfident_fraction':float(np.mean((abs(d)>5)&(ne>3.841458820694124))),'accepted_fraction':float(accept.mean()),'accepted_harmful_fraction':float(np.mean(accept&~useful)),'rejected_helpful_fraction':float(np.mean(rej&useful)),'proposal_squared_error_change_deg2':float(np.mean(np.degrees(ec)**2-np.degrees(ep)**2)),'max_heading_latent_correlation':float(cross.max()),'cov_min_eigenvalue':float(result['P_update_eigmin'][mask,j].min())})
    return rows


def equivalence(result,arms,event):
    b=arms.index('POWER1');j=arms.index('MEM_WHITE')
    dx=result['state'][:,j,:4]-result['state'][:,b,:4];dx[:,2]=wrap(dx[:,2])
    dp=result['cov'][:,j,:4,:4]-result['cov'][:,b,:4,:4]
    tests={'memoryless_path_state_max':float(abs(dx).max()),'memoryless_path_cov_max':float(abs(dp).max()),'memoryless_gate_differences':int(np.sum(result['accepted'][:,j]!=result['accepted'][:,b]))}
    for arm in ['LOCAL_MEM_KEEP','LOCAL_MEM_DROP','LOCAL_RICH']:
        k=arms.index(arm);end=event['start']
        if end>0:
            xx=result['state'][:end,k,:4]-result['state'][:end,b,:4];xx[:,2]=wrap(xx[:,2])
            tests[arm+'_prefix_state_max']=float(abs(xx).max())
    return tests


def episode_rows(result,truth,t,arms,data):
    rows=[]
    for name in ['JOINT4','POWER1','MEM_RS','MEM_S','POWER_RECOVERY']:
        if name not in arms:continue
        j=arms.index(name);e=np.degrees(wrap(result['state'][:,j,2]-truth[:,2]));s=np.degrees(np.sqrt(result['cov'][:,j,2,2]))
        flag=(abs(e)>2)&(abs(e)>1.959964*s)&(t>=30)
        starts=np.flatnonzero(flag&~np.r_[False,flag[:-1]]);ends=np.flatnonzero(flag&~np.r_[flag[1:],False])+1
        for a,b in zip(starts,ends):
            if b-a<5:continue
            rows.append({'arm':name,'start_frame':int(a),'end_frame':int(b),'start_t':float(t[a]),'end_t':float(t[b-1]),'x_m':float(truth[a,0]),'y_m':float(truth[a,1]),'body_yaw_deg':float(np.degrees(truth[a,2])),'distance_m':float(data['feature_distance'][a]),'relative_yaw_deg':float(np.degrees(data['feature_relative_yaw'][a])),'gpsi':float(data['feature_gpsi'][a]),'fp_tap':int(data['feature_fp_tap'][a]),'risk':float(data['risk'][a]),'mean_error_deg':float(e[a:b].mean()),'peak_error_deg':float(abs(e[a:b]).max()),'description':'GT-defined diagnostic error episode, never used to trigger intervention'})
    return rows
