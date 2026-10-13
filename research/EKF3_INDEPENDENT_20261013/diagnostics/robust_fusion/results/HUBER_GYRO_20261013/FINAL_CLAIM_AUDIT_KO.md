# 최종 독립 결과·주장 감사

판정: ACCEPT. 감사자: ablation_audit; read-only.

- 실행 범위·수치·결론이 증빙과 일치한다. 낮은 Bias의 Full RF 정확도 이득은 탐색적 결과로 제한했고 Level1/2의 Joint 악화를 명시했다.
- Level2 세 조합 모두7/7조건에서 Heading/위치 RMSE가 악화됐고 Pose95%포함률0%가 확인됐다. 수치적 정상 종료를 성능 PASS로 해석하지 않는다.
- Gyro-only의 백색잡음 비활성화, seed 부호, E1·단일 scene 한계 및 scientific_PASS=false를 유지한다.
- 테스트54 PASS; NOISE/L0/L1/L2 각각504셀, exit0, parity PASS; NOISE 양모델 기존재현 차이0.
- 분석2016셀, 1,785,888행; 최대 지표차이7.28e-12, Pose NEES 차이7.64e-11. 주요표·조건별횟수·p95·거부율이 ANALYSIS CSV와 일치한다.
- 실행 소스 SHA208건과 분석 출력 SHA5건 일치. 관리 프로세스9개 모두 exit0, 소유참조0, 실제프로세스/감독프로세스/job 부재를 확인했다.

필수 수정: 없음.

감사 시점의 한계: GitHub 게시 완료 증빙은 아직 없으며 실험 완료와 게시 완료를 구분한다. 게시 여부는 이후 원격 commit 확인으로 별도 검증한다. 감사자는 전체 실험을 별도 재실행하지 않았다.
