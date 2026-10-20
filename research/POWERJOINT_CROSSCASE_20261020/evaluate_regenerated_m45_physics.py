#!/usr/bin/env python3
"""M45 regenerated R4/R5 physically evaluated against native Direct LoS.
First-visit T10 catalog only. NO 4-state EKF, NO no-RF local causal intervention.
"""
import csv,json,pathlib,sys,math
import numpy as np
root=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
route=sys.argv[3];anch={"A":(4.,0.),"B":(10.,0.)}
C=299792458.;w=.5-.5*np.cos(2*np.pi*np.arange(257)/256)
assert route in ("R4","R5")
def wrap(a):return (a+180)%360-180
def observe(H):
 n=len(H);a=np.fft.ifft(H[:,:,:,0]*w[None,:,None],n=1028,axis=1)*257
 p=abs(a)**2
 strong=abs(a).max(axis=1).argmax(axis=1)
 amp=abs(a)[np.arange(n),:,strong];peaks=amp.max(axis=1)
 tap=np.argmax(amp>=.3*peaks[:,None],axis=1)
 q=p[np.arange(n),tap,:];den=q.sum(axis=1)
 s=np.divide(q[:,0]-q[:,1],den,out=np.full(n,np.nan),where=den>1e-35)
 return s,tap,peaks>1e-16,p
def episodes(mask):
 z=np.r_[False,mask,False];d=np.diff(z.astype(int));return list(zip(np.flatnonzero(d==1),np.flatnonzero(d==-1)))
def rms(z):return float(np.sqrt(np.mean(np.square(z)))) if len(z) else None
def mean(z):return float(np.mean(z)) if len(z) else None
stats=[]
for a,(ax,ay) in anch.items():
 src=root/route/"CASES"/f"{route}_{a}_M45_FULL"
 H=np.load(src/"H_FULL.npy",allow_pickle=False);L=np.load(src/"H_DIRECT_LOS.npy",allow_pickle=False)
 with (src/"RADIO_POSE.csv").open(newline="") as f:rows=list(csv.DictReader(f))
 assert len(rows)==len(H)==len(L)
 x=np.array([float(k["x_m"]) for k in rows]);y=np.array([float(k["y_m"]) for k in rows]);t=np.array([float(k["t_s"]) for k in rows]);ant=np.array([float(k["yaw_antenna_deg"]) for k in rows])
 relative=wrap(ant-np.degrees(np.arctan2(ay-y,ax-x)))
 sF,tF,validF,pF=observe(H);sL,tL,validL,pL=observe(L)
 m=validF&validL
 sm=sF-sL
 def add(left,right,i0,i1,visit):
  mask=np.arange(len(H))[i0:i1];mm=mask[m[mask]]
  ret={"route":route,"anchor":a,"mount_deg":45,"xbin":f"[{left},{right})","visit":visit,"n":int(i1-i0),"n_direct":int(len(mm)),
       "direct_exists_fraction":float(m[mask].mean()),"t_s_first":float(t[i0]),"t_s_last":float(t[i1-1]),
       "relative_antenna_deg_median":float(np.median(relative[mask])),
       "s_full_minus_los_RMS":rms(sm[mm]),"s_full_minus_los_signed_mean":mean(sm[mm]),
       "FP_mismatch_fraction":mean(tF[mm]!=tL[mm]),
       "los_extremum_fraction_abs_s_gt_0p95":mean(abs(sL[mm])>.95),
       "LoS_direct_bandwidth":"257 bins Hann 4N 30percent strong-RX",
       "time_domain_contract":"catalog first T10 visit; NOT Tnone full repeated route"}
  stats.append(ret)
 for l,r in [(1,4),(4,10),(10,16),(16,20)]:
  groups=episodes((x>=l)&(x<r))
  for v,(b,e) in enumerate(groups[:5],1):
   if e-b>=5:add(l,r,b,e,v)
 # Special physical signal magnitude for whole catalog; NOT overall sensor heading score
 if m.any():
  print("REGEN_GLOBAL",route,a,len(H),"LoSfrac",round(float(m.mean()),4),"sRMSE",round(rms(sm[m]),4))
fp=out/f"{route}_M45_OBSERVER_REGION_PHYSICS.csv"
with fp.open("w",newline="") as f:
 wri=csv.DictWriter(f,fieldnames=list(stats[0]));wri.writeheader();wri.writerows(stats)
for r in stats:
 if r["xbin"]=="[10,16)":
  print("REGEN_EVENT",json.dumps(r,allow_nan=False))
(out/f"{route}_M45_SCIENCE_STATUS.json").write_text(json.dumps({"route":route,"status":"PHYSICAL_SIGNAL_ONLY_NOT_TIME_ALIGNED_RECURSIVE","n_physical_regions":len(stats),"source_run":39279851027},indent=2))
