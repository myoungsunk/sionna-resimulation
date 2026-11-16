# Mount +45° V7 R2 대조

질문 ID는 `G1-INT-001/KS-TRANSFER/M45-V7-R2`다. 기존 KS 실행에서 앵커 A 입력이 빠져 V7을 보류했다. 이후 확보된 앵커 A R2의 X1 동결 보정과 parity 통과 E0를 사용해 B0와 L2를 대조했다. A/B가 모두 수용한 동일 패킷에서, 원본 E0의 감도와 관측분산으로 보정 후 잔차에 가중치를 줬다. 원본 V7 계산과 10 s 블록 bootstrap 1,500회를 적용했다. [동결 계약](RUN_CONTRACT.json) · [실행 코드](../run_v7_mount45_r2.py)

| R2 | 공통 수용 | 정보 방향 | A signed | B signed | 절대비 A/B | 동결 판정 |
|---|---:|---|---:|---:|---:|---|
| B0 | 769 | 편파→heading | +0.066 | −0.240 | 0.27 | 2배 기준 미달 |
| B0 | 769 | 거리→anchor ray | −0.081 | −0.070 | 1.16 | 2배 기준 미달 |
| L2 | 817 | 편파→heading | +0.051 | −0.172 | 미결 | B의 95% 구간에 0 포함 |
| L2 | 817 | 거리→anchor ray | −0.076 | −0.079 | 0.96 | 2배 기준 미달 |

두 대조 모두 완전한 10 s 블록은 19개다. A/B 짝 차이의 95% 구간은 네 행 모두 0을 포함한다. B·B0의 보정 후 잔차는 D2와 정확히 일치했고, B·L2의 E0 prior, Jacobian, 관측분산 및 gate는 보관된 별도 비교 trace와 일치했다. A/B의 pose ID, 시간, 참 자세, 주행 입력을 대조했다. 출력과 계약의 SHA-256도 일치했다. [수치·구간·검사](execution/V7_R2.json) · [실행 기록](execution/EXECUTION.json)

V7의 주 비교는 R4 편파다. R5 거리는 보조 비교다. A·R4/R5의 +45° 동결 MB_VAR와 E0 gate가 확보돼야 두 비교를 재개할 수 있다. 기존 D4 판정과 KS 진입 판정은 그대로다. [기존 KS 진입 기록](../ks/execution/KS.json) · [체크리스트 결과](../CHECKLIST_STATUS_KO.md)
