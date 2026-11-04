"""Resolve the published N0B code-audit grant before any outcome work."""
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
here=Path(__file__).resolve().parent
pkg=here.parents[1]
repo=pkg.parents[1]
plan_commit='37d4dfb93c500547e377b42a00b66ce9c59ea0a5'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',str(repo),*args])
def bind(commit,path):
    raw=git('show',commit+':'+path.relative_to(repo).as_posix())
    if raw!=path.read_bytes():raise ValueError('pinned bytes '+str(path))
    return hashlib.sha256(raw).hexdigest()
def authorize():
    spec=importlib.util.spec_from_file_location('n0b_previous_grant',pkg/'S3/grant.py')
    previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
    inherited=previous.authorize('eval')
    remote=git('ls-remote','origin','refs/heads/proposal/mbvar-post-s3-causal-guard-shadow-20261104').decode().split()[0]
    path=here/'audit/GO_N0B.json';raw=git('show',remote+':'+path.relative_to(repo).as_posix());g=json.loads(raw)
    if g['token']!='GO_N0B' or g['auditor']!='/root/a0':raise ValueError('grant')
    code=g['code_commit']
    git('merge-base','--is-ancestor',code,remote);git('merge-base','--is-ancestor',plan_commit,code)
    for f in here.glob('*.py'):bind(code,f)
    if bind(code,here/'RULES_KO.md')!=g['rules_sha256']:raise ValueError('rules')
    bind(plan_commit,here.parent/'FOLLOWUP_EXECUTION_PLAN_KO.md')
    for f in ['LABELS.csv','BENEFIT.csv','P0_INDEPENDENT_AUDIT.md']:bind(plan_commit,here.parent/'P0'/f)
    for s in ['S2','S3']:
        for f in ['TRACE_INDEX.json','EVENTS.json']:bind(plan_commit,pkg/s/'runs/EVAL_001'/f)
    for rel in ('S2/runs/DEV_REPAIR_001/TRACE_INDEX.json','S3/runs/DEV_001/TRACE_INDEX.json','S3/runs/DEV_001/RUN_MANIFEST.json','S3/RULES.json'):
        bind(plan_commit,pkg/rel)
    return dict(**g,approval_commit=remote,inherited=inherited)

