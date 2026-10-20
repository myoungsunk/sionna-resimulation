#!/usr/bin/env python3
"""Route-paired physical mechanism diagnostic from immutable Full and Direct-LoS.
No EKF run here. Compares predeclared harmful/beneficial RF-skip episodes.
GT pose only for offline geometry; no proposed online policy.
"""
import csv,json,re,sys,pathlib,hashlib,math
import numpy as np
from collections import defaultdict

rt=sys.argv[3];source=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2])
out.mkdir(parents=True,exist_ok=True)
cases={"C01":["A","B"],"C02":["A","B"],"C03":["A","B"],"O01":["O0"],"O02":["O0"],"O03":["O0"]}
anchors={"A":(4.,0.),"B":(10.,0.),"O0":(5.,2.2)}
f=np.array([6250400000+k*1950000 for k in range(257)],dtype=float)
window=.5-.5*np.cos(2*np.pi*np.arange(257)/256)
data=source/rt;assert data.exists(),(str(data),list(source.iterdir())[:10])
row_data={}
def wrap(a):return (a+180)%360-180
def fp(C):
 amp=np.abs(C)
 branch=np.argmax(amp.max(axis=1),axis=1)
 selected=amp[np.arange(len(C)),:,branch]
 peak=selected.max(axis=1)
 ix=np.argmax(selected>=.3*peak[:,None],axis=1)
 valid=peak>1e-16
 return ix,valid

def pol(v):
 po=(v.real*v.real+v.imag*v.imag)
 den=po.sum(axis=-1)
 return np.divide(po[:,0]-po[:,1],den,out=np.full(len(den),np.nan),where=den>1e-35)

def calculate(Full,LoS):
 n=len(Full); assert Full.shape==LoS.shape and Full.shape[1:]==(257,2,2),Full.shape
 F=np.fft.ifft(Full[:,:,:,0]*window[None,:,None],n=1028,axis=1)*257
 L=np.fft.ifft(LoS[:,:,:,0]*window[None,:,None],n=1028,axis=1)*257
 M=F-L
 ixF,hasF=fp(F);ixL,hasL=fp(L);valid=hasF &hasL
 sl=pol(L[np.arange(n),ixL])
 sf=pol(F[np.arange(n),ixF])
 sfix=pol(F[np.arange(n),ixL])
 vl=L[np.arange(n),ixL];vm=M[np.arange(n),ixL];vf=F[np.arange(n),ixL]
 pl=np.sum(abs(vl)**2,axis=1);pm=np.sum(abs(vm)**2,axis=1)
 pure=(abs(vl)**2+abs(vm)**2)
 inc=np.divide(pure[:,0]-pure[:,1],pure.sum(axis=1),out=np.full(n,np.nan),where=pure.sum(axis=1)>1e-35)
 real=2*np.real(np.sum(np.conj(vl)*vm,axis=1))
 den=np.sqrt(pl*pm)
 align=np.divide(abs(np.sum(np.conj(vl)*vm,axis=1)),den,out=np.full(n,np.nan),where=den>1e-34)
 cosph=np.divide(real,2*den,out=np.full(n,np.nan),where=den>1e-34)
 mp=np.divide(pm,pl,out=np.full(n,np.nan),where=pl>1e-35)
 alpha=.5*Full+.5*LoS
 C=np.fft.ifft(alpha[:,:,:,0]*window[None,:,None],n=1028,axis=1)*257
 ihalf,_=fp(C)
 shalf=pol(C[np.arange(n),ihalf])
 return {"valid_direct":valid,"s_full":sf,"s_los":sl,"d_s_total":sf-sl,"d_s_fp_fixed":sfix-sl,"d_s_reflection_power":inc-sl,"d_s_interference":sfix-inc,"d_s_detector":sf-sfix,"d_s_gamma_half":shalf-sl,"fp_mismatch":ixF!=ixL,"mp_over_los":mp,"jones_alignment_at_los_tap":align,"coherent_interference_cos":cosph,"destructive":cosph<-.5,"tap_shift":(ixF-ixL).astype(float)}

for anchor in cases[rt]:
 pat=f"{rt}_{anchor}_M45_FULL_P"
 batch=sorted((data/"BATCHES").glob(f"{pat}*"))
 assert batch,pat
 packs=[];meta=[]
 for d in batch:
  p=d/"H_FULL.npy";q=d/"H_DIRECT_LOS.npy"
  if not (p.is_file() and q.is_file()):raise AssertionError(("MISSING_H",d))
  H=np.load(p,allow_pickle=False);L=np.load(q,allow_pickle=False)
  parts=calculate(H,L)
  posefile=data/"BATCH_POSES"/(d.name+".csv")
  assert posefile.exists(),posefile
  with posefile.open(newline="") as z:rows=list(csv.DictReader(z))
  assert len(rows)==len(H)==len(L),(d,len(rows),len(H),len(L))
  meta.extend(rows);packs.append(parts)
 keys=packs[0].keys();metrics={k:np.concatenate([a[k] for a in packs]) for k in keys}
 n=len(meta);assert n==len(metrics["s_full"])
 stamp=np.array([float(x["t_s"]) for x in meta]);x=np.array([float(q["x_m"]) for q in meta]);y=np.array([float(q["y_m"]) for q in meta]);ant=np.array([float(q["yaw_antenna_deg"]) for q in meta])
 assert np.all(np.diff(stamp)>0),("NONMONOTONE",rt,anchor)
 bx,by=anchors[anchor]; bearing=np.degrees(np.arctan2(by-y,bx-x));rel=wrap(ant-bearing)
 columns={"route":np.repeat(rt,n),"anchor":np.repeat(anchor,n),"t_s":stamp,"x_m":x,"y_m":y,"yaw_antenna_deg":ant,"relative_heading_deg":rel,**metrics}
 row_data[anchor]=columns

records=[]
def runs(mask):
 a=np.r_[False,mask,False].astype(int)
 return list(zip(np.flatnonzero(np.diff(a)==1),np.flatnonzero(np.diff(a)==-1)))
def stat(v):return float(np.mean(v)) if len(v) else None
def rms(v):return float(np.sqrt(np.mean(np.square(v)))) if len(v) else None
def record(anchor,coordinate,low,high,visit,prior_skip_gain,kind):
 d=row_data[anchor];n=len(d["t_s"]);mask=(d[coordinate]>=low)&(d[coordinate]<high)&(d["t_s"]>=0)
 episodes=runs(mask)
 if visit>len(episodes):return dict(route=rt,anchor=anchor,region=f"{coordinate}[{low},{high})",visit=visit,status="NO_SUCH_VISIT")
 lo,hi=episodes[visit-1]
 if hi-lo<3:return dict(route=rt,anchor=anchor,region=f"{coordinate}[{low},{high})",visit=visit,status="TOO_FEW_FRAMES",n=hi-lo)
 valid=d["valid_direct"][lo:hi]
 v=valid&np.isfinite(d["d_s_total"][lo:hi])
 def get(k):return d[k][lo:hi][v]
 ds=get("d_s_total")
 dfix=get("d_s_fp_fixed")
 dpow=get("d_s_reflection_power")
 dint=get("d_s_interference")
 ddet=get("d_s_detector")
 dhalf=get("d_s_gamma_half")
 if len(ds):
  identity=float(np.max(abs(dpow+dint+ddet-ds)))
  assert identity<1e-8,identity
 else:identity=None
 ret={"route":rt,"anchor":anchor,"region":f"{coordinate}[{low},{high})","visit":visit,"status":"PHYSICAL_EVAL_ONLY",
      "skip_gain_reference_deg":prior_skip_gain,"reference_type":kind,"i0":int(lo),"i1":int(hi),"n":int(hi-lo),"t_start_s":float(d["t_s"][lo]),"t_end_s":float(d["t_s"][hi-1]),
      "n_direct":int(valid.sum()),"direct_fraction":float(valid.mean()),"antenna_relative_deg_median":float(np.median(d["relative_heading_deg"][lo:hi])),
      "s_full_minus_los_RMS":rms(ds),"signed_d_s_mean":stat(ds),"d_s_reflection_power_rms":rms(dpow),"d_s_interference_rms":rms(dint),"d_s_detector_rms":rms(ddet),
      "RMS_s_after_half_amplitude":rms(dhalf),"FP_mismatch_fraction":stat(get("fp_mismatch")),"MP_over_LoS_median":float(np.median(get("mp_over_los"))) if len(ds) else None,
      "port_alignment_median":float(np.median(get("jones_alignment_at_los_tap"))) if len(ds) else None,
      "interference_cos_median":float(np.median(get("coherent_interference_cos"))) if len(ds) else None,
      "destructive_fraction":stat(get("destructive")),"mean_abs_tap_shift":stat(abs(get("tap_shift"))),"telescoping_max_error":identity}
 return ret

specs=[
("C01","A","x_m",16,21,1,5.393),("C01","B","x_m",16,21,1,4.340),("C01","A","x_m",10,16,1,-3.079),
("C02","A","x_m",4,10,1,1.775),("C03","A","x_m",1,4,1,.767),("C03","A","x_m",4,10,1,-3.115),
("C03","B","x_m",10,16,1,.610),("C03","B","x_m",10,16,2,.537),
("O02","O0","y_m",4,8,1,-4.330),
("O03","O0","y_m",4,8,1,1.798),("O03","O0","y_m",4,8,2,-15.347),("O03","O0","y_m",0,4,2,-14.462)
]
for route,anchor,c,low,hi,visit,skip in specs:
 if route==rt:
  records.append(record(anchor,c,low,hi,visit,skip,"PRIOR_RECURSIVE_EFFECT_REPORT_OFFLINE_REFERENCE"))
for anchor in cases[rt]:
 c="x_m" if rt.startswith("C") else "y_m"
 for lo,hi in ([(1,4),(4,10),(10,16),(16,21)] if rt.startswith("C") else [(0,4),(4,8),(8,12)]):
  mask=(row_data[anchor][c]>=lo)&(row_data[anchor][c]<hi)
  for visit in range(1,min(5,len(runs(mask)))+1):
   key=(rt,anchor,c,lo,hi,visit)
   if any((s[0],s[1],s[2],s[3],s[4],s[5])==key for s in specs):continue
   records.append(record(anchor,c,lo,hi,visit,None,"ADDITIONAL_UNSCORED_PHYSICAL_CONTRAST"))
field=sorted(set().union(*(r.keys() for r in records)))
with (out/(rt+"_PHYSICAL_EVENTS.csv")).open("w",encoding="utf-8",newline="") as z:
 writer=csv.DictWriter(z,fieldnames=field);writer.writeheader();writer.writerows(records)
receipt={"route":rt,"status":"PHYSICS_OBSERVER_COMPUTED_NO_EKF_RUN","case_count":len(cases[rt]),"N_route_cases":{anchor:len(row_data[anchor]["t_s"]) for anchor in cases[rt]},
         "n_events":len(records),"analyzed_source":"immutable GitHub Actions source snapshot run 39277485012; LP TX index=0, RX +/-45; Hann IFFT 4N; stronger-port threshold 30% leading edge"}
(out/(rt+"_AUDIT.json")).write_text(json.dumps(receipt,indent=2))
print("ROUTE_AUDIT",json.dumps(receipt))
for r in records:
 if r.get("skip_gain_reference_deg") is not None:
  print("EVENT",json.dumps(r,allow_nan=False))
