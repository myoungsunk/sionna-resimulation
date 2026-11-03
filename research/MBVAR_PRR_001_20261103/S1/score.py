"""Postprocess a completed trace using scoring-only ground truth."""
import numpy as np
from scipy.stats import chi2
def score(pk,tr,truth,channel):
 x=tr['x'];P=tr['P'];t=truth['t'];gt=truth['truth']
 e=np.column_stack((x[:,:3]-gt,x[:,3]-truth['bg']));e[:,2]=np.angle(np.exp(1j*e[:,2]))
 rad=gt[:,:2]-[10.,0.];rho=np.linalg.norm(rad,axis=1);rad=rad/rho[:,None];tan=np.column_stack((-rad[:,1],rad[:,0]))
 head=np.degrees(e[:,2]);xy=np.linalg.norm(e[:,:2],axis=1)
 nees={i:np.einsum('ni,ni->n',e[:,:i],np.linalg.solve(P[:,:i,:i],e[:,:i,None])[:,:,0]) for i in (2,3,4)}
 ep=np.abs(truth['e_mp']) if channel=='Full' else np.zeros(len(t));large=ep>.30;clean=ep<=.05
 pre=tr['mask'];flag=tr['weight']<1.
 out=[]
 for name,sel in [('all',np.ones(len(t),bool)),('initial',t<30),('primary',t>=30),('near',rho<=1.5),('late',t>=2*t[-1]/3)]:
  d=dict(window=name,n=int(sel.sum()))
  if not sel.any():out.append(d);continue
  def rms(v):return float(np.sqrt(np.mean(v[sel]**2)))
  d.update(heading_rmse_deg=rms(head),xy_rmse_m=rms(xy),radial_rmse_m=rms(np.sum(e[:,:2]*rad,axis=1)),tangent_rmse_m=rms(np.sum(e[:,:2]*tan,axis=1)),signed_heading_deg=float(head[sel].mean()),signed_x_m=float(e[sel,0].mean()),signed_y_m=float(e[sel,1].mean()),heading_p95_deg=float(np.quantile(abs(head[sel]),.95)),heading_max_deg=float(abs(head[sel]).max()),xy_p95_m=float(np.quantile(xy[sel],.95)),xy_max_m=float(xy[sel].max()),sigma_heading_deg=float(np.degrees(np.sqrt(P[sel,2,2])).mean()),ellipse95_area=float(np.mean(np.pi*chi2.ppf(.95,2)*np.sqrt(np.linalg.det(P[sel,:2,:2])))))
  for i,v in nees.items():d[f'nees{i}']=float(v[sel].mean())
  for prob in (.68,.95,.99):d[f'heading_coverage{round(prob*100)}']=float(np.mean(e[sel,2]**2/P[sel,2,2]<=chi2.ppf(prob,1)))
  d['xy_coverage95']=float(np.mean(nees[2][sel]<=chi2.ppf(.95,2)))
  elig=pre&sel
  for k,v in dict(accepted=pre,discounted=pre&flag,large=pre&large,clean=pre&clean,true_positive=pre&large&flag,clean_flagged=pre&clean&flag,intermediate=pre&~large&~clean).items():d[k]=int(np.sum(sel&v))
  d['precision']=d['true_positive']/d['discounted'] if d['discounted'] else None;d['recall']=d['true_positive']/d['large'] if d['large'] else None
  d['clean_loss']=d['clean_flagged']/d['clean'] if d['clean'] else None;d['pregate_nis_mean']=float(np.mean(tr['nis'][sel]))
  if elig.any():
   r=tr['nu'][elig,1]**2;v=tr['Reff'][elig,1,1];d['mean_residual2_over_R']=float(np.mean(r/v));d['ratio_mean_residual2_to_mean_R']=float(np.mean(r)/np.mean(v))
  for q in (.50,.95,.99):d[f'packet_p{round(q*100)}_ms']=float(np.quantile(tr['latency_ns'][sel],q)/1e6)
  out.append(d)
 return out
