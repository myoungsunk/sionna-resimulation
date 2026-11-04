"""Exact phase authorization, checked before any child/model creation."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
BOUND = ('authority.py','engine.py','evaluate.py','run.py','launch.py','test_engine.py',
         'PLAN.json','WINDOWS.json','INPUT_LOCK.json','CONTRACT_KO.md','GOVERNANCE.json',
         '../../C1/C1B_001/legacy.py')
BRANCH = 'refs/heads/proposal/mbvar-physical-causality-preflight-20261104'
sha = lambda path:hashlib.sha256(path.read_bytes()).hexdigest()


def authorization(plan, phase):
    p = plan['phases'][phase]
    return dict(stage='C2_only',phase=phase,routes=plan['routes'],biases=plan['biases'],seeds=p['seeds'],
                output=p['output'],window_cells=p['window_cells'],trajectories=p['trajectories'],posterior_rows=p['posterior_rows'])


def check(phase):
    plan = json.loads((HERE/'PLAN.json').read_bytes());p = plan['phases'][phase]
    go = json.loads((HERE/p['go']).read_bytes())
    bindings = {name:sha(HERE/name) for name in BOUND}
    if go.get('schema')!='C2_GO_V1' or go.get('decision')!='GO' or go.get('authorized')!=authorization(plan,phase) or go.get('bindings_sha256')!=bindings:
        raise ValueError('independent phase-specific exact-code C2 GO required')
    if phase=='remaining':
        receipt = HERE/'audit/C2_DEV_RESULT_AUDIT_RESULT.json'
        if sha(receipt)!=go.get('prerequisite_sha256') or json.loads(receipt.read_bytes()).get('decision')!='ACCEPT':
            raise ValueError('independent DEV acceptance prerequisite')
    return plan,p,go,bindings


def committed_revision(phase):
    repo = HERE.parents[4]
    def git(*args):return subprocess.check_output(['git','-C',str(repo),*args])
    if Path(git('rev-parse','--show-toplevel').decode().strip()).resolve()!=repo.resolve():
        raise ValueError('verified repository root')
    revision = git('ls-remote','origin',BRANCH).decode().split()[0]
    plan = json.loads((HERE/'PLAN.json').read_bytes())
    paths = [*(HERE/name for name in BOUND),HERE/plan['phases'][phase]['go']]
    if phase=='remaining':paths.append(HERE/'audit/C2_DEV_RESULT_AUDIT_RESULT.json')
    for path in paths:
        relative = path.resolve().relative_to(repo.resolve()).as_posix()
        if git('show',revision+':'+relative)!=path.read_bytes():raise ValueError('local bound file differs from published commit '+relative)
    return revision
