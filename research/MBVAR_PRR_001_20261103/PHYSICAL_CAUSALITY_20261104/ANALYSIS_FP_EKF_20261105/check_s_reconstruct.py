from pathlib import Path
import numpy as np,pandas as pd
D=Path('/mnt/data')
for route in ['R4','R5']:
 tr=np.load(D/f'replay_{route.lower()}/{route}_aB_m0_full_B0_TRACE.npz')
 j=list(tr['arms']).index('POWER1')
 ori=pd.read_csv(D/f'replay_{route.lower()}/{route}_aB_m0_full_B0_UPDATE_ORIGINS.csv.gz')
 ori=ori[ori.model=='POWER1']
 counts={'tot':0,'one':0,'two':0,'none':0,'mismatch':0,'numerics_fail':0,'nan':0}
 sm=[]
 for row in ori.itertuples(index=False):
  k=int(round(float(row.t_s)/.2)); R=tr['R'][k,j]
  if abs(row.r_nu)<1e-10 or abs(row.s_nu)<1e-10: counts['nan']+=1;continue
  a=np.sign(row.r_nu)*np.sqrt(float(row.marginal_nis_r));b=np.sign(row.s_nu)*np.sqrt(float(row.marginal_nis_s));N=float(row.joint_nis)
  disc=(a*b)**2-N*(a*a+b*b-N)
  if disc < -1e-7: counts['numerics_fail']+=1;continue
  candidates=[(a*b+np.sqrt(max(0,disc)))/N,(a*b-np.sqrt(max(0,disc)))/N]
  Srr=float(row.r_nu)**2/float(row.marginal_nis_r); Sss=float(row.s_nu)**2/float(row.marginal_nis_s)
  results=[]
  for rho in candidates:
   S=np.array([[Srr,rho*np.sqrt(Srr*Sss)],[rho*np.sqrt(Srr*Sss),Sss]])
   if abs(rho)>=1:continue
   check=float(np.array([row.r_nu,row.s_nu])@np.linalg.solve(S,np.array([row.r_nu,row.s_nu])))
   # feasibility Pprior>=0
   eval=np.linalg.eigvalsh(S-R)
   if eval.min()>-1e-8:results.append((rho,check,eval.min()))
  counts['tot']+=1
  if len(results)==0:counts['none']+=1;sm.append((k,'zero',a,b,N,R,Srr,Sss,candidates))
  if len(results)==1:counts['one']+=1
  if len(results)==2:counts['two']+=1
  if len(results)>0 and max(abs(x[1]-N) for x in results)>1e-6:counts['mismatch']+=1
 print(route, counts, 'bad example',sm[:1])
