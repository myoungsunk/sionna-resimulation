"""Offline recovery endpoints, retaining false recoveries and censoring."""
import numpy as np

def recovery_endpoints(t,x,truth,start):
 heading=np.abs(np.degrees(np.angle(np.exp(1j*(x[:,2]-truth[:,2])))))
 xy=np.linalg.norm(x[:,:2]-truth[:,:2],axis=1)
 good=(heading<=1)&(xy<=.1);first=None;recovered=None
 for i in range(len(t)):
  if good[i]:
   if first is None:first=float(t[i])
   if t[i]-first>=2-1e-9:recovered=float(t[i])-float(start);break
  else:first=None
 result=dict(start_heading_deg=float(heading[0]),start_xy_m=float(xy[0]),recovery_time_s=recovered,censored=recovered is None,available_s=float(t[-1]-start),already_accurate=bool(good[0]))
 for duration in (10,20):
  mask=t<=start+duration+1e-9;tt=t[mask]
  result[f'heading_integral_{duration}s']=float(np.trapezoid(heading[mask],tt))
  result[f'xy_integral_{duration}s']=float(np.trapezoid(xy[mask],tt))
  result[f'window_{duration}s_censored']=bool(t[-1]<start+duration-1e-9)
 return result
