"""D3: four immutable numerical failures (GitHub-cloud diagnostic ONLY).

A two-phase PRE-RUN audit must pass before this script is allowed to
read the archived input. This is NOT a new estimator, RF calibration,
full P2 rerun, or scientific hypothesis decision.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import zipfile
import numpy as np
import mpmath as mp
from scipy.optimize import least_squares
from core import SyntheticRF, map_update, gaussian_update, wrap
from d3_pre_audit import METADATA, ARTIFACT_COMMIT, path_for, file_sha

HERE=Path(__file__).resolve().parent
OUTCOME='FOUR_FIXED_FAILURE_NUMERICAL_CAUSE_DIAGNOSTIC_ONLY'
TOL=1e-8


def sha(blob):
 return hashlib.sha256(blob).hexdigest()


def plain(obj):
 if isinstance(obj,dict):
  return {k:plain(v) for k,v in obj.items()}
 if isinstance(obj,list):
  return [plain(v) for v in obj]
 if isinstance(obj,np.ndarray):
  return [plain(v) for v in obj.tolist()]
 if isinstance(obj,(np.floating,np.integer)):
  return obj.item()
 return obj


def load_json(z,name):
 return json.loads(z.read(name).decode('utf-8'))


def evaluate64(y,mu,Lp,z,Lr):
 x=mu+Lp@y
 h,H=SyntheticRF()(x)
 v=np.linalg.solve(Lr,z-h)
 B=np.linalg.solve(Lr,H@Lp)
 return (.5*float(y@y+v@v),y-B.T@v,np.eye(len(y))+B.T@B,
         h,H)


class IndependentMP:
 """80-digit independent forward physics, gradient and Gaussian objective."""
 def __init__(self,mu,Lp,z,Lr):
  self.n=len(mu)
  self.mu=mp.matrix([mp.mpf(float(v)) for v in mu])
  self.Lp=mp.matrix([[mp.mpf(float(v)) for v in row] for row in Lp])
  self.z=mp.matrix([mp.mpf(float(v)) for v in z])
  self.Rinv=(mp.matrix([[mp.mpf(float(v)) for v in row] for row in Lr]))**-1
  self.hgt=mp.mpf(float(1.3))
  self.a=mp.mpf(float(.8));self.b=mp.mpf(float(.15))

 def eval(self,yy):
  u=mp.matrix([mp.mpf(v) for v in yy])
  x=self.mu+self.Lp*u
  dx=x[0]+2;dy=x[1]-3;q=dx*dx+dy*dy
  r=mp.sqrt(q+self.hgt*self.hgt)
  sz=mp.sqrt(q)
  ss=self.a*mp.sin(x[2])+self.b*dy/sz
  h=mp.matrix([r,ss])
  HH=mp.matrix(2,self.n)
  HH[0,0]=dx/r;HH[0,1]=dy/r
  HH[1,0]=-self.b*dx*dy/(q*sz)
  HH[1,1]=self.b*dx*dx/(q*sz)
  HH[1,2]=self.a*mp.cos(x[2])
  v=self.Rinv*(self.z-h)
  B=self.Rinv*HH*self.Lp
  j=(mp.fdot(u,u)+mp.fdot(v,v))/2
  grad=u-B.T*v
  return j,grad,h

 def vec(self,y):
  return [mp.mpf(float(v)) for v in np.asarray(y,dtype=float)]

 def cost(self,y):
  return self.eval(self.vec(y))[0]

 def grad_inf(self,y):
  _,g,_=self.eval(self.vec(y))
  return max(abs(v) for v in g)


def midpoint_first(mu,P,z,R):
 """Independent range-only EKF initial candidate (same affine formula)."""
 Lp=np.linalg.cholesky(P)
 h,H=SyntheticRF()(mu)
 hr=H[0]
 S=float(hr@P@hr+R[0,0])
 d=(P@hr)*float(z[0]-h[0])/S
 d[2]=wrap(d[2])
 return np.linalg.solve(Lp,d)


def replay_steps(fail,mu,P,z,R,model):
 Lp=np.linalg.cholesky(P);Lr=np.linalg.cholesky(R)
 hist=fail['history']
 y=midpoint_first(mu,P,z,R)
 steps=[]
 for row in hist:
  it=int(row['iteration'])
  c,g,info,_,_=evaluate64(y,mu,Lp,z,Lr)
  if 'step_fraction' not in row:
   steps.append({'iteration':it,'terminal':True,'cost':c,
                 'gradient_inf':float(np.max(np.abs(g))),
                 'recorded_gradient_inf':row['gradient_inf'],
                 'recorded_cost':row['cost']})
   break
  d=np.linalg.solve(info,-g)
  t=float(row['step_fraction'])
  yc=y+t*d
  c1,g1,_,_,_=evaluate64(yc,mu,Lp,z,Lr)
  mp0=model.cost(y);mp1=model.cost(yc)
  direction=float(g@d)
  roundoff=4*np.finfo(float).eps*max(1.,abs(c))
  armijo_bound=c+1e-4*t*direction+roundoff
  diff_mp=mp1-mp0
  steps.append({'iteration':it,'acceptance':row.get('step_acceptance','UNKNOWN'),
    'step_fraction':t,'before_cost_64':c,'after_cost_64':c1,
    'floating_cost_change':c1-c,'high_precision_cost_change':mp.nstr(diff_mp,47),
    'true_cost_increased':bool(diff_mp>0),'true_cost_decreased':bool(diff_mp<0),
    'gradient_before_inf':float(np.max(np.abs(g))),
    'gradient_after_inf':float(np.max(np.abs(g1))),
    'armijo_direct_would_accept':bool(np.isfinite(c1) and c1<=armijo_bound),
    'direct_roundoff_allowance':roundoff,
    'direct_armijo_term':1e-4*t*direction,
    'recorded_cost':row['cost'],
    'recorded_gradient_inf':row['gradient_inf']})
  y=yc
 return y,steps


def range_conflict(mu,P,z,R,truth,k):
 """Truth is consulted ONLY after the original archived estimator run."""
 model=SyntheticRF()
 h,H=model(mu)
 tstate=truth[k+1]
 htrue,_=model(tstate)
 rDR=float(h[0]);rRF=float(z[0]);rTrue=float(htrue[0])
 diff=float(rDR-rRF)
 Rr=float(R[0,0])
 innovation=float(H[0]@P@H[0]+Rr)
 return {
  'r_DR_prior_m':rDR,'r_RF_observed_m':rRF,'r_true_scoring_only_m':rTrue,
  'dr_minus_rf_m':diff,'abs_disagreement_m':abs(diff),
  'rf_signed_error_m':rRF-rTrue,'dr_signed_error_m':rDR-rTrue,
  'rf_abs_error_m':abs(rRF-rTrue),'dr_abs_error_m':abs(rDR-rTrue),
  'rf_better_than_dr_in_range':bool(abs(rRF-rTrue)<abs(rDR-rTrue)),
  'RF_measurement_sd_m':math.sqrt(Rr),
  'range_disagreement_in_RF_sd':abs(diff)/math.sqrt(Rr),
  'range_NIS_from_prior':diff*diff/innovation,
  'prior_prediction_range_sd_m':math.sqrt(innovation),
  'original_1d_NIS99_reference':6.634896601,
  's_dr_predicted':float(h[1]),'s_rf_observed':float(z[1]),
  's_innovation':float(z[1]-h[1]),
  'gyro_bias_true_dps_scoring_only':.05,
  'interpretation':'One-step radial comparison; not complete position/heading or independently calibrated real RF'
 }


def single_case(zipped,route,alg,k,npz_sha,json_sha):
 npz_path=path_for(route,alg,'FAILED_STEP.npz')
 json_path=path_for(route,alg,'FAILURE.json')
 if sha(zipped.read(npz_path))!=npz_sha or sha(zipped.read(json_path))!=json_sha:
  raise RuntimeError('Original snapshot has changed: '+npz_path)
 fail=load_json(zipped,json_path)
 with np.load(io.BytesIO(zipped.read(npz_path)),allow_pickle=False) as data:
  mu,P,z,R=[np.array(data[n],dtype=np.float64) for n in ('prior_x','prior_P','z','R')]
  final_delta=np.array(data['prior_delta'],dtype=np.float64)
  final_x=np.array(data['solution'],dtype=np.float64)
 inp='_temp/p2_preflight/trials/'+route+'/0.05/000/INPUTS.npz'
 with np.load(io.BytesIO(zipped.read(inp)),allow_pickle=False) as data:
  truth=data['truth'].copy()
  zin=data['z'][k].copy()
 if max(abs(zin-z))>1e-14:
  raise RuntimeError('Archived input/failed-observation mismatch')
 if abs(wrap(final_x[2]-mu[2]-final_delta[2]))>1e-8 or max(abs((final_x-mu)[:2]-final_delta[:2]))>1e-8:
  raise RuntimeError('Failed state/prior_delta not aligned')
 mp.mp.dps=80
 Lp=np.linalg.cholesky(P);Lr=np.linalg.cholesky(R)
 ref=IndependentMP(mu,Lp,z,Lr)
 y=np.linalg.solve(Lp,final_delta)
 base_cost,g,A,h,H=evaluate64(y,mu,Lp,z,Lr)
 if abs(float(ref.cost(y))-base_cost)>1e-9:
  raise RuntimeError('Independent high precision forward model inconsistent with original objective')
 h_prior,_=SyntheticRF()(mu)
 gMP=ref.grad_inf(y)
 d=np.linalg.solve(A,-g)
 yc=y+d
 cost_next,gn,_,_,_=evaluate64(yc,mu,Lp,z,Lr)
 deltaMP=ref.cost(yc)-ref.cost(y)
 derivative_mp_next=ref.grad_inf(yc)
 rf=range_conflict(mu,P,z,R,truth,k)
 yreplay,steps=replay_steps(fail,mu,P,z,R,ref)
 discrepancy=float(np.linalg.norm(yreplay-y,np.inf))
 accepted_uphill=sum(s.get('true_cost_increased',False) for s in steps)
 original=map_update(mu,P,z,SyntheticRF(),R,range_first=True,max_iter=80,gradient_tol=TOL)
 # A controlled counterfactual diagnostic, NOT a new estimator experiment.
 counter={}
 for label,obs in (
  ('original_z',z.copy()),
  ('range_replaced_by_DR_prediction',np.array([h_prior[0],z[1]])),
  ('s_replaced_by_DR_prediction',np.array([z[0],h_prior[1]])),
  ('both_replaced_by_DR_predictions',h_prior.copy())):
  result=map_update(mu,P,obs,SyntheticRF(),R,range_first=True,max_iter=80,gradient_tol=TOL)
  counter[label]={'status':result.status,'gradient_inf':result.gradient_inf,
                  'cost':result.cost,'iterations':result.iterations,
                  'is_original_observation':label=='original_z'}
 # Root-finding is a separate numerical diagnostic; lack of convergence
 # cannot invalidate the archived input or its exact fixed-step calculations.
 root={'status':'UNRESOLVED'}
 try:
  def eq(*args):
   _,grad,_=ref.eval(args)
   return tuple(grad[j] for j in range(len(y)))
  solution=mp.findroot(eq,tuple(ref.vec(y)),tol=mp.mpf('1e-45'),maxsteps=30)
  xr=np.array([float(v) for v in solution])
  root={'status':'MP_STATIONARY_FOUND','gradient_inf':mp.nstr(
      max(abs(t) for t in ref.eval(solution)[1]),45),
        'cost_gap_from_saved':mp.nstr(ref.cost(y)-ref.eval(solution)[0],45),
        'distance_y_inf':float(np.linalg.norm(xr-y,np.inf))}
 except Exception as exc:
  root={'status':'MP_STATIONARY_UNRESOLVED','error':type(exc).__name__,'message':str(exc)[:250]}
 # Determine which assertions are truly supported by the frozen source.
 refutable=deltaMP<0 and float(derivative_mp_next)<=TOL
 numerical_floor=(abs(cost_next-base_cost)<=128*np.finfo(float).eps*max(1.,abs(base_cost)))
 c={
  'case':route+'/'+alg,'cell':fail['cell'],'n_states':len(mu),
  'frozen_source_run':fail.get('cell'),'archived_failure_status':fail['solver_status'],
  'archived_failure_grad_inf':fail['gradient_inf'],
  'replay_status':original.status,'replay_grad_inf':original.gradient_inf,
  'original_prior_x':mu,'original_prior_P':P,
  'original_z':z,'original_R':R,
  'saved_delta':final_delta,'saved_state':final_x,
  'saved_stationarity':{
    'double_J':base_cost,'double_gradient_inf':float(np.linalg.norm(g,np.inf)),
    'mp_gradient_inf':mp.nstr(gMP,45),
    'double_mp_gradient_difference':float(abs(float(gMP)-np.linalg.norm(g,np.inf))),
    'GN_condition_number':float(np.linalg.cond(A))},
  'single_full_GN_candidate':{
    'step_y':d,'norm_y':float(np.linalg.norm(d,np.inf)),
    'double_delta_J':cost_next-base_cost,
    'MP_80digit_delta_J':mp.nstr(deltaMP,55),
    'double_gradient_next_inf':float(np.linalg.norm(gn,np.inf)),
    'MP_80digit_gradient_next_inf':mp.nstr(derivative_mp_next,45),
    'genuine_descent_step_below_original_tol':bool(refutable),
    'direct_cost_cancellation_floor':bool(numerical_floor)},
  'reconstructed_steps':steps,
  'history_reproduction_delta_inf':discrepancy,
  'accepted_steps_with_mp_cost_increase':accepted_uphill,
  'dr_rf_range_conflict':rf,
  'counterfactual_fixed_input_diagnostic':counter,
  'high_precision_stationary_search':root,
  'provisional_cause':(
   'VERIFIED_NUMERICAL_STEP_REJECTION_OR_STALL' if refutable and discrepancy<1e-6
   else 'INSUFFICIENT_TO_PINPOINT_SINGLE_CAUSE'),
  'qualification':'Original P2 model not changed; DR/RF scoring truth never supplied to MAP.'
 }
 return plain(c)


def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--source-audit',type=Path,required=True)
 parser.add_argument('--input-audit',type=Path,required=True)
 parser.add_argument('--artifact',type=Path,required=True)
 parser.add_argument('--out',type=Path,required=True)
 args=parser.parse_args()
 if os.getenv('GITHUB_ACTIONS')!='true':
  raise RuntimeError('Numeric diagnostics must run on GitHub Actions')
 src=json.loads(args.source_audit.read_text())
 inp=json.loads(args.input_audit.read_text())
 if (src['verdict']!='GO' or inp['verdict']!='GO' or
     src['git_sha']!=os.getenv('GITHUB_SHA') or inp['git_sha']!=os.getenv('GITHUB_SHA')):
  raise RuntimeError('D3 two-phase PRE_RUN_AUDIT gate mismatch')
 for key,expected in inp['source_sha256'].items():
  if file_sha(HERE/key)!=expected:
   raise RuntimeError('D3 source changed after audit: '+key)
 out=args.out.resolve()
 out.mkdir(parents=True,exist_ok=False)
 start={'schema':'EKF4_D3_FOUR_FROZEN_NUMERICAL_FAILURES','scope':OUTCOME,
        'source_commit':os.getenv('GITHUB_SHA'),'source_input_run':ARTIFACT_COMMIT,
        'run_id':os.getenv('GITHUB_RUN_ID'),'started_utc':datetime.now(timezone.utc).isoformat(),
        'source_audit_sha256':file_sha(args.source_audit),'input_audit_sha256':file_sha(args.input_audit),
        'original_artifact_sha256':file_sha(args.artifact),
        'scientific_PASS':False,'R3_SOLVER_PATCH':'NOT_RUN','P2_FULL':'NOT_RUN','P3_P6':'NOT_RUN'}
 (out/'START.json').write_text(json.dumps(start,indent=2)+'\n')
 cases=[]
 try:
  with zipfile.ZipFile(args.artifact) as orig:
   for route,alg,k,nsha,jsha in METADATA:
    item=single_case(orig,route,alg,k,nsha,jsha)
    cases.append(item)
    name=route+'_'+alg+'_step'+str(k)
    (out/(name+'.json')).write_text(json.dumps(item,indent=2,allow_nan=False)+'\n')
    print('D3_CASE '+json.dumps({'case':item['case'],'range':item['dr_rf_range_conflict'],
     'GN':item['single_full_GN_candidate'],
     'replay_status':item['replay_status'],
     'uphill_accepted_steps':item['accepted_steps_with_mp_cost_increase'],
     'provisional_cause':item['provisional_cause']},allow_nan=False),flush=True)
  summary={'case_count':len(cases),
           'proven_numerical_stall_count':sum(x['provisional_cause']=='VERIFIED_NUMERICAL_STEP_REJECTION_OR_STALL' for x in cases),
           'rf_more_accurate_radial_count':sum(x['dr_rf_range_conflict']['rf_better_than_dr_in_range'] for x in cases),
           'large_DR_RF_disagreement_nis99_count':sum(x['dr_rf_range_conflict']['range_NIS_from_prior']>6.634896601 for x in cases),
           'high_precision_uphill_accepted_steps':sum(x['accepted_steps_with_mp_cost_increase'] for x in cases),
           'cases':[{'case':x['case'],'mechanism':x['provisional_cause'],
                      'gn_full_step_true_descent_and_converged':x['single_full_GN_candidate']['genuine_descent_step_below_original_tol'],
                      'r_DR':x['dr_rf_range_conflict']['r_DR_prior_m'],
                      'r_RF':x['dr_rf_range_conflict']['r_RF_observed_m'],
                      'r_true':x['dr_rf_range_conflict']['r_true_scoring_only_m'],
                      'Range_NIS':x['dr_rf_range_conflict']['range_NIS_from_prior'],
                      'rf_better_radial':x['dr_rf_range_conflict']['rf_better_than_dr_in_range']} for x in cases]}
  (out/'SUMMARY.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
  result={**start,'status':'DIAGNOSTIC_COMPLETED','summary':summary,'exit_code':0}
  code=0
 except Exception as exc:
  import traceback
  (out/'TRACEBACK.log').write_text(traceback.format_exc())
  result={**start,'status':'D3_NUMERICAL_OR_DIAGNOSTIC_INVALID','error':str(exc),
          'error_type':type(exc).__name__,'exit_code':2}
  code=2
 result['ended_utc']=datetime.now(timezone.utc).isoformat()
 result['output_sha256']={p.name:file_sha(p) for p in out.iterdir() if p.is_file()}
 (out/'FINAL.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
 print('D3_FINAL '+json.dumps({k:v for k,v in result.items() if k!='output_sha256'},
         ensure_ascii=False,allow_nan=False),flush=True)
 return code

if __name__=='__main__':
 raise SystemExit(main())
