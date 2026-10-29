# PRE_CONTRACT_DISCLOSURE — POL-XCORR-001

COMMON_CONTRACT I에 따라 계약 작성 전에 proposer가 실행하거나 관찰한 것을 모두 기록한다. 아래 결과는 **사전등록이 아니며**, 계약의 가설 설정에 영향을 주었다.

| # | 시각(KST) | 실행 | 관찰 | 계약에 준 영향 |
|---|---|---|---|---|
| 1 | 10-29 19:3x | Full/LoS H·SAMPLES·timeline·freqs sha256 재계산 | manifest 25개 자산 불일치 0 | `config/INPUT_LOCK.json` |
| 2 | 〃 | `CASES.json` layout 읽기 | `pose,frequency,rx(+45,-45),tx(+45,-45)`, LoS max_depth 0 | R-06 RESOLVED, tx=0 주분석 |
| 3 | 〃 | R2_aA path trace 3개 위치에서 저장 tau와 image-method 1차 경로 지연 대조 | tau는 오름차순, signature는 알파벳순으로 각각 정렬됨. LOS·ceiling만 일치 | R-01 OPEN, T4 조건부 |
| 4 | 〃 | R2_aA 925개 trace에서 Δτ<1, 2 ns 경로 에너지 합계(center node jones 노름) | **무효**: #3의 정렬 결함으로 jones–tau 대응이 보장되지 않음. 수치는 근거로 사용하지 않음 | 없음(폐기 기록) |
| 5 | 〃 | 기하만으로 ceiling/floor/wall 1차 경로 δ, Λ 예측 (R2·R5 경로, anchor x=4, 10) | ceiling δ 0.05–0.30 ns·Λ 10–22 m; floor δ 중앙 1.2–1.5 ns·Λ 1.1–2.2 m; wall δ 1.4–1.8 ns·Λ 0.9–1.7 m; Λ<8 cm ≤ 1% | H4 예상, ceiling 한계 명시, P2b 예측 |
| 6 | 〃 | SAMPLES/timeline 간격·phase 집계 | drive 0.040 m/step, turn 샘플 R2 54/R4 195/R5 72, SAMPLES 행 수 ≠ timeline 행 수 | R-05 OPEN |
| 7 | 〃 | HP_PACKETS 열 목록·case별 행 수 | 9,519행, 63열(e_s, e_r, sF/sL 등) | label·baseline 정의 |

**관찰하지 않은 것:** Full/LoS H에서 ε, ρ, τ*, A_k, M3, M4 계산 결과; 어떤 지표와 e_s·e_r·η의 관계. 선행 메모 `00_PLAN_KO.md`(v0)는 #1–#6 이후, 지표 계산 전에 작성됐다.
