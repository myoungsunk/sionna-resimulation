"""Independent cold covariance/mean replay using direct matrix conditioning."""
import math
import numpy as np

def cold_replay(checkpoint,suffix,prevention,episode_first,identity,core,model,spec):
 x=checkpoint.x.copy();P=checkpoint.P.copy();sx=checkpoint.shadow_x.copy();sp=checkpoint.shadow_P.copy();last=checkpoint.last_index
 expected=None if last==-1 else checkpoint.source_pose_ids[last]
 if checkpoint.last_pose_id!=expected:raise ValueError('cold checkpoint source ID mismatch')
 records=[]
 def predict(a,C,row,index):
  if index==0:return a,C
  Q=np.diag([2e-5*abs(row['ds']),math.radians(.015)**2*row['dt'],0.])
  y,C,_,_=core.predict(a,C,row['ds'],row['gy'],row['dt'],Q);return y,C
 def update(a,C,H,v,R,accept):
  if not accept:return a,C
  gain=np.linalg.solve(H@C@H.T+R,H@C).T
  y=a+gain@v;y[2]=math.atan2(math.sin(y[2]),math.cos(y[2]));A=np.eye(4)-gain@H
  N=A@C@A.T+gain@R@gain.T;return y,(N+N.T)/2
 for index,t,row in suffix:
  if index!=last+1:raise ValueError('cold discontinuity')
  if index<0 or index>=len(checkpoint.source_pose_ids) or row['pose_id']!=checkpoint.source_pose_ids[index]:raise ValueError('cold source pose ID mismatch')
  sx,sp=predict(sx,sp,row,index);sh,sH=model.batch(sx[None],spec);v0=row['z']-sh[0]-row['muBASE'];H0=sH[0]
  allowed=bool(v0@np.linalg.solve(H0@sp@H0.T+row['R'],v0)<=9.210340371976184)
  sx,sp=update(sx,sp,H0,v0,row['R'],allowed)
  radius=float(np.linalg.norm(x[:2]-np.asarray(spec['anchor'])[:2]));sigma=float(np.interp(radius,[0,1.5,3,6,10],[.011,.020,.050,.120,.240]))
  xp,pp=predict(x,P,row,index);h,H=model.batch(xp[None],spec);h,H=h[0],H[0]
  weight=1.
  if prevention:
   wd=max(.25,min(1.,.20/(abs(row['z'][1]-h[1])+1e-12))**2)
   ws=max(.25,min(1.,.07138038868537433/(abs(row['D'])+1e-12))**2)
   weight=max(.25,wd*ws)
  if not identity and t>=episode_first:weight=min(weight,.25)
  R=row['R'].copy();R[1,1]+=sigma**2;R[1,1]/=weight
  x,P=update(xp,pp,H,row['z']-h-row['muMB'],R,allowed)
  records.append((index,x.copy(),P.copy()));last=index
 return x,P,last,records
