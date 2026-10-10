from pathlib import Path
import json, subprocess, sys, hashlib
root=Path(__file__).resolve().parent
plugin=Path(r'C:\Users\Myoungsun Kim\.codex\plugins\cache\local-experiment-tools\codex-experiment-ledger\0.6.1+codex.20260626000000')
sys.path.insert(0,str(plugin))
from ledger_core.core import mcp_call_tool
turn='01a11947-3137-7e32-a32e-0f146e160fa1'
ctx=mcp_call_tool('get_turn_context',{'turn_id':turn})
ev=ctx.get('evidence',[])
valid=[x['evidence_id'] for x in ev if 'report_sha256' in x.get('excerpt','') and 'source_unchanged' in x.get('excerpt','')]
provenance=[x['evidence_id'] for x in ev if 'prereg_unchanged_from_original' in x.get('excerpt','')]
evidence=(valid[-2:]+provenance[-1:])
assert evidence
report=root/'INDEPENDENT_SCIENTIFIC_AUDIT_KO.md'
s=report.read_text(encoding='utf-8')
sections=[x for x in s.splitlines() if x.startswith('## ') and x[3:4].isdigit()]
assert len(sections)==11,sections
assert subprocess.check_output(['git','status','--porcelain'],cwd=root/'checkout',text=True)==''
count=None
for line in s.splitlines():
    if line.startswith('|'):
        current=line.count('|')-1
        assert count is None or current==count
        count=current
    else:count=None
check=json.loads((root/'AUDIT_COMPLETION_CHECK.json').read_text(encoding='utf-8'))
check.update(report_sections=len(sections),tables_valid=True,report_sha256=hashlib.sha256(report.read_bytes()).hexdigest())
(root/'AUDIT_COMPLETION_CHECK.json').write_text(json.dumps(check,ensure_ascii=False,indent=2),encoding='utf-8')
print('FINAL_REPORT_QA '+json.dumps(check,ensure_ascii=False))
semantic={'schema_version':3,'turn_kind':'analysis_note','relation':{'type':'new_group_related','target_group_id':None,'related_group_ids':['grp-1df3ba49c54d'],'confidence':.98,'reason':'기존 production 재현과 구분되는 독립 과학 감사이며 같은 DRIVE_SIM 결과를 대상으로 한다.'},'title':'DRIVE_SIM 독립 과학 감사와 제한된 claim 판정','theme':{'primary':'DRIVE_SIM 주행 시뮬레이션 재현','secondary':[],'confidence':.98,'reason':'동일 연구 결과의 독립 source·provenance·통계 감사'},'intent':{'objective':'고정 branch의 RF·관측·localization·사전등록·통계를 독립 검증하고 한국어 보고서를 보존한다.','hypotheses':['현재 결과가 single-anchor RF-derived heading 연구의 강한 타당성 주장을 뒷받침하는가'],'experiment_type':'read-only independent scientific audit','success_criteria':['고정 revision와 실행 provenance','전 중요 영역 검토 및 evidence boundary','독립 수치 계산과 additive 한국어 보고서']},'method':{'variables_changed':[],'controls':['HEAD155bf5a 고정','source와 원 결과 불변','production RF rerun 금지'],'assumptions':['고정 환경 simulation과 hardware/generalization 구분'],'environment':['Windows CPU deterministic tests','KMS read-only Snowball evidence']},'outcome':{'execution_status':'completed','hypothesis_outcome':'mixed','adoption_status':'deferred','execution_reason':'독립 감사, 원본 검사와 CPU 검증, 11-section 한국어 보고서 및 QA를 완료했다.','hypothesis_reason':'일부 tracking 정확도와 provenance는 확인했으나 LUT 실패·NEES 불일치·gate chronology 및 추가 검증 한계가 강한 scientific claim을 차단한다.','adoption_reason':'기존 수치는 diagnostic simulation으로 보존하고 강한 논문 claim은 bounded validation까지 보류한다.','one_line_result':'감사 완료: BOUNDED_CORRECTION_OR_VALIDATION_REQUIRED, scientific_PASS=false 유지.','observations':[{'text':'고정 HEAD155bf5a에서 원본 source·artifact 검사와 독립 계산 보고서를 생성하고 source 불변을 확인했다.','evidence_ids':evidence,'strength':'direct','confidence':.98},{'text':'Strict G3 FAIL와 relaxed delay eligibility PASS를 분리하고 covariance/LUT/GSF/coverage 한계를 보고했다.','evidence_ids':evidence,'strength':'direct','confidence':.95}],'interpretation':'현재 결과는 한정된 local-tracking simulation evidence이며 강한 물리·uncertainty·global observability·hardware claim은 미확립이다.','metrics':[]},'limitations':['Full RF regeneration 및 전체 paired A/B H 재계산 미실시','Hardware/generalization 미검증','작은 P0 replay 차이 원인 미확정'],'unresolved_questions':['GSF production component PSD','Anchor-B production 최악 pose parity','Held-out covariance/model consistency'],'next_steps':['자동 다음 단계 없음; 보고서 P0/P1/P2는 후속 승인 scope에서만 수행'],'group_update':{'mode':'merge','title':'DRIVE_SIM 독립 과학 감사','status':'active','current_conclusion':'감사 완료; 제한된 simulation 근거 보존, 강한 claim에는 보완 검증 필요.','unresolved_questions':['LUT·covariance·parity coverage의 후속 검증'],'next_steps':['사용자 요청 전 수정·rerun 없음']},'overall_confidence':.95}
(root/'ledger_semantic.json').write_text(json.dumps(semantic,ensure_ascii=False,indent=2),encoding='utf-8')
result=subprocess.run([sys.executable,'-X','utf8',str(plugin/'scripts/ledger.py'),'finalize','--turn',turn],input=json.dumps(semantic,ensure_ascii=False),text=True,capture_output=True,encoding='utf-8')
print(result.stdout)
print(result.stderr)
raise SystemExit(result.returncode)
