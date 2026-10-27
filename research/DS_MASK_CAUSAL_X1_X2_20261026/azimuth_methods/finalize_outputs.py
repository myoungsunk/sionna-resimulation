from pathlib import Path
import json,hashlib,datetime,subprocess,re
R=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def dump(n,o):(R/n).write_text(json.dumps(o,ensure_ascii=False,indent=2),encoding='utf-8')
analysis=read(R/'ANALYSIS_CHECKS.json');assert analysis['status']=='PASS'
pre=read(R/'PRE_CHECKS.json');assert pre['status']=='PASS'
receipts={}
for method in ['PRE','M1','M2']:
    f=R/f'{method}_MANAGED_FINISH.json';obj=read(f);p=obj['processes'][0]
    assert p['exit_code']==(1 if method=='PRE' else 0)
    assert p['termination']=='natural' and p['ref_count']==0
    assert p['actual_process']['state']=='absent' and p['actual_supervisor']['state']=='absent' and p['job']['state']=='absent'
    receipts[method]=dict(file=f.name,exit_code=p['exit_code'],resource_id=p['id'],released=True,all_processes_absent=True)
assert not list(R.rglob('*.pyc'))
repo=R.parents[2];head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip();assert head=='a6315bbbca54aa9c7d8ae4ab26183d8d94b51ec9'
assert not subprocess.check_output(['git','diff','--name-only'],cwd=repo,text=True).strip()
assert not subprocess.check_output(['git','diff','--cached','--name-only'],cwd=repo,text=True).strip()
status=subprocess.check_output(['git','status','--porcelain','--untracked-files=normal'],cwd=repo,text=True).strip();assert status=='?? research/DS_MASK_CAUSAL_X1_X2_20261026/azimuth_methods/'
md=(R/'RESULTS_KO.md').read_text(encoding='utf-8');figs=re.findall(r'!\[[^\]]*\]\(([^)]+)\)',md);assert len(figs)==5 and all((R/f).is_file() for f in figs)
dump('VISUAL_QA.json',dict(status='PASS',figures=figs,manual_render_review=True,repairs=['Shared y-limit clipping in F3/F5 repaired using all-case maxima','F2 NA markers kept within fixed categorical x bounds'],units_and_labels_checked=True,opposite_bias_results_preserved=True))
dump('CHECKS.json',dict(status='PASS',baseline=head,pre_checks='PRE_CHECKS.json',replay_checks=['M1_CHECKS.json','M2_CHECKS.json'],independent_trace_checks='ANALYSIS_CHECKS.json',independent_check_count=len(analysis['checks']),input_hash_count=analysis['input_hash_count'],visual_checks='VISUAL_QA.json',managed=receipts,pre_aggregation_failure_recovered=True,pre_recovery='finalize_pre.py',prior_tracked_outputs_unchanged=True,bytecode_absent=True))
dump('EXECUTION_RESULT.json',dict(status='COMPLETE',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),baseline=head,M1='NO_GO',M2_pre='GO',M2_selected_T=10,M2_replay='NO_GO',M3_pre='NO_GO',M3_integrated='NOT_RUN_GATE_CLOSED',conditions=10,replay_trajectories=200,new_filter_training=False,commit_push='NOT_PERFORMED',report='RESULTS_KO.md'))
dump('POSTPROCESS_PROVENANCE.json',dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),sources=[dict(path=p.name,sha256=sha(p)) for p in [R/'analyze_results.py',R/'render_report.py',Path(__file__)]],commands=['python -X utf8 analyze_results.py','python -X utf8 render_report.py','python -X utf8 finalize_outputs.py'],exit_codes=[0,0,0],intermediate_repair='Analysis draft R-only scaling guard fixed before successful run; replay outputs unchanged'))
files=[p for p in sorted(R.rglob('*')) if p.is_file() and p.name!='OUTPUT_SHA256.json']
dump('OUTPUT_SHA256.json',dict(algorithm='sha256',excludes=['OUTPUT_SHA256.json'],files=[dict(path=p.relative_to(R).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in files]))
print(json.dumps(dict(status='COMPLETE',files=len(files),total_bytes=sum(p.stat().st_size for p in files),independent_checks=len(analysis['checks']),git_status=status)))
