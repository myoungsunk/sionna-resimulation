from runtime import *
import zipfile,io,time,csv
from scipy.stats import norm
from scipy.optimize import brentq, minimize_scalar
Z=norm.ppf(.975);p=ROOT.parent
start=time.time();m=model();print('MODEL_LOADED',time.time()-start,flush=True)
policies=[('current',1,1,1),('no_extra',1,0,1),('no_base',0,1,1),('width75',1,1,.75),('width50',1,1,.5),('width25',1,1,.25),('width10',1,1,.1),('width0',1,1,0)]
parity=[]
for route in ['R2','R4','R5']:
 stop_check();q=ROOT/(route+'_SCAN.npz')
 if q.exists():print('EXISTING_IMMUTABLE',route,flush=True);continue
 z=zipfile.ZipFile(p/(route+'.zip'));name=next(n for n in z.namelist() if '/active/B_FROZEN/OFF/' in n and n.endswith('.npz'))
 a=dict(np.load(io.BytesIO(z.read(name))));o=dict(np.load(p/(route+'_B0_Full_10__online.npz')))
 x=a['prior'];n=len(x);h=[];H=[]
 for k in range(0,n,32):
  hh,jj=m.batch(x[k:k+32],SPEC);h.append(hh);H.append(jj)
 h=np.concatenate(h);H=np.concatenate(H);eh=float(np.max(abs(h-a['h'])));ej=float(np.max(abs(H-a['H'])))
 print('PARITY',route,eh,ej,flush=True);assert eh<1e-10 and ej<1e-10
 base=o['R'][:,1,1];total=a['Rbase'][:,1,1];extra=total-base
 half=Z*np.sqrt(a['Pprior'][:,2,2]);target=(a['nu']+a['h'])[:,1]
 widths=np.array([scale*Z*np.sqrt(wb*base+we*extra) for _,wb,we,scale in policies]).T
 mins=[];coarse=[];curves=[]
 # 129 nested nodes cover the SAME gyro 95% interval; fixed XY isolates nonlinearity.
 grid=np.linspace(-1,1,129)
 for k in range(n):
  stop_check();states=np.tile(x[k],(len(grid),1));states[:,2]+=half[k]*grid
  values=m.batch(states,SPEC,gradient=False)[0][:,1];res=abs(values-target[k])
  best=float(res.min())
  def residual(u):
   state=x[k].copy();state[2]+=half[k]*u
   return float(m.batch(state[None],SPEC,gradient=False)[0][0,1]-target[k])
  # A verified nonlinear root proves overlap even for the zero-width diagnostic.
  crossings=np.flatnonzero((values[:-1]-target[k])*(values[1:]-target[k])<0)
  for b in crossings:
   rt=brentq(residual,grid[b],grid[b+1],xtol=1e-11)
   value=abs(residual(rt));best=min(best,value)
   if value<1e-9:best=0.;break
  if best>0:
   for b in np.flatnonzero((res[1:-1]<res[:-2])&(res[1:-1]<res[2:]))+1:
    opt=minimize_scalar(lambda u:abs(residual(u)),bounds=(grid[b-1],grid[b+1]),method='bounded',options={'xatol':1e-9})
    best=min(best,float(opt.fun))
  mins.append(best);coarse.append(res[::2].min());curves.append(values)
  if k%100==0:print('SCAN',route,k,n,'elapsed',round(time.time()-start,1),flush=True)
 mins=np.array(mins);coarse=np.array(coarse);curves=np.array(curves)
 # Refine every row whose decision changes with nested grid OR is close to a threshold.
 near=np.any((mins[:,None]>widths)!=(coarse[:,None]>widths),axis=1)|np.any(abs(mins[:,None]-widths)<np.maximum(1e-5,.02*widths),axis=1)
 refined=np.zeros(n,bool);refine_changed=np.zeros(n,bool)
 for k in np.flatnonzero(near):
  stop_check();fine=np.linspace(-1,1,513);states=np.tile(x[k],(len(fine),1));states[:,2]+=half[k]*fine
  vv=[]
  for j in range(0,len(fine),129):vv.extend(m.batch(states[j:j+129],SPEC,gradient=False)[0][:,1])
  mm=min(mins[k],np.min(abs(np.array(vv)-target[k])));refine_changed[k]=np.any((mm>widths[k])!=(mins[k]>widths[k]));mins[k]=mm;refined[k]=True
 linear_min=np.maximum(0,abs(a['nu'][:,1])-abs(a['H'][:,1,2])*half)
 np.savez_compressed(q,minimum_residual=mins,coarse_minimum=coarse,linear_minimum=linear_min,widths=widths,grid=grid,curve=curves,half=half,target=target,refined=refined,refine_changed=refine_changed,policy_names=np.array([v[0] for v in policies]),t=a['t'],pose_id=a['pose_id'],prior=x,parity=np.array([eh,ej]))
 print('DONE',route,'refined',int(near.sum()),'refine_changes',int(refine_changed.sum()),flush=True)
(ROOT/'COMPUTE_DONE.json').write_text(json.dumps({'elapsed_s':time.time()-start,'status':'COMPLETED_GRID_DIAGNOSTIC','grid_nodes':129,'refined_nodes':513,'not_global_continuous_proof':True,'new_closed_loop':False},indent=2))
