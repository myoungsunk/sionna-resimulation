from pathlib import Path
import pandas as pd,json,hashlib,zipfile,numpy as np
ROOT=Path('/mnt/data/B_MCG_CASE_GALLERY_20261109')
cat=pd.read_csv(ROOT/'CASE_CATALOG.csv',encoding='utf-8-sig')
d=pd.read_csv(ROOT/'FULL_ENRICHED_6272.csv',encoding='utf-8-sig')
aud=json.loads((ROOT/'CASE_AUDIT.json').read_text())
pan=json.loads((ROOT/'PANEL_MANIFEST.json').read_text());pics={x['case_id']:x['file'] for x in pan['panels']}
catdesc={
'ACTIVE_ALL':'실제 가드 감쇠 전수','COMPATIBLE_HARM_HEADING':'COMPATIBLE·Heading 손해',
'COMPATIBLE_HARM_XY':'COMPATIBLE·XY 손해','COMPATIBLE_CORRUPTED_S':'COMPATIBLE·큰 Δs',
'UNKNOWN_HARM_HEADING':'UNKNOWN·Heading 손해','UNKNOWN_HARM_XY':'UNKNOWN·XY 손해',
'BENEFICIAL_FULL_HEADING':'B full·Heading 유익','BENEFICIAL_FULL_XY':'B full·XY 유익',
'CLEAN_TAP_S_DISTORTED':'같은 tap·s 왜곡','TAP_CHANGED_S_STABLE':'tap 변화·s 안정',
'LOW_NIS_HIGH_NEES':'작은 NIS·큰 NEES','GYRO_BIAS_EXTREME':'gyro bias 극값',
'HIGH_S_MP':'큰 s 왜곡','HIGH_R_MP':'큰 range 왜곡','RF_SMALL_AFTER_LARGE':'큰 왜곡→작은 왜곡',
'ROUTE_REFERENCE':'대표 주행시점'}
repo='https://github.com/myoungsunk/sionna-resimulation'
head=[
'# B-MCG v1 — 506개 사례 기반 궤적·필터·IMU·RF 비교 보고서',
'',
'**분석일:** 2026-11-09 | **검토 범위:** R2(979)·R4(742)·R5(1415), B0 Full seed10, 두 가지 보정 조건(B_FROZEN/B_BIAS_COV), OFF/ACTIVE_RS 실제 폐루프.',
'',
'**보기:** [인터랙티브 506개 사례 갤러리](../B_MCG_506_CASES_INTERACTIVE_20261109.html) · [전수 506개 색인](CASE_BY_CASE_506_KO.md) · [원본 6,272행 분석 CSV](FULL_ENRICHED_6272.csv) · [48개 대표 그림 목록](PANEL_MANIFEST.json)',
'',
'## 연구 질문과 결론',
'',
'**어떤 RF는 현재 운동 기준과 충돌하지만, 어떤 다중경로로 왜곡된 RF는 운동 기준과 모순되지 않는 이유는 무엇인가?**',
'',
'기존 운동 정합성 가드는 과거 RF로 정렬한 최근 운동 궤적의 *설명 가능성*을 검사합니다. 따라서 (a) 과거 정렬 자체가 RF 왜곡을 흡수했거나 (b) 유해 RF 갱신이 운동 경로의 상대 모양을 크게 바꾸지 않을 때, 관측 자체는 잘못돼 있어도 COMPATIBLE 또는 UNKNOWN으로 남을 수 있습니다. 반대로 (c) 갱신이 기존 절대 위치·헤딩 오차를 수정하는 경우에도 과거 정렬과 충돌할 수 있어 감쇠가 반드시 이득은 아닙니다.',
'',
'**본 보고서의 `COMPATIBLE_HARM_*`는 데이터로 확인된 “운동-호환성 판정 + 사후 유해 갱신”의 동시 발생을 의미합니다. RF 단독 인과원인이나 실제 NLoS 클래스의 정답 라벨을 뜻하지 않습니다.**',
'',
'## 증거의 양과 검증 결과',
'',
'- **전체 추적:** 동일 물리 측정 3,136시점 × 2가지 B 보정 조건 = 6,272개의 비교 행. 가드 OFF/ON 상태·공분산·range/s·CIR 요약과 참값을 같은 route/k/pose_id로 연결했습니다.',
'- **탐색 사례:** 506개 고유 `(route,stratum,k)`를 선정해 검색·분류·시간창 조절이 가능하도록 구성했습니다. 모든 3,136시점은 갤러리의 k 직접 조회로 접근할 수 있습니다.',
'- **실제 B-MCG 감쇠:** 총 23개 모델별 시점이며, 모두 range의 βr만 감소했습니다. s의 βs는 항상 1이었습니다.',
'- **같은 prior 가드 효과:** 23개 중 두 지표 동시 개선 2개, 두 지표 동시 악화 5개, heading/XY 손익 상충 16개였습니다. 이것은 단일 시점의 반사실 비교이며 모든 후속 상태의 손익과 다릅니다.',
'- **상태 판정:** 6,272행에서 `UNKNOWN` 5,163개(82.3%). 불개입을 정상·정확 판정으로 해석하지 않습니다.',
'- **운동 재구성:** 원본 `online.npz`의 gyro 배열을 직접 확보하지는 않았으나, pinned `core.transition()`의 예측식과 저장된 prior/posterior에서 gyro 증분·odom 거리증분을 역산했습니다. 동일 실제 입력을 공유하는 네 스트림 간 최대 차이는 gyro 1.33×10⁻¹⁵ rad, ds 3.33×10⁻¹⁵ m였습니다. 실제 참 yaw rate 대비 gyro rate RMS 차이는 route별 약 0.033 deg/s입니다.',
'- **절대 정렬 기준:** Gyro/odom DR 경로의 GT-anchored 선은 첫 시점 GT pose로 시각화한 사후 대조이며 추정기 사용 가능 GT를 뜻하지 않습니다. OFF-anchored 선은 구간 첫 OFF 추정 상태를 사용합니다.',
'',
'## 판정 기준 — 1회 갱신과 장기 오차를 구분',
'',
'1. **same-prior 가드 인과 대비:** ACTIVE_RS 본인 prior와 기존 shadow gate를 고정하고, 원래 `Rbase`의 unweighted B update vs `Reff`의 weighted update를 비교했습니다. `guard_harm_* > 0`이면 해당 지표에 대해 가드가 악화한 것입니다.',
'2. **same-prior B 관측의 유해성:** 동일 prior와 unweighted B update를 비교했습니다. `B_update_harm_* > 0`은 해당 시점 B 갱신이 추정오차를 키웠다는 뜻이지 RF 왜곡만의 원인이라는 뜻은 아닙니다.',
'3. **폐루프 결과:** OFF와 ON의 실제 x/P 시계열을 별도로 보였습니다. 과거 갱신이 달라 후속 prior가 다르므로 위 단일 시점 인과와 합쳐서는 안 됩니다.',
'4. **물리 RF 차이:** `e_s_mp=s_F−s_L`, `e_r_mp_m=(B_F−B_L)*STEP`은 동일 B 검출기를 Full/LoS에 적용한 evaluator-only 값입니다. 온라인 가드는 clean CIR/GT를 보지 못합니다.',
'',
'## 케이스 가족의 전체 분포',
'',
'| 범주 / 실제 판정 | 원본 B | 보정 B | 전체 모델별 행 |',
'|---|---:|---:|---:|'
]
mask=(d.monitor_state=='COMPATIBLE')&d.legacy_accepted&(d.e_s_mp.abs()>.03)
for label,cond in [
 ('감쇠 실제 발생',d.legacy_accepted&(d.beta_r<.999999)),
 ('운동 정합 판정 + s 왜곡 >0.03 + Heading 갱신 손해',mask&(d.B_update_harm_heading_deg2>0)),
 ('운동 정합 판정 + s 왜곡 >0.03 + XY 갱신 손해',mask&(d.B_update_harm_xy_cm2>0)),
 ('판단 불가 UNKNOWN',d.monitor_state=='UNKNOWN'),
 ('NIS<1인데 실제 NEES3>20, 기존 gate 수용',d.legacy_accepted&(d.nis_off<1)&(d.nees_off>20)),
]:
 n1=int((cond&(d.stratum=='B_FROZEN')).sum());n2=int((cond&(d.stratum=='B_BIAS_COV')).sum())
 head.append(f'| {label} | {n1:,} | {n2:,} | **{n1+n2:,}** |')
head += [
'',
'**주의:** 두 보정 조건은 같은 RF 시점을 공유하므로 열을 더한 모델별 행 수를 독립 RF 사건 수로 쓰지 않습니다. `COMPATIBLE` 자체는 필터가 정의한 정합성 판정이고, 오차·진실 상태와 동일한 단어가 아닙니다.',
'',
'## 눈여겨볼 상세 사례',
'',
'| 사건 | 현재 가드 판정 | 관측/상태 대조 | 사후 관찰 | 대표 그림 |',
'|---|---|---|---|---|'
]
stories=[
 ('R5','B_FROZEN',435,'같은 RF, B 원본: range 감쇠로 Heading·XY 양축 개선'),
 ('R5','B_BIAS_COV',435,'같은 RF, B 보정: heading만 개선되고 XY 악화'),
 ('R5','B_FROZEN',35,'초기 구간: range 감쇠로 Heading·XY 양축 개선'),
 ('R4','B_FROZEN',393,'경보는 올랐지만 양축 손해'),
 ('R4','B_FROZEN',492,'경보는 올랐지만 양축 손해, S 채널 왜곡도 존재'),
 ('R2','B_FROZEN',243,'heading 개선 ↔ XY 악화의 전형적 상충'),
 ('R5','B_BIAS_COV',33,'보정 B에서 range 감쇠 양축 손해'),
 ('R5','B_FROZEN',725,'작은 편파 왜곡에서도 가드 양축 손해'),
 ('R4','B_BIAS_COV',225,'COMPATIBLE지만 B full 갱신이 양축 악화'),
 ('R2','B_FROZEN',750,'NIS가 작고 NEES가 매우 큰 경우'),
 ('R2','B_FROZEN',523,'큰 편파 왜곡에서도 B full 갱신이 유익'),
 ('R5','B_BIAS_COV',979,'보정 B에서 여러 시점 연속 range 감쇠 / XY 손해')]
for route,st,k,title in stories:
    x=d[(d.route==route)&(d.stratum==st)&(d.k==k)];assert len(x)==1
    v=x.iloc[0];cid=f'{route}_{st}_k{k:04d}'; link=f'../B_MCG_506_CASES_INTERACTIVE_20261109.html#{route}|{st}|{k}'
    fig=f'[그림](panels/{cid}.png)' if cid in pics else f'[상세 열람]({link})'
    stat=f'βr={v.beta_r:.3f}, Δs={v.e_s_mp:+.3f}, IMU={np.degrees(v.gyro_increment_rad):+.3f}°/step'
    effects=f'가드: Heading {v.guard_harm_heading_deg2:+.4f} deg²; XY {v.guard_harm_xy_cm2:+.2f} cm² / B full 갱신: H {v.B_update_harm_heading_deg2:+.3f} deg²'
    head.append(f'| [{route}/{st}/k{k}]({link}) | `{v.monitor_state}` | {stat} | {title}. {effects} | {fig} |')
head += [
'',
'## 실제로 감쇠가 발생한 23개 모델별 케이스 — 빠짐없이',
'',
'아래 “가드 손익”은 같은 사전상태에서 무가중 B와 비교한 **Heading 제곱오차 / XY 제곱오차 차이**입니다. 음수는 가드 이득, 양수는 가드 손해입니다.',
'',
'| 경로 / 보정 / k / t(s) | GT heading° | 원본 gyro Δ° | βr, βs | Δs Full−LoS | 가드 손익(H deg² / XY cm²) | 해석 |',
'|---|---:|---:|---|---:|---|---|'
]
active=cat[cat.categories.str.contains('ACTIVE_ALL')].sort_values(['route','stratum','k'])
for _,v in active.iterrows():
    key=f'{v.route}|{v.stratum}|{int(v.k)}';link=f'../B_MCG_506_CASES_INTERACTIVE_20261109.html#{key}'
    h=v.guard_harm_heading_deg2;x=v.guard_harm_xy_cm2
    status='양축 이득' if h<0 and x<0 else '양축 손해' if h>0 and x>0 else '손익 상충'
    head.append(f'| [{v.route}/{v.stratum}/k{int(v.k)} ({v.t_s:.1f}s)]({link}) | {v.heading_true_deg:.1f} | {v.gyro_increment_deg:+.4f} | {v.r_beta:.3f}, {v.s_beta:.3f} | {v.e_s_mp:+.4f} | {h:+.5f} / {x:+.2f} | {status} |')
head += [
'',
'## 이 데이터가 확인한 것과 아직 확인하지 못한 것',
'',
'**확인:** 일부 RF는 운동 가드가 `CONFLICT_R`로 분류해 range 갱신을 줄였고 그 결과 양축 오차가 줄었습니다. 같은 RF라도 기존 평균·공분산 보정으로 prior가 달라지면 감쇠의 손익이 달라집니다. 실제 편파 왜곡이 존재하고 현재 갱신이 손해인데도 `COMPATIBLE`인 사례가 있습니다. 작은 main NIS와 큰 상태 NEES가 동시 발생합니다.',
'',
'**아직 확정 불가:** `COMPATIBLE` 사례의 큰 오차가 오직 한 개 CIR 경로 때문에 발생했는지, 각 사례가 새로운 환경에서도 재현되는지, 가드가 거절하지 않은 원인이 환경 편향인지 gyro bias 오추정인지 단일 프레임만으로 인과 확정할 수 없습니다. `UNKNOWN`은 판정 실패라기보다 정보 부족 상태로 설계돼 있으므로 이를 다른 오염 발생률과 혼동하지 않습니다.',
'',
'**SourceFFD 모델 정합 복귀 시험과 실제 B 주행을 구별:** 이전 반례 R4 k212는 주입한 model-ideal 현재 관측과 오염 history의 대조입니다. 이 케이스북의 R4 k212 행은 원래 B Full 관측에 대한 결과이므로 같은 물리 사건처럼 합쳐서는 안 됩니다.',
'',
'## 감사를 위한 원본 계보 및 한계',
'',
f'- 원본 CI: [GitHub Actions #42600632209]({repo}/actions/runs/42600632209).',
 f'- 게시된 원본 41개 파일: [RUN_42600632209]({repo}/tree/61ad3da300fdf5c235c60c7f23c04696c07b2e59/research/B_MCG_V1_20261109/RUN_42600632209).',
'- 원본 predictor: `core.transition()`은 `a=gyro_angle-b_g dt`, midpoint `ds*sinc(a/2)`를 사용합니다. 본 감사의 gyro/ds는 각 저장 필터의 previous posterior와 next prior에서 역계산했고 네 스트림 간 불일치를 검산했습니다. 원본 `online.npz`의 gy/ds 바이트를 이번 실행에서 직접 읽어 비교한 것은 아닙니다.',
'- 참값 및 CFR 기반 특징: 이전 Full/LoS 복소 CFR 전수 분석의 `PRIMARY_3136.csv`를 재사용했으며 입력 파일 SHA는 `CASE_AUDIT.json`에 기록했습니다.',
'- 그 경로·시드·환경은 학습·검토에 이미 노출됐습니다. 개별 case를 최종 독립 과학 검증으로 간주하지 않습니다.',
'- 그림의 초기 GT 정렬을 온라인 정답 접근으로 오해하지 않도록 별도 선으로 표시했습니다.',
'- 플롯의 `local_complex_distortion`은 두 RX 원본 복소 파형 자체가 아니라 FP 주변 특징입니다. 원본 전수 CIR의 복소 샘플을 새로 업로드하거나 재시뮬레이션하지 않았습니다.',
'- 506개는 데이터 기반 진단 사례 목록입니다. 정상/오염에 대한 통계적 표본추출이나 새 정책 채택 근거로 직접 사용할 수 없습니다.',
'',
'## 첨부 목록',
'',
'`analyze_cases.py` (상태/IMU 역산과 분류), `build_gallery.py` (인터랙티브 HTML), `export_panels.py` (정적 경로별 8축 그림), `make_reports.py` (이 문서), `CASE_CATALOG.csv`, `FULL_ENRICHED_6272.csv`, `CASE_AUDIT.json`, `panels/` 48개, `PANEL_MANIFEST.json`, `SHA256.json`.',
]
(ROOT/'CASEBOOK_REPORT_KO.md').write_text('\n'.join(head)+'\n',encoding='utf-8')

# Full 506 row static list with direct deep links.
rows=['# B-MCG — 506개 케이스 전수 색인','',
'이 문서는 506개 선택 사례를 모두 나열하며 각 행은 [동일 케이스 인터랙티브 시계열]로 연결됩니다. 실제 가드 개입뿐 아니라, 호환 판정/판단 불가와 오차, CIR 특징, IMU 증분을 함께 제공합니다.','',
'| 순번 | Route · 기준 · k · 시간 | 핵심 분류 | monitor 상태 | βr | Δs | GT yaw° | OFF→ON yaw error° | OFF→ON XY error cm | gyro Δ° | 사진 |',
'|---:|---|---|---|---:|---:|---:|---|---|---:|---|']
for i,(_,v) in enumerate(cat.iterrows(),1):
    cid=v.id;link=f'../B_MCG_506_CASES_INTERACTIVE_20261109.html#{v.route}|{v.stratum}|{int(v.k)}'
    pic=f'[PNG](panels/{cid}.png)' if cid in pics else '인터랙티브만'
    rows.append(f'| {i} | [{v.route} · {v.stratum} · k{int(v.k)} · {v.t_s:.1f}s]({link}) | {catdesc.get(v.primary_category,v.primary_category)} | {v.guard_status} | {v.r_beta:.3f} | {v.e_s_mp:+.3f} | {v.heading_true_deg:.1f} | {v.heading_error_OFF_deg:+.2f}→{v.heading_error_ON_deg:+.2f} | {v.xy_error_OFF_cm:.1f}→{v.xy_error_ON_cm:.1f} | {v.gyro_increment_deg:+.3f} | {pic} |')
(ROOT/'CASE_BY_CASE_506_KO.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')
print('REPORT',len(head),'lines','case book',len(rows),'lines', 'actual guard',len(active),'PNGs',len(pics))
