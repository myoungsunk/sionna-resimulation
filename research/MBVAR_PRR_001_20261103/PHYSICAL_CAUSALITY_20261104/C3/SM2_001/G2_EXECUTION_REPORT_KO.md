# C3 G2 canary 실행 결과 — 독립 DATA 감사 제출

R4_168 고정 좌표에서 0°, 180°, +35.7°, −35.7° 네 yaw를 완료했다. 본 PathSolver 호출 1,028회와 사전 고정한 반복 QA 12회이며, 4×257=1,028개 bin 원본을 저장했다. 이는 실행 및 자체 수치 검사 통과이며 독립 DATA 감사는 별도이다.

|yaw deg|bins|raw rays|semantic groups|F64 closure rel L2|direct 최대 bin 상대오차|repeat exact|
|---:|---:|---:|---:|---:|---:|---|
|0.0|257|16080|63|3.194e-16|8.086e-07|True|
|180.0|257|16080|63|3.546e-16|1.164e-06|True|
|35.7|257|16080|63|2.661e-16|7.877e-07|True|
|-35.7|257|16080|63|2.780e-16|1.031e-06|True|

실행 코드/GO 게시 기준: `907af979a8827772a60e9835b2bc8b39c325c924`. 상세 joint/각 RX 검산, delay, legacy/F64 분리, 반복 raw 및 해시는 각 조건 QA/MANIFEST/ARTIFACT_HASHES와 전체 INDEX에 있다.

첫 CANARY_001 시도는 native frequency 자료형 읽기 오류로 실제 PathSolver 호출 0회에서 중단했다. 실패 증거와 이전 GO를 보존하고, 독립 수정 재감사와 새 GO를 받아 CANARY_002를 실행했다. 테스트003의 import명 충돌도 실패 로그를 보존했으며 수정 후 테스트004 11건이 통과했다.

이번 단계는 원시 데이터·정밀도·좌표/자세·반복 QA 검증이다. G3 나머지20은 독립 DATA PASS 및 별도 승인 전까지 HOLD, G4 물리분해/source-model Hpsi 계산은 미실행이다. 원본 actual-yaw 두 조건은 다시 추적하지 않았다. C0–C2도 재실행하지 않았다. 전체 알고리즘 채택 NO-GO/실시간 HOLD 유지.
