# R2 진행 상태 — R2-0 → R2-1 → R2-4 완료, R2-5 검토

경계 유지: `scientific_PASS=false`, `stage_B_allowed=false`. R1 파일은 수정하지 않았다. 새 산출물은 `out_R2/`와 이 디렉터리의 새 스크립트/문서.

## R2-0 정정: `ERRATA_R2_KO.md` (E1~E13)
## R2-1 P5 감사: `P5_AUDIT_R2_1_KO.md`
- seed가 바꾸는 것은 센서 스트림과 초기 pose뿐. RF 관측은 케이스당 noise-free 시리즈 1개 고정(독립 RF 12개, range 측정 잡음 0).
- 유효 run 수 ≈ 90~190 (명목 4,608/arm). 방향 일관성은 36 셀 중 E_COND 36/36, IAT 35/36. "B_OLD가 RF 없음보다 나쁨"은 23/36 셀.

## R2-4 통계·구현
| 항목 | 결과 |
|---|---|
| 4a P3 전역 site 균등 가중 재계산 | fold별 RMSE는 R1과 1e-16 일치(재현 확인). B 0.1496 vs E1 0.1243 m → 상대 **0.8308** (R1 0.8374). 선택 규칙 재적용 시 **E1_on_B 유지**, 다른 후보 통과 없음 (D1 0.965, D2 0.964, D1+E1은 개별 통과 조건 불충족) |
| 4b leakage v2 | 3 fold 모두: 학습/평가 행 분리, 기록된 fold 계수와 재적합 일치, 평가 route 라벨 섞기에 계수 비트 동일, 음성 대조(학습 라벨 섞기)는 계수가 변함 → **all_pass**. 한계: 학습 route와 평가 route가 공유하는 XY 1곳은 학습에 포함됨(평가 점수에서만 제외) |
| 4c P4 LoS에서 E1 채점 | LoS-only에서 E1은 B 대비 RMSE **+36~42 %** 악화 (과보정, 평균 −0.044 m). Full-RF에서만 −17 % → E1은 "LoS detector 보정"이 아니라 "다중경로 조건부 편향 보정" |
| 4d P5 fold 계수 vs P4 전체 계수 (blind 960 pose) | Full-RF 상대변화 −16.2~−17.2 % (CI는 모두 0 미만), 전체 계수 −17.2 %와 동등 수준 → E6(계수 집합 불일치)는 실질 영향 작음. noisy(snr30/10)에서도 −16.2~−16.9 % |

## R2-5 새 scene 검토 (질문: 복도 중앙 앵커 포함 기존 데이터가 적용 가능한가)
검토 대상: `results/CORRIDOR_SETUP/SWEEP/SCAN/SCAN2` (44개 로봇 위치 × yaw 19개 × 257 bin, anchor x=4 y=0 z=2.65).

**결론: P4(c) "다른 scene" 용으로는 적용 불가. 보조 within-scene 시험으로는 사용 가능.**
- 같은 scene이다: `CorridorSetup` 기본값(20×2.4×2.7 m), 같은 재질(concrete/plasterboard), 같은 FFD bank SHA, 같은 solver 설정(max_depth 3, seed 20260924). 앵커 (4,0)은 P3/P4의 aA와 동일하다. 즉 scene·재질·앵커 기하 중 어느 것도 바뀌지 않았다.
- 새 정보는 (i) yaw 0~180° 전체(주행 데이터는 route 진행 방향 위주), (ii) |y|=0.7 m(주행 데이터 |y|≤0.52)이다. 위치는 학습 XY와 겹치지 않고(최근접 중앙값 0.18 m), P4 사이트와도 겹치지 않는다.
- 한계: 44개 위치 중 37개가 앵커에서 5 m 이내(근거리 편중), 먼 거리 대표성 낮음. 데이터가 P3/P4 동결 이후에 선택된 것이 아니라 사후 선택이므로 gate가 아닌 기술(descriptive) 결과다.
- 실행 결과(`out_R2/R25A_CORRIDOR_SCAN_APPLICABILITY.json`, 노이즈 없음): 44 위치 × 19 yaw = 836 채널, 위치 클러스터 부트스트랩으로 E1 vs B RMSE **−34.3 % [−49.2, −22.7]**. yaw 구간별 −25~−44 %, |y|>0.52에서 −36.8 %. 동일 scene 안에서 yaw·측면 외삽에도 방향이 유지됨 → `GENERALIZATION_NOT_VERIFIED`는 그대로이고, "yaw/측면 within-scene 확인"으로만 기록.

**진짜 새 scene을 만들려면 새 시뮬레이션이 필요하다.** 좋은 점: `LegacyMethodBAtPose`는 `CorridorSetup`을 인자로 받는 구조라 폭·높이·길이·앵커 y를 바꿔 같은 파이프라인으로 생성할 수 있다(P4 blind는 240 pose ≈ 10분/프로세스, 4 병렬이면 960 pose ≈ 40분). 후보(권장 순):
1. **기하 변경 복도**: 폭 2.4→3.6 m, 높이 2.7→3.2 m, 앵커 y=+0.6(오프센터). 재질 동일 → 기하 효과만 분리.
2. **재질 변경**: 벽 plasterboard→concrete/brick(반사 강화). 기하 동일 → 재질 효과만 분리.
3. 위 둘의 조합(최종 일반화 시험).
각 scene에서 사전 동결 판정(점추정 ≤ −10 %, CI 상한 < 0, 학습·fit 없이 동결 계수만 적용)을 그대로 적용한다. 재질 정의가 `build_scene`에 하드코딩되어 있는지(인자화 가능 여부)는 아직 확인하지 않았다 — 실행 전에 확인이 필요하다.

## 중단점
R2-0, R2-1, R2-4 완료. 다음은 R2-2(A_DR NEES 실패 분해). 새 scene 시뮬레이션(R2-5)은 위 후보 중 선택과 승인을 기다린다.

## 갱신 (2026-10-13): 오피스 scene 전이 시험 (R2-5b)
기존 `claude/office-e-layout`의 `full35_stride1`(오피스 10×12×2.7 m, 앵커 (5.0, 2.2), 35 위치 × yaw 19)이 **다른 scene**이며 동일 bank·solver로 생성되어 있어 새 시뮬레이션 없이 range 수준 P4(c)를 수행했다(사전등록 `R25B_OFFICE_PREREG_KO.md`, 코드 `r25b_office_p4c.py`, 결과 `out_R2/R25B_OFFICE_P4C.json`).
- 사전 동결 gate(LoS-clear 25 위치, noise-free, 점추정 ≤ −10 % & CI 상한 < 0): E1 vs B RMSE **−31.7 % [−44.7, −14.5]** → 통과. 잡음 CIR(snr30 −31.8 %, snr10 −29.5 %)에서도 유지.
- 판정어: **`ONE_NEW_SCENE_TRANSFER_PASS`** (일반화 확립 아님: scene 1개, 독립 클러스터 25개).
- 단서: ① 오피스 clear 위치의 절대 오차가 작아(B 0.049 → E1 0.033 m) 개선의 절대량은 1.5 cm; ② 25개 중 17개 위치만 개선, 최악 위치 상대변화 +419 %(B 오차가 매우 작은 위치) → 위치별 분포가 한쪽으로 치우치지 않았다고 말할 수 없음; ③ LoS-blocked 10 위치는 B 평균 오차 +0.37 m로 NLoS 편향이 지배하며 E1 개선은 −6 %뿐 — E1은 NLoS를 고치지 않는다; ④ B 오프셋(−0.5316 m)은 오피스에서도 평균 오차 +0.011 m로 이전된다.
- 코드 변경 공개: 사전등록 커밋 뒤 스크립트의 오피스 모듈 import 방식만 수정(`importlib` 직접 로드; dataclass용 `sys.modules` 등록). 결과가 나오기 전이었고 판정 기준·모델·데이터는 불변.
- EKF 수준 오피스 시험·독립 RF 실현·반사실 채널이 필요하면 `OFFICE_SIM_DATA_REQUEST_SPEC_KO.md`(새 시뮬레이션 사양서) 참조.
