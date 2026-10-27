from pathlib import Path
import sys,json,hashlib,datetime,subprocess,re
sys.dont_write_bytecode=True
R=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,o):(R/n).write_text(json.dumps(o,indent=2,ensure_ascii=False),encoding='utf-8')
assert read(R/'REPLAY_RESULT.json')['status']=='TECHNICAL_PASS'
assert read(R/'VERIFY_CHECKS.json')['status']=='PASS'
assert read(R/'D_CHECKS.json')['status']=='PASS'
rec=read(R/'MANAGED_FINISH.json')['processes'][0]
assert rec['exit_code']==0 and rec['termination']=='natural' and rec['ref_count']==0
assert all(rec[k]['state']=='absent' for k in ['actual_process','actual_supervisor','job'])
repo=R.parents[2];head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip();assert head=='2ee731336fc2b37ffcd67f96a07bdaf3dccc2898'
assert not subprocess.check_output(['git','diff','--name-only'],cwd=repo,text=True).strip()
assert not subprocess.check_output(['git','diff','--cached','--name-only'],cwd=repo,text=True).strip()
status=subprocess.check_output(['git','status','--porcelain','--untracked-files=normal'],cwd=repo,text=True).strip();assert status=='?? research/DS_MASK_CAUSAL_X1_X2_20261026/why_ds_worse/'
assert not list(R.rglob('*.pyc'))
locks={}
for name in ['INPUT_LOCK.json','REPLAY_INPUT_LOCK.json','ANALYSIS_INPUT_LOCK.json']:
    for r in read(R/name)['files']:assert sha(Path(r['path']))==r['sha256'];locks[r['path']]=r['sha256']
md=(R/'RESULTS_KO.md').read_text();figs=re.findall(r'!\[[^\]]*\]\(([^)]+)\)',md);assert len(figs)==6 and all((R/f).exists() for f in figs)
assert read(R/'VISUAL_QA.json')['status']=='PASS'
dump('CHECKS.json',dict(status='PASS',D_checks='D_CHECKS.json',replay_checks='REPLAY_CHECKS.json',independent_trace_checks='VERIFY_CHECKS.json',independent_trace_check_count=len(read(R/'VERIFY_CHECKS.json')['checks']),input_hash_count=len(locks),OFF_and_ORACLE_controls='PASS_1e-10',D3_three_term_closure='PASS_1e-10',Q_R_pol_mask_unchanged=True,managed_receipt='MANAGED_FINISH.json',helper_exit_code=0,all_helpers_absent=True,tracked_existing_outputs_unchanged=True,bytecode_absent=True,visual_review='VISUAL_QA.json'))
r=read(R/'REPLAY_RESULT.json');dump('EXECUTION_RESULT.json',dict(status='COMPLETE',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),baseline=head,conditions=14,replay_trajectories=r['trajectories'],T1_est_D=r['T1_est_D'],T4='NOT_RUN_R_IDENTICAL',report='RESULTS_KO.md',retraining=False,commit_push='NOT_PERFORMED'))
dump('POSTPROCESS_PROVENANCE.json',dict(commands=['python -B -X utf8 diagnostics.py','managed replay.py','python -B -X utf8 verify_analyze.py','python -B -X utf8 render_report.py','python -B -X utf8 finalize.py'],sources=[dict(path=p.name,sha256=sha(p)) for p in [R/'diagnostics.py',R/'replay.py',R/'verify_analyze.py',R/'render_report.py',Path(__file__)]],W4_definition_clarification='DECISION_CLARIFICATION.md'))
files=[p for p in sorted(R.rglob('*')) if p.is_file() and p.name!='OUTPUT_SHA256.json'];dump('OUTPUT_SHA256.json',dict(algorithm='sha256',excludes=['OUTPUT_SHA256.json'],files=[dict(path=p.relative_to(R).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in files]))
print(json.dumps(dict(status='COMPLETE',files=len(files),bytes=sum(p.stat().st_size for p in files),checks=len(read(R/'VERIFY_CHECKS.json')['checks']))))
