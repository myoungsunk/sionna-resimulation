"""P3 frozen RF archive eligibility + P4 SAME-prior one-step numerical parity.

No new 4state RF run. Runs only GitHub cloud after source/zip audits.
"""
from __future__ import annotations
import argparse, ast, datetime, hashlib, io, json, os, pathlib, zipfile

HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[1]
ARCHIVE_SHA='88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63'
SCENE_IDS=('R2_aA_m0','R2_aA_m45','R2_aB_m0','R4_aA_m0','R4_aB_m0','R5_aA_m0','R5_aB_m0')
CHANNELS=('full','los')
P0='research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json'
ORIGINAL='research/EKF3_INDEPENDENT_20261013/P2_RUN_RECEIPT.json'
WF='.github/workflows/ekf4-rf-p3-p4.yml'
CODE='research/EKF4_RANGE_S_STAGED_20261014/rf_p3_p4.py'

def sha(b):return hashlib.sha256(b).hexdigest()
def digest(p):return sha(pathlib.Path(p).read_bytes())
def dump(path,x):
 pathlib.Path(path).write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def audit(a):
 root=pathlib.Path(a.out);root.mkdir(parents=True,exist_ok=False)
 checks=[]
 for n in (P0,ORIGINAL,CODE,WF):
  checks.append({'name':'source-file-presence','path':n,'ok':(ROOT/n).exists()})
 if all(x['ok'] for x in checks):
  p0=json.loads((ROOT/P0).read_text())
  q=json.loads((ROOT/ORIGINAL).read_text())
  checks.extend([
   {'name':'original-manifest-schema','ok':p0['schema']=='EKF3_P0_FREEZE_V1'},
   {'name':'prior-frozen-seven-cases','ok':len(p0['cases'])==7},
   {'name':'original-one-step-not-recursive','ok':q['p2']['type'].startswith('one-step')},
   {'name':'original-one-step-artifact-hash','ok':q['artifact']['archive_sha256']==ARCHIVE_SHA},
   {'name':'original-reference-success-but-not-scientific-PASS',
    'ok':q['github_actions']['conclusion']=='success' and q['scientific_PASS'] is False},
  ])
  ast.parse((ROOT/CODE).read_text(),filename=CODE)
  workflow=(ROOT/WF).read_text()
  tokens=['rf_p3_p4.py --phase audit','rf_p3_p4.py --phase verify','rf_p3_p4.py --phase p4']
  ix=[workflow.find(t) for t in tokens]
  checks.append({'name':'audits-are-before-math','ok':all(i>=0 for i in ix) and ix==sorted(ix),'positions':ix})
  checks.append({'name':'token-readonly','ok':'contents: read' in workflow and 'actions: read' in workflow})
 receipt={'stage':'P3_PRE_RUN_SOURCE_AUDIT','git_sha':os.environ['GITHUB_SHA'],
 'decision':'GO' if all(x['ok'] for x in checks) else 'HOLD',
 'independent_peer_review':False,'scientific_PASS':False,'checks':checks,
 'source_sha256':{n:digest(ROOT/n) for n in (P0,ORIGINAL,CODE,WF) if (ROOT/n).is_file()}}
 dump(root/'PRE_RUN_AUDIT.json',receipt)
 print('P3_SOURCE_AUDIT '+json.dumps({'decision':receipt['decision'],'checks':len(checks),
 'errors':[x for x in checks if not x['ok']]}),flush=True)
 return 0 if receipt['decision']=='GO' else 2

def verified_zip(a):
 if os.getenv('GITHUB_ACTIONS')!='true':raise RuntimeError('cloud-only')
 audit=json.loads(pathlib.Path(a.audit).read_text())
 if audit['decision']!='GO' or audit['git_sha']!=os.environ['GITHUB_SHA']:
  raise RuntimeError('P3 source audit missing or different SHA')
 for n,expected in audit['source_sha256'].items():
  if digest(ROOT/n)!=expected:raise RuntimeError('P3 source changed after audit')
 b=pathlib.Path(a.archive).read_bytes()
 if sha(b)!=ARCHIVE_SHA:raise RuntimeError('frozen ZIP SHA mismatch')
 with zipfile.ZipFile(io.BytesIO(b)) as z:
  if z.testzip():raise RuntimeError('ZIP CRC mismatch')
  names=set(z.namelist())
  needed={'P2_OUT/P2_ONE_STEP_SUMMARY.json','P2_VERIFY_P0_RUNTIME.json'}
  needed|={'P2_OUT/'+c+'_'+m+'_seed0_ONE_STEP.npz' for c in SCENE_IDS for m in CHANNELS}
  if not needed.issubset(names):raise RuntimeError('missing frozen traces')
  report=json.loads(z.read('P2_OUT/P2_ONE_STEP_SUMMARY.json'))
  if report['num_case_channel_runs']!=14 or report['scientific_PASS'] is not False:
   raise RuntimeError('frozen report identity mismatch')
 return b

def verify(a):
 global np
 import numpy as np
 b=verified_zip(a)
 root=pathlib.Path(a.out);root.mkdir(parents=True,exist_ok=False)
 receipt={'stage':'P3_RF_ARCHIVE_ELIGIBILITY','git_sha':os.environ['GITHUB_SHA'],
 'source_archive_sha256':ARCHIVE_SHA,'cases':[],'status':'STARTED',
 'scientific_PASS':False,'four_state_adapter':'NOT_IMPLEMENTED'}
 try:
  with zipfile.ZipFile(io.BytesIO(b)) as z:
   for c in SCENE_IDS:
    for channel in CHANNELS:
     name=f'P2_OUT/{c}_{channel}_seed0_ONE_STEP.npz'
     with np.load(io.BytesIO(z.read(name)),allow_pickle=False) as r:
      n=len(r['t_s'])
      shape=(r['xminus'].shape==(n,3) and r['Pminus'].shape==(n,3,3)
       and r['H'].shape==(n,3,2,3) and r['R'].shape==(n,3,2,2)
       and r['xplus'].shape==(n,3,3) and r['Pplus'].shape==(n,3,3,3)
       and r['innovation'].shape==(n,3,2) and r['status'].shape==(n,3)
       and r['z_s'].shape==(n,) and r['z_r_m'].shape==(n,))
      # Frozen A(s-only) and B(range-only) store NaN in UNUSED second
      # observation slots by design. Audit only active likelihood dimensions.
      finite=all(np.isfinite(r[k]).all() for k in (
        'xminus','Pminus','xplus','Pplus','z_s','z_r_m'))
      for arm in range(3):
       active=1 if arm<2 else 2
       finite = finite and bool(np.isfinite(r['H'][:,arm,:active]).all()
        and np.isfinite(r['R'][:,arm,:active,:active]).all()
        and np.isfinite(r['innovation'][:,arm,:active]).all())
      temporal=bool(np.all(np.diff(r['t_s'])>0) and len(np.unique(r['pose_id']))==n)
      if not shape or not finite or not temporal:
       raise RuntimeError('P3 invalid RF adapter arrays '+name)
      receipt['cases'].append({'case':c,'channel':channel,'samples':n,
       'shape_PASS':shape,'finite_PASS':finite,'time_pose_alignment_PASS':temporal,
       'file_sha256':sha(z.read(name))})
  receipt['status']='INPUT_ELIGIBLE_FOR_FIXED_ONE_STEP'
 except Exception as e:
  receipt['status']='INPUT_INELIGIBLE';receipt['error']=str(e)
 dump(root/'P3_FINAL.json',receipt)
 print('P3_FINAL '+json.dumps({'status':receipt['status'],'files':len(receipt['cases'])}),flush=True)
 return 0 if receipt['status']=='INPUT_ELIGIBLE_FOR_FIXED_ONE_STEP' else 2

def p4(a):
 global np
 import numpy as np
 b=verified_zip(a)
 gate=json.loads(pathlib.Path(a.p3).read_text())
 if gate['status']!='INPUT_ELIGIBLE_FOR_FIXED_ONE_STEP' or gate['git_sha']!=os.environ['GITHUB_SHA']:
  raise RuntimeError('P3 eligibility missing')
 root=pathlib.Path(a.out);root.mkdir(parents=True,exist_ok=False)
 results=[]
 try:
  with zipfile.ZipFile(io.BytesIO(b)) as z:
   for c in SCENE_IDS:
    for ch in CHANNELS:
     name=f'P2_OUT/{c}_{ch}_seed0_ONE_STEP.npz'
     with np.load(io.BytesIO(z.read(name)),allow_pickle=False) as q:
      max_pose=max_cov=0.;count=0;gated=0
      for i in range(len(q['t_s'])):
       if str(q['status'][i,2])!='applied':
        gated+=1
        continue
       x=q['xminus'][i];P=q['Pminus'][i]
       H=q['H'][i,2];R=q['R'][i,2];v=q['innovation'][i,2]
       S=H@P@H.T+R
       K=np.linalg.solve(S,H@P).T
       dx=K@v
       xm=x+dx;xm[2]=(xm[2]+np.pi)%(2*np.pi)-np.pi
       A=np.eye(3)-K@H
       cov=A@P@A.T+K@R@K.T
       delta=xm-q['xplus'][i,2];delta[2]=(delta[2]+np.pi)%(2*np.pi)-np.pi
       max_pose=max(max_pose,float(np.max(np.abs(delta))))
       max_cov=max(max_cov,float(np.max(np.abs(cov-q['Pplus'][i,2]))))
       count+=1
      results.append({'case':c,'channel':ch,'accepted_joint':count,
       'excluded_rejected':gated,'max_pose_error':max_pose,'max_cov_error':max_cov})
  worst=max(max(x['max_pose_error'],x['max_cov_error']) for x in results)
  status='FROZEN_LINEARIZED_JOINT_PARITY_PASS' if worst<1e-7 else 'PARITY_NOT_ESTABLISHED'
 except Exception as e:
  status='PARITY_CALCULATION_FAILED';results.append({'error':str(e)})
 rec={'stage':'P4_FROZEN_ONE_STEP_JOINT_PARITY','git_sha':os.environ['GITHUB_SHA'],
  'status':status,'cases':results,'scientific_PASS':False,
  'P4_relinearized_nonlin':'NOT_RUN','P5_multimodal':'NOT_RUN',
  'P6_fourstate_recursive':'NOT_RUN'}
 dump(root/'P4_FINAL.json',rec)
 print('P4_FINAL '+json.dumps({'status':status,'cases':len(results),'examples':results[:2]}),flush=True)
 return 0 if status=='FROZEN_LINEARIZED_JOINT_PARITY_PASS' else 2

def main():
 q=argparse.ArgumentParser();q.add_argument('--phase',choices=['audit','verify','p4'],required=True)
 q.add_argument('--archive');q.add_argument('--audit');q.add_argument('--p3')
 q.add_argument('--out',required=True);a=q.parse_args()
 if os.getenv('GITHUB_ACTIONS')!='true':raise RuntimeError('GitHub only')
 return {'audit':audit,'verify':verify,'p4':p4}[a.phase](a)
if __name__=='__main__':raise SystemExit(main())
