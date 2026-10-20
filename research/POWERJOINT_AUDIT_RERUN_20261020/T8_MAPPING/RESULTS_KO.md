# T8 재생성 M45 시간 바인딩 결과

계산 TECHNICAL_PASS; 재귀 입력 인증 과학 판정 BLOCKED_INPUT. Actions run39361554110 / artifact12237048283에서 4조건 모두 ordered pose/time 바인딩에 실패했다. 재귀 EKF·B0/L2 Heading·visit skip 비교는 실행하지 않았다.

|조건|M0/M45 행수|동일 ID의 geometry 불일치|인증된 기준 clock 없는 행|정적 pose 쌍|재귀|
|---|---:|---:|---:|---:|---|
|R4_aA_m0|922/922|741|921|922|BLOCKED_INPUT|
|R4_aB_m0|922/922|741|921|922|BLOCKED_INPUT|
|R5_aA_m0|1883/1883|1414|1882|1883|BLOCKED_INPUT|
|R5_aB_m0|1883/1883|1414|1882|1883|BLOCKED_INPUT|

행별 인증 5610행 중 5606행 실패다. 같은 pose_id 또는 같은 행수는 같은 geometry/clock 인증이 아니다. 원 M0 Tnone과 재생성 T10 first-visit의 완전한 pose·시간·body yaw·antenna yaw 대응이 필요하다. 없는 clock을 추정하거나 일치하지 않는 pose_id의 시간을 붙이지 않았다.

Geometry-only matching은 위치≤1mm·body yaw≤.01°·antenna=body+45°를 충족하는 pose만 사용했다. 총 5,610개 pose 쌍에서 M0/M45 각각 관측하여 STATIC_RF_COMPARISON.csv 11,220행을 보존했다. 모호한 후보와 미매칭 pose는 모두 0이다. 이 비교는 정적 단일 RF 관측 비교이며 EKF one-step 상태 갱신이나 Heading 개선 검증이 아니다.

|조건|mount|Δs RMS|Full/LoS FP 불일치|LoS abs(s)>.95|
|---|---:|---:|---:|---:|
|R4_aA_m0|0|0.201823|47.180%|7.701%|
|R4_aA_m0|45|0.178686|38.937%|29.935%|
|R4_aB_m0|0|0.126293|35.033%|7.484%|
|R4_aB_m0|45|0.105903|27.874%|24.837%|
|R5_aA_m0|0|0.187480|37.706%|38.131%|
|R5_aA_m0|45|0.188433|46.999%|4.249%|
|R5_aB_m0|0|0.097659|32.501%|35.741%|
|R5_aB_m0|45|0.117185|42.963%|3.611%|

위 수치는 인증된 정적 전체 pose 집합의 요약이며 x10–16 V1/V2 시간 구간 통계로 해석하지 않는다. Native LoS의 무효 행을 생성·대체하지 않았다. 모든 원본 detector는 고정 Hann/4N IFFT·strongest RX30% leading edge·공통 tap을 사용한다.

원본 코드 commit: `90c7d752d1dc246e93164a0c57b16702cce826fa`. artifact SHA256: `sha256:ccef83200319b37665d6a0421af811ac649103cd1fd0363e63531866864ef63e`. MANIFEST에 SourceFFD observer·원 RF·M45 RF·pose·lock·release multipart asset의 SHA와 receipt를 보존했다. 기존 실패 execution_r01/r02/r03도 삭제하지 않았다.

## 주장하지 않는 것

정적 비교로 시간 바인딩, 재귀 Heading/gyro bias 개선, 독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다. 이번 결과는 T10 first-visit pose 집합의 관측 대비이며 M0 Tnone 궤적 재귀의 대체물이 아니다.
