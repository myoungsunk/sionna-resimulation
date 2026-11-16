# M6 최종 판정과 실패 위치

mount 0°, 앵커 B, B0, Full RF의 R2/R4/R5에서 계획 순서에 따라 특성화, 구현 검사, seed 10 grid와 대조, seed 11–14 LORO 반복, 최종 재집계를 완료했다. 주 구조 G1과 결합 G1+KI의 동결 채택 기준은 모두 미충족이다.

## 분기

K1′의 공통 감도 지수는 0.3288, 95% 구간은 [0.1041, 0.5813]이었다. 사전 등록한 조건에 따라 G1+KI를 추가했다. R4의 공통 기울기 기여는 약 1.09%이며 R4 자체의 기술적 기울기는 2.38이다.

K2는 공통 지원 셀이 0개인 NO_COMMON_SUPPORT다. 같은 식으로 계산한 LORO 규모 2.134°/2.022°/2.042°는 동결한 진단값으로 사용했다.

G1은 R4의 heading 과신을 회복했다. 전체 공통 grid는 NO_BAND이며 LORO pooled 통과는 0/5 seed다. R2의 XY 정확도 비용과 R5의 heading 포함률·정확도·거울해가 공통 통과를 막았다.

G1+KI는 R4 heading95를 모든 seed에서 100%로 회복했고 거울해는 모든 seed에서 0건이었다. pooled 통과는 3/5 seed다. 궤적별 정확도와 10초 하한이 실패한 조건을 아래에 기록했다. 동결한 NEES3 하한 1.5는 유지했다.

| seed | pooled 통과 | R2 궤적 기준 | R4 궤적 기준 | R5 궤적 기준 | 실패 항목 |
|---:|---|---|---|---|---|
| 10 | PASS | PASS | PASS | PASS | 없음 |
| 11 | FAIL | FAIL | PASS | FAIL | R2 Pose95의 10 s 하한·두 RMSE, R5 두 RMSE, pooled Pose95·하한·두 RMSE |
| 12 | PASS | FAIL | PASS | FAIL | R2 XY +28.3%, R5 XY +47.5% |
| 13 | FAIL | PASS | PASS | PASS | pooled 평균 NEES3 1.4487 |
| 14 | PASS | PASS | PASS | FAIL | R5 XY +33.3% |

## K4·K5와 국소 구간

seed 10 R5의 세 앵커 통과 ±10초에서 G0의 y RMSE는 2.73/2.82/2.03 cm, G1은 2.89/4.78/4.82 cm, G1+KI는 3.35/2.68/2.67 cm였다. 명목 H_y를 유지하는 조건에서도 실제 gain·교차 공분산과 순차 prior 변화로 y 정확도 비용이 남았다. 두 번째·세 번째 통과의 결합 arm 개선은 통과별 Kν·P와 함께 표에 기록했다.

R2 120–140초에서 seed 10 heading95는 G0 6.9%, G1 38.6%, G1+KI 100%였다. y RMSE는 6.08/5.89/7.44 cm였다. 이 구간의 무결성 회복과 정확도 비용을 함께 기록한다.

K5의 짧은 통과 창 bootstrap은 reference_only로 표시했다. K3 variogram은 고정 길이와 대조하는 후순위 기술 통계로 저장했으며 이번 구조·길이 선택을 바꾸지 않았다.

## 허용 주장과 실행 정정

이번 RF·복도·grid에서 G1 단독의 R4 개선과 결합 arm의 증분 효과를 확인했다. 5-seed 전체 기준의 공통 통과는 없었다. 다음 범위 변경 안건은 계획서의 y/−y 이중 가설과 고감도로 앵커를 두 번 이상 지나는 새 궤적이다.

처음 구현 검사 실행은 trace의 t·pose_id 메타데이터가 빠져 중단됐다. replay와 replay_failed_sources에 원본을 보존하고, 메타데이터를 추가한 attempt_02에서 구현·전체 재생·재집계를 다시 검증했다. 수식·문턱·입력 데이터는 동결 계약에 연결돼 있다.

근거는 attempt_02/results/SCORES.json, BAND.json, K4.json, R2_LOCAL.json 및 attempt_02/VERIFICATION.json이다. 전체 표는 attempt_02/results/REPORT_KO.md에 있다.
