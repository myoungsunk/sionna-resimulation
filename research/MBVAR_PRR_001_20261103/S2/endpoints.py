"""Offline recovery endpoints with pre-treatment cohort assignment."""
import numpy as np
TIME_TOLERANCE_S=1e-9

def snapshot_end_index(t,start_index,seconds=20):
 """Include nominal final packets despite binary timestamp addition error."""
 return int(np.searchsorted(t,float(t[start_index])+seconds+TIME_TOLERANCE_S,side='right'))

def recovery_endpoints(t,x,truth,start,*,pretreatment_prior,pretreatment_truth):
 if len(t)==0:raise ValueError('empty recovery interval')
 before=np.asarray(pretreatment_prior);target=np.asarray(pretreatment_truth)
 if before.shape!=(4,) or target.shape!=(3,) or not np.isfinite(before).all() or not np.isfinite(target).all():raise ValueError('pre-treatment alignment')
 start_heading=float(abs(np.degrees(np.angle(np.exp(1j*(before[2]-target[2]))))))
 start_xy=float(np.linalg.norm(before[:2]-target[:2]))
 heading=np.abs(np.degrees(np.angle(np.exp(1j*(x[:,2]-truth[:,2])))))
 xy=np.linalg.norm(x[:,:2]-truth[:,:2],axis=1)
 good=(heading<=1)&(xy<=.1);first=None;recovered=None
 for i in range(len(t)):
  if good[i]:
   if first is None:first=float(t[i])
   if t[i]-first>=2-TIME_TOLERANCE_S:recovered=float(t[i])-float(start);break
  else:first=None
 result=dict(start_heading_deg=start_heading,start_xy_m=start_xy,first_emitted_heading_deg=float(heading[0]),first_emitted_xy_m=float(xy[0]),recovery_time_s=recovered,censored=recovered is None,available_s=float(t[-1]-start),already_accurate=bool(start_heading<=1 and start_xy<=.1),cohort_source='PRETREATMENT_PREDICTED_PRIOR')
 for duration in (10,20):
  mask=t<=start+duration+TIME_TOLERANCE_S;tt=t[mask]
  result[f'heading_integral_{duration}s']=float(np.trapezoid(heading[mask],tt))
  result[f'xy_integral_{duration}s']=float(np.trapezoid(xy[mask],tt))
  result[f'window_{duration}s_censored']=bool(t[-1]<start+duration-TIME_TOLERANCE_S)
 return result
