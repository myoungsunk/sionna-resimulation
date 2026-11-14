# G1-RT-TB3-002 G8 파일럿 결과

Snowball에서 2026-11-14 08:22:41–08:23:33 UTC에 G-T1 × A의 P001–P003 TEACH·REPEAT를 실행했다. 관측 338행, RF pose 332개, XY 위치 6개다. F1 솔버 호출 102회로 H와 `PATHS_NEAR`를 함께 만들었다. 경로 export에 추가 솔버 호출은 없었고, 기존 Method B 합성과 비교한 H의 최대 절대차는 0이다. 실행 소요 시간은 51.98초다. [실행 결과](output/G8.json) · [실행 manifest](output/RUN_MANIFEST.json) · [위치별 trace 기록](output/TRACE_RECEIPTS.json).

| 검사 | 결과 |
| --- | --- |
| 002 §3의 G8 판정 | **FAIL**. 동결 G1 `H_LoS`와의 341,296개 복소 원소 비교에서 최대 상대 오차는 3.4236004 × 10⁻⁵로 기준 < 1 × 10⁻⁶을 초과했다. 최대 절대 오차는 2.6026169 × 10⁻⁷이다. |
| 같은 F1 trace의 LoS 재합성 | 332/332 RF pose에서 저장된 단일 LoS 경로를 재합성했다. 최대 상대 오차는 6.8621801 × 10⁻¹⁵다. |
| near 경로 수 | 332개 pose 모두 2개씩 총 664개다. LoS와 천장 정반사가 포함됐다. 최대 초과 경로 길이는 0.097763 m이고 2 tap 범위는 0.299105 m다. NPZ는 10,486,293 bytes다. |

기존 G1 `PATHS_LoS`에서 원래 수식과 단정밀도 자료형을 사용해 `H_LoS`를 비트 단위로 재현했다. 두 trace의 LoS 지연은 모든 pose·bin에서 같았다. 기존 G1 계수와 지연을 그대로 두고 위상 계산만 배정밀도로 바꿨을 때 최대 상대 차이는 2.9992244 × 10⁻⁵였다. 양쪽 위상을 배정밀도로 계산해도 포트 계수 차이로 원소별 최대 상대 오차 7.1792496 × 10⁻⁶이 남았다. [저장 결과 대조](SAVED_LOS_COMPARISON.json) · [대조 코드](compare_saved_los.py).

파일럿 기준과 동결 G1 `H_LoS`를 적용한 판정은 FAIL이다. 이 실행은 파일럿에서 종료했다. 원본 배열과 NPZ는 Snowball의 `/home/KMS/G1_RT_TB3_G8_20261114T082240Z_qOhMGz/output`에 보관했다. [경로 스키마](output/paths/G-T1_A/PATHS_NEAR_SCHEMA.json) · [체크섬](SHA256.txt).
