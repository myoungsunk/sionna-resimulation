"""Circular heading-grid / Gaussian-sum filter with latent noise-scale IMM.

Likelihood is derived from the frozen polarization forward model, not an
independently invented angle sensor. Integrates heading on the full circle;
position/bias conditional on heading use a first-order Gaussian approximation.
Discrete variance modes are marginalized, including between-mode covariance.
"""
import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import sys,json,time,csv,math,hashlib
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
from scipy.signal import find_peaks
from scipy.ndimage import gaussian_filter1d
BASE=Path(__file__).resolve().parent
OLD_CODE=BASE.parent/'POL_FGO_CORR_20261106_v1';sys.path.insert(0,str(OLD_CODE))
import experiment as e
SCALES=np.array([1.,2.,4.,8.,16.,32.]);PI=np.array([.70,.15,.075,.04,.025,.01]);PI/=PI.sum()
STEP=.25;TH=np.deg2rad(np.arange(-180.,180.,STEP));OTH=np.array([0,1,3]);PERSIST=5.
def dump(name,x):(BASE/name).write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def model(x):
 """Vectorized exact frozen trilinear LUT and analytic x/y derivatives."""
 lut=e.LUT;ax,ay,az=e.CASE['anchor'];u=x[:,0]-ax;v=x[:,1]-ay;h=az-e.CASE['robot_z_m'];r2=np.maximum(u*u+v*v,1e-12);r=np.sqrt(r2);k=180/np.pi
 tg=np.arctan2(r,h)*k;tx=np.arctan2(-v,u)*k;rx=(np.arctan2(-v,-u)*k-x[:,2]*k+180)%360-180
 tt=np.clip(tg/lut.dt,0,lut.nt-1-1e-9);aa=(tx+180)/lut.dp;bb=(rx+180)/lut.dp
 i=np.floor(tt).astype(int);j=np.floor(aa).astype(int)%lut.np;q=np.floor(bb).astype(int)%lut.np;ft=tt-i;fa=aa-np.floor(aa);fb=bb-np.floor(bb);j1=(j+1)%lut.np;q1=(q+1)%lut.np;S=lut.s
 c000,c001,c010,c011=S[i,j,q],S[i,j,q1],S[i,j1,q],S[i,j1,q1];c100,c101,c110,c111=S[i+1,j,q],S[i+1,j,q1],S[i+1,j1,q],S[i+1,j1,q1]
 c00=c000*(1-fb)+c001*fb;c01=c010*(1-fb)+c011*fb;c10=c100*(1-fb)+c101*fb;c11=c110*(1-fb)+c111*fb;c0=c00*(1-fa)+c01*fa;c1=c10*(1-fa)+c11*fa
 val=c0*(1-ft)+c1*ft;gt=(c1-c0)/lut.dt;ga=((c01-c00)*(1-ft)+(c11-c10)*ft)/lut.dp;gb=(((c001-c000)*(1-fa)+(c011-c010)*fa)*(1-ft)+((c101-c100)*(1-fa)+(c111-c110)*fa)*ft)/lut.dp
 H=np.zeros((len(x),4));H[:,0]=gt*h/(r2+h*h)*u/r*k+ga*v/r2*k-gb*v/r2*k
 H[:,1]=gt*h/(r2+h*h)*v/r*k-ga*u/r2*k+gb*u/r2*k;H[:,2]=-gb*k
 return val,H

def moment(parts):
 """[(weight,mean,cov)] -> normalized circular mean and total covariance."""
 weights=np.array([a[0] for a in parts]);mass=weights.sum();weights/=mass;X=np.array([a[1] for a in parts]);mean=weights@X
 cs=np.sum(weights*np.exp(1j*X[:,2]));mean[2]=np.angle(cs) if abs(cs)>1e-8 else X[np.argmax(weights),2]
 delta=X-mean;delta[:,2]=e.wrap(delta[:,2]);P=sum(w*(c+np.outer(dx,dx)) for w,(_,_,c),dx in zip(weights,parts,delta))
 return mass,mean,(P+P.T)/2

def interact(comps,dt,variable):
 """IMM interaction within distinct circular-heading basins; preserve modes."""
 # Basin identity is assigned by the previous circular posterior projection.
 # Never collapse distinct basins merely because their means are nearby.
 groups={}
 for comp in comps:groups.setdefault(comp[4],[]).append(comp)
 n=6 if variable else 1;stay=np.exp(-dt/PERSIST);T=stay*np.eye(n)+(1-stay)*np.tile(PI if variable else [1.],(n,1));result=[]
 for basin,g in groups.items():
  for dest in range(n):
   parts=[(w*T[src,dest],mu,P) for w,src,mu,P,_ in g];mass,mu,P=moment(parts)
   result.append((mass,dest,mu,P,basin))
 return result

def measurement(comps,z,variable,theta=TH,fun=model):
 n=len(theta);step=2*np.pi/n;records=[]
 for weight,scale,mu,P,basin in comps:
  sy=P[2,2];delta=e.wrap(theta-mu[2]);a=P[OTH,2]/sy;C=P[np.ix_(OTH,OTH)]-np.outer(P[OTH,2],P[2,OTH])/sy
  # Each winding has its own correlated conditional state and likelihood.
  # Omit only windings whose entire grid lies beyond 9 prior standard deviations.
  J=int(np.ceil((9*np.sqrt(sy)+np.pi)/(2*np.pi)))
  for winding in range(-J,J+1):
   unwrapped=delta+2*np.pi*winding
   if np.min(abs(unwrapped))>9*np.sqrt(sy):continue
   xx=np.tile(mu,(n,1));xx[:,2]=theta;xx[:,OTH]=mu[OTH]+unwrapped[:,None]*a
   h,H=fun(xx);Ho=H[:,OTH];R=e.RS*(SCALES[scale] if variable else 1.);CH=Ho@C;V=R+np.einsum('ni,ni->n',CH,Ho)
   assert np.all(V>0)
   innovation=z-h;K=CH/V[:,None];cond=xx.copy();cond[:,OTH]+=K*innovation[:,None]
   CC=np.tile(C,(n,1,1))-np.einsum('ni,nj->nij',CH,CH)/V[:,None,None]
   lp=-.5*unwrapped**2/sy-.5*np.log(2*np.pi*sy)
   ll=np.log(weight)+lp+np.log(step)-.5*(innovation**2/V+np.log(2*np.pi*V))
   records.append((scale,ll,cond,CC))
 norm=logsumexp(np.concatenate([x[1] for x in records]));density=sum(np.exp(x[1]-norm) for x in records)
 # Physical-angle smoothing is used ONLY for topology detection, never likelihood.
 # Subcell peak interpolation and continuous partition remove nearest-node jumps.
 smooth=gaussian_filter1d(density,np.deg2rad(1.)/step,mode='wrap')
 ext=np.tile(smooth,3);peaks=find_peaks(ext,prominence=max(smooth)*.01)[0];peaks=peaks[(peaks>=n)&(peaks<2*n)]-n
 if not len(peaks):peaks=np.array([np.argmax(smooth)])
 if len(peaks)>24:raise RuntimeError('EXCESSIVE_HEADING_MODES')
 yl=smooth[(peaks-1)%n];yc=smooth[peaks];yr=smooth[(peaks+1)%n]
 denom=yl-2*yc+yr;offset=np.divide(.5*(yl-yr),denom,out=np.zeros(len(peaks)),where=abs(denom)>1e-300)
 centers=e.wrap(theta[peaks]+np.clip(offset,-.5,.5)*step)
 dist=abs(e.wrap(theta[:,None]-centers[None,:]))
 logits=-dist/np.deg2rad(1.);partition=np.exp(logits-logsumexp(logits,axis=1)[:,None]);new=[]
 for mode in range(len(peaks)):
  cells=np.ones(n,dtype=bool);ref=centers[mode]
  for sc in range(6 if variable else 1):
   mass=0.;first=np.zeros(4);second=np.zeros((4,4))
   for idx,ll,cond,CC in records:
    if idx!=sc:continue
    weights=np.exp(ll[cells]-norm)*partition[:,mode];m=cond[cells].copy();m[:,2]=ref+e.wrap(m[:,2]-ref);cov=np.zeros((len(m),4,4));cov[:,OTH[:,None],OTH]=CC[cells]
    mass+=weights.sum();first+=weights@m;second+=np.einsum('n,nij->ij',weights,cov)+np.einsum('n,ni,nj->ij',weights,m,m)
   if mass<1e-280:continue
   mean=first/mass;P=second/mass-np.outer(mean,mean);mean[2]=e.wrap(mean[2]);P=(P+P.T)/2
   if np.linalg.eigvalsh(P).min()<=0:raise RuntimeError('NON_PD_MIXTURE_MOMENT')
   new.append((float(mass),sc,mean,P,mode))
 total=sum(x[0] for x in new);new=[(w/total,sc,x,P,mode) for w,sc,x,P,mode in new]
 return new,density,{'heading_modes':len(peaks),'entropy':float(-np.sum(density*np.log(np.maximum(density,1e-300)))),'mass_before_renormalize':float(total)}

def wrapped_prior(theta,mean,var):
 delta=e.wrap(theta-mean);J=int(np.ceil((9*np.sqrt(var)+np.pi)/(2*np.pi)))
 return sum(np.exp(-.5*(delta+2*np.pi*j)**2/var) for j in range(-J,J+1))/np.sqrt(2*np.pi*var)

def run(ctrl,z,x0,variable,mask,theta=TH):
 mu,P=e.initial(x0,4);comps=[(float(w),j,mu.copy(),P.copy(),0) for j,w in enumerate(PI if variable else [1.])];X=[];C=[];scaleprobs=[];modes=[];density=[];maxcomps=0
 for k in range(len(z)):
  if os.getenv('MANAGED_PROCESS_STOP_FILE') and Path(os.environ['MANAGED_PROCESS_STOP_FILE']).exists():raise RuntimeError('CANCELLED')
  if k:
   comps=interact(comps,ctrl['dt_s'][k],variable);nxt=[]
   for w,j,x,P,basin in comps:
    xp,pp=e.predict_one(x,P,ctrl['ds_odom'][k],ctrl['dtheta_gyro'][k],ctrl['dt_s'][k]);nxt.append((w,j,xp,pp,basin))
   comps=nxt
  if mask[k]:comps,den,di=measurement(comps,z[k],variable,theta);modes.append(di['heading_modes'])
  else:
   den=sum(w*wrapped_prior(theta,x[2],P[2,2]) for w,j,x,P,basin in comps);den/=den.sum();modes.append(0)
  _,x,P=moment([(w,x,P) for w,j,x,P,basin in comps]);X.append(x);C.append(P);density.append(den.astype('float32'));probs=np.zeros(6 if variable else 1)
  for w,j,_,_,_ in comps:probs[j]+=w
  scaleprobs.append(probs);maxcomps=max(maxcomps,len(comps))
 return np.array(X),np.array(C),dict(scale_prob=np.array(scaleprobs),heading_density=np.array(density),heading_modes=np.array(modes),theta_rad=theta,max_components=maxcomps)

def prepare():
 files=[Path(__file__),OLD_CODE/'experiment.py',e.OLD/'AnchorB_8arm_Run_v1.zip']+list((e.OLD/'verified_inputs').glob('*.npz'))+list((e.OLD/'results/replay').glob('*recursive.npz'))+list(e.REPO.rglob('*.py'))+list(e.REPO.rglob('*.npy'))
 dump('INPUT_HASHES.json',{str(p):sha(p) for p in files})
 dump('CONTRACT.json',dict(question_id='POL-HEADING-VAR-003',role='IMPLEMENTER',source='archived original S4; no new Git commit claimed',data='R2 Anchor B mount0 seed0, 979 samples, score t>=30 (829)',model='full-circle heading quadrature + conditional Gaussian position/bias; Gaussian-sum mode projection + discrete latent variance IMM',grid_deg=STEP,variance_scales=SCALES.tolist(),variance_prior=PI.tolist(),variance_persistence_s=PERSIST,parameters='engineering choices frozen before results; no GT fitting/tuning',uncertainty='full mixture covariance includes variance/heading mode scatter; conditional linearization approximation remains',ambiguity='all circular-grid candidates retained at update; topology only: circular Gaussian smoothing sigma1deg, prominence1percent, subcell peak fit, soft angular-distance partition temperature1deg; raw likelihood unchanged; IMM preserves distinct posterior basin IDs; winding-specific correlated conditional calculations; 9-sigma prior tail truncation; no truth branch selection',limits='known initial heading prior std5deg; no global relocalization claim; white conditional noise with variable scale does not model temporal error correlation; source LUT physics validity unproven',arms=['S4_original','HeadingFixed_all','HeadingVariable_all','HeadingFixed_matched','HeadingVariable_matched'],gate='matched uses original causal S4 selector; all uses every observation; selector covariance ignored',criteria='exploratory: both Full RMSE <=1.10*S4 per bias, report NEES/coverage separately; no adoption on one seed',python=sys.version,numpy=np.__version__,scipy=__import__('scipy').__version__,governance={n:sha(Path(r'C:\Users\Myoungsun Kim\.codex\research-governance')/n) for n in ['COMMON_CONTRACT.md','ROLE_IMPLEMENTER.md']}))

def tests():
 rng=np.random.default_rng(2);x=np.column_stack([rng.uniform(1,19,200),rng.uniform(-.5,.5,200),rng.uniform(-np.pi,np.pi,200),np.zeros(200)]);v,H=model(x);ref=[e.LUT.model(a,e.CASE) for a in x];dv=float(np.max(abs(v-np.array([a[0][1] for a in ref]))));dh=float(np.max(abs(H-np.array([a[1][1] for a in ref]))));assert max(dv,dh)<1e-10
 mu=np.zeros(4);P=np.diag([.1,.2,.1,.001]);P[0,2]=P[2,0]=.03
 def linear(x):
  h=x[:,2]+.2*x[:,0];HH=np.tile([.2,0,1,0],(len(x),1));return h,HH
 parts,den,di=measurement([(1.,0,mu,P,0)],.05,False,fun=linear);_,xm,pm=moment([(w,x,p) for w,j,x,p,_ in parts]);H0=np.array([.2,0,1,0]);S=H0@P@H0+e.RS;K=P@H0/S;xe=K*.05;pe=P-np.outer(K,H0@P);err=float(max(np.max(abs(xm-xe)),np.max(abs(pm-pe))));assert err<1e-7,err
 # Two antipodal heading modes must survive an ambiguous cos(2psi) observation.
 def amb(x):
  HH=np.zeros((len(x),4));HH[:,2]=-2*np.sin(2*x[:,2]);return np.cos(2*x[:,2]),HH
 m1=mu.copy();m1[2]=.3;m2=mu.copy();m2[2]=e.wrap(.3+np.pi);pp=np.diag([.1,.1,.03,.001]);parts,den,di=measurement([(.5,0,m1,pp,0),(.5,0,m2,pp,1)],np.cos(.6),False,fun=amb)
 mass1=float(den[abs(e.wrap(TH-.3))<np.pi/2].sum());assert abs(mass1-.5)<1e-6 and di['heading_modes']>=2
 # Between-mode covariance must be present, and likelihood evidence must retain log variance.
 total,xx,pc=moment([(w,x,p) for w,j,x,p,_ in parts]);assert pc[2,2]>.5
 p2,dd,_=measurement([(float(w),j,mu,P,0) for j,w in enumerate(PI)],0.,True,fun=linear);post=np.array([sum(w for w,j,_,_,_ in p2 if j==i) for i in range(6)]);assert post[0]>PI[0]
 dump('TESTS.json',dict(status='PASS_SELF_CHECK',vector_lut_value_error=dv,vector_lut_jacobian_error=dh,linear_gaussian_moment_error=err,antipodal_mass=mass1,antipodal_modes=di['heading_modes'],zero_residual_scale_posterior=post.tolist()))
 print('TESTS PASS',flush=True)

def main():
 out=BASE/'outputs';out.mkdir(exist_ok=False);rows=[];parity=[]
 for lv in ['B0','L0','L1','L2']:
  for ch in ['los','full']:
   d=e.data(ch);ctrl,x0=e.build_positive_bias_controls(d['t_s'],d['truth_for_offline_scoring_only'],lv);saved=np.load(e.OLD/f'results/replay/R2_aB_m0_{ch}_{lv}_seed0_recursive.npz');j=saved['names'].tolist().index('S4');mask=saved['status'][:,j]=='APPLIED'
   for arm in ['S4_original','HeadingFixed_all','HeadingVariable_all','HeadingFixed_matched','HeadingVariable_matched']:
    start=time.perf_counter();extra={}
    if arm=='S4_original':
     X,P,status=e.run_ekf(ctrl,d['z_s'],x0,True);dx=X-saved['estimate'][:,j];dx[:,2]=e.wrap(dx[:,2]);px=float(abs(dx).max());pc=float(abs(P-saved['covariance'][:,j]).max());sm=int(np.sum(status!=saved['status'][:,j]));assert max(px,pc)<1e-7 and sm==0;parity.append(dict(channel=ch,level=lv,state_error=px,cov_error=pc,mask_error=sm));dump('PARITY.json',parity)
    else:X,P,extra=run(ctrl,d['z_s'],x0,'Variable' in arm,mask if 'matched' in arm else np.ones(len(mask),bool))
    assert np.isfinite(X).all() and np.isfinite(P).all() and np.linalg.eigvalsh(P).min()>0
    np.savez_compressed(out/f'{ch}_{lv}_{arm}.npz',estimate=X,covariance=P,t_s=d['t_s'],**extra)
    row=dict(channel=ch,level=lv,method=arm,seconds=time.perf_counter()-start,**e.metrics(X,P,d['truth_for_offline_scoring_only'],d['t_s']))
    if extra:
     m=d['t_s']>=30;row.update(max_components=extra['max_components'],multimodal_frames=int(np.sum(extra['heading_modes'][m]>1)),mean_variance_scale=float(np.mean(extra['scale_prob'][m]@(SCALES if 'Variable' in arm else np.array([1.])))))
    rows.append(row);dump('PROGRESS.json',rows);print(json.dumps(row),flush=True)
 fields=sorted(set().union(*(r.keys() for r in rows)))
 with (BASE/'COMPARISON.csv').open('w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
 assert all(sha(p)==h for p,h in json.loads((BASE/'INPUT_HASHES.json').read_text(encoding='utf-8')).items())
 dump('RESULT.json',dict(status='EXECUTION_COMPLETED',rows=len(rows),inputs_unchanged=True,adoption=False,output_hashes={p.name:sha(p) for p in out.glob('*')}))
if __name__=='__main__':{'prepare':prepare,'tests':tests,'run':main}[sys.argv[1]]()
