"""D3B: compute independent DR-only trajectory on ORIGINAL frozen inputs.

No RF measurement is ever passed to the DR-only predictor; only wheel
distance and gyro increments are used. Truth is used exclusively to
score after the state is estimated. No estimator model is changed.
"""
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
from core import predict, SyntheticRF, wrap
from d3_pre_audit import METADATA, ARTIFACT_COMMIT, ARTIFACT_RUN, path_for, file_sha

HERE=Path(__file__).resolve().parent
EPS=1e-10

def wrap_scalar(theta):
 return (float(theta)+math.pi)%(2*math.pi)-math.pi


def float_complex_step(x,ds,a):
 """Independent exact constant-yaw-rate displacement reference."""
 a=float(a)
 ds=float(ds)
 y=np.asarray(x,float).copy()
 z=1. if a==0 else np.expm1(1j*a)/(1j*a)
 move=ds*np.exp(1j*y[2])*z
 y[:2] += [move.real,move.imag]
 y[2]=wrap_scalar(y[2]+a)
 return y


def calc_dr_only(frozen,step,spec):
 init=np.asarray(frozen['initial'],float).copy()
 x=init.copy()
 P=np.diag(np.asarray(spec['initial_estimate_error_sd'],float)**2)
 max_motion_reference_diff=0.
 for k in range(step+1):
  ds=float(frozen['ds'][k])
  a=float(frozen['gyro'][k])
  dt=float(frozen['dt'][k])
  Q=np.asarray(frozen['Q2'][k],float)
  control= float_complex_step(x,ds,a)
  y,p,_,_=predict(x,P,ds,a,dt,Q)
  delta=y-control
  delta[2]=wrap_scalar(delta[2])
  diff=float(np.max(np.abs(delta)))
  max_motion_reference_diff=max(max_motion_reference_diff,diff)
  if diff>EPS:
   raise RuntimeError('Independent DR integration parity failure at sample '+str(k))
  x,P=y,p
 return x,P,max_motion_reference_diff


def data_case(z,route,alg,step,spec):
 root='_temp/p2_preflight/trials/'+route+'/0.05/000/'
 with np.load(io.BytesIO(z.read(root+'INPUTS.npz')),allow_pickle=False) as original:
  frozen={k:original[k].copy() for k in original.files}
 with np.load(io.BytesIO(z.read(root+alg+'/FAILED_STEP.npz')),allow_pickle=False) as failed:
  prior=np.asarray(failed['prior_x'],float).copy()
  prior_P=np.asarray(failed['prior_P'],float).copy()
  obs=np.asarray(failed['z'],float).copy()
  R=np.asarray(failed['R'],float).copy()
 if not np.array_equal(obs,frozen['z'][step]):
  raise RuntimeError('Original observation time index mismatch')
 xdr,Pdr,diff=calc_dr_only(frozen,step,spec)
 true_pose=frozen['truth'][step+1]
 model=SyntheticRF()
 rdr,hdr=model(xdr)
 rprior,hprior=model(prior)
 rtruth,_=model(true_pose)
 rrf=float(obs[0]);t=float(rtruth[0])
 variance_dr=float(hdr[0]@Pdr@hdr[0]+R[0,0])
 variance_map=float(hprior[0]@prior_P@hprior[0]+R[0,0])
 e=np.asarray(xdr-true_pose[:3],float)
 e[2]=wrap_scalar(e[2])
 m=np.asarray(prior[:3]-true_pose[:3],float)
 m[2]=wrap_scalar(m[2])
 result={
  'case':route+'/'+alg,'time_s':float((step+1)*frozen['dt'][step]),
  'original_step_index':int(step),'true_bias_dps_scoring_only':.05,
  'DR_only_uses_RF_in_prediction':False,
  'DR_only_input_history_steps':int(step+1),
  'DR_only_state':xdr,'DR_only_covariance':Pdr,
  'MAP_prior_state':prior,'MAP_prior_covariance':prior_P,
  'truth_scoring_only':true_pose,
  'RF_current_observation':obs,
  'r_true_m':t,
  'r_DR_only_m':float(rdr[0]),'r_MAP_prior_m':float(rprior[0]),
  'r_RF_m':rrf,
  'DR_only_minus_RF_m':float(rdr[0]-rrf),
  'MAP_prior_minus_RF_m':float(rprior[0]-rrf),
  'DR_only_absolute_range_error_m':abs(float(rdr[0])-t),
  'MAP_prior_absolute_range_error_m':abs(float(rprior[0])-t),
  'RF_absolute_range_error_m':abs(rrf-t),
  'RF_better_than_DR_only_radial':bool(abs(rrf-t)<abs(float(rdr[0])-t)),
  'RF_better_than_MAP_prior_radial':bool(abs(rrf-t)<abs(float(rprior[0])-t)),
  'DR_only_Range_NIS':(float(rdr[0])-rrf)**2/variance_dr,
  'MAP_prior_Range_NIS':(float(rprior[0])-rrf)**2/variance_map,
  'DR_only_heading_error_deg':math.degrees(e[2]),
  'MAP_prior_heading_error_deg':math.degrees(m[2]),
  'DR_only_position_error_m':float(np.linalg.norm(e[:2])),
  'MAP_prior_position_error_m':float(np.linalg.norm(m[:2])),
  'DR_only_independent_motion_parity_max':diff,
  'interpretation':'Pure DR-only is a separate 3-state prediction. MAP prior already includes past RF. Both differ from the independent signed RF branch dataset.'
 }
 return result


def to_json(value):
 if isinstance(value,dict):return {k:to_json(v) for k,v in value.items()}
 if isinstance(value,(list,tuple)):return [to_json(v) for v in value]
 if isinstance(value,np.ndarray):return value.tolist()
 if isinstance(value,(np.floating,np.integer)):return value.item()
 return value


def main():
 p=argparse.ArgumentParser()
 p.add_argument('--source-audit',type=Path,required=True)
 p.add_argument('--input-audit',type=Path,required=True)
 p.add_argument('--artifact',type=Path,required=True)
 p.add_argument('--out',type=Path,required=True)
 args=p.parse_args()
 if os.environ.get('GITHUB_ACTIONS')!='true':
  raise RuntimeError('Cloud execution only')
 src=json.loads(args.source_audit.read_text())
 inp=json.loads(args.input_audit.read_text())
 if not (src['verdict']==inp['verdict']=='GO'
         and src['git_sha']==inp['git_sha']==os.environ['GITHUB_SHA']):
  raise RuntimeError('D3B requires both bound pre-run audit passes')
 for name,h in inp['source_sha256'].items():
  if file_sha(HERE/name)!=h:
   raise RuntimeError('D3B source changed after code audit: '+name)
 out=args.out.resolve()
 out.mkdir(parents=True,exist_ok=False)
 summary={'schema':'D3B_FROZEN_P2_PURE_DR_VS_MAP_PRIOR_VS_RF',
          'source_sha':os.environ['GITHUB_SHA'],
          'original_p2_run':ARTIFACT_RUN,
          'original_p2_commit':ARTIFACT_COMMIT,
          'cloud_run_id':os.environ['GITHUB_RUN_ID'],
          'source_audit_sha256':file_sha(args.source_audit),
          'input_audit_sha256':file_sha(args.input_audit),
          'cloud_artifact_sha256':file_sha(args.artifact),
          'scientific_PASS':False,
          'P2_full':'NOT_RUN','R3':'NOT_RUN','P3_P6':'NOT_RUN',
          'start_utc':datetime.now(timezone.utc).isoformat()}
 try:
  with zipfile.ZipFile(args.artifact) as z:
   contract=json.loads(z.read('_temp/p2_preflight/START.json'))
   spec=contract['contract']
   cases=[data_case(z,route,alg,k,spec) for route,alg,k,_,_ in METADATA]
  converted=to_json(cases)
  (out/'D3B_DR_ONLY_CASES.json').write_text(json.dumps(converted,indent=2,allow_nan=False)+'\n')
  summary['cases']=converted
  summary['rf_better_than_DR_only_count']=sum(x['RF_better_than_DR_only_radial'] for x in cases)
  summary['rf_better_than_MAP_prior_count']=sum(x['RF_better_than_MAP_prior_radial'] for x in cases)
  summary['DR_only_NIS_above_6_635_count']=sum(x['DR_only_Range_NIS']>6.634896601 for x in cases)
  summary['MAP_prior_NIS_above_6_635_count']=sum(x['MAP_prior_Range_NIS']>6.634896601 for x in cases)
  summary['status']='DIAGNOSTIC_COMPLETED'
  summary['exit_code']=0
 except Exception as exc:
  import traceback
  summary.update(status='DIAGNOSTIC_FAILED',exit_code=2,
     error_type=type(exc).__name__,error=str(exc),traceback=traceback.format_exc())
 summary['end_utc']=datetime.now(timezone.utc).isoformat()
 (out/'FINAL.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
 for case in summary.get('cases',[]):
  print('D3B_CASE '+json.dumps({k:case[k] for k in (
   'case','r_true_m','r_DR_only_m','r_MAP_prior_m','r_RF_m',
   'DR_only_absolute_range_error_m','MAP_prior_absolute_range_error_m',
   'RF_absolute_range_error_m','DR_only_Range_NIS','MAP_prior_Range_NIS',
   'RF_better_than_DR_only_radial','RF_better_than_MAP_prior_radial',
   'DR_only_heading_error_deg','MAP_prior_heading_error_deg')},allow_nan=False),flush=True)
 print('D3B_FINAL '+json.dumps({k:summary[k] for k in
  ('status','exit_code','rf_better_than_DR_only_count',
   'rf_better_than_MAP_prior_count','DR_only_NIS_above_6_635_count',
   'MAP_prior_NIS_above_6_635_count') if k in summary},allow_nan=False),flush=True)
 return summary['exit_code']

if __name__=='__main__':
 raise SystemExit(main())
