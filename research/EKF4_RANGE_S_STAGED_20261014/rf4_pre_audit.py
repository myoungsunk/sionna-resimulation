"""Mandatory source audit for P6 local RF pilot; stdlib-only before any model."""
import argparse,ast,datetime,hashlib,json,os,pathlib,subprocess
HERE=pathlib.Path(__file__).resolve().parent
REPO=HERE.parents[1]
ORIGINAL_P0='research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json'
ORIGINAL_P2='research/EKF3_INDEPENDENT_20261013/p2_frozen_rf_one_step.py'
PY='research/EKF4_RANGE_S_STAGED_20261014/rf4_recursive_pilot.py'
WF='.github/workflows/ekf4-rf4-p6-local-pilot.yml'
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def main():
 a=argparse.ArgumentParser();a.add_argument('--out',required=True);args=a.parse_args()
 if os.environ.get('GITHUB_ACTIONS')!='true':raise RuntimeError('cloud only')
 out=pathlib.Path(args.out);out.mkdir(parents=True,exist_ok=False)
 checks=[]
 for path in (ORIGINAL_P0,ORIGINAL_P2,PY,WF):
  checks.append({'name':'required_source_exists','path':path,'ok':(REPO/path).is_file()})
 if all(x['ok'] for x in checks):
  p0=json.loads((REPO/ORIGINAL_P0).read_text())
  checks.extend([
   {'name':'P0_manifest_schema','ok':p0['schema']=='EKF3_P0_FREEZE_V1'},
   {'name':'P0_FFD_asset_inventory','ok':len(p0['assets'])==39},
   {'name':'P0_LoS_Full_case_inventory','ok':len(p0['cases'])==7},
   {'name':'fixed_R0_no_oracle','ok':p0['experiment']['inverse_RF_heading_pseudomeasurement'].startswith('diagnostic only')},
  ])
  source=(REPO/PY).read_text()
  ast.parse(source)
  checks.append({'name':'one_RF Range_factor_plus_s','ok':"z=np.array([float(obs['range_m'][k]),float(obs['s'][k])])" in source})
  checks.append({'name':'four_state_bias_model','ok':'MAP4_GATED' in source and 'MAP4_ALL' in source})
  checks.append({'name':'fixed_source_not_importing_h3_oracle','ok':'h3_range_sign_audit' not in source})
  w=(REPO/WF).read_text()
  cmds=['rf4_pre_audit.py --out','p0_verify_inputs.py','rf4_recursive_pilot.py --audit']
  pos=[w.find(n) for n in cmds]
  checks.append({'name':'preaudit_before_RF_numerics','ok':min(pos)>=0 and pos==sorted(pos)})
  checks.append({'name':'GitHub read-only','ok':'contents: read' in w and 'actions: read' in w})
 verdict='GO' if all(c['ok'] for c in checks) else 'HOLD'
 outp={'schema':'P6_LOCAL_PILOT_PRE_RUN_SOURCE_AUDIT','git_sha':os.environ['GITHUB_SHA'],
  'verdict':verdict,'checks':checks,'source_sha256':{path:sha(REPO/path) for path in
   (ORIGINAL_P0,ORIGINAL_P2,PY,WF) if (REPO/path).is_file()},
  'scientific_PASS':False,'P5_full_posterior_reference':'NOT_VALIDATED',
  'audit_type':'source AST and frozen manifest; not independent RF physics certification',
  'time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 (out/'PRE_RUN_AUDIT.json').write_text(json.dumps(outp,indent=2,ensure_ascii=False)+'\n')
 print('P6_PRE_RUN_AUDIT '+json.dumps({'verdict':verdict,'failures':[x for x in checks if not x['ok']]}),flush=True)
 return 0 if verdict=='GO' else 2
if __name__=='__main__':raise SystemExit(main())
