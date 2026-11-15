# G1-MODEL-003 v2 → v3 변경 기록

- 작성: 2026-11-15 KST. 역할: PROPOSER.
- 대상: [SPEC_B_NEW_RT_KO.md](SPEC_B_NEW_RT_KO.md)(v2) → [SPEC_B_NEW_RT_V3_KO.md](SPEC_B_NEW_RT_V3_KO.md)(v3), [SPEC_A_BLOCKC_KO.md](SPEC_A_BLOCKC_KO.md) D7.
- v2 실행 기록: `research/g1-model003-s0-20261115` @ `1e59fc0dc178d92ca188e067bfae5ba036e69346`, S3 `DEV_FAIL`, 봉인 유지.

## 원칙

1. v2 사양과 v2 산출물은 수정하지 않는다.
2. 아래 변경은 **모두 v2 G-T1 결과를 본 뒤의 변경**이다. G-T1은 개발 자료이므로 허용되지만, G-T1 LOAO 수치는 v2·v3 모두 주장 근거가 아니다.
3. 봉인 데이터(G-T2, G-V)는 v2에서 열리지 않았다. 확인 분석 횟수는 여전히 0이며, v3 S4가 첫 번째이자 유일한 확인이다.
4. v3는 마지막 개발 반복이다. v3가 DEV_FAIL이면 구조 불가로 결론낸다.
5. 논문에는 v2 DEV_FAIL과 v3 결과를 모두 보고한다.

## 변경 항목

"결과 의존"은 v2 결과가 없었다면 이 변경을 하지 않았을 것인지를 뜻한다. "값 이전"은 v2에서 얻은 수치를 v3의 모수로 옮겼는지를 뜻한다.

| ID | 항목 | v2 정의 | v3 정의 | 계기가 된 v2 결과 (파일) | 결과 의존 | 값 이전 |
|---|---|---|---|---|---|---|
| A1 | 개발 순서 | 전 arm 동시 | range 먼저(S3-R), 통과 후 편파(S3-J) | R4 heading 포함률 38.3%, NEES 134, XY RMSE 1.04 m 대 DR 0.69 m (`S3/LOAO_RESULTS.json` findings.R4) | 예 | 아니오 |
| A2 | range 평균 | 보정 없음 | 거리 구간 평균 b_r(r̃) 보정 + consider 잔여 K_r | 잔차 평균 +0.002 / +0.026 / +0.099 / +0.189 m (`S2/CHARACTERIZATION_003.json` ABC.C6.distance) | 예 | 아니오. v3 S2′에서 다시 추정 |
| A3 | ranging 규칙 선택 지표 | range RMSE 최소 | noise-free LoS offset 제거 후 RMS 최소, 동률 폭 5 mm | 전 후보 RMSE ≈ \|bias\|: O30 −0.486/0.500, O20 −0.594/0.604, O10 −0.734/0.739 m (`S1/RANGING_RULE_SELECTION.json`) | 예 | 아니오. v3 S1′ 결과로 선택 |
| A4 | C2 분산 적합 | 절점 0/1.5/3/6/10 m, 제약 없는 구간 선형 최소제곱 | 지원 절점만, σ_95, log 분산, 평활 벌점, 하한, 구간 최소 표본, 지원 밖 packet은 s 미사용 | 1.5 m 절점 7/7이 1e-8 ~ 7e-5, 6 m 절점 4/7이 1e-6 이하, 0 m 절점은 지원 밖 (`CHARACTERIZATION_003.json` C2) | 예 | 아니오 |
| A5 | 백색 통합 분산 | C2 절점 표준편차의 pose 가중 평균 | 솎은 잔차의 σ_95²를 직접 계산 | A4의 붕괴 절점이 평균에 포함됨 (`S3/LOAO_PLAN_KO.md`) | 예 | 아니오 |
| A6 | C3 상관 적합 | 지수 | nugget + 지수, 범위 제한, 경계 도달 규칙 | ρ(4 cm) = 0.39–0.66으로 0에서 1이 아님 (`CHARACTERIZATION_003.json` C3). DIAG-003 D7의 상한 도달 중단 | 예 | 아니오 |
| A7 | 정지 packet의 전이 | 명시 없음 | Δd = 0, Δψ = 0이면 φ = 1, 과정잡음 0 | TEACH 2,637 packet, 이동 7.65 m, 회전 4,330° (`S0/TIMELINE_CHECK.json` streams). 속도로 환산하면 약 82%가 18개 station XY | 예 | 아니오 |
| A8 | C7 꼬리 추정 | 전체 잔차에 Student-t | 거리 정규화와 솎기 후 추정, ν 하한 3 | ν 1.30–1.62, σ_b가 거리에 따라 10배 변함 (`CHARACTERIZATION_003.json` C7, C2) | 예 | 아니오 |
| A9 | 꼬리 arm | 없음 (측정만) | +T (J-C, J-CS와 각 +K) | C7을 쓰는 arm이 없었음 | 예 | 아니오 |
| A10 | M1-R 거리 노드 | 절단 없음 | d_floor 0.5 m 절단, 잔여 분산은 선형항으로 R에 가산 | J-CI·J-CI+K 18 fold "Nonpositive M1-R quadrature distance" (`LOAO_RESULTS.json` J-CI.fold_issues) | 예 | 아니오 |
| A11 | 판정 순서 | integrity 항목에 B0 비열등(CI 상한 ≤ 1.10) 포함 | integrity → 무해성(점추정 ≤ 1.10, CI 상한 ≤ 1.25) → 정확도 | J4 B0 비율 점추정 0.999, CI [0.787, 1.30] (`LOAO_RESULTS.json` J4.integrity.pooled) | 예 | 아니오 |
| A12 | pooled XY 포함률 | 기준 없음 (case 심각 실패만) | 점추정 ≥ 0.90 | J4 XY 포함률 25.8%, R4 22.6%인데 pooled 항목이 heading뿐 | 예 | 아니오 |
| A13 | sensor seed | 20 | 40 | A11과 같음 | 예 | 아니오 |
| A14 | 개발 실행 범위 | B0에서 전 후보 탈락 시 종료 | 전 수준 실행 | L0–L2·TB3 점 미실행으로 진단 정보 부족 (`S3/PRIMARY_ARM.json` not_evaluated_levels) | 예 | 아니오 |
| A15 | 초기 오차 0 조건 | 없음 | B0에서 함께 실행 (보고용) | DR B0 heading RMSE 4.69°, heading NEES 0.15, b_g NEES 0 (`LOAO_RESULTS.json` findings.DR) | 예 | 아니오 |
| A16 | 이전 가능성 사전 기록 | 없음 | S2-T: fold별 Z_s, Z_r을 S3 전에 커밋 | 5 m 창 평균 s: A 0.047, B 0.009, C 0.158 (`CHARACTERIZATION_003.json` C5_by_path). miss 방향 쏠림 (`LOAO_RESULTS.json` path_descriptives) | 예 | 아니오 |
| A17 | 개발 반복 한도 | 없음 | v3가 마지막 | 특성화 "한 번" 규칙의 재실행에 대한 통제 | 예 | — |
| A18 | 구간별 기여 보고 | "직진과 sweep 구간의 갱신 기여" | 직진·회전·정지 구분, 필드 이름을 계획에 명시 | `contributions_by_fold`의 배열 필드 의미가 산출물에 없음 | 예 | 아니오 |
| A19 | DIAG-003 D7 | 상관길이 미식별 시 규칙 없음 | D7.1: 상한 도달 시 두 arm 병행, 분산은 다른 경로에서, 하한 도달 시 백색 | D7 진입 중단(R2-aB 편파·range, R4-B 편파가 탐색 상한 도달) | 예 | 아니오 |

## 바꾸지 않은 것

- 추정기 유형(packet 단위 재귀 EKF), mount 0, Goal 1 경계.
- 봉인, 확인 형상, pose 집합, packet timeline.
- integrity의 pooled heading 포함률 기준, NEES 범위, case 심각 실패 기준.
- S2-F의 정의.
- 1차 arm 선택 규칙의 형식(integrity 통과 → L1 RMSE → 단순성).

## 감사에서 확인하지 못한 것

- LFS 파일(H, timeline CSV, fold 원자료).
- DIAG-003 D1–D6 결과(로컬에만 있음).
- `FUTILITY.json`의 checkpoint별 세부.
- `contributions_by_fold` 배열의 필드 정의.

## 재실행 조건 점검표

| 조건 | 상태 |
|---|---|
| v2 결과 동결·게시 | 완료 (`1e59fc0`) |
| 변경 항목과 계기 기록 | 이 문서 |
| v3 계획과 합성 검산을 실행 전에 커밋 | 미완료 |
| 봉인 SHA가 v2 S1 진입 기록과 일치 | S1′ 진입 시 확인 |
| 연구자 승인(§11 "승인이 필요한 값") | 미완료 |
