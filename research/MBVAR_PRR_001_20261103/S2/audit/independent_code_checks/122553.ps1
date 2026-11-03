@'
from pathlib import Path
import ast,json,types,subprocess,hashlib,importlib.util
import numpy as np
repo=Path('/mnt/d/codex/MBVAR_PRR_001_20261103');package=Path('research/MBVAR_PRR_001_20261103');stage=package/'S2';root=repo/stage;code='4eeb7f539ea40fbbc4a4d5eb477d788f2d230945';rules=(root/'IMPLEMENTATION_RULES.json').read_bytes();contract='6c24e19de5ddb9d22f8e6b7724a7955680a2108295f02aac7793a13a4d33bf96'
# Execute the actual frozen authorize function with an in-memory remote store.
# No files, credentials, runtime config, or Git refs are modified.
source=(root/'grant.py').read_text();fn=next(x for x in ast.parse(source).body if isinstance(x,ast.FunctionDef) and x.name=='authorize');compiled=compile(ast.Module(body=[fn],type_ignores=[]),'frozen_S2_grant.py','exec')
sha=lambda b:hashlib.sha256(b).hexdigest();records={str(p.relative_to(repo)):p.read_bytes() for d in ['S1','S2'] for p in (repo/package/d).glob('*.py')};records[str(stage/'IMPLEMENTATION_RULES.json')]=rules
basegrant=dict(token='GO_S2_DEV',auditor='/root/a0',code_commit=code,rules_sha256=sha(rules),contract_sha256=contract);box={};calls=[]
def require(condition,why):
 if not condition:raise RuntimeError(why)
def blob(head,path):
 name=path.as_posix()
 if name.endswith('OWNER_APPROVAL.json'):return json.dumps(box.get('owner',dict(S2_authorized=True,S3_authorized=True))).encode()
 if name.endswith('DEV_RESULTS.json'):return json.dumps(box.get('dev',dict(complete=True,code_commit=code,run_manifest_sha256='development-frozen-sha'))).encode()
 return json.dumps(box['grant']).encode()
def pinned(commit,path):
 require(commit==code,'frozen code mismatch');require(str(path)!=box.get('bad_path'),'pinned dependency mismatch');return records[str(path)]
def external():require(not box.get('bad_external'),'external lineage mismatch');calls.append('external')
g=types.SimpleNamespace(authorize=lambda phase:dict(contract_sha256=contract),git=lambda *args:(code+' refs/heads/research/mbvar-prr-001-20261103\n').encode(),branch='refs/heads/research/mbvar-prr-001-20261103',blob=blob,require=require,pinned=pinned,digest=sha,verify_external=external)
ns=dict(g=g,repo=repo,package=package,stage=stage,json=json);exec(compiled,ns);original_run=subprocess.run
try:
 subprocess.run=lambda *a,**kw:types.SimpleNamespace(returncode=box.get('ancestry',0))
 box['grant']=basegrant.copy();assert ns['authorize']('dev')['code_commit']==code and calls==['external']
 failures=[]
 cases=[('wrong_auditor',{'auditor':'implementer'},{}),('wrong_phase',{'token':'GO_S2_LOCKED_EVAL'},{}),('wrong_code',{'code_commit':'0'*40},{}),('wrong_rules',{'rules_sha256':'0'*64},{}),('wrong_contract',{'contract_sha256':'0'*64},{}),('unpublished_code',{},dict(ancestry=1)),('no_owner_S2',{},dict(owner=dict(S2_authorized=False,S3_authorized=True))),('modified_inherited_online',{},dict(bad_path=str(package/'S1/online.py'))),('modified_external_model',{},dict(bad_external=True))]
 for name,changes,extra in cases:
  box.clear();box.update(extra);box['grant']={**basegrant,**changes}
  try:ns['authorize']('dev')
  except RuntimeError:failures.append(name)
  else:raise AssertionError('invalid approval accepted: '+name)
 box.clear();box['grant']={**basegrant,'token':'GO_S2_LOCKED_EVAL','dev_manifest_sha256':'development-frozen-sha'};assert ns['authorize']('eval')['token']=='GO_S2_LOCKED_EVAL'
 box['grant']['dev_manifest_sha256']='wrong'
 try:ns['authorize']('eval')
 except RuntimeError:failures.append('wrong_dev_manifest')
 else:raise AssertionError('wrong development manifest accepted')
finally:subprocess.run=original_run
# Endpoint definitions independently checked with analytic constant-error integrals.
sp=importlib.util.spec_from_file_location('s2_endpoint_target',root/'endpoints.py');ep=importlib.util.module_from_spec(sp);sp.loader.exec_module(ep)
t=np.arange(0,4.01,.2);truth=np.zeros((len(t),3));x=np.zeros((len(t),4));x[:,0]=.2;x[:,2]=np.deg2rad(2)
a=ep.recovery_endpoints(t,x,truth,0);assert a['censored'] and a['recovery_time_s'] is None and np.isclose(a['heading_integral_10s'],8) and np.isclose(a['xy_integral_20s'],.8) and a['window_10s_censored']
x[:,0]=.01;x[:,2]=np.deg2rad(.5);a=ep.recovery_endpoints(t,x,truth,0);assert a['already_accurate'] and np.isclose(a['recovery_time_s'],2)
x[:5,0]=.2;a=ep.recovery_endpoints(t,x,truth,0);assert not a['already_accurate'] and np.isclose(a['recovery_time_s'],3)
print(json.dumps(dict(status='PASS',grant_valid_dev_and_eval_fixtures=2,grant_negative_tests_rejected=failures,analytic_endpoint_cases=3,external_calls_exercised=True,inherited_S1_runtime_validation_previously_audited=True,local_environment_and_refs_modified=False)))
'@ | wsl -d Ubuntu-24.04 env PYTHONDONTWRITEBYTECODE=1 PYTHONHOME=/home/myoung-sun/.local/share/prr31117 LD_LIBRARY_PATH=/home/myoung-sun/.local/share/prr31117/lib OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /home/myoung-sun/.local/share/prr31117/bin/python3 -