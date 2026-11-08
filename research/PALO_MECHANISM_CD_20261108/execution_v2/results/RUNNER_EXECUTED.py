"""PALO CD mechanism experiment: exact nonlinear factorial and recursive interventions.
Truth is confined to diagnostics/scoring. Frozen controls, LUT, Q/R; no detector fitting.
"""
from pathlib import Path
import os,sys,json,hashlib,base64,time,itertools,urllib.request,argparse,concurrent.futures,math
import numpy as np
import pandas as pd
REPO='myoungsunk/sionna-resimulation'
RAW='4c43020f04fbbf7d0510f792c4ab99a1d9f5ddb5'
EXACT='eaf9a386ec8da9cb58aaeec2e3481563de0c0a7f'
GAP='16450dc14366ba4ed2cb4e151952493f0efc944f'
DESIGN='657af33d5bd52c1fc706546b18c75a0a8901312b'
POL='research/POL_HEADING_RESEARCH_20261107/'
FROZEN='experiments/POL_FGO_CORR_20261106_v1/frozen/repo/'
DEST='research/PALO_MECHANISM_CD_20261108/execution_v1'
LEVELS=['B0','L0','L1','L2'];DONORS=['s4','dr','heading']
ALPHAS=[0,.05,.1,.25,.5,1];ARMS=['off','mean_only','P_only','on','on_no_bg','bg_only','a005','a010','a025','a050']
HORIZONS=[0,1,5,10,20];EVENTS=[201,483,485,525,630,962,973]
RS=.0081;GATE=6.6348966010212145;RAD=180/np.pi
QA={};RECEIPTS=[]
def wrap(x):return (x+np.pi)%(2*np.pi)-np.pi
def sha(b):return hashlib.sha256(b).hexdigest()
def clean_json(x):
 if isinstance(x,dict):return {str(k):clean_json(v) for k,v in x.items()}
 if isinstance(x,(list,tuple)):return [clean_json(v) for v in x]
 if isinstance(x,np.ndarray):return clean_json(x.tolist())
 if isinstance(x,np.generic):return clean_json(x.item())
 if isinstance(x,float) and not math.isfinite(x):return None
 return x
def dump(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(clean_json(x),indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def request(url,method='GET',body=None,token=None):
 headers={'User-Agent':'palo-cd-mechanism','Accept':'application/vnd.github+json'}
 if token:headers['Authorization']='Bearer '+token
 if body is not None:headers['Content-Type']='application/json'
 data=None if body is None else json.dumps(body).encode()
 for attempt in range(4):
  try:
   with urllib.request.urlopen(urllib.request.Request(url,data=data,headers=headers,method=method),timeout=180) as r:return r.read()
  except Exception:
   if attempt==3:raise
   time.sleep(2**attempt)
def raw(ref,path):return request(f'https://raw.githubusercontent.com/{REPO}/{ref}/{path}')
def download(src):
 im=json.loads(raw(EXACT,'research/PALO_EXACT_ORACLE_20261107/INPUT_MANIFEST.json'))
 gm=json.loads(raw(GAP,'research/PALO_GAP_STUDY_20261107/DELIVERY_MANIFEST.json'))['files']
 todo=[]
 for s in im['files']:
  p=s['path'];r=p.split(POL,1)[1]
  keep=(r.endswith('/core.py') or r.endswith('/p3_rf_adapter4.py') or r.endswith('/P0_INPUT_MANIFEST.json') or '/LUT/hs_lut_' in r or '/outputs/controls_' in r or ('/verified_inputs/' in r and r.endswith('.npz')) or ('/results/replay/' in r and r.endswith('_recursive.npz')))
  if keep:todo.append((RAW,p,src/'pol'/r,s))
 for lv in LEVELS:
  for d in DONORS:
   r=f'results/trajectories/baseline_{lv}_{d}.npz'
   todo.append((GAP,'research/PALO_GAP_STUDY_20261107/'+r,src/'gap'/Path(r).name,gm[r]))
 def get(v):
  ref,p,d,s=v;b=raw(ref,p);assert len(b)==s['bytes'] and sha(b)==s['sha256'],p
  blob=hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest();assert blob==s['git_blob'],p
  d.parent.mkdir(parents=True,exist_ok=True);d.write_bytes(b)
  return dict(commit=ref,path=p,bytes=len(b),sha256=sha(b),git_blob=blob,local=str(d.relative_to(src)))
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:RECEIPTS.extend(pool.map(get,todo))
 dump(src/'INPUT_MANIFEST.json',dict(design=DESIGN,files=RECEIPTS))
 print('INPUT_VERIFIED',len(todo),sum(s['bytes'] for s in RECEIPTS),flush=True)
def pdcheck(p,name):
 assert np.isfinite(p).all(),name
 err=float(np.max(abs(p-np.swapaxes(p,-1,-2))))
 assert err<1e-9,name
 eig=float(np.linalg.eigvalsh(p).min());assert eig>0,(name,eig)
 QA['min_P_eigenvalue']=min(QA.get('min_P_eigenvalue',np.inf),eig)
def maximum(name,val,tol):
 v=float(np.max(abs(val)));QA[name]=max(QA.get(name,0.),v);assert v<=tol,(name,v,tol)
def initial(c):return np.r_[c['initial_pose'],0.],np.diag(np.array([.1,.1,np.deg2rad(5),np.deg2rad(.1)])**2)
class Model:
 def __init__(self,root):
  f=root/'pol'/FROZEN;sys.path.insert(0,str(f/'research/EKF4_RANGE_S_STAGED_20261014'))
  import core,p3_rf_adapter4
  self.core=core;self.original=p3_rf_adapter4.FrozenLut(f);self.lut=self.original.s
  mm=json.loads((f/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())
  self.case=next(x for x in mm['cases'] if x['id']=='R2_aB_m0')
  self.dt=self.original.dt;self.dp=self.original.dp;self.nt=self.original.nt;self.np=self.original.np
 def observe(self,x):
  x=np.asarray(x);ax,ay,az=self.case['anchor'];u=x[:,0]-ax;v=x[:,1]-ay;h=az-self.case['robot_z_m'];r2=np.maximum(u*u+v*v,1e-12);r=np.sqrt(r2)
  theta=np.arctan2(r,h)*RAD;ta=theta/self.dt;clip=(ta<0)|(ta>self.nt-1-1e-9)
  t=np.clip(ta,0,self.nt-1-1e-9);a=(np.arctan2(-v,u)*RAD+180)/self.dp
  b=((np.arctan2(-v,-u)*RAD-x[:,2]*RAD-self.case['mount_deg']+180)%360)/self.dp
  i=np.floor(t).astype(int);ja=np.floor(a);ka=np.floor(b);ft=t-i;fa=a-ja;fb=b-ka;j=ja.astype(int)%self.np;k=ka.astype(int)%self.np;j1=(j+1)%self.np;k1=(k+1)%self.np
  s=self.lut
  c000,c001,c010,c011=s[i,j,k],s[i,j,k1],s[i,j1,k],s[i,j1,k1]
  c100,c101,c110,c111=s[i+1,j,k],s[i+1,j,k1],s[i+1,j1,k],s[i+1,j1,k1]
  c00=c000*(1-fb)+c001*fb;c01=c010*(1-fb)+c011*fb;c10=c100*(1-fb)+c101*fb;c11=c110*(1-fb)+c111*fb
  c0=c00*(1-fa)+c01*fa;c1=c10*(1-fa)+c11*fa
  value=c0*(1-ft)+c1*ft;gt=(c1-c0)/self.dt;ga=((c01-c00)*(1-ft)+(c11-c10)*ft)/self.dp
  gb=(((c001-c000)*(1-fa)+(c011-c010)*fa)*(1-ft)+((c101-c100)*(1-fa)+(c111-c110)*fa)*ft)/self.dp
  H=np.zeros((len(x),4));H[:,0]=gt*h/(r2+h*h)*u/r*RAD+ga*v/r2*RAD-gb*v/r2*RAD
  H[:,1]=gt*h/(r2+h*h)*v/r*RAD-ga*u/r2*RAD+gb*u/r2*RAD;H[:,2]=-gb*RAD
  assert np.isfinite(value).all() and np.isfinite(H).all()
  return value,H,clip
 def candidate(self,x,P,z):
  h,H,clip=self.observe(x);nu=np.asarray(z)-h;ph=np.einsum('nij,nj->ni',P,H);S=np.einsum('ni,ni->n',H,ph)+RS;K=ph/S[:,None];d=K*nu[:,None];out=x+d;out[:,2]=wrap(out[:,2])
  A=np.eye(4)[None]-K[:,:,None]*H[:,None,:];C=A@P@A.transpose(0,2,1)+RS*K[:,:,None]*K[:,None,:];C=(C+C.transpose(0,2,1))/2
  return out,C,dict(h=h,H=H,nu=nu,S=S,K=K,d=d,nis=nu*nu/S,clip=clip)
 def advance(self,x,P,ds,gyro,dt):
  n=len(x);ds=np.broadcast_to(ds,(n,));gyro=np.broadcast_to(gyro,(n,));dt=np.broadcast_to(dt,(n,));a=gyro-x[:,3]*dt;small=abs(a)<1e-4;c=np.empty(n);dc=np.empty(n)
  aa=a[small];c[small]=1-aa**2/24+aa**4/1920-aa**6/322560;dc[small]=-aa/12+aa**3/480-aa**5/53760
  hh=a[~small]/2;c[~small]=np.sin(hh)/hh;dc[~small]=(hh*np.cos(hh)-np.sin(hh))/(2*hh*hh)
  ph=x[:,2]+a/2;u=np.stack([np.cos(ph),np.sin(ph)],1);up=np.stack([-u[:,1],u[:,0]],1);dist=ds[:,None]*c[:,None]*u;v=ds[:,None]*(dc[:,None]*u+c[:,None]*up/2)
  out=x.copy();out[:,:2]+=dist;out[:,2]=wrap(x[:,2]+a);F=np.broadcast_to(np.eye(4),(n,4,4)).copy();F[:,:2,2]=np.stack([-dist[:,1],dist[:,0]],1);F[:,:2,3]=-dt[:,None]*v;F[:,2,3]=-dt
  g0=np.zeros((n,4));g1=np.zeros((n,4));g0[:,:2]=c[:,None]*u;g1[:,:2]=v;g1[:,2]=1
  C=F@P@F.transpose(0,2,1)+(2e-5*abs(ds))[:,None,None]*g0[:,:,None]*g0[:,None,:]+(np.deg2rad(.015)**2*dt)[:,None,None]*g1[:,:,None]*g1[:,None,:]
  C=(C+C.transpose(0,2,1))/2
  return out,C

def get_arrays(src):
 inp={ch:dict(np.load(src/'pol'/f'inputs/original_run/verified_inputs/R2_aB_m0_{ch}_seed0_ONE_STEP.npz',allow_pickle=False)) for ch in ['los','full']}
 ctr={(ch,lv):dict(np.load(src/'pol'/f'experiments/POL_FGO_CORR_20261106_v1/outputs/controls_{ch}_{lv}.npz',allow_pickle=False)) for ch in inp for lv in LEVELS}
 orig={(ch,lv):dict(np.load(src/'pol'/f'inputs/original_run/results/replay/R2_aB_m0_{ch}_{lv}_seed0_recursive.npz',allow_pickle=False)) for ch in inp for lv in LEVELS}
 ds={(lv,d):dict(np.load(src/'gap'/f'baseline_{lv}_{d}.npz',allow_pickle=False)) for lv in LEVELS for d in DONORS}
 t=inp['full']['t_s'];truth=inp['full']['truth_for_offline_scoring_only'];assert len(t)==979 and np.all(np.diff(t)>0) and np.allclose(np.diff(t),.2,atol=1e-10)
 for a in inp.values():assert np.array_equal(a['t_s'],t) and np.array_equal(a['truth_for_offline_scoring_only'],truth)
 for a in ds.values():
  assert np.array_equal(a['t'],t) and np.array_equal(a['truth'],truth) and np.array_equal(a['pose_id'],inp['full']['pose_id'])
  yes=a['accepted'];assert np.array_equal(a['X'],np.where(yes[:,None],a['candidate_X'],a['prior_X']))
  assert np.array_equal(a['P'],np.where(yes[:,None,None],a['candidate_P'],a['prior_P']))
 return inp,ctr,orig,ds,t,truth

def check_reference(m,inp,ctr,orig,donors):
 parity=[]
 for ch in ['los','full']:
  for lv in LEVELS:
   c=ctr[ch,lv];ix,ip=initial(c);x=np.stack([ix,ix]);p=np.stack([ip,ip]);xx=[];pp=[];ns=[];yes=[]
   for k,z in enumerate(inp[ch]['z_s']):
    if k:x,p=m.advance(x,p,c['ds_odom'][k],c['dtheta_gyro'][k],c['dt_s'][k])
    u,v,d=m.candidate(x,p,z);accept=np.array([d['nis'][0]<=GATE,False]);x=np.where(accept[:,None],u,x);p=np.where(accept[:,None,None],v,p)
    xx.append(x.copy());pp.append(p.copy());ns.append(d['nis'][0]);yes.append(accept[0])
   xx=np.array(xx);pp=np.array(pp);o=orig[ch,lv]
   ex=float(np.max(abs(xx-o['estimate'][:,[3,1],:])));ep=float(np.max(abs(pp-o['covariance'][:,[3,1],:,:])));en=float(np.max(abs(ns-o['nis'][:,3])));em=int(np.sum(np.array(yes)!=(o['status'][:,3]=='APPLIED')))
   assert ex<1e-7 and ep<1e-8 and en<1e-7 and em==0,(ch,lv,ex,ep,en,em)
   pdcheck(pp,'parity');parity.append(dict(channel=ch,level=lv,state=ex,covariance=ep,nis=en,mask=em))
 QA['C0_original_replay']=parity
 for (lv,dn),a in donors.items():
  u,v,g=m.candidate(a['prior_X'],a['prior_P'],inp['full']['z_s'])
  maximum('donor_candidate_X',u-a['candidate_X'],1e-7);maximum('donor_candidate_P',v-a['candidate_P'],1e-8);maximum('donor_NIS',g['nis']-a['nis'],1e-7)
  for k in np.unique(np.r_[np.arange(0,979,23),EVENTS]):
   x=a['prior_X'][k];p=a['prior_P'][k];h,H=m.original.model(x,m.case)
   maximum('vector_h_scalar',g['h'][k]-h[1],1e-10);maximum('vector_H_scalar',g['H'][k]-H[1],1e-9)
   uf,pf,df=m.core.gaussian_update(x,p,np.array([inp['full']['z_s'][k]]),lambda q:(m.original.model(q,m.case)[0][1:],m.original.model(q,m.case)[1][1:]),np.array([[RS]]))
   maximum('vector_update_scalar',u[k]-uf,1e-9);maximum('vector_cov_scalar',v[k]-pf,1e-9)
   if k:
    c=ctr['full',lv];xo,po=m.advance(a['X'][k-1:k],a['P'][k-1:k],c['ds_odom'][k],c['dtheta_gyro'][k],c['dt_s'][k])
    q=np.diag([2e-5*abs(c['ds_odom'][k]),np.deg2rad(.015)**2*c['dt_s'][k],0.])
    xf,pf,*_=m.core.predict(a['X'][k-1],a['P'][k-1],c['ds_odom'][k],c['dtheta_gyro'][k],c['dt_s'][k],q)
    maximum('vector_predict_scalar_X',xo[0]-xf,1e-10);maximum('vector_predict_scalar_P',po[0]-pf,1e-10)
  maximum('H_bg_zero',g['H'][:,3],0.)
 print('C0_PASS',len(parity),'CASES',flush=True)

def errors(x,truth):
 e=x[:,:3]-truth;e[:,2]=wrap(e[:,2]);return e

def candidate_rows(m,x,P,z,truth,meta):
 u,v,q=m.candidate(x,P,z);e=errors(x,truth);eu=errors(u,truth);gh=(e[:,2]**2-eu[:,2]**2)*RAD**2;gx=np.sum(e[:,:2]**2-eu[:,:2]**2,1)
 row=dict(meta);row.update(h=q['h'],innovation=q['nu'],S=q['S'],nis=q['nis'],gate=q['nis']<=GATE,clipped=q['clip'],prior_e_deg=e[:,2]*RAD,prior_xy=np.linalg.norm(e[:,:2],axis=1),post_e_deg=eu[:,2]*RAD,post_xy=np.linalg.norm(eu[:,:2],axis=1),gh=gh,gx=gx)
 for j,n in enumerate(['x','y','psi','bg']):row['prior_'+n]=x[:,j];row['H_'+n]=q['H'][:,j];row['K_'+n]=q['K'][:,j];row['delta_'+n]=q['d'][:,j]
 row['Ppsi']=P[:,2,2];row['candidate_Ppsi']=v[:,2,2]
 row['K_direct']=P[:,2,2]*q['H'][:,2]/q['S'];row['K_position_cross']=np.einsum('ni,ni->n',P[:,2,:2],q['H'][:,:2])/q['S']
 maximum('gain_term_sum',row['K_direct']+row['K_position_cross']-q['K'][:,2],1e-10)
 for tag,aa in [('prior',P),('candidate',v)]:pdcheck(aa,tag)
 return pd.DataFrame(row),u,v,q

def phase_c(m,inp,donors,t,truth,out):
 idx=np.flatnonzero(t>=40);z=inp['full']['z_s'][idx];tru=truth[idx];facts=[];innovation=[];factor=[];alpha_rows=[];verdicts=[];gainpairs=[]
 for lv in LEVELS:
  for dn in DONORS:
   a=donors[lv,dn];x=a['prior_X'][idx];P=a['prior_P'][idx];meta=dict(level=lv,donor=dn,k=idx,t=t[idx])
   df,u,v,q=candidate_rows(m,x,P,z,tru,meta);facts.append(df)
   tt=x.copy();tt[:,:3]=tru;et=x.copy();et[:,2]=tru[:,2];te=x.copy();te[:,:2]=tru[:,:2]
   hTT=m.observe(tt)[0];hET=m.observe(et)[0];hTE=m.observe(te)[0];hEE=q['h'];r0=z-hTT;cp=.5*((hTT-hET)+(hTE-hEE));cs=.5*((hTT-hTE)+(hET-hEE));inter=hEE-hET-hTE+hTT
   maximum('innovation_additivity',q['nu']-(r0+cp+cs),1e-10)
   innovation.append(pd.DataFrame(dict(meta,hTT=hTT,hET=hET,hTE=hTE,hEE=hEE,rf_model_mismatch=r0,position_component=cp,heading_component=cs,interaction=inter,full_minus_los=z-inp['los']['z_s'][idx],innovation=q['nu'])))
   e=errors(x,tru);d=q['d'];dotp=np.sum(e[:,:2]*d[:,:2],1);d2=np.sum(d[:,:2]**2,1);ed=e[:,2]*d[:,2]
   unwrapped=np.all(np.abs(e[:,2,None]+np.array(ALPHAS)[None,:]*d[:,2,None])<np.pi,axis=1)
   uh=np.divide(-2*ed,d[:,2]**2,out=np.zeros(len(x)),where=(ed<0)&(abs(d[:,2])>1e-15));up=np.divide(-2*dotp,d2,out=np.zeros(len(x)),where=(dotp<0)&(d2>1e-30));joint=np.minimum(np.minimum(uh,up),1)
   for al in ALPHAS:
    xa=x+al*d;xa[:,2]=wrap(xa[:,2]);pa=P-al*(P-v);ea=errors(xa,tru);pdcheck(pa,'alpha')
    ghead=(e[:,2]**2-ea[:,2]**2)*RAD**2;gxy=np.sum(e[:,:2]**2-ea[:,:2]**2,1)
    if al>0:
     Ra=q['S']/al-(q['S']-RS);ka=q['K']*al;A=np.eye(4)[None]-ka[:,:,None]*q['H'][:,None,:];jp=A@P@A.transpose(0,2,1)+Ra[:,None,None]*ka[:,:,None]*ka[:,None,:]
     maximum('soft_covariance_joseph',pa-jp,1e-9)
    alpha_rows.append(pd.DataFrame(dict(meta,alpha=al,gate=q['nis']<=GATE,gh=ghead,gx=gxy,head_error_deg=ea[:,2]*RAD,xy_error=np.linalg.norm(ea[:,:2],axis=1),Ppsi=pa[:,2,2],head_no_wrap=unwrapped,head_alpha_upper_exclusive=uh,xy_alpha_upper_exclusive=up,joint_positive_available=(ed<0)&(dotp<0)&unwrapped,joint_upper=joint,head_opt_alpha=np.clip(np.divide(-e[:,2],d[:,2],out=np.zeros(len(x)),where=abs(d[:,2])>1e-15),0,1))))
  for da,db in [('s4','dr'),('s4','heading'),('dr','heading')]:
   aa=donors[lv,da];bb=donors[lv,db];xs=[aa['prior_X'][idx],bb['prior_X'][idx]];ps=[aa['prior_P'][idx],bb['prior_P'][idx]];combos={}
   for bp,bh,bP in itertools.product([0,1],repeat=3):
    code=4*bp+2*bh+bP;x=xs[0].copy();x[:,:2]=xs[bp][:,:2];x[:,2]=xs[bh][:,2];P=ps[bP]
    meta=dict(level=lv,pair=da+'__'+db,k=idx,t=t[idx],combination=code,p_source=bp,heading_source=bh,P_source=bP,bg_source=da)
    df,u,v,q=candidate_rows(m,x,P,z,tru,meta);combos[code]=(df,q);factor.append(df)
    if code in (0,7):
     donor=aa if code==0 else bb
     maximum('factor_endpoint_pose',u[:,:3]-donor['candidate_X'][idx,:3],1e-7);maximum('factor_endpoint_P',v-donor['candidate_P'][idx],1e-8)
     maximum('factor_endpoint_delta_bg',q['d'][:,3]-(donor['candidate_X'][idx,3]-donor['prior_X'][idx,3]),1e-9)
   A,qa=combos[0];B,qb=combos[7];dis=(A.gh.to_numpy()>1e-10)!=(B.gh.to_numpy()>1e-10)
   nu_effect=.5*(qa['K'][:,2]+qb['K'][:,2])*(qb['nu']-qa['nu']);k_effect=.5*(qa['nu']+qb['nu'])*(qb['K'][:,2]-qa['K'][:,2]);dd=qb['d'][:,2]-qa['d'][:,2]
   maximum('symmetric_delta_decomposition',dd-nu_effect-k_effect,1e-10)
   gainpairs.append(pd.DataFrame(dict(level=lv,pair=da+'__'+db,k=idx,t=t[idx],delta_difference=dd,innovation_effect=nu_effect,gain_effect=k_effect,K_A=qa['K'][:,2],K_B=qb['K'][:,2],nu_A=qa['nu'],nu_B=qb['nu'],algebraic_only=True)))
   for j,k in enumerate(idx):
    base=A.iloc[j].gh>1e-10;target=B.iloc[j].gh>1e-10
    changers=[c for c in range(1,8) if (combos[c][0].iloc[j].gh>1e-10)!=base]
    minimal=[c for c in changers if not any(s!=c and (s&c)==s for s in changers)]
    verdicts.append(dict(level=lv,pair=da+'__'+db,k=int(k),t=float(t[k]),disagreement=bool(dis[j]),both_gate=bool(A.iloc[j].gate and B.iloc[j].gate),gh_A=float(A.iloc[j].gh),gh_B=float(B.iloc[j].gh),P_only_flips=1 in changers,heading_only_flips=2 in changers,position_only_flips=4 in changers,minimum_factor_sets=';'.join(str(x) for x in minimal),minimum_order=min([int(c).bit_count() for c in changers],default=0),interpretation='local intervention, not naturally generated history'))
  print('C_FACTORS_DONE',lv,flush=True)
 frames={'factual_events':pd.concat(facts,ignore_index=True),'innovation_components':pd.concat(innovation,ignore_index=True),'factorial_candidates':pd.concat(factor,ignore_index=True),'admissible_alpha':pd.concat(alpha_rows,ignore_index=True),'gain_components':pd.concat(gainpairs,ignore_index=True),'mechanism_verdicts':pd.DataFrame(verdicts)}
 for name,df in frames.items():df.to_csv(out/(name+'.csv.gz'),index=False,compression={'method':'gzip','mtime':0})
 summaries=[]
 for (lv,pair),g in frames['mechanism_verdicts'].groupby(['level','pair']):
  for scope,mask in [('all',np.ones(len(g),bool)),('common_gate',g.both_gate.to_numpy())]:
   q=g[mask & g.disagreement.to_numpy()]
   summaries.append(dict(level=lv,pair=pair,scope=scope,n=int(mask.sum()),disagreements=len(q),P_only_flips=int(q.P_only_flips.sum()),heading_only_flips=int(q.heading_only_flips.sum()),position_only_flips=int(q.position_only_flips.sum()),requires_multiple=int((q.minimum_order>=2).sum()),minimum_sets=q.minimum_factor_sets.value_counts().to_dict()))
 dump(out/'C_summary.json',summaries)
 expect={'B0':420,'L0':370,'L1':368,'L2':359}
 for lv in LEVELS:
  g=frames['mechanism_verdicts'];assert int(g[(g.level==lv)&(g.pair=='s4__dr')].disagreement.sum())==expect[lv]
 return frames

def partition_end(t):
 return np.where(t<100,100.,np.where(t<120,120.,np.where(t<140,140.,np.inf)))
def score_arrays(x,P,tr,btrue):
 e=x[:,:3]-tr;e[:,2]=wrap(e[:,2]);xy=np.linalg.norm(e[:,:2],axis=1);hn=e[:,2]**2/P[:,2,2];ep=e[:,:2];xn=np.einsum('ni,ni->n',ep,np.linalg.solve(P[:,:2,:2],ep[...,None])[...,0])
 return dict(epsi=e[:,2],ex=e[:,0],ey=e[:,1],xy=xy,ebg=x[:,3]-btrue,hnees=hn,xnees=xn,Ppsi=P[:,2,2],Pxy=P[:,0,0]+P[:,1,1])

def phase_d(m,inp,ctr,donors,t,truth,C,out):
 outdir=out/'history_rollouts';outdir.mkdir();v=C['mechanism_verdicts'];meta_all=[];snapshots=[];effects=[];rollout_count=0;states_count=0;negative=0.;rf_P_changed=0;hf_reversals={};iv=['off','mean_only','P_only','on','on_no_bg','bg_only','a005','a010','a025','a050']
 for lv in LEVELS:
  dis=v[(v.level==lv)&(v.pair=='s4__dr')&v.disagreement].k.to_numpy(int)
  events=np.unique(np.r_[dis,EVENTS]);events=events[(events>=200)&(events<len(t))]
  btrue=np.deg2rad(dict(B0=0,L0=.01,L1=.05,L2=.20)[lv])
  for dn in ['s4','dr']:
   a=donors[lv,dn];eidx=np.repeat(events,len(iv));arm=np.tile(np.arange(len(iv)),len(events));n=len(eidx);c=ctr['full',lv]
   x0=a['prior_X'][eidx].copy();P0=a['prior_P'][eidx].copy();u,Pu,q=m.candidate(x0,P0,inp['full']['z_s'][eidx]);x=x0.copy();P=P0.copy()
   for i,name in enumerate(iv):
    sel=arm==i
    if name in ['mean_only','on','on_no_bg']:x[sel]=u[sel]
    if name in ['P_only','on','on_no_bg']:P[sel]=Pu[sel]
    if name=='on_no_bg':x[sel,3]=x0[sel,3]
    if name=='bg_only':x[sel,3]=u[sel,3]
    if i>=6:
     al=[.05,.1,.25,.5][i-6];x[sel]=x0[sel]+al*q['d'][sel];x[sel,2]=wrap(x[sel,2]);P[sel]=P0[sel]-al*(P0[sel]-Pu[sel])
   pdcheck(P,'D_intervention')
   pend=partition_end(t[eidx]);maxstep=np.minimum(100,len(t)-1-eidx)
   for j in range(1,101):
    kk=np.minimum(eidx+j,len(t)-1);cross=t[kk]>=pend-1e-9;maxstep=np.where(cross,np.minimum(maxstep,j-1),maxstep)
   for future in ['s4','rf_off']:
    xx=x.copy();pp=P.copy();initial=score_arrays(xx,pp,truth[eidx],btrue)
    ih=np.zeros(n);ix=np.zeros(n);ib=np.zeros(n);mxh=abs(initial['epsi']);mxx=initial['xy'].copy();used=np.zeros(n,int);reject_streak=np.zeros(n,int);reaccept=np.zeros(n,int);reaccept_harm=np.zeros(n,int);hclip=np.zeros(n,int)
    histX=np.full((101,n,4),np.nan);histP=np.full((101,n,4,4),np.nan);histGate=np.zeros((101,n),bool);histValid=np.zeros((101,n),bool)
    last=initial
    local_rows=[]
    for j in range(101):
     valid=maxstep>=j;ii=np.flatnonzero(valid);kk=eidx[ii]+j
     if j:
      oldx=xx[ii].copy();oldp=pp[ii].copy()
      xp,pc=m.advance(oldx,oldp,c['ds_odom'][kk],c['dtheta_gyro'][kk],c['dt_s'][kk]);uu,cc,gg=m.candidate(xp,pc,inp['full']['z_s'][kk]);hclip[ii]+=gg['clip']
      if j in [1,5,25,50,100] and len(ii):
       for jj in np.unique([0,len(ii)//2,len(ii)-1]):
        kscalar=kk[jj];Q=np.diag([2e-5*abs(c['ds_odom'][kscalar]),np.deg2rad(.015)**2*c['dt_s'][kscalar],0.])
        xr,pr,*_=m.core.predict(oldx[jj],oldp[jj],c['ds_odom'][kscalar],c['dtheta_gyro'][kscalar],c['dt_s'][kscalar],Q)
        maximum('D_offpath_predict_X',xp[jj]-xr,1e-9);maximum('D_offpath_predict_P',pc[jj]-pr,1e-9)
        ur,vr,dd=m.core.gaussian_update(xr,pr,np.array([inp['full']['z_s'][kscalar]]),lambda qq:(m.original.model(qq,m.case)[0][1:],m.original.model(qq,m.case)[1][1:]),np.array([[RS]]))
        maximum('D_offpath_candidate_X',uu[jj]-ur,1e-8);maximum('D_offpath_candidate_P',cc[jj]-vr,1e-8);maximum('D_offpath_NIS',gg['nis'][jj]-dd['NIS'],1e-7)
      ac=(gg['nis']<=GATE) if future=='s4' else np.zeros(len(ii),bool)
      pree=errors(xp,truth[kk])[:,2];poste=errors(uu,truth[kk])[:,2]
      ra=(reject_streak[ii]>=5)&ac;reaccept[ii]+=ra;reaccept_harm[ii]+=ra&(abs(poste)>abs(pree)+1e-12)
      reject_streak[ii]=np.where(ac,0,reject_streak[ii]+1);used[ii]+=ac
      xx[ii]=np.where(ac[:,None],uu,xp);pp[ii]=np.where(ac[:,None,None],cc,pc);histGate[j,ii]=ac
     if len(ii):pdcheck(pp[ii],'D_recursive')
     sc=score_arrays(xx,pp,truth[np.minimum(eidx+j,len(t)-1)],btrue)
     if j:
      dt=c['dt_s'][eidx[ii]+j];ih[ii]+=.5*(last['epsi'][ii]**2+sc['epsi'][ii]**2)*dt;ix[ii]+=.5*(last['xy'][ii]**2+sc['xy'][ii]**2)*dt;ib[ii]+=.5*(last['ebg'][ii]**2+sc['ebg'][ii]**2)*dt
     mxh[ii]=np.maximum(mxh[ii],abs(sc['epsi'][ii]));mxx[ii]=np.maximum(mxx[ii],sc['xy'][ii]);histX[j,ii]=xx[ii];histP[j,ii]=pp[ii];histValid[j,ii]=True;last=sc
     if future=='rf_off' and len(ii):
      for aa,bb in [(0,2),(1,3)]:
       ia=np.flatnonzero(valid&(arm==aa));ibx=np.flatnonzero(valid&(arm==bb));err=xx[ia]-xx[ibx];err[:,2]=wrap(err[:,2]);negative=max(negative,float(np.max(abs(err))) if len(err) else 0.)
     if j in [0,5,25,50,100]:
      hz=j/5
      for aidx in ii:
       rr=dict(level=lv,donor=dn,future=future,event_k=int(eidx[aidx]),event_t=float(t[eidx[aidx]]),arm=iv[arm[aidx]],horizon=hz,is_primary_disagreement=bool(eidx[aidx] in dis),initial_gate=bool(q['nis'][aidx]<=GATE),future_used=int(used[aidx]),reaccept=int(reaccept[aidx]),reaccept_harm=int(reaccept_harm[aidx]),clipping_count=int(hclip[aidx]),heading_error_deg=float(sc['epsi'][aidx]*RAD),ex=float(sc['ex'][aidx]),ey=float(sc['ey'][aidx]),xy=float(sc['xy'][aidx]),bias_error_deg_s=float(sc['ebg'][aidx]*RAD),Ppsi=float(pp[aidx,2,2]),Pxy_trace=float(pp[aidx,0,0]+pp[aidx,1,1]),heading_nees=float(sc['hnees'][aidx]),xy_nees=float(sc['xnees'][aidx]),heading_covered=bool(sc['hnees'][aidx]<=3.841458820694124),xy_covered=bool(sc['xnees'][aidx]<=5.991464547107979),heading_integral_deg2_s=float(ih[aidx]*RAD**2),xy_integral_m2_s=float(ix[aidx]),bias_integral_deg2_s=float(ib[aidx]*RAD**2),heading_max_deg=float(mxh[aidx]*RAD),xy_max=float(mxx[aidx]))
       local_rows.append(rr)
    assert negative<1e-10,('RF_OFF_P_MEAN_CONTROL',negative)
    fn=f'{lv}_{dn}_{future}.npz';np.savez_compressed(outdir/fn,X=histX,P=histP,gate=histGate,valid=histValid,event_k=eidx,arm=arm,arm_names=np.array(iv),event_t=t[eidx],maxstep=maxstep,truth=truth,t=t,initial_prior_X=x0,initial_prior_P=P0,initial_candidate_X=u,initial_candidate_P=Pu)
    assert (outdir/fn).stat().st_size<90_000_000,'shard exceeds publication ceiling'
    df=pd.DataFrame(local_rows);snapshots.append(df);rollout_count+=n;states_count+=int(histValid.sum())
    pivot=df.pivot(index=['event_k','horizon'],columns='arm',values=['heading_error_deg','xy','heading_integral_deg2_s','xy_integral_m2_s','future_used'])
    for (ek,hz),row in pivot.iterrows():
     for name in iv[1:]:
      effects.append(dict(level=lv,donor=dn,future=future,event_k=int(ek),event_t=float(t[int(ek)]),horizon=hz,arm=name,heading_gain_deg2=float(row['heading_error_deg']['off']**2-row['heading_error_deg'][name]**2),xy_gain_m2=float(row['xy']['off']**2-row['xy'][name]**2),heading_integral_gain=float(row['heading_integral_deg2_s']['off']-row['heading_integral_deg2_s'][name]),xy_integral_gain=float(row['xy_integral_m2_s']['off']-row['xy_integral_m2_s'][name]),off_h_deg=float(row['heading_error_deg']['off']),arm_h_deg=float(row['heading_error_deg'][name]),off_xy=float(row['xy']['off']),arm_xy=float(row['xy'][name]),future_used_difference=float(row['future_used'][name]-row['future_used']['off'])))
    print('D_SHARD',lv,dn,future,n,'valid',histValid.sum(),'bytes',(outdir/fn).stat().st_size,flush=True)
   meta_all.append(dict(level=lv,donor=dn,events=len(events),primary=len(dis),horizons={str(h):int(np.sum(maxstep[arm==0]>=int(h*5))) for h in HORIZONS}))
 snapshot=pd.concat(snapshots,ignore_index=True);eff=pd.DataFrame(effects)
 snapshot.to_csv(out/'D_snapshots.csv.gz',index=False,compression={'method':'gzip','mtime':0});eff.to_csv(out/'D_effects_vs_OFF.csv.gz',index=False,compression={'method':'gzip','mtime':0})
 summaries=[]
 for (lv,dn,ft,arm,h),g in eff.groupby(['level','donor','future','arm','horizon']):
  summaries.append(dict(level=lv,donor=dn,future=ft,arm=arm,horizon=h,n=len(g),heading_help=int((g.heading_gain_deg2>1e-10).sum()),heading_harm=int((g.heading_gain_deg2< -1e-10).sum()),xy_help=int((g.xy_gain_m2>1e-12).sum()),xy_harm=int((g.xy_gain_m2< -1e-12).sum()),heading_integral_help=int((g.heading_integral_gain>1e-10).sum()),heading_integral_harm=int((g.heading_integral_gain< -1e-10).sum()),heading_gain_sum=float(g.heading_gain_deg2.sum()),xy_gain_sum=float(g.xy_gain_m2.sum()),heading_integral_gain_sum=float(g.heading_integral_gain.sum()),xy_integral_gain_sum=float(g.xy_integral_gain.sum()),mean_path_changed=int((abs(g.off_h_deg-g.arm_h_deg)>1e-8).sum())))
 pd.DataFrame(summaries).to_csv(out/'D_summary.csv',index=False)
 same=eff[eff.arm=='on'].merge(eff[(eff.arm=='on')&(eff.horizon==0)][['level','donor','future','event_k','heading_gain_deg2','xy_gain_m2']],on=['level','donor','future','event_k'],suffixes=('','_immediate'),validate='many_to_one')
 rev=[]
 for (lv,dn,ft,h),g in same.groupby(['level','donor','future','horizon']):
  rev.append(dict(level=lv,donor=dn,future=ft,horizon=h,n=len(g),initial_help_to_later_harm=int(((g.heading_gain_deg2_immediate>1e-10)&(g.heading_gain_deg2< -1e-10)).sum()),initial_harm_to_later_help=int(((g.heading_gain_deg2_immediate< -1e-10)&(g.heading_gain_deg2>1e-10)).sum())))
 pd.DataFrame(rev).to_csv(out/'D_sign_reversals.csv',index=False)
 QA['RF_OFF_covariance_mean_negative_control_max']=negative
 dump(out/'D_receipt.json',dict(rollouts=rollout_count,valid_states=states_count,events=meta_all,arms=iv,future_rules=['s4: own-prior NIS99','rf_off'],boundary='No future horizon crosses 100/120/140s or sequence end; 120..140 recorded as gap diagnostic',limitation='checkpoint interventions; no new detector; correlated policy-events, not independent samples'))
 return snapshot,eff

def report(out,C):
 s=json.loads((out/'C_summary.json').read_text());d=pd.read_csv(out/'D_summary.csv');dr=json.loads((out/'D_receipt.json').read_text());r=pd.read_csv(out/'D_sign_reversals.csv')
 lines=['# PALO C·D 메커니즘 검증 실행 결과','', '**범위: R2/Anchor B/seed0의 동결 모델 내부 개입 및 체크포인트 재생. 새 판정기·독립 RF 일반화·공분산 보정 인증 아님.**','', '## C: 동일 RF에서 위치·헤딩·전체 공분산 교환','주 분석은 gate 이전 전체 후보. 아래 요인 단독 반전 수는 겹칠 수 있으며 인과 기여율로 합산하지 않는다.','|수준|전체 손익 불일치|P만 교환 반전|헤딩만 교환 반전|위치만 교환 반전|다중요인 필요|','|---|---:|---:|---:|---:|---:|']
 for q in s:
  if q['pair']=='s4__dr' and q['scope']=='all':lines.append(f"|{q['level']}|{q['disagreements']}|{q['P_only_flips']}|{q['heading_only_flips']}|{q['position_only_flips']}|{q['requires_multiple']}|")
 lines+=['','C의 혼합 상태/P는 자연스럽게 생성된 이력을 뜻하지 않는다. 현재 bias 평균은 A로 고정했으며 H_bg=0을 확인했고 pose/P endpoint를 검산했다.','', '## D: 이력 개입 이후 영향',f"{dr['rollouts']}개 개입-미래규칙 궤적, 유효 상태 {dr['valid_states']}개. 모든 원시 평균/P를 history_rollouts에 저장했다. 초기 ON/OFF/mean/P/bias/alpha 개입 뒤 같은 규칙(각자 prior의 S4 또는 RF-off)을 적용했다.", '수용 mask 강제 복사나 donor Jacobian 재사용은 하지 않았다. 0/1/5/10/20초를 기록하며 분할 경계·끝부분 horizon을 제외했다.', '', '|prior|수준|10초 P-only로 평균 차이 발생|비교 사건 수|','|---|---|---:|---:|']
 for _,q in d[(d.future=='s4')&(d.arm=='P_only')&(d.horizon==10)].iterrows():lines.append(f"|{q.donor}|{q.level}|{int(q.mean_path_changed)}|{int(q.n)}|")
 lines+=['',f"미래 RF-off에서 같은 평균·다른 P의 평균 궤적 차이 최대: {QA['RF_OFF_covariance_mean_negative_control_max']:.3e}.", '', '## 한계와 해석', 'C는 수학적 메커니즘의 국소 개입, D는 저장 이력의 같은 checkpoint에서 한 행동을 바꾼 모델 내부 인과 대조다. 특정 실제 반사 경로 원인을 확정하지 않는다. 사후 평균/P 혼합은 정상 Bayesian posterior가 아니다.', 'D의 source=DR는 RF를 쓰지 않고 도달한 checkpoint, source=S4는 기존 융합 후 checkpoint이다. t=140 및 전후 사건을 따로 기록했으며, 완전히 새로운 온라인 판정기를 처음부터 학습/비교하지 않았다.', '편파 보정의 필요성/방향/범위는 참값 기반 오프라인 진단이다. 구현 가능한 온라인 규칙, 전역 최적성, 통계적 공분산 신뢰도는 미입증.', '', '## 검증 상태','입력 SHA256/Git blob, C0 원본 8조건 재현, frozen scalar 대조, 요인교환 endpoint, innovation/gain 항등식, alpha Joseph 검산, 전수 양정치, RF-off 음성대조를 검사했다. 상세 QA.json 참조. 자체검산이며 독립 감사 아님.','']
 (out/'REPORT_KO.md').write_text('\n'.join(lines))
 dump(out/'SUMMARY.json',dict(status='C_D_EXECUTED_SELF_CHECK_PASS',C_main=[q for q in s if q['pair']=='s4__dr'],D=dr,limitations=['single route/anchor/seed','no new selector','no independent science audit','no uncertainty calibration certification','no global causal fractions']))

def publish(out):
 token=os.environ['GITHUB_TOKEN'];branch=os.environ['BRANCH'];expected=os.environ['SOURCE_SHA']
 def api(method,path,body=None):return json.loads(request('https://api.github.com/repos/'+REPO+path,method,body,token))
 head=api('GET','/git/ref/heads/'+branch)['object']['sha'];assert head==expected,'branch moved; refusing push'
 tree=api('GET','/git/commits/'+head)['tree']['sha'];entries=[]
 for p in sorted(out.rglob('*')):
  if not p.is_file():continue
  b=p.read_bytes();assert len(b)<90_000_000
  bl=api('POST','/git/blobs',dict(content=base64.b64encode(b).decode(),encoding='base64'))['sha']
  want=hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest();assert want==bl
  entries.append(dict(path=DEST+'/results/'+str(p.relative_to(out)),mode='100644',type='blob',sha=bl))
  print('PUBLISH_BLOB',str(p.relative_to(out)),len(b),flush=True)
 tr=api('POST','/git/trees',dict(base_tree=tree,tree=entries))['sha'];commit=api('POST','/git/commits',dict(message='Execute exact nonlinear C/D mechanism interventions and full checkpoint rollouts; self-validated',tree=tr,parents=[head]))['sha']
 assert api('GET','/git/ref/heads/'+branch)['object']['sha']==head
 api('PATCH','/git/refs/heads/'+branch,dict(sha=commit,force=False));assert api('GET','/git/ref/heads/'+branch)['object']['sha']==commit
 print('PUBLISHED',commit,flush=True)
 dump(Path('PUBLICATION.json'),dict(commit=commit,branch=branch,files=len(entries),source=expected))

def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=Path('source'));p.add_argument('--output',type=Path,default=Path('output'));p.add_argument('--publish',action='store_true');args=p.parse_args()
 out=args.output;out.mkdir(exist_ok=False,parents=True);start=time.time()
 contract=dict(design_commit=DESIGN,raw_input=RAW,donor_input=GAP,source_sha=os.environ.get('SOURCE_SHA'),scope='C0-C4 and D checkpoint interventions; NOT detector evaluation',truth_use='decomposition, event selection, offline score only; frozen future S4 gate/DR never reads truth',alphas=ALPHAS,arms=ARMS,horizons=HORIZONS,event_selection='all S4-vs-DR pre-gate heading-benefit disagreements at t>=40 plus illustrative fixed list; both source priors; no skipping gate discordance',partitions=[40,100,120,140],bias_truth_diagnostic_only=dict(B0=0,L0=.01,L1=.05,L2=.2),published_before_run=True)
 dump(out/'EXECUTION_CONTRACT.json',contract)
 (out/'RUNNER_EXECUTED.py').write_bytes(Path(__file__).read_bytes())
 try:
  download(args.source);dump(out/'SOURCE_MANIFEST.json',dict(files=RECEIPTS));m=Model(args.source);inp,ctr,orig,donors,t,truth=get_arrays(args.source)
  check_reference(m,inp,ctr,orig,donors);dump(out/'C0_PASS.json',QA)
  C=phase_c(m,inp,donors,t,truth,out);snapshot,eff=phase_d(m,inp,ctr,donors,t,truth,C,out)
  dump(out/'QA.json',dict(status='SELF_CHECK_PASS',**QA,seconds=time.time()-start));report(out,C)
  dump(out/'OUTPUT_SHA256.json',{str(f.relative_to(out)):dict(sha256=sha(f.read_bytes()),bytes=f.stat().st_size) for f in sorted(out.rglob('*')) if f.is_file()})
  print('EXECUTION_PASS',time.time()-start,flush=True)
  if args.publish:publish(out)
 except Exception as exc:
  dump(out/'FAILURE.json',dict(error=repr(exc),QA=QA,seconds=time.time()-start));raise
if __name__=='__main__':main()
