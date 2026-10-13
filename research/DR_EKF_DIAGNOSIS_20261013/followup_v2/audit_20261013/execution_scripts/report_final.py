from pathlib import Path
import json,hashlib,re
root=Path(__file__).parent;out=root/'audit_evidence/remote_f1d6d9fc';old=root/'audit_evidence/remote_03e06b55'
def read(p):return json.loads(p.read_text())
v1=read(out/'V1_FINAL_RECONCILIATION.json');checks=read(out/'PROVENANCE_CHECKS.json')
tree={l.split('\t')[1]:l.split()[2] for l in (out/'git_tree.txt').read_text().splitlines()}
code=[]
for c in checks:
 if c['kind']!='inputs' or c['path'] not in tree:continue
 p=root/c['path'];q=out/c['path'].removeprefix('research/DR_EKF_DIAGNOSIS_20261013/')
 if q.exists():p=q
 b=p.read_bytes();oid=hashlib.sha1(f'blob {len(b)}'.encode()+b'\0'+b).hexdigest()
 code.append(dict(path=c['path'],matches_current_commit=oid==tree[c['path']]))
assert all(c['matches_current_commit'] for c in code)
pf_unchanged=(out/'out/D5_PF_VALIDATION.json').read_bytes()==(old/'out/D5_PF_VALIDATION.json').read_bytes()
assert pf_unchanged
log=(out/'out/logs/D6_EVALUATE_s8100-8399.log').read_text()
assert all(f'{k} {v["status"]} -' in log for k,v in v1['criteria'].items())
assert json.loads(log.split('verdict ',1)[1])==v1['verdict']
pflog=(out/'out/logs/D6_RUN_PF_A2_3_s8100-8399.log').read_text()
matches=re.findall(r'PF_A2_3\s+(R[245]_d[012]) ANEES\s+(\S+) late\s+(\S+) cov (\S+) head (\S+) condXY (\S+)',pflog)
assert len(matches)==9 and 'computed/verified arms' in pflog
cells={r['cell']:r for r in v1['arms']['PF_A2_3']['cells']}
for cell,*values in matches:
 for value,key,digits in zip(values,['anees','anees_late25','coverage95','mean_nees_heading','mean_nees_cond_xy'],[2,2,3,2,2]):
  assert value==f'{cells[cell][key]:.{digits}f}',(cell,key)
evidence=dict(remote_source_blob_checks=code,pf_json_unchanged=pf_unchanged,d6_verdict_log_matches=True,d6_pf_log_9_cells_match=True,pf_validation_log_truncated=True)
(out/'FINAL_SUPPLEMENTAL_CHECKS.json').write_text(json.dumps(evidence,indent=2))
lines=['# D6 최종 업로드 감사 — f1d6d9fc','',
'감사 결론: **'+v1['status']+'**. 공식 D6 과학적 판정은 **UNRESOLVED**이며 사전등록 규칙과 일치한다.','',
'## 검증 범위','',
'- 원격 커밋: f1d6d9fc984feb2c9a3b5fba36ca9aaa31fbe933; claude/pensive-johnson-kxx6t6.',
'- 캐시 63/63, 300 seed(8100–8399), 원본 총 5,492,985,426 bytes. 전체 원본 SHA256·크기를 재검증.',
'- 기존 61개는 매니페스트가 동일하고 이전 전 시점 공분산/NEES 내용 감사 결과를 재사용. 새 PF R5_d1/R5_d2는 Git blob ID, SHA256, shape, seed, 유한성, 전 시점 pose 공분산 대칭·양정정부호, pose/heading/conditional XY NEES 및 heading sigma 검증 통과.',
'- V1: 63셀 요약 및 모든 arm 집계, C1–C7/S1 수치와 판정, 최종 verdict, CSV 63행을 읽기 전용 재계산. 상대·절대 허용오차 1e-8. 불일치 '+str(len(v1['value_differences'])+len(v1['csv_differences']))+'건.',
'- D6와 PF 매니페스트 입력·출력 '+str(len(checks))+'개 해시 모두 일치. 기록된 연구 입력 파일을 현재 원격 Git blob과도 대조. 동결 spec은 사전등록 커밋과 일치.',
'- D6 판정 로그의 모든 상태/최종 verdict와 PF 완료 로그 9셀의 표시 수치를 대조하여 일치 확인.',
'- 실행 환경 Python 3.10에서 재계산; 원 실행의 Python 3.13/NumPy 2.5.3 환경과 동일한 환경 복제는 아니다. 수치 대조로 결과 재현성을 확인.',
'','## 사전등록 판정','','| 기준 | 결과 |','|---|---|']
for k,v in v1['criteria'].items():lines.append(f'| {k} | {v["status"]} |')
lines+=['','- C3: R2_d2 heading NEES 1.5327379606 > 1.5. 두 대상 셀 모두 심한 과신은 관찰되지만 사전등록된 복합 조건은 실패한다.',
'- C4: PF ANEES R2_d2=5.7801975209, R5_d2=4.3490242341 > 3.6. EKF보다 개선되었다는 사실과 일관성 충족은 구분한다.',
'- S1: PF strict gate 4/9. 실패 셀 R2_d0, R2_d2, R5_d0, R5_d1, R5_d2. 보조 기준은 원인 판정에 합치지 않는다.',
'- C3/C4가 원인 판정 핵심 기준이므로 UNRESOLVED 유지. 임계값 완화, CAUSE_CONFIRMED 승격, PF를 확정적 해결책으로 채택할 근거 없음.',
'','## 남는 증거 제한','',
'- D5 PF V1–V4 결과 JSON은 이전 감사 때와 동일하며 매니페스트 해시도 일치한다. 기존 V2 감사의 입자 수/재표집/게이트 한계가 그대로 남는다.',
'- D5_PF_VALIDATION_V2-V4.log는 여전히 coverage_un에서 잘려 있다. README의 완료 표기만으로 완결 로그 또는 원격 exit 0을 확인할 수 없다. 결과 JSON 무결성 검증과 구분한다.',
'- D6 매니페스트 research_dir_dirty=true. 기록된 입력 해시는 모두 일치하지만 실행 당시 저장소 전체가 깨끗했다고 주장하지 않는다. 실행 매니페스트는 각 NPZ를 입력으로 열거하지 않으므로 현재 캐시 매니페스트·전체 재계산으로 결과와의 대응을 확인했다.',
'','## 보존 및 후속 경계','',
'- D6 생성기/실험 재실행, 원본 결과 수정, 원격 업로드 없음. 감사 프로세스에서 캐시 읽기 경로만 새 스냅샷으로 지정. 기존 61개 로컬 캐시는 읽기 전용 재사용 링크.',
'- V3/V4 이전 개발 pilot와 코드 감사는 별도 증거이며 이번 D6 판정을 대체하지 않는다. V5 후보 선정·사전등록·신규 확증은 실행하지 않았다.',
'- 기계 판독 증거: V0_FINAL_CACHE_AUDIT.json, V1_FINAL_RECONCILIATION.json, PROVENANCE_CHECKS.json, FINAL_SUPPLEMENTAL_CHECKS.json.']
(out/'FINAL_AUDIT_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(v1['status'],'provenance checks',len(checks),'source checks',len(code))
