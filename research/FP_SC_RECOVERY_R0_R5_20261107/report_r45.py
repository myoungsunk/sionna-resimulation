from pathlib import Path
import csv,json,hashlib,zipfile,math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'R45_RUN_001'
def read(n):return list(csv.DictReader((OUT/n).open(encoding='utf-8-sig')))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
check=json.loads((OUT/'CHECKS.json').read_text());assert check['status']=='PASS_IMPLEMENTER_CHECK'
hashes=json.loads((OUT/'ARTIFACT_HASHES.json').read_text());assert all(sha(OUT/n)==h for n,h in hashes.items())
rows=read('R5_ROWS.csv');metrics=read('R5_METRICS.csv');sens=read('R4_SENSITIVITY.csv')
ARMS=['B','DROP','K1_R','K2_R','K1_RS','K2_RS'];names={'B':'B 기준','DROP':'경보 제외','K1_R':'K1 거리만','K2_R':'K2 거리만','K1_RS':'K1 거리+S','K2_RS':'K2 거리+S'}
aggregate=[]
for arm in ARMS:
 q=[r for r in rows if r['arm']==arm];assert len(q)==3136
 aggregate.append(dict(arm=arm,n=len(q),heading_RMSE_deg=float(np.sqrt(np.mean([float(r['heading_error_deg'])**2 for r in q]))),XY_RMSE_m=float(np.sqrt(np.mean([float(r['XY_error_m'])**2 for r in q]))),NEES3_mean=float(np.mean([float(r['NEES3']) for r in q])),alarms=sum(r['alarm']=='True' for r in q),accepted=sum(r['accepted']=='True' for r in q),selected_normal_harm=sum(r['selected_normal_harm']=='True' for r in q)))
(OUT/'AGGREGATE.json').write_text(json.dumps(aggregate,indent=2),encoding='utf-8')
fig,axes=plt.subplots(3,2,figsize=(14,10),layout='constrained')
colors=['black','#0072b2','#e69f00','#009e73','#cc79a7','#d55e00']
for i,route in enumerate(['R2','R4','R5']):
 for arm,col in zip(ARMS,colors):
  q=sorted([r for r in rows if r['arm']==arm and r['case'].startswith(route+'_')],key=lambda r:int(r['k']))
  for j,colname in enumerate(['heading_error_deg','XY_error_m']):axes[i,j].plot([float(r['time_s']) for r in q],[abs(float(r[colname])) for r in q],label=arm,color=col,lw=.9)
 for j,unit in enumerate(['Heading absolute error (deg)','XY error (m)']):
  ax=axes[i,j];ax.set_title(route+' | '+unit);ax.set_xlabel('Time (s)');ax.grid(alpha=.2);ax.legend(fontsize=8,ncol=3)
fig.suptitle('Closed-loop EKF | fixed P radius 7.5 cm | own pre-update P each arm')
fig.savefig(OUT/'R5_ERRORS.png',dpi=160);fig.savefig(OUT/'R5_ERRORS.pdf');plt.close(fig)
fig,axes=plt.subplots(1,2,figsize=(12,4),layout='constrained')
agg4=[]
for pol in ['K1','K2']:
 for off in [-15,-7.5,-5,-2.5,0,2.5,5,7.5,15]:
  q=[r for r in sens if r['policy']==pol and float(r['offset_cm'])==off]
  agg4.append(dict(policy=pol,offset_cm=off,recovered=sum(int(r['exact_recovery']) for r in q),harmed=sum(int(r['normal_harm']) for r in q),alarms=sum(int(r['alarms']) for r in q)))
 q=[r for r in agg4 if r['policy']==pol]
 for j,k in enumerate(['recovered','harmed']):axes[j].plot([r['offset_cm'] for r in q],[r[k] for r in q],marker='o',label=pol)
for ax,title in zip(axes,['Exact recovery from 999 B errors','Damage among 2137 B-normal samples']):
 ax.set_title(title);ax.set_xlabel('P center offset (cm), radius fixed at 7.5 cm');ax.set_ylabel('Count');ax.grid(alpha=.2);ax.legend()
fig.savefig(OUT/'R4_SENSITIVITY.png',dpi=150);plt.close(fig)
(OUT/'R4_AGGREGATE.json').write_text(json.dumps(agg4,indent=2),encoding='utf-8')
lines=['# R4–R5: 고정 B + P 7.5 cm 재귀 EKF 비교','','## 실행 범위와 결론 해석','','원본 SourceFFD·운동모델·W0 재귀 EKF를 재사용했다. R4는 저장 P 중심의 편차 민감도, R5는 각 실행의 측정 전 상태·공분산으로 P를 다시 계산하는 폐루프 재생이다. 궤도/센서 입력은 동일하며 로봇을 실제로 운행하지 않았다.','', '6개 구성 모두 원래 초기 상태·공분산, odometry/gyro, Q, 기본 R, muMB/muBASE 및 SourceFFD 관측모델을 고정했다. 각 구성은 자체 shadow 게이트를 원래 W0 구조대로 유지하고 해당 구성의 관측으로 수용 여부를 계산한다. 경보 제외는 main과 shadow 모두 해당 시점의 거리/S 관측 갱신을 건너뛴다. 거리만 복구하면 S는 B tap 값, 동시 복구하면 두 RX의 선택된 공통 tap 값이다. 보정항 재학습이나 선택 정책 튜닝은 하지 않았다.','', 'P는 main 필터의 현재 측정 전 prior·공분산을 2σ 7점 SourceFFD stencil에 넣은 native range min/max의 중점이다. 최종 반경은 항상 0.075 m다. 이전 실험의 경보 689건은 R5에서 고정하지 않는다. 미래 프레임·true pose·참조 tap은 선택과 재귀 계산 입력이 아니며 평가에만 사용한다.','','## 궤도별 RMSE','','각 셀은 Heading RMSE (deg) / XY RMSE (cm). XY는 좌표별 평균이 아닌 2차원 위치오차 norm의 RMS다. Heading 오차는 ±π로 wrap했다. 초기 표본 포함 전체 R2 979행, R4 742행, R5 1,415행.','','|구성|R2|R4|R5|전체 3136행|','|---|---:|---:|---:|---:|']
for arm in ARMS:
 vals=[]
 for route in ['R2','R4','R5']:
  v=next(r for r in metrics if r['arm']==arm and r['case'].startswith(route+'_'));vals.append(f"{float(v['heading_RMSE_deg']):.3f} / {100*float(v['XY_RMSE_m']):.2f}")
 v=next(r for r in aggregate if r['arm']==arm);vals.append(f"{v['heading_RMSE_deg']:.3f} / {100*v['XY_RMSE_m']:.2f}")
 lines.append('|'+names[arm]+'|'+'|'.join(vals)+'|')
lines+=['','![궤도별 오차](R5_ERRORS.png)','','## 폐루프 관측 처리와 정상 훼손','','|궤도|구성|경보|수용 관측|선택 정확 복구|선택 정상 훼손|수용된 정상 훼손|','|---|---|---:|---:|---:|---:|---:|']
for r in metrics:lines.append('|'+ '|'.join([r['case'].split('_')[0],names[r['arm']],r['alarms'],r['accepted'],r['selected_exact_recovery'],r['selected_normal_harm'],r['accepted_normal_harm']])+'|')
lines+=['','정상 훼손은 각 궤도의 원래 B=참조인 표본이 잘못된 tap으로 바뀐 건수다. 폐루프의 정상 경보 집합은 고정 실험의 11건보다 커질 수 있다. 선택 복구 수와 실제 게이트를 통과해 필터에 들어간 수를 분리했다. 경보 제외의 복구 0건은 관측을 고치지 않고 뺀다는 정책 정의에 따른다.','','## 신뢰도','','truth 파일은 [x,y,yaw] 3열이므로 NEES는 3차원 pose marginal 공분산으로 계산했다. gyro bias 참값을 만들거나 4차원 NEES로 표기하지 않았다. 95% 영역은 χ² 임계값 pose 7.8147, XY 5.9915, Heading 3.8415다.','','|궤도|구성|평균 NEES3|Pose 95% 포함률|XY 95% 포함률|Heading 95% 포함률|','|---|---|---:|---:|---:|---:|']
for r in metrics:lines.append(f"|{r['case'].split('_')[0]}|{names[r['arm']]}|{float(r['NEES3_mean']):.2f}|{100*float(r['pose95_coverage']):.1f}%|{100*float(r['XY95_coverage']):.1f}%|{100*float(r['heading95_coverage']):.1f}%|")
lines+=['','포함률이 명목 95%와 다르면 RMSE 개선만으로 공분산 신뢰도까지 개선됐다고 주장할 수 없다. 현재 결과는 시간적으로 상관된 한 seed의 노출 데이터로, 독립 환경 반복이나 일반화 검증이 아니다.','','## R4: 예측 중심 편차 민감도','','아래 수치는 전체 999건의 기존 오류 중 정확 복구 / 기존 정상 2,137건 중 훼손. 중심 이동 후 경보를 다시 판정했으므로 복구 수가 기존 경보 TP 678을 넘을 수 있다. 이 스윕으로 운영 중심이나 반경을 재선정하지 않았다.','','|중심 편차(cm)|K1 복구 / 훼손|K2 복구 / 훼손|','|---:|---:|---:|']
for off in [-15,-7.5,-5,-2.5,0,2.5,5,7.5,15]:
 v=[next(r for r in agg4 if r['policy']==p and r['offset_cm']==off) for p in ['K1','K2']];lines.append(f"|{off:+g}|{v[0]['recovered']} / {v[0]['harmed']}|{v[1]['recovered']} / {v[1]['harmed']}|")
lines+=['','![R4 민감도](R4_SENSITIVITY.png)','','## 검증 및 재현','','- 실제 FFD bank 2개의 SHA256과 원본 SourceFFD/운동모델/W0 코드 해시 검사 통과. 원본 W0를 세 궤도 전부 재실행해 보관된 prior·Pprior·h·H·Reff·K·mask와 비교했다.','- 새 루프의 B 구성을 원래 W0 함수에 B 관측을 넣은 별도 계산과 비교해 x·P·prior·H·K 및 수용 mask 일치를 확인했다. 고정 P 중심도 전체 표본에서 재현했다. 허용오차는 정규화 1e-10, mask는 정확 일치.','- R4 중심 편차 0 결과는 R2의 네 정책 정확 복구·정상 훼손 수와 일치했다. 모든 trace는 유한하며 공분산 PSD 검사를 통과했다.','- 최초 R4_RUN_001은 과거 캐시 경로 탐색 누락으로 계산 전에 실패했다. 파일·SHA를 바꾸지 않고 기존 캐시를 읽도록 수정한 R4_RUN_002에서 완료했고 실패 기록을 보존했다.','- 구현자 자체 검증 완료이며 독립 감사, 실시간 하드웨어 검증, 최종 정책 채택은 아니다. R5에서 종료했다.','','[정밀 지표 CSV](R5_METRICS.csv) · [행별 오차·경보·수용 CSV](R5_ROWS.csv) · [R4 전체 표](R4_SENSITIVITY.csv) · [검사 결과](CHECKS.json) · [동결 계약](CONTRACT.json)','','전체 상태·공분산·prior·관측모델·관측·gain·shadow 상태는 R2_TRACE.npz, R4_TRACE.npz, R5_TRACE.npz에 보존했다. 소스 기준 커밋은 fca24720524068badeab79b78098a244cebc62b5이며 로컬 실험 스크립트는 별도 SHA로 식별한다. GitHub에 새 코드를 배포하지 않았다.']
lines[2:2]=['전체 3,136행에서는 B 기준이 Heading 1.557도 / XY 12.81 cm RMSE로 가장 좋았다. 경보 제외는 1.894도 / 13.85 cm, 네 복구 구성은 Heading 2.361~2.684도 / XY 21.32~30.06 cm였다. R2의 경보 제외는 XY를, R4의 K1 거리만 복구는 Heading을 개선했지만, 두 지표를 함께 개선한 구성은 없었다.','', 'R4에서는 ±2.5 cm의 중심 편차만으로 정상 훼손이 11건에서 196/341건으로 증가했다. R5에서도 네 복구 구성의 정상 tap 훼손이 736~1,100건으로 증가했다. 예측 중심의 변화와 오정정 증가가 함께 관찰됐으나 각 요인의 인과 기여를 분리해 입증한 것은 아니다. 고정 P의 복구 성능을 그대로 폐루프 성능으로 해석할 수 없으며 현재 결과는 복구 정책 채택을 지지하지 않는다.','']
(OUT/'REPORT_KO.md').write_text('\n'.join(lines),encoding='utf-8')
(OUT/'DELIVERY_HASHES.json').write_text(json.dumps({p.name:sha(p) for p in OUT.iterdir() if p.is_file() and p.name!='DELIVERY_HASHES.json'},indent=2),encoding='utf-8')
with zipfile.ZipFile(ROOT/'R4_R5_RESULTS.zip','w',zipfile.ZIP_DEFLATED) as z:
 for folder in [OUT,ROOT/'R4_RUN_002']:
  for p in folder.iterdir():
   if p.is_file():z.write(p,p.relative_to(ROOT))
 for n in ['r45.py','r4.py','r2.py','prepare_r45.py','report_r45.py']:z.write(ROOT/n,n)
 for p in (ROOT/'R45_sources').rglob('*.py'):z.write(p,p.relative_to(ROOT))
print(json.dumps({'aggregate':aggregate,'R4':agg4,'zip_bytes':(ROOT/'R4_R5_RESULTS.zip').stat().st_size},indent=2))
