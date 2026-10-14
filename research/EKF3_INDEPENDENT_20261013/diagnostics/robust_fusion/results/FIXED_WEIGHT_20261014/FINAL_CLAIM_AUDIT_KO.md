# 독립 코드·실험 결과 최종 감사

VERDICT: ACCEPT

감사자: /root/ablation_audit. 요청한 동일 prior·재귀 Joint C 비교를 완료했으며 파라미터·gate·허용치와 과학적 주장 경계를 유지했다.

## 확인 결과

- 무편향 Full B_OLD에서 Cauchy는 고정 1/3보다 재귀 RMSE가 작으나 one-step 우위는 donor에 따라 달라진다. 순수 선택 효과로 단정하지 않은 결론이 타당하다.
- Gyro L1/L2에서는 세 RF 조합과 양 donor 모두 Cauchy의 허용 one-step 평균 Heading·위치 제곱오차가 고정 1/3보다 크다. 채택 보류를 뒷받침한다.
- 115 tests PASS. 756개 재귀·1,512개 one-step 집계 셀 검증.
- 기존 세 모델 567개 셀 parity 최대 차이 7.11e-15, 허용치 1e-8 유지.
- 분석 CSV 5개 해시 일치.
- 독립 NPZ 표본 32,232행 재검산: 오차·Gain 차이 0, Joseph 최대 6.94e-18, NEES 최대 1.46e-11. SPD와 Pose coverage 일치.
- SUMMARY의 pooled 지표·7case 방향·donor 의존성은 CSV와 일치한다. 세 전체 실행 종료 및 참조 해제 확인.

## 감사 중 명확화

경로별 방향 표에 '고정 1/3 대비'를 명시하고, 가중치·gate·공분산 표의 B_OLD 범위를 명시하도록 지적했다. 두 문구를 수정 후 재확인했다. 수치·파라미터·실행 코드 변경 및 실험 재실행은 없었다.

필수 수정 잔여 없음. 독립 RF 장면 확증과 GitHub 게시 증빙은 이 감사 범위 밖이다. scientific_PASS=false를 유지한다.
