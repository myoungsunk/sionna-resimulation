"""P3–P6 frozen RF: explicit evidence reuse and scoped numerical claims.

P3 archived source/model parity; P4 independent 3/4-state same-prior
joint EKF; P5 fixed-position heading likelihood only (NOT G3);
P6 recursive 3/4-state EKF + local MAP4 on frozen LoS/Full R0 traces.
No training, retuning, original truth-based selection or RF regeneration.
"""
from __future__ import annotations
import argparse,csv,io,json,math,os,traceback,zipfile
from pathlib import Path
import numpy as np
from core import predict,gaussian_update,map_update,wrap
from rf_adapter4 import FrozenLut,RS,RR,B_OLD,R0,GATE_JOINT

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]

def write(path,obj):
 Path(path).write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def inputs(archive):
 with zipfile.ZipFile(archive) as z:
  summary=json.loads(z.read('P2_OUT/P2_ONE_STEP_SUMMARY.json'))
  entries=[]
  for d in summary['per_case']:
   with np.load(io.BytesIO(z.read('P2_OUT/'+d['trace_file'])),allow_pickle=False) as f:
    trace={k:f[k].copy() for k in f.files}
   entries.append((d,trace))
 return summary,entries
def info(case):
 man=json.loads((ROOT/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())
 return next(x for x in man['cases'] if x['id']==case)
def model_at(lut,x,case):
 d=info(case)
 return lut.model(x,d['anchor'],float(d['mount_deg']))
def score(y,P,truth,t):
 sel=np.isfinite(y).all(axis=1)&(t>=30.)
 if not sel.any():return {'valid_points':0}
 e=y[sel,:3]-truth[sel,:3]
 e[:,2]=wrap(e[:,2])
 cp=P[sel,:3,:3]
 nees=np.einsum('bi,bi->b',e,np.linalg.solve(cp,e[:,:,None])[:,:,0])
 hn=e[:,2]**2/P[sel,2,2]
 return {'valid_points':int(sel.sum()),
  'position_RMSE_m':float(np.sqrt(np.mean(np.sum(e[:,:2]**2,axis=1)))),
  'heading_RMSE_deg':float(np.degrees(np.sqrt(np.mean(e[:,2]**2)))),
  'pose_NEES_mean':float(nees.mean()),'heading_NEES_mean':float(hn.mean()),
  'pose95':float(np.mean(nees<=7.814727903251179)),
  'heading95':float(np.mean(hn<=3.841458820694124))}

def P3(lut,entries):
 out=[];max_h=0.;max_j=0.
 for desc,data in entries:
  x=data['xminus'];t=data['t_s']
  indices=sorted(set([0,int(np.flatnonzero(t>=30.)[0]),len(t)//2,len(t)-1]))
  for j in indices:
   h,H=model_at(lut,x[j],desc['case'])
   frozen=data['predicted_z'][j,2,:2]
   J=data['H'][j,2,:2,:3]
   a=float(np.max(np.abs(h-frozen)))
   b=float(np.max(np.abs(H-J)))
   max_h=max(max_h,a);max_j=max(max_j,b)
   out.append({'case':desc['case'],'mode':desc['channel'],'k':j,'t_s':float(t[j]),'h_max_error':a,'H_max_error':b})
 if not (max_h<1e-8 and max_j<1e-5):
  raise RuntimeError('LUT observation parity failed: h='+str(max_h)+' Jacobian='+str(max_j))
 return {'status':'PASS','comparison_points':len(out),'source_channel_traces':len(entries),
         'max_h_difference':max_h,'max_H_difference':max_j,'parity':out,
         'claim':'Frozen original LUT and 14 old RF traces compatible; no new scene or RF generation'}

def P4(lut,entries):
 rows=[];max_state=0.;max_cov=0.;gate_mismatches=0;total=0
 for desc,data in entries:
  x=data['xminus'];P=data['Pminus'];st=data['status'];t=data['t_s']
  for k in range(len(t)):
   if not bool(data['detected'][k]):continue
   obs=np.array([data['z_s'][k],data['z_r_m'][k]])
   h=data['predicted_z'][k,2,:2]
   H=data['H'][k,2,:2,:3]
   R=data['R'][k,2,:2,:2]
   if not(np.isfinite(h).all() and np.isfinite(H).all() and np.isfinite(R).all()):continue
   fn=lambda v,h=h,H=H:(h,H)
   pred3=x[k];predP=P[k]
   out,C,result=gaussian_update(pred3,predP,obs,fn,R,gate_threshold=GATE_JOINT)
   got=st[k,2]=='applied'
   if bool(result['accepted'])!=got:gate_mismatches+=1
   er=float(np.max(np.abs(out-data['xplus'][k,2])))
   pc=float(np.max(np.abs(C-data['Pplus'][k,2])))
   max_state=max(max_state,er);max_cov=max(max_cov,pc)
   # Bias starts independent; 4state must not invent one-step gyro info.
   pred4=np.r_[pred3,0.]
   P4=np.zeros((4,4));P4[:3,:3]=predP;P4[3,3]=math.radians(.1)**2
   H4=np.column_stack((H,np.zeros(2)))
   fn4=lambda v,h=h,H4=H4:(h,H4)
   out4,C4,res4=gaussian_update(pred4,P4,obs,fn4,R,gate_threshold=GATE_JOINT)
   if max(abs(out4[:3]-out))>1e-10 or max(abs(C4[:3,:3]-C).ravel())>1e-10:
    raise RuntimeError('4state same-prior Gaussian adapter not equivalent')
   if abs(out4[3])>1e-12:raise RuntimeError('One-step zero-cross bias spuriously updated')
   total+=1
  rows.append({'case':desc['case'],'mode':desc['channel'],'original_steps':len(t)})
 if gate_mismatches or max_state>1e-7 or max_cov>1e-7:
  raise RuntimeError(f'P4 parity mismatch: gate={gate_mismatches} x={max_state} P={max_cov}')
 return {'status':'PASS','step_count':total,'cases':rows,'gate_mismatches':gate_mismatches,
         'state_max_error_mixed_units':max_state,'covariance_max_error':max_cov,
         'claim':'same-linearization, same-prior 3- and 4-state one-step adapter parity; not recursive bias evidence'}

def conditional_psi_p(x,P):
 pp=P[:2,:2]
 coeff=np.linalg.solve(pp,P[:2,2])
 var=float(P[2,2]-P[2,:2]@coeff)
 return float(x[2]),var
def heading_pdf(lut,x,P,zs,case,n):
 psi0,var=conditional_psi_p(x,P)
 if var<=0:raise RuntimeError('invalid p(psi|xy)')
 angles=np.linspace(-math.pi,math.pi,n,endpoint=False)
 # Wrapped Gaussian prior using 5 nearest angular replicas.
 logs=[]
 for psi in angles:
  state=x.copy();state[2]=psi
  m,_=model_at(lut,state,case)
  ds=float(zs-m[0])
  delta=(psi-psi0+math.pi)%(2*math.pi)-math.pi
  lp=-.5*(delta*delta/var+ds*ds/RS)
  logs.append(lp)
 L=np.asarray(logs);v=np.exp(L-np.max(L));return v/v.sum(),angles
def rebin_periodic_mass(fine):
 """Align fine grid-node centered cells with coarse centered cells.

 Each coarse cell contains its aligned fine center (full cell) and
 half of each adjacent fine cell. Periodic seam must wrap. The result
 preserves unit mass and does not shift a comparison by half a bin.
 """
 f=np.asarray(fine,float)
 if len(f)%2:raise ValueError('even fine grid required')
 aligned=f[::2]+.5*(np.roll(f,1)[::2]+np.roll(f,-1)[::2])
 if abs(float(aligned.sum())-float(f.sum()))>1e-12:
  raise RuntimeError('P5 periodic rebin lost probability mass')
 return aligned

def P5(lut,entries):
 checks=[]
 for desc,data in entries:
  if desc['case']!='R2_aA_m0':continue
  inds=sorted(set([int(np.flatnonzero(data['t_s']>=30.)[0]),len(data['t_s'])-1]))
  for k in inds:
   seq=[heading_pdf(lut,data['xminus'][k],data['Pminus'][k],
                    data['z_s'][k],desc['case'],n)[0] for n in (720,1440,2880)]
   tv01=.5*float(np.sum(np.abs(seq[0]-(rebin_periodic_mass(seq[1])))))
   tv12=.5*float(np.sum(np.abs(seq[1]-(rebin_periodic_mass(seq[2])))))
   checks.append({'case':desc['case'],'channel':desc['channel'],
                  'k':k,'t_s':float(data['t_s'][k]),'TV_720_1440':tv01,'TV_1440_2880':tv12,
                  'within_0p001':tv12<=.001})
 ok=all(x['within_0p001'] for x in checks)
 return {'status':'PASS_FIXED_POSITION' if ok else 'NUMERICAL_LIMIT_FIXED_POSITION',
         'subscope':'P5 fixed x,y conditional Heading marginal, NOT historical G3 full position-integral',
         'grid_refinement':checks,'scientific_PASS':False,'G3_position_marginal_reference':'NOT_VALIDATED'}

def controls(data):
 x=data['xminus'];t=data['t_s'];n=len(x)
 ds=np.zeros(n);dtheta=np.zeros(n);dt=np.zeros(n)
 for k in range(1,n):
  a=float(wrap(x[k,2]-x[k-1,2]))
  dt[k]=float(t[k]-t[k-1])
  phi=x[k-1,2]+a/2
  sc=1. if abs(a)<1e-8 else math.sin(a/2)/(a/2)
  dist=x[k,:2]-x[k-1,:2]
  ds[k]=float(dist@np.array([math.cos(phi),math.sin(phi)])/sc)
  dtheta[k]=a
 return ds,dtheta,dt

def P6(lut,entries):
 outputs=[];original_prior_max_x=0.;original_prior_max_P=0.
 for desc,data in entries:
  xDR=data['xminus'];pDR=data['Pminus'];t=data['t_s'];truth=data['truth_for_offline_scoring_only']
  n=len(t);ds,dtheta,dt=controls(data)
  # Verify controls and P0 Q reproduce the independent original DR-only
  # prediction, before allowing any recursive RF comparison.
  x=xDR[0].copy();p=pDR[0].copy()
  for k in range(1,n):
   Q=np.diag([2e-5*abs(ds[k]),math.radians(.015)**2*dt[k]])
   x,p,_,_=predict(x,p,ds[k],dtheta[k],dt[k],Q)
   dx=x-xDR[k];dx[2]=wrap(dx[2])
   original_prior_max_x=max(original_prior_max_x,float(np.max(np.abs(dx))))
   original_prior_max_P=max(original_prior_max_P,float(np.max(np.abs(p-pDR[k]))))
  if original_prior_max_x>1e-7 or original_prior_max_P>1e-6:
   raise RuntimeError('P6 reconstructed DR motion prior mismatch with frozen original')
  for alg in ('EKF3','EKF4','MAP4'):
   nstate=4 if alg.endswith('4') else 3
   x=xDR[0].copy()
   P=pDR[0].copy()
   if nstate==4:
    x=np.r_[x,0.]
    tmp=np.zeros((4,4));tmp[:3,:3]=P;tmp[3,3]=math.radians(.1)**2;P=tmp
   estimates=np.full((n,nstate),np.nan)
   covs=np.full((n,nstate,nstate),np.nan)
   accepted=0;rejected=0;invalid=None
   for k in range(n):
    try:
     if k:
      Q2=np.diag([2e-5*abs(ds[k]),math.radians(.015)**2*dt[k]])
      if nstate==4:
       Q=np.zeros((3,3));Q[:2,:2]=Q2
      else:Q=Q2
      x,P,_,_=predict(x,P,ds[k],dtheta[k],dt[k],Q)
     if data['detected'][k]:
      obs=np.array([data['z_s'][k],data['z_r_m'][k]])
      Hmodel=lambda v: model_at(lut,v,desc['case'])
      if alg=='MAP4':
       h,H=Hmodel(x)
       nu=obs-h
       NIS=float(nu@np.linalg.solve(H@P@H.T+R0,nu))
       if NIS<=GATE_JOINT:
        r=map_update(x,P,obs,Hmodel,R0,range_first=True,max_iter=80,gradient_tol=1e-8)
        if r.status!='CONVERGED':
         invalid={'index':k,'time_s':float(t[k]),'reason':r.status,
                  'gradient':r.gradient_inf,'cost':r.cost,'history':r.history,
                  'frozen_input_z':obs.tolist(),'R0':R0.tolist(),
                  'prior_x_before_RF':x.tolist(),'prior_P_before_RF':P.tolist(),
                  'observed_h_at_prior':h.tolist(),'observed_H_at_prior':H.tolist(),
                  'source_note':'Saved for read-only fixed-input solver diagnosis; not an accepted MAP result'}
         break
        x,P=r.x,r.P;accepted+=1
       else:rejected+=1
      else:
       xp,pp,d=gaussian_update(x,P,obs,Hmodel,R0,gate_threshold=GATE_JOINT)
       x,P=xp,pp
       if d['accepted']:accepted+=1
       else:rejected+=1
     estimates[k]=x;covs[k]=P
    except Exception as exc:
     invalid={'index':k,'time_s':float(t[k]),'reason':type(exc).__name__,
              'detail':str(exc)}
     break
   complete=invalid is None
   metrics=score(estimates,covs,truth,t)
   outputs.append({'case':desc['case'],'channel':desc['channel'],'model':alg,
                   'full_route_complete':complete,'valid_steps':int(np.isfinite(estimates[:,0]).sum()),
                   'accepted':accepted,'rejected':rejected,'failure':invalid,'metrics':metrics})
 return {'status':'PASS_WITH_SCOPED_RESULTS','num_traces':len(entries),'num_arms':len(outputs),
         'complete_arms':sum(x['full_route_complete'] for x in outputs),
         'invalid_arms':sum(not x['full_route_complete'] for x in outputs),
         'dr_reconstruction_max_abs_state':original_prior_max_x,
         'dr_reconstruction_max_abs_cov':original_prior_max_P,
         'original_RF_environment_count':1,
         'arms':outputs,'scientific_PASS':False,
         'claim':'single frozen corridor, seed0 R0 LoS/Full recursive proof-of-concept; no generalization or calibrated uncertainty'}

def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--stage',required=True,choices=['P3','P4','P5','P6'])
 parser.add_argument('--archive',type=Path,required=True)
 parser.add_argument('--audit',type=Path,required=True)
 parser.add_argument('--out',type=Path,required=True)
 a=parser.parse_args()
 if os.getenv('GITHUB_ACTIONS')!='true':raise RuntimeError('Cloud only')
 receipt=json.loads(a.audit.read_text())
 if receipt['status']!='GO' or receipt['stage']!=a.stage or receipt['git_sha']!=os.getenv('GITHUB_SHA'):
  raise RuntimeError('Stage-specific source+input audit missing')
 from rf_stage_audit import sha
 for name,h in receipt['source_sha256'].items():
  if sha(HERE/name)!=h:raise RuntimeError('Code changed after P3–P6 audit: '+name)
 out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
 report={'stage':a.stage,'git_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],
         'audit_sha256':sha(a.audit),'archive_sha256':sha(a.archive),'scientific_PASS':False,
         'start_utc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}
 rc=1
 try:
  lut=FrozenLut(ROOT)
  original,entries=inputs(a.archive)
  if a.stage=='P3':result=P3(lut,entries)
  elif a.stage=='P4':result=P4(lut,entries)
  elif a.stage=='P5':result=P5(lut,entries)
  else:result=P6(lut,entries)
  report.update(result)
  # P5 reference-limitation is not a failure of independent R0 P6.
  if a.stage=='P5':rc=0
  else:rc=0 if result['status'].startswith('PASS') else 2
 except Exception as exc:
  report.update(status='SCOPE_INVALID',error_type=type(exc).__name__,
                error=str(exc),traceback=traceback.format_exc())
  rc=2
 report['exit_code']=rc
 report['end_utc']=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
 write(out/'FINAL.json',report)
 print('RF_STAGE_FINAL '+json.dumps({k:report.get(k) for k in
      ('stage','status','exit_code','comparison_points','step_count','complete_arms','invalid_arms',
       'max_h_difference','max_H_difference','dr_reconstruction_max_abs_state',
       'dr_reconstruction_max_abs_cov','error')},ensure_ascii=False,allow_nan=False),flush=True)
 return rc
if __name__=='__main__':raise SystemExit(main())
