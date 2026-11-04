"""Limited report supplement to completed C1b numeric-prefix verification.
Read JSON evidence bundle on stdin. No observer, matrix, gate, scoring or policy
execution. Preserves the initial signed-zero assertion failure as evidence.
"""
import ast,csv,hashlib,json,math,re,sys
from pathlib import Path
ROOT=Path(r'D:/codex/MBVAR_PRR_001_20261103/research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/C1/C1B_001')
payload=json.load(sys.stdin);proof=payload['proof']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
js=lambda p:json.loads(p.read_bytes())
source=Path(payload['initial_verifier_source_path']).read_bytes().decode('utf8');sourcehash=hashlib.sha256(source.encode('utf8')).hexdigest()
assert sourcehash==proof['initial_verifier_source_sha256']=='928c147998a7932df316c57f5377b1a5c918aee871d1d57733b9b04c5184facc'
assert proof['initial_exit_code']==1 and proof['decision']=='PASS_NUMERIC_PREFIX_ONLY'
completed=re.findall(r'^C1B_REMAINING_INDEPENDENT_CELL (.+)$',proof['stdout_utf8_lf'],re.M)
expected_cells=[f'{r}_{b}_{s}' for r in ['R2','R4','R5'] for b in ['B0','L2'] for s in range(11,30)]
assert completed==proof['completed_cells']==expected_cells
failure=proof['stdout_utf8_lf'].split('AssertionError: ')[-1].strip()
failure=ast.literal_eval(failure)
assert failure[:4]==('report table','R2','B0','FF')
assert failure[4]=='|R2|B0|FF|0.062292024|0.933489046|+0.000000000|+0.000000000|-0.000000000|0/0|'
for name,h in proof['phase_artifact_and_report_sha256'].items():
    assert sha(ROOT/name)==h,name
go=js(ROOT/'GO_REMAINING.json');devaccept=ROOT/'audit/C1B_DEV_RESULT_AUDIT_RESULT.json'
assert sha(devaccept)==go['prerequisite_sha256']=='3ed290cde38e0da2a0766f6104aecfdde51ab858f3ccda03bd66aabb8ba886bd'
assert js(devaccept)['decision']=='ACCEPT'
assert go['authorized']==dict(stage='C1b_only',phase='remaining',routes=['R2','R4','R5'],biases=['B0','L2'],seeds=list(range(11,30)),output='REMAINING_001')
for n,h in go['bindings_sha256'].items():assert sha(ROOT/n)==h,n
allrows=[];artifactcounts={}
for phase in ['DEV_001','REMAINING_001']:
    out=ROOT/phase;index=js(out/'ARTIFACT_HASHES.json')
    assert {p.relative_to(out).as_posix() for p in out.rglob('*') if p.is_file()}==set(index)|{'ARTIFACT_HASHES.json'}
    for n,h in index.items():assert sha(out/n)==h,n
    artifactcounts[phase]=len(index)
    allrows.extend(js(out/'CELL_SUMMARY.json'))
    m=js(out/'MANIFEST.json')
    assert m['bindings_sha256']==go['bindings_sha256'] and m['new_MBVAR_baseline_replays']==m['new_training_runs']==m['new_RT_calls']==0
remaining_run=js(ROOT/'RUN_RESULT_REMAINING.json')
assert remaining_run['exit_code']==0 and remaining_run['status']=='NUMERICAL_PASS_PENDING_INDEPENDENT_RESULT_AUDIT'
expected={(r,b,s,a) for r in ['R2','R4','R5'] for b in ['B0','L2'] for s in range(10,30) for a in ['FF','LF','FL','LL']}
keys=[(r['route'],r['bias'],r['seed'],r['arm']) for r in allrows]
assert len(keys)==len(set(keys))==480 and set(keys)==expected
report=(ROOT/'RESULTS_KO.md').read_text(encoding='utf8')
reportrows=[line for line in report.splitlines() if line.startswith(('|R2|','|R4|','|R5|'))]
aggregate=list(csv.DictReader((ROOT/'AGGREGATE_SUMMARY.csv').open(newline='',encoding='utf8')))
assert len(reportrows)==len(aggregate)==24
def normalized_display(line):
    # Only signed textual zero is identified; other digits are preserved.
    return '|'.join('0.000000000' if field in ['-0.000000000','+0.000000000','0.000000000'] else field for field in line.split('|'))
assert normalized_display(failure[4])==normalized_display(reportrows[0])
fields=['mean_xy_m','mean_heading_deg','mean_delta_xy_vs_FF','mean_delta_heading_vs_FF','mean_delta_xy_vs_C1a','mean_delta_heading_vs_C1a']
flips=['newly_accepted_all','newly_rejected_all','newly_accepted_primary','newly_rejected_primary']
maximum_aggregate_difference=0.;i=0
for route in ['R2','R4','R5']:
 for bias in ['B0','L2']:
  for arm in ['FF','LF','FL','LL']:
    group=[r for r in allrows if (r['route'],r['bias'],r['arm'])==(route,bias,arm)]
    assert len(group)==20 and {r['seed'] for r in group}==set(range(10,30))
    assert len({r['n'] for r in group})==1
    values={k:math.fsum(r[k] for r in group)/20 for k in fields}
    values.update({k:sum(r[k] for r in group) for k in flips})
    row=aggregate[i]
    assert (row['route'],row['bias'],row['arm'],int(row['seeds']))==(route,bias,arm,20)
    for k in fields:
        delta=abs(float(row[k])-values[k]);maximum_aggregate_difference=max(maximum_aggregate_difference,delta)
        assert delta<=1e-12+1e-12*abs(values[k]),(route,bias,arm,k)
    for k in flips:assert int(row[k])==values[k]
    line=(f"|{route}|{bias}|{arm}|{values['mean_xy_m']:.9f}|{values['mean_heading_deg']:.9f}|"
      f"{values['mean_delta_xy_vs_FF']:+.9f}|{values['mean_delta_heading_vs_FF']:+.9f}|"
      f"{values['mean_delta_heading_vs_C1a']:+.9f}|{values['newly_accepted_all']}/{values['newly_rejected_all']}|")
    assert normalized_display(line)==normalized_display(reportrows[i]),(route,bias,arm)
    i+=1
for statement in ['RMSE·미래 오차 적분·재귀효과가 아니다','동일 RF와 반복 seed를 독립 사건으로 해석하지 않는다','공분산 교정·일관성 개선이라고 부르지 않는다','기존 NO-GO/HOLD는 유지한다','상세 계약·코드·실행 GO는 별도']:
    assert statement in report
dev=js(ROOT/'DEV_001/MANIFEST.json');remaining=js(ROOT/'REMAINING_001/MANIFEST.json')
assert (dev['completed_cells']+remaining['completed_cells'],dev['priors']+remaining['priors'],dev['posterior_rows']+remaining['posterior_rows'])==(120,125440,501760)
result=dict(schema='C1B_FULL_RESULT_AUDIT_V1',decision='ACCEPT',
 question_id='C1B-BASE-GATE-001',scope='All120 same-prior C1b results and report only',
 bindings_sha256=go['bindings_sha256'],remaining_go_sha256=sha(ROOT/'GO_REMAINING.json'),
 dev_acceptance_sha256=sha(devaccept),
 phase_artifact_and_report_sha256=proof['phase_artifact_and_report_sha256'],
 remaining_run_result_sha256=sha(ROOT/'RUN_RESULT_REMAINING.json'),
 remaining_execution_log_sha256=sha(ROOT/'EXECUTION_REMAINING.log'),
 counts=dict(cells=120,priors=125440,posterior_rows=501760,summary_rows=480,aggregate_rows=24,
 report_table_numeric_values=168,aggregate_numeric_values=264),
 remaining_independent_numeric_prefix=dict(cells=114,priors=119168,posterior_rows=476672,summary_rows=456,
 BASE_transition_edges=119168,BASE_update_edges=119168,source_observer_states=238336),
 independent_numeric_pass_condition='All individual comparisons in the executed prefix passed atol=1e-10 plus rtol=1e-10; covariance symmetry/PSD limits 1e-12*max(1,norm2). Exact peak differences were not emitted before the later display assertion, so none are invented.',
 accepted_DEV_cells_reused_without_reexecution=6,verified_phase_artifact_counts=artifactcounts,
 numerical_prefix_source_sha256=sourcehash,
 initial_verifier_exit_code=1,
 initial_failure='Report exact-string comparison of -0.000000000 against +0.000000000, after all114 numerical cells passed',
 limited_supplement='Only signed zero presentation normalized; all other printed digits, aggregate numbers and counts verified; scientific tolerances/data/code unchanged',
 max_aggregate_difference_from_verified_cell_summaries=maximum_aggregate_difference,
 report_source_sha256=sha(ROOT/'report.py'),report_source_executions=0,
 production_conditional_calls=0,production_score_calls=0,production_legacy_loader_calls=0,
 initial_prefix_observer_initializations=1,supplement_observer_initializations=0,
 scientific_conditions_reexecuted_for_supplement=0,seed10_reruns=0,
 new_policy_runs=0,new_MBVAR_baseline_replays=0,new_RT_calls=0,
 auditor_files_modified=0,children=0,C2_GO=False,
 claim_boundary='Published-RF conditional current-packet BASE gate effects only. No recursive hybrid policy, independent-event sample count, covariance calibration improvement, generalization or adoption. Existing NO-GO/HOLD preserved.',
 required_corrections=[])
print('C1B_RESULT_AUDIT_RESULT '+json.dumps(result,ensure_ascii=False,allow_nan=False))
