"""Scope-specific PRE-RUN audit for frozen RF artifact and LUT.

No model inference. Run before P3, P4, P5 and P6, verifying exact code
and evidence SHA. Previously audited RF H/LUT byte parity is reused rather
than re-executing the 326 MB FFD conversion.
"""
import argparse,hashlib,json,os,zipfile
from datetime import datetime,timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
ARCHIVE_SHA='88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63'
ROOT_LUT='results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/'
MANIFEST='research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json'
SOURCE_FILES=['rf_stage_audit.py','rf_adapter4.py','rf_staged.py','core.py',
              'P3_P6_FROZEN_RF_CONTRACT_KO.md']
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for block in iter(lambda:f.read(1<<20),b''):h.update(block)
 return h.hexdigest()
def main():
 a=argparse.ArgumentParser()
 a.add_argument('--stage',choices=['P3','P4','P5','P6'],required=True)
 a.add_argument('--archive',required=True,type=Path)
 a.add_argument('--prior',type=Path)
 a.add_argument('--out',required=True,type=Path)
 args=a.parse_args()
 if os.getenv('GITHUB_ACTIONS')!='true':raise RuntimeError('GitHub-hosted audit required')
 out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
 results=[];checks=lambda name,ok,**extra:results.append({'check':name,'ok':bool(ok),**extra})
 try:
  for name in SOURCE_FILES:
   f=HERE/name;checks('source_exists_'+name,f.is_file())
  manifest=json.loads((ROOT/MANIFEST).read_text())
  asset={x['path']:x for x in manifest['assets']}
  checks('P0_frozen_schema',manifest['schema']=='EKF3_P0_FREEZE_V1')
  for name in ('hs_lut_2deg.npy','hs_lut_meta.json'):
   rel=ROOT_LUT+name
   f=ROOT/rel
   checks('LUT_sha_'+name,f.is_file() and sha(f)==asset[rel]['sha256'])
  checks('P2_archive_sha',args.archive.exists() and sha(args.archive)==ARCHIVE_SHA)
  with zipfile.ZipFile(args.archive) as z:
   checks('ZIP_CRC',z.testzip() is None)
   names=z.namelist()
   trace=[x for x in names if x.endswith('_ONE_STEP.npz')]
   checks('14_frozen_channels',len(trace)==14)
   summary=json.loads(z.read('P2_OUT/P2_ONE_STEP_SUMMARY.json'))
   p0=json.loads(z.read('P2_VERIFY_P0_RUNTIME.json'))
   checks('P0_original_39_sources',p0.get('status')=='PASS_LOCAL_SHA256_SHAPE_POSE_PREFLIGHT' and p0.get('assets')==39)
   checks('P2_original_source',summary.get('status')=='ONE_STEP_FROZEN_RF_EXECUTED_MATHEMATICAL_CHECKS_PASS')
   checks('R0_noise_model',summary['R0']=={'Rs':.0081,'Rr_m2':.0068578637,'Rsr':0.,'range_offset_m':-.5315983906250129})
   checks('archive_trace_SHA',len(summary['per_case'])==14 and all(
    hashlib.sha256(z.read('P2_OUT/'+case['trace_file'])).hexdigest()==case['trace_sha256']
    for case in summary['per_case']))
  if args.prior is not None:
   p=json.loads((args.prior/'FINAL.json').read_text())
   checks('prerequisite_parity',p.get('status')=='PASS' and p.get('git_sha')==os.getenv('GITHUB_SHA'))
  import ast
  for file in ('rf_adapter4.py','rf_staged.py'):
   ast.parse((HERE/file).read_text(),filename=file)
  checks('source_AST',True)
  workflow=ROOT/'.github/workflows/ekf4-frozen-rf-p3p6.yml'
  s=workflow.read_text()
  checks('cloud_workflow_readonly','contents: read' in s and 'actions: read' in s)
  checks('audits_in_each_stage',all(s.count('rf_stage_audit.py --stage '+x)>=1 for x in ('P3','P4','P5','P6')))
 except Exception as e:checks('AUDIT_RUNTIME_FAILURE',False,error=type(e).__name__+': '+str(e))
 r={'schema':'EKF4_RF_PRE_RUN_AUDIT','status':'GO' if all(x['ok'] for x in results) else 'HOLD',
    'stage':args.stage,'git_sha':os.getenv('GITHUB_SHA'),'run_id':os.getenv('GITHUB_RUN_ID'),
    'time_utc':datetime.now(timezone.utc).isoformat(),
    'decision':'Does this exact frozen RF trace+LUT and source safely support this specific stage?',
    'checks':results,'source_sha256':{name:sha(HERE/name) for name in SOURCE_FILES if (HERE/name).is_file()},
    'archive_sha256':sha(args.archive) if args.archive.exists() else None,
    'independent_external_scene_count':1,'independent_peer_review':False,'scientific_PASS':False}
 (out/'PRE_RUN_AUDIT.json').write_text(json.dumps(r,indent=2,allow_nan=False)+'\n')
 print('RF_PRE_RUN_AUDIT '+json.dumps({k:r[k] for k in ('stage','status','run_id')},allow_nan=False),flush=True)
 if r['status']!='GO':print('AUDIT_DEFECTS '+json.dumps([x for x in results if not x['ok']]),flush=True)
 return 0 if r['status']=='GO' else 2
if __name__=='__main__':raise SystemExit(main())
