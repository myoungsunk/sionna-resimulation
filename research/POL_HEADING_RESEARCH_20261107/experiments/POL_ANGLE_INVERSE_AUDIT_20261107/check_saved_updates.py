"""Single-update decomposition from saved states; no recursive estimator replay."""
import sys,json,numpy as np
from pathlib import Path
from scipy.special import logsumexp
BASE=Path(__file__).resolve().parent;sys.path.insert(0,str(BASE.parent/'POL_ANGLE_CALIBRATED_20261107_v5'));import model as m
p=json.loads((m.BASE/'CALIBRATION.json').read_text(encoding='utf-8'))['parameters'];rows=[]
for ch in ['los','full']:
 raw=m.e.data(ch);ctrl,x0=m.e.build_positive_bias_controls(raw['t_s'],raw['truth_for_offline_scoring_only'],'B0');d=np.load(m.BASE/f'outputs/{ch}_B0_v5.npz')
 assert np.all(d['modes'][raw['t_s']>=40]==1)
 for k in np.flatnonzero((raw['t_s']>=40)&d['mask']):
  mu,P=m.e.predict_one(d['estimate'][k-1],d['covariance'][k-1],ctrl['ds_odom'][k],ctrl['dtheta_gyro'][k],ctrl['dt_s'][k]);rts=m.roots(mu,raw['z_s'][k]);parts=[];eps=p['outlier_probability']
  if rts:
   parts.append((np.log(eps)-np.log(2*np.pi),mu,P,True))
   for a,Ho,slope in rts:
    sd=float(m.sigma(slope,p));H=np.array([Ho[0],Ho[1],1.,0.]);PH=P@H;S=H@PH+sd*sd;lp,g,c=m.base.wrapped_stats(m.e.wrap(a-mu[2]),S);x=mu-PH*g;x[2]=m.e.wrap(x[2]);cov=P+np.outer(PH,PH)*c;parts.append((np.log1p(-eps)-np.log(len(rts))+lp,x,cov,False))
  else:parts=[(-np.log(2*np.pi),mu,P,True)]
  w=np.exp(np.array([a[0] for a in parts])-logsumexp([a[0] for a in parts]));keep=w>=1e-12;w=w[keep];w/=w.sum();kept=[r for r,yes in zip(parts,keep) if yes]
  _,approx,cp=m.base.moment([(ww,r[1],r[2]) for ww,r in zip(w,kept)]);exact=np.angle(sum(ww*np.exp(1j*r[1][2]-.5*r[2][2,2]) for ww,r in zip(w,kept)))
  parts2,di=m.measurement([(1.,0,mu,P,0)],raw['z_s'][k],p);_,reconstructed,pc=m.base.moment([(ww,x,P) for ww,j,x,P,b in parts2]);delta=reconstructed-d['estimate'][k];delta[2]=m.e.wrap(delta[2])
  rows.append(dict(channel=ch,k=int(k),t=float(raw['t_s'][k]),predicted_root_count=len(rts),uniform_posterior_weight=float(sum(ww for ww,r in zip(w,kept) if r[3])),min_root_to_prior_deg=float(np.rad2deg(min([abs(m.e.wrap(a-mu[2])) for a,H,s in rts],default=np.pi))),circular_mean_approx_error_deg=float(np.rad2deg(abs(m.e.wrap(approx[2]-exact)))),state_reconstruction_error=float(abs(delta).max()),cov_reconstruction_error=float(abs(pc-d['covariance'][k]).max())))
summary=[]
for ch in ['los','full']:
 r=[x for x in rows if x['channel']==ch];summary.append(dict(channel=ch,accepted_frames=len(r),uniform_weight_over99_count=sum(x['uniform_posterior_weight']>.99 for x in r),max_mean_approx_error_deg=max(x['circular_mean_approx_error_deg'] for x in r),max_state_reconstruction_error=max(x['state_reconstruction_error'] for x in r),max_cov_reconstruction_error=max(x['cov_reconstruction_error'] for x in r)))
(BASE/'SAVED_UPDATE_CHECK.json').write_text(json.dumps(dict(scope='B0 only; single-step decomposition at saved priors, not correction or recursive rerun',summary=summary,examples=[r for r in rows if r['channel']=='los' and r['k'] in [262,266]],frames=rows),indent=2),encoding='utf-8');print(summary)
