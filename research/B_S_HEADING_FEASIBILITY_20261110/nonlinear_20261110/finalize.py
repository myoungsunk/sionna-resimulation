from runtime import *
import csv,platform,datetime
rows=list(csv.DictReader((ROOT/'COMPARISON.csv').open(encoding='utf-8-sig')))
allrows=[r for r in rows if r['route']=='ALL'];checks=json.loads((ROOT/'CHECKS.json').read_text())
lines=['# B 비선형 S–Heading 범위 가능성 검토','',
'결론: 현재 폭에서는 선형과 비선형 판정이 동일하고 해로운 S 검출은 0/1,390이다. 폭 10%에서는 유익한 S 31건 추가 보호·해로운 S 7건 추가 검출이 있지만, 유익한 S 524건을 함께 배제한다. 비선형화 자체가 현재 교차 규칙의 구분 한계를 해결하지 않았다.','',
'실제 SourceFFD의 복소 패턴 보간·스펙트럼·CIR 검출을 다시 평가했다. 단순 Jacobian 역산을 비선형 결과로 부르지 않았다. B OFF prior와 위치·평균 보정·분산은 동일하게 고정했다. 새 가드와 재귀 EKF는 실행하지 않았다.','',
'## 같은 표본 비교','',
'전체 3,136행을 계산하고, 기존 게이트가 수용한 3,125행에서 갱신 손익을 평가했다. 제외된 11행은 P 정상 오경보 11건과 다른 집합이다. 정상은 같은 B tap에서 Full–LoS S 차이 ≤0.03인 1,743행이다. 해로운 S는 동일 prior의 range+S 갱신이 range-only보다 Heading 제곱오차를 키운 1,390행, 유익한 S는 반대인 1,735행이다.','',
'|허용폭|모델|RF 정상 보호|유익한 S 보호|해로운 S 검출|선형과 다른 판정|','|---|---|---:|---:|---:|---:|']
for r in allrows:
 rate=lambda a,b:f'{int(r[a])}/{int(r[b])} ({100*int(r[a])/int(r[b]):.2f}%)'
 lines.append(f"|{r['policy']}|{r['method']}|{rate('normal_protected','normal_total')}|{rate('helpful_protected','helpful_total')}|{rate('harmful_detected','harmful_total')}|{r['changed_vs_linear']}|")
lines+=['','## 범위 정의와 해석 한계','',
'G = [ψprior − 1.96√Pψψ, ψprior + 1.96√Pψψ]. 이는 과거 RF 영향을 받은 EKF 운동 prior이며 독립 gyro-only 절대 Heading 범위가 아니다. 현재 데이터만으로 95% 실제 포함률을 보증하지 않는다.','',
'S 지지 집합 = {ψ: |hS(xprior,yprior,ψ) − (SB−μS)| ≤ wS}. wS = 1.96√Rss에 표의 배율을 적용했다. 실제 비선형 함수가 만드는 여러 구간을 하나로 합치지 않고 G와 교차하는지 검사했다. 정답은 이후 손익/정상 라벨에만 사용했다.','',
'위치 고정 선형 결과와 위치 고정 비선형 결과의 대조다. 이전 위치 불확실성 포함 표와 직접 섞으면 안 된다. 위치·Heading 결합 비선형 허용집합은 이번 범위 밖이다.','',
'129개 Heading 격자와 실제 함수 근 찾기/국소 최소화, 판정 민감 행의 513개 격자를 사용했다. 이는 연속 함수의 전역 완전탐색 증명이 아니다. 폭 0은 수치 민감도 끝점이며, 잔차 1e-9 이하 근을 수치적 0으로 처리했다. 대표 원주 그림의 구간 끝점 해상도는 0.25°다.','',
'세 그림은 이전 실패가 논의된 시점의 OFF prior이다. 과거 ACTIVE의 prior·손익 수치를 이 그림에 대입하지 않는다.','',
'## 검증','',json.dumps(checks,ensure_ascii=False,indent=2),'',
'입력 SHA, 모델 h/H 전수 일치, 시간/행 연결, 이전 위치 고정 선형 집계 재현을 확인했다. 자기검사이며 독립 감사가 아니다. 새 환경의 검출 성능·재귀 RMSE 개선·정책 채택은 주장하지 않는다.','',
'![전수 비교](COMPARISON.png)','','![실제 비선형 범위](NONLINEAR_RANGES.png)']
(ROOT/'REPORT_KO.md').write_text('\n'.join(lines),encoding='utf-8')
files=[q for q in ROOT.rglob('*') if q.is_file() and '__pycache__' not in str(q) and q.name!='PROVENANCE.json']
inputs=[ROOT.parent/(r+s) for r in ['R2','R4','R5'] for s in ['.zip','_B0_Full_10__online.npz','_B0_Full_10__evaluator.npz']]+[ROOT.parent/'s_width_sweep_rows.csv',ROOT.parent/'s_width_sweep_summary.csv']
gov=pathlib.Path('C:/Users/Myoungsun Kim/.codex/research-governance')
def sha(q):
 with q.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
receipt=dict(question='Q-NONLINEAR-S-GYRO-20261110',timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),source_commit='e3ddc9fa4371d899a08a2a873d2ee5cf32074a01',python=platform.python_version(),numpy=np.__version__,managed_run='bd10ab78-1b50-47a5-844a-8e551e55fd2a',role='IMPLEMENTER_SELF_CHECK',inputs={str(q):sha(q) for q in inputs},files={str(q.relative_to(ROOT)):sha(q) for q in files},governance={str(q):sha(q) for q in [gov/'COMMON_CONTRACT.md',gov/'ROLE_IMPLEMENTER.md']},adoption=False,new_guard=False,new_recursive_run=False)
(ROOT/'PROVENANCE.json').write_text(json.dumps(receipt,indent=2))
print('FINALIZED',len(files),flush=True)
