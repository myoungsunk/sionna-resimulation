"""Resolve the published, phase-specific S3 authorization."""
import importlib.util
import json
import subprocess
from pathlib import Path
s=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('previous_stage_grant',s.parent/'S2/grant.py')
previous=importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
g=previous.g
def authorize(phase):
    inherited=previous.authorize('eval')
    head=g.git('ls-remote','origin',g.branch).decode().split()[0]
    stage=g.package/'S3'
    token={'dev':'GO_S3_DEV','eval':'GO_S3_LOCKED_EVAL'}[phase]
    raw=g.blob(head,stage/'audit'/(token+'.json'))
    grant=json.loads(raw)
    code=grant['code_commit']
    g.require(grant['auditor']=='/root/a0' and grant['token']==token,'phase grant')
    g.require(subprocess.run(['git','-C',str(g.repo),'merge-base','--is-ancestor',code,head]).returncode==0,'ancestry')
    for name in ('S1','S2','S3'):
        for path in (g.repo/g.package/name).glob('*.py'):
            g.pinned(code,path.relative_to(g.repo))
    rules=g.pinned(code,stage/'RULES.json')
    g.require(g.digest(rules)==grant['rules_sha256'] and inherited['contract_sha256']==grant['contract_sha256'],'locked rules')
    completion=json.loads(g.blob(head,g.package/'S2/audit/FINAL_RESULTS.json'))
    g.require(completion['complete'] and completion['independent_audit']=='ACCEPT','S2 terminal technical audit')
    g.require(completion['code_commit']==inherited['code_commit'],'S2 completed code')
    previous_manifest=g.blob(head,g.package/'S2/runs/EVAL_001/RUN_MANIFEST.json')
    g.require(g.digest(previous_manifest)==completion['run_manifest_sha256']==grant['s2_manifest_sha256'],'S2 terminal manifest')
    if phase=='eval':
        dev=json.loads(g.blob(head,stage/'audit/DEV_RESULTS.json'))
        g.require(dev['complete'] and dev['code_commit']==code and dev['run_manifest_sha256']==grant['dev_manifest_sha256'],'development prerequisite')
    return dict(token=token,code_commit=code,approval_commit=head,audit_sha256=g.digest(raw),contract_sha256=inherited['contract_sha256'])
