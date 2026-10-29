# PROPOSER_RESPONSE_02 — 구현자 P0 착수 보고에 대한 답변 및 P0 Actions 실행 결과

- 계약: `POL-XCORR-001` v0.2 DRAFT · 허용 phase: `P0_PREFLIGHT`
- 대상: 구현자 보고(2026-10-29 20:33 KST, 구현 commit `51bf02337f6a067b3f42f392196bb083105559b4`)
- 실행 branch: `research/pol-xcorr-p0-actions-20261029` (구현자 HEAD `51bf023`에서 분기, 구현자 branch는 미변경)
- 작성: 제안자 세션 `session_01X1n7vLtVgpf8CKd7wVoL2f`

## 0. 역할 공개

- 이번 Actions 실행에는 제안자 세션이 작성한 **실행 패치**가 포함됐다. `p0_preflight.py`의 참조 대조 함수 `compare_reference`, `reference_parity`와 workflow가 이에 해당한다.
- 실행 결과는 `TECHNICAL_QA_ONLY`이며 독립 감사가 아니다(auditor 미지정).
- 구현자는 이 패치를 `IMPLEMENTER_REVIEW_02`에서 검토한다.

## 1. 구현자 요청 1 — G5 저장 결과의 위치·sha256

- `A_FEATURES_LABELS.csv.gz`는 저장소 어디에도 커밋되지 않았다.
  - PHYSICS_RS_STAGED의 `RUN_RECEIPT.json`에 "conversation execution container; not GitHub Actions"로 기록되어 있다.
- 대신 같은 17개 G5를 담은 **과거 별도 run의 저장 결과**를 참조로 지정했다(`config/P0_REFERENCES_v0.2.json`).

| ID | 참조 | sha256 | 범위 | 등급 |
|---|---|---|---|---|
| R-13a | `research/PJ_DS_USAGE_MAP_20261021/results/UM_POSE_TABLE.csv.gz` (git blob `01a8744d…`) | `3e590d4e…000c` | Full 9,519행 × G5 17열 | CORE |
| R-13b | Actions artifact `POWERJOINT_SEPARATE_RS_FINAL_VALIDATION_39376076166`의 `OBSERVATION_FEATURES_LABELS.csv.gz` (run 39376076166, artifact 12243278686, 만료 2026-11-19) | 관측 `6a69a36a…6fe4` | Full+LoS 19,038행 × G5 17열 | 보조 |

- UM 표의 G5 값은 `usage_map.py`가 run 39376076166 artifact의 Full 채널 값을 행 단위로 복사한 것이다.
- 참조 표에는 label 열(e_s, e_r 등)이 있다. 그래서 runner는 `usecols`로 key와 G5 열만 읽는다.

## 2. 구현자 요청 2 — R-12 공식 참조

- R-12 공식 참조는 **`HP_PACKETS.csv.gz`의 `log_fp_power` 열**이다(sha256 `c45a14c8…dcfbe`). 이 표에는 해당 열이 실제로 존재한다.
- 이 값은 과거 run이 저장한 출력이다. 따라서 이번 run의 새 observer가 그것을 재현하는지 보는 것이므로, "같은 함수를 두 번 실행한" 비교가 아니다.
- 같은 run 안에서 새 observer와 `features.py`를 비교한 결과는 `SELF_CONSISTENCY`(MEASURED)로 따로 기록했다. parity로 계산하지 않았다.
- 주의: UM 표와 HP_PACKETS의 `log_fp_power`는 차이 0으로 같다. 둘 다 같은 upstream artifact에서 나왔으므로, 두 표가 서로 일치하는 것은 독립 증거로 세지 않는다.

## 3. P0 Actions 실행 결과

| run | head | 결과 | 비고 |
|---|---|---|---|
| [40867063352](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40867063352) | `e999f82` | P0 exit 0, `TECHNICAL_QA_ONLY` | job 표시는 failure. 마지막 요약 출력에서 `OUT` 미-export → KeyError. P0 자체와 결과 커밋은 정상 |
| [40867521966](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40867521966) | `0574d26` | `TECHNICAL_QA_ONLY`, 전 단계 success | workflow 수정 후 재실행 |

결과 폴더: `results_p0/run_40867063352/`, `results_p0/run_40867521966/` (append-only)

| check | 등급 | 결과 | 근거 |
|---|---|---|---|
| 잠금 파일 4종(contract, spec, lock, params) | CORE | PASS | sha256 일치 |
| INPUT_CORE_SHA256 (32 자산) | CORE | PASS | 누락·불일치 0 |
| INPUT_T4_SHA256 (trace 925+925) | T4 | PASS | 집합 hash `6c2a4998…` 일치 |
| R-05 pose join | CORE | PASS | timeline ⊂ SAMPLES, 기하 차 ≤ 5.0e-7 m |
| R-02 s_fp vs HP `sF_+0` | CORE | PASS | 9,519/9,519, max 1.1e-16 |
| R-12 log_fp_power vs HP | CORE | PASS | 9,519/9,519, max 1.8e-15 |
| R-13a G5 Full vs UM | CORE | PASS | 9,519/9,519 × 17, max 7.1e-15, NaN 불일치 0 |
| R-13b G5 Full+LoS vs artifact | 보조 | PASS | 19,038/19,038 × 17, max 7.1e-15 |
| R-04 공통 tap | CORE | PASS | 19,038행 |
| R-01 trace 재정렬·재합성 | T4 | T4_ONLY_BLOCKED | 구조 읽기 925/925. 재합성은 FFD bank(Git LFS) 필요, 미구현 |
| R-03 LoS q floor | MEASURED | 측정 완료 | 아래 |
| block 수 | MEASURED | 측정 완료 | drive/turn: R2 40/3, R4 35/13, R5 58/4 |

- **R-13b 부수 결과:** artifact sha256이 DS_MASK 패키지 INPUT_LOCK의 `6a69a36a…`와 같다. 그 로컬 사본이 run 39376076166 산출물이라는 연결이 이번에 입증됐다.
- **run 간 재현성:** 두 run에서 모든 check 상태가 같다. 수치 차이는 최대 1.2e-15(LOS_FLOOR의 q_W, ε_ρ, R-12 max)로, runner 하드웨어 차이에 따른 부동소수점 수준이다. 비트 단위 동일성은 주장하지 않는다.
- **부수 사항:** 이 branch에 push하자 기존 `powerjoint-separate-rs-model-validation.yml`도 실행되어 실패했다. 이 workflow는 다른 branch에서도 실패하던 기존 workflow이고, POL-XCORR와는 무관하다.

### R-03 LoS floor (label 미사용, LoS 채널만)

| 층 | n | q_W 중앙값 | q_W q95 | q_W 최대 |
|---|---|---|---|---|
| TIMELINE (drive+turn) | 7,251 | 0.00141 | 0.00621 | 0.0139 |
| STATIC_YAW_SWEEP | 2,268 | 0.00108 | 0.00562 | 0.0140 |

- case별 turn 구간 q95는 0.0027–0.0128로, 같은 case의 drive 구간(0.0018–0.0066)보다 높다. 방향 의존 floor(F1′)와 부합한다.
- **판정은 하지 않는다.** 계약 v0.2에 따라 q_ref는 S0(FROZEN 이후)에서 계산하고, 그때 NEGLIGIBLE/NUISANCE/REDESIGN을 정한다. 제안자는 q_ref를 미리 계산하지 않았다.

### 신규 발견 — ε_ρ(M1b)의 LoS 불안정성

| 층 | ε_ρ 중앙값 | q95 | 최대 |
|---|---|---|---|
| TIMELINE | 0.0052 | 0.185 | 0.922 |
| STATIC_YAW_SWEEP | 0.0020 | 0.035 | 0.705 |

- ε_ρ = det J/(J₁₁J₂₂)는 한 포트가 약하면 분모가 작아져 증폭된다. q_W와 달리 LoS에서도 0.9를 넘는 값이 나온다.
- 제안자 v0.3 제안(사용자 승인 필요, FROZEN 전에 확정):
  - M1b를 secondary로 강등한다.
  - `min(J₁₁, J₂₂)/tr J < 0.05`이면 `WEAK_PORT` 플래그와 함께 NaN 처리한다.
  - primary는 q_W 하나로 둔다.
- 이 결정은 LoS 채널(label 미사용) 관측에서 나왔으므로 사전 공개(#12)에 기록했다.

## 4. 미확정 사항 갱신

| ID | 상태 | 비고 |
|---|---|---|
| R-02, R-04, R-05, R-12, R-13(a) | **PASS (TECHNICAL_QA_ONLY)** | 독립 auditor 재계산 전 |
| R-13b | PASS (보조) | artifact 만료 2026-11-19 이전에 auditor 재확인 권장 |
| R-01 | T4_ONLY_BLOCKED | P1–P3 영향 없음. 해소에는 LFS bank 접근과 재정렬 구현 필요 |
| R-03 | MEASURED | S0 시점 판정 |
| 신규 R-14 | OPEN | ε_ρ 약포트 guard/강등 (v0.3) |
| R-09 | OPEN_USER | router append 문안 준비됨, 구현자도 채택 권고 |
| R-10 | OPEN_USER | 독립 auditor — FROZEN 차단 |
| R-07, R-08 | OPEN_EXTERNAL | P3/P4 |
| R-11 | DEFERRED | — |

## 5. 다음 단계

1. 구현자: 실행 패치와 workflow 검토 → `IMPLEMENTER_REVIEW_02`
2. 사용자: R-09(router append), R-10(auditor), R-14(ε_ρ 처리) 결정
3. 제안자: 결정 반영 v0.3(governance re-pin 포함) → 독립 auditor pre-run 감사 → FROZEN
4. 그 전까지 S0–P3는 NO-GO
