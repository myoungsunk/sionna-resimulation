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
 token={'dev':'GO_S2_DEV','eval':'GO_S2_LOCKED_EVAL'}[phase]
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
 if phase=='eval':
  dev=json.loads(g.blob(head,stage/'audit/DEV_RESULTS.json'))
  g.require(dev['complete'] and dev['code_commit']==code and dev['run_manifest_sha256']==grant['dev_manifest_sha256'],'S2 development result')
 g.verify_external()
 return dict(token=token,code_commit=code,approval_commit=head,audit_sha256=g.digest(raw),rules_sha256=g.digest(rules),contract_sha256=inherited['contract_sha256'])
