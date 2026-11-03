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
def verify_terminal_bytes(frozen_final,current_final,published_manifest,current_manifest,expected_code,grant):
    g.require(current_final==frozen_final,'immutable S2 terminal receipt changed')
    completion=json.loads(frozen_final)
    g.require(completion['complete'] and completion['independent_audit']=='ACCEPT','S2 terminal technical audit')
    g.require(completion['code_commit']==expected_code,'S2 completed code')
    g.require(g.digest(frozen_final)==grant['s2_final_sha256'],'S2 final receipt binding')
    g.require(current_manifest==published_manifest,'S2 published manifest changed')
    g.require(g.digest(published_manifest)==completion['run_manifest_sha256']==grant['s2_manifest_sha256'],'S2 terminal manifest')
    manifest=json.loads(published_manifest)
    g.require(manifest['status']=='COMPLETE' and manifest['phase']=='eval' and manifest['grant']['code_commit']==expected_code,'S2 actual completed evaluation')

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
    final_commit='dfd90f46adda11fbab2665d862cffb005fa93248'
    final_path=g.package/'S2/audit/FINAL_RESULTS.json'
    frozen_final=g.blob(final_commit,final_path)
    current_final=g.blob(head,final_path)
    completion=json.loads(frozen_final)
    published=completion['published_commit']
    g.require(subprocess.run(['git','-C',str(g.repo),'merge-base','--is-ancestor',published,final_commit]).returncode==0,'S2 published ancestry')
    g.require(subprocess.run(['git','-C',str(g.repo),'merge-base','--is-ancestor',final_commit,head]).returncode==0,'S2 terminal ancestry')
    manifest_path=g.package/'S2/runs/EVAL_001/RUN_MANIFEST.json'
    published_manifest=g.blob(published,manifest_path)
    current_manifest=g.blob(head,manifest_path)
    verify_terminal_bytes(frozen_final,current_final,published_manifest,current_manifest,inherited['code_commit'],grant)
    g.pinned(final_commit,final_path)
    g.pinned(published,manifest_path)
    # Cross-stage scoring reads this local file, so bind it to the audited publication.
    for directory in ('DEV_001','EVAL_001'):
        score_path=g.package/'S2/runs'/directory/'SCORES_PER_SEED.csv'
        g.pinned(published,score_path)
        g.require(g.blob(head,score_path)==g.blob(published,score_path),'S2 published scores changed')
    if phase=='eval':
        dev=json.loads(g.blob(head,stage/'audit/DEV_RESULTS.json'))
        g.require(dev['complete'] and dev['code_commit']==code and dev['run_manifest_sha256']==grant['dev_manifest_sha256'],'development prerequisite')
    return dict(token=token,code_commit=code,approval_commit=head,audit_sha256=g.digest(raw),contract_sha256=inherited['contract_sha256'])
