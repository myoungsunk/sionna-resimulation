"""S2 grant resolution binds its implementation and inherited S1 dependencies."""
import importlib.util
import json
import sys
from pathlib import Path
s=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('s1_grant',s.parent/'S1/grant.py');g=importlib.util.module_from_spec(sp);sp.loader.exec_module(g)
repo=g.repo;package=g.package;stage=package/'S2'
def authorize(phase):
 # Reuse all published A0/platform/dependency checks from the audited S1 grant.
 inherited=g.authorize('dev')
 head=g.git('ls-remote','origin',g.branch).decode().split()[0]
 token={'dev':'GO_S2_DEV','eval':'GO_S2_LOCKED_EVAL','repair':'GO_S2_REPAIR'}[phase]
 path=stage/'audit'/(token+'.json');raw=g.blob(head,path);grant=json.loads(raw)
 g.require(grant['token']==token and grant['auditor']=='/root/a0','S2 phase grant')
 code=grant['code_commit']
 import subprocess
 g.require(subprocess.run(['git','-C',str(repo),'merge-base','--is-ancestor',code,head]).returncode==0,'S2 code ancestry')
 for root in (repo/stage,repo/package/'S1'):
  for p in root.glob('*.py'):g.pinned(code,p.relative_to(repo))
 rules=g.pinned(code,stage/'IMPLEMENTATION_RULES.json')
 g.require(g.digest(rules)==grant['rules_sha256'],'S2 rules')
 g.require(grant['contract_sha256']==inherited['contract_sha256'],'S2 contract')
 approval=json.loads(g.blob(head,stage/'OWNER_APPROVAL.json'))
 g.require(approval['S2_authorized'] and approval['S3_authorized'],'owner sequence approval')
 if phase=='repair':
  scope_raw=g.pinned(code,stage/'REPAIR_SCOPE.json');scope=json.loads(scope_raw)
  g.require(g.digest(scope_raw)==grant['scope_sha256'],'repair scope')
  g.require(scope['source_commit']==grant['source_commit'],'repair source commit')
  g.require(scope['maximum_scientific_replays']==8 and len(scope['replay_files'])==8,'repair cap')
  g.require(subprocess.run(['git','-C',str(repo),'merge-base','--is-ancestor',scope['source_code_commit'],scope['source_commit']]).returncode==0,'source code ancestry')
  g.require(g.blob(code,stage/'recovery.py')==g.blob(scope['source_commit'],stage/'recovery.py'),'repair changes dynamics')
  for name,h in scope['source_metadata_hashes'].items():
   path=stage/scope['source_directory']/name
   g.require(g.digest(g.pinned(scope['source_commit'],path))==h,'repair source '+name)
 if phase=='eval':
  dev=json.loads(g.blob(head,stage/'audit/DEV_RESULTS.json'))
  g.require(dev['complete'] and dev['code_commit']==code and dev['run_manifest_sha256']==grant['dev_manifest_sha256'],'S2 development result')
  g.require(dev['mode']=='ADDITIVE_REPAIR','S2 repaired development required')
  repair_path=Path(dev['repair_manifest_path'])
  g.require(repair_path.parts[:2]==('runs','DEV_REPAIR_001') and '..' not in repair_path.parts,'repair receipt path')
  repair_raw=g.blob(head,stage/repair_path);repair=json.loads(repair_raw)
  g.require(g.digest(repair_raw)==dev['run_manifest_sha256'],'published repair manifest')
  g.require(repair['status']=='COMPLETE' and repair['scientific_replays']==8 and repair['grant']['code_commit']==code,'repair completion')
  g.require(repair['source_manifest_sha256']==dev['original_run_manifest_sha256'],'original development lineage')
  authorization=g.blob(repair['grant']['approval_commit'],stage/'audit/GO_S2_REPAIR.json')
  g.require(g.digest(authorization)==repair['grant']['audit_sha256'],'authentic repair grant')
  issued=json.loads(authorization)
  g.require(issued['token']=='GO_S2_REPAIR' and issued['auditor']=='/root/a0' and issued['code_commit']==code,'issued repair scope')

 g.verify_external()
 result=dict(token=token,code_commit=code,approval_commit=head,audit_sha256=g.digest(raw),rules_sha256=g.digest(rules),contract_sha256=inherited['contract_sha256'])
 if phase=='repair':result.update(scope_sha256=grant['scope_sha256'],source_commit=grant['source_commit'])
 return result
