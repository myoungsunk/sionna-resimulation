import json,hashlib,shutil
from pathlib import Path
B=Path(__file__).resolve().parent; O=B/'results_v2'
m=json.loads((B/'INPUT_MANIFEST.json').read_text())
for r in m['files']:
 p=B/'inputs'/r['path'].split('research/POL_HEADING_RESEARCH_20261107/',1)[1]
 assert hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256']
logs=B/'logs'; logs.mkdir(exist_ok=False)
for label,pid in [('fetch','888fba2c-a050-4a57-8e3f-5e4acaa15f7c'),('failed_v1','bfe7fe35-e2ee-49c7-92f1-9064bbe557c5'),('successful_v2','ab0e9da1-f86c-4bd8-b35c-f6ff80c295bb')]:
 for name in ['stdout.log','stderr.log']:
  shutil.copyfile(Path.home()/'.codex/managed-processes/runs'/pid/name,logs/f'{label}_{name}')
s=json.loads((O/'SUMMARY.json').read_text()); rows=s['metrics']
report=['# PALO-ORACLE-001 실행 결과','', '범위: 선택적 편파 사용의 가능성을 탐색하는 진단 대조. R2 / anchor B / seed0의 LoS·Full × B0·L0·L1·L2. 7정책, 총 56개 폐루프 궤적, 각 979시점 중 t>=40의 779시점 평가.', '', '동결 LUT를 각 정책 자신의 prior에서 재평가하고 선택한 상태와 공분산을 다음 시점으로 전달했다. 즉시 오차 감소를 참값으로 선택하는 greedy oracle이며 전체 궤적 최적해나 성능 상한이 아니다.', '', '## 검증','8조건 S4 사전 재현 PASS. 상태 최대차 6.18e-14, 공분산 5.37e-15, NIS 1.46e-13, 수용 mask 불일치 0. 모든 저장 상태·공분산 유한/양정치 검사 및 56정책 결정·상태/P 선택·RMSE 재집계 자체검사 PASS. 독립 감사는 미실행.', '', '## Full 결과','|수준|정책|Heading RMSE deg|XY RMSE m|Heading NEES|XY NEES|','|---|---|---:|---:|---:|---:|']
for r in rows:
 if r['channel']=='full':report.append(f"|{r['level']}|{r['policy']}|{r['heading_rmse_deg']:.6f}|{r['xy_rmse_m']:.6f}|{r['heading_nees']:.6f}|{r['xy_nees']:.6f}|")
report += ['', '## 해석 및 한계','Heading 선택 오라클의 큰 개선은 유용한 갱신을 선택할 가능성을 보여준다. 그러나 참값을 사용하며 온라인 판별 가능성·독립 환경 일반화는 입증하지 않았다. XY만 선택한 오라클은 Heading이 기존 S4보다 악화된다. Heading 오라클의 NEES는 1보다 매우 낮다. NEES 감소 자체를 공분산 보정/일관성 달성으로 해석하지 않는다. 시점들은 상관되어 있으며 통계적 보장 없음.', '', '## 수정·실행 기록','전달 실행기의 4상태 예측에 2x2 Q를 넘기는 결함으로 첫 실행 중단. 실패 로그와 계약은 results/ 및 logs/에 보존. v2는 동결 원본 r2_bias_replay.predict_one을 재사용하며 원본 입력 86개 SHA 재확인. numpy2.2.4/scipy1.15.2 동결 환경 사용. 시작 전 S4 8조건 모두 통과한 후 오라클 실행. RF 오염 oracle(다음 우선순위)은 미실행.', '', '실행: python run_exact.py → python check_results.py. run_exact.py는 출력 디렉터리 존재 시 거부하므로 재실행은 별도 사본/새 경로 필요. 입력 provenance는 INPUT_MANIFEST.json, 수학/실험 계약은 results_v2/CONTRACT.json. 종료코드 v1=1, v2=0. 모든 관리 helper 종료 확인.', '', '운영 코드·기존 연구 결과 변경 없음. 새 결과 GitHub push 및 독립 감사 미실행.']
(B/'REPORT_KO.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
files=[p for p in B.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='OUTPUT_SHA256.json']
(B/'OUTPUT_SHA256.json').write_text(json.dumps({str(p.relative_to(B)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},indent=2)+'\n')
print('INPUT_HASH_PASS',len(m['files']),'ARTIFACT_HASHES',len(files))
