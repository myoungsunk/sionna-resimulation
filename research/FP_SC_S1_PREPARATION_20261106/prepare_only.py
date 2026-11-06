"""Preparation only: no adapter instantiation, selection or EKF calls."""
import sys, json, hashlib, shutil, subprocess, datetime
from pathlib import Path
root=Path(__file__).resolve().parents[2]
old=Path(sys.argv[1]).resolve()
sys.path[:0]=[str(root/'src'),str(root/'scripts')]
import fp_sc_vab_shadow_stages as s
from qclean_uwb.fp_sc.e0_baseline import BANKS, ORIGINAL_CODE
from qclean_uwb.fp_sc.followup.data import load_shadow_online_only, load_shadow_reference_after_s1
out=Path(__file__).resolve().parent/'FINAL_002'
out.mkdir(exist_ok=True)
b='research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_SELECTIVE_CORRECTION_001'
source=json.loads((old/b/'PRIOR_INTEGRITY_R1_20261105/PREPARATION_001/MANIFEST_PREP_ONLY.json').read_text())
def h(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def materialize(rel,sha):
    p=root/rel
    if p.exists() and h(p)==sha:return
    if p.exists():
        assert p.stat().st_size<1024 and p.read_bytes().startswith(b'version https://git-lfs.github.com/spec/v1'),rel
    q=old/rel
    p.parent.mkdir(parents=True,exist_ok=True)
    if q.exists() and h(q)==sha:shutil.copyfile(q,p)
    else:
        data=subprocess.check_output(['git','show','HEAD:'+rel],cwd=root)
        assert hashlib.sha256(data).hexdigest()==sha,rel
        p.write_bytes(data)
    assert h(p)==sha
for rel,sha in BANKS.items():materialize(rel,sha)
for rel,sha in ORIGINAL_CODE.items():materialize(rel,sha)
for rel in s.BASELINE_REQUIRED:
    p=root/rel
    if not p.exists():
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes(subprocess.check_output(['git','show','HEAD:'+rel],cwd=root))
paths=subprocess.check_output(['git','ls-tree','-r','--name-only','HEAD',
    'src/qclean_uwb/drivesim','src/qclean_uwb/scenarios'],cwd=root,text=True).splitlines()
for rel in paths:
    if rel.endswith('.py') and not (root/rel).exists():
        p=root/rel;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes(subprocess.check_output(['git','show','HEAD:'+rel],cwd=root))
code=set(s.CODE_REQUIRED)
for folder in ('src/qclean_uwb/fp_sc/followup','src/qclean_uwb/drivesim','src/qclean_uwb/scenarios'):
    code.update(p.relative_to(root).as_posix() for p in (root/folder).glob('*.py'))
locks={p:h(root/p) for p in sorted(code)}
baseline={p:h(root/p) for p in s.BASELINE_REQUIRED}
assert source['policy']==s.Policy().__dict__
rows=[]
for cid,case in source['cases'].items():
    if case['metadata'].get('corpus')!='dynamic':continue
    inputs={case[key]:source['input_files'][case[key]] for key in ('online_npz','evaluator_npz')}
    for rel,sha in inputs.items():materialize(rel,sha)
    c=load_shadow_online_only(root,case,inputs)
    load_shadow_reference_after_s1(root,case,inputs,expected_t=c.t,expected_pose=c.pose_id)
    m=dict(schema='FP_SC_VAB_SHADOW_STAGES_V1',stage=s.STAGES[0],case_id=cid,case=case,
        policy=source['policy'],policy_sha256=s.Policy(**source['policy']).sha,
        candidate_arm='VAB',candidate_mode='TWO_PORT_UNION',
        source_commit='e416cf62c0cde15151a1851168231da73a0cbfff',
        implementation_commit='9cc34f0675a79ee94e2af39f93bf84bb3e45d587',
        code_files=locks,baseline_sources=baseline,model_files=BANKS,input_files=inputs,previous={})
    p=out/(cid+'_S1_MANIFEST.json')
    assert not p.exists(), 'PREPARATION_OUTPUT_EXISTS'
    p.write_text(json.dumps(m,indent=2),encoding='utf-8')
    r=subprocess.run([sys.executable,str(root/'scripts/fp_sc_vab_shadow_stages.py'),
        'preflight','--manifest',str(p)],cwd=root,capture_output=True,text=True)
    rows.append(dict(case=cid,n=len(c.t),expected_s1_rows=4*len(c.t),
        manifest_sha256=h(p),common_identity=s.identity(m),input_schema_and_join='PASS',
        baseline_context_present=c.baseline_trace is not None,
        exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr))
    print(cid,len(c.t),'preflight',r.returncode,flush=True)
    assert r.returncode==0,r.stderr
receipt=dict(question='FP-SC-S1-PREP-001',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    role='IMPLEMENTER_SELF_CHECK',independent_audit=False,status='PASS_PREFLIGHT_NO_SCIENCE',
    python=sys.version,rows=rows,total_packets=sum(r['n'] for r in rows),
    expected_total_s1_rows=sum(r['expected_s1_rows'] for r in rows),approval_created=False,science_runs=0,
    model_hashes=BANKS,model_check='original byte hashes; no model inference',
    preparation_script_sha256=h(Path(__file__)))
(out/'PREFLIGHT_RECEIPT.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print('COMPLETE',receipt['total_packets'],receipt['expected_total_s1_rows'])
