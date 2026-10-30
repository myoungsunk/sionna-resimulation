# S0_REVIEW_02 — S0 run 40989019866 검토 (AUDITOR, SELF_REVIEW_ONLY)

- 대상:
  - implementer branch `research/pol-xcorr-s0-implementer-20261030` HEAD `91329a5a`
  - run [40989019866](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40989019866)(성공), [40988893943](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40988893943)(fixture 결함, 보존됨)
- 계약: v1.0 FROZEN `c36c1c56…e219`
- 감사 코드: `audit/s0_review_diag.py` (sha256 `ccd70060b187528ac43f97629cd13d3a79d509515f06cfd0f9df5df8f395d683`). 저장소 모듈은 import하지 않는다. 합성 데이터와 LoS만 쓰고 label은 쓰지 않는다.
- 출력: `audit/results_s0_review/`
- 독립성: **SELF_REVIEW_ONLY**. 감사 세션이 결함 있는 사양(TASK_HANDOFF_v1.0 §2, 계약 D6 채널식)을 작성했다.

## 1. 구현 충실도

| 항목 | 결과 |
|---|---|
| 채널식 | 구현(`s0_synthetic_v1.py` L147–152)이 handoff 식 `exp(jψ − j2π·f·δ)`(f = 절대 RF 주파수)를 **그대로** 따랐다 → 사양 충실 |
| q_ref 재현 | 감사 재계산 0.0010961014 = 구현 0.0010961014 |
| R-03 입력 | TIMELINE q95 0.0062090 일치 |
| 판정 적용 | 계약 규칙 그대로(사후 완화 없음) |
| 실패 run 보존 | 40988893943 보존. fixture 수정 사유가 기록됨 |
| label 접근 | 없음 |

**구현 결함은 없다.** 아래 결함은 모두 사양 쪽(제안자)에 있다.

## 2. H1_FAIL 원인 분해 (사양 결함 3개)

| ID | 결함 | 증거 (감사 재계산) |
|---|---|---|
| C1 | **반송파 위상 결합.** 지연 항의 절대 주파수 f 때문에 baseband 유효 위상이 ψ_eff = ψ − 2π·f₀·δ가 된다. δ 0.05 ns마다 0.31 cycle 회전하므로 "ψ 고정" 층이 성립하지 않는다 | sweep당 n₀ 전환: frozen 9.17회 → 대역 중심 기준 0.71회 |
| C2 | **기준 주파수.** 대역 하단 기준이면 펄스가 B/2 반송파를 가진 복소 펄스가 되어 δ당 π·B·δ 위상이 추가로 생긴다. F2는 실수 대칭 펄스를 가정한다 | 0.05–0.25 ns 기울기 분포(p05–p95): 하단 기준 1.54–2.25, **중심 기준 1.81–1.97** |
| C3 | **적합 구간.** [0.05, 1.0] ns는 소 δ 영역을 벗어난다. 펄스 σ_t = 1/(2π·B_rms) = **2.25 ns**, δ/σ_t ≤ 0.44. tolerance ±0.1과 양립하지 않는다 | 중심 기준·n₀ 고정의 구간별 기울기 중앙값: 0.002–0.01 ns **1.997**(p05 1.993), 0.01–0.05 1.983, 0.05–0.25 1.907, 0.25–0.5 1.677, 0.5–1.0 1.180 |

- **결론:** F2 소 δ 법칙(det J ∝ δ²)은 δ → 0에서 성립한다(EXPLORATORY 확인). 동결된 H1 판정 `H1_FAIL`은 **사양 결함에 의한 실패**로 분류한다. F2 반증이 아니다.
- **tap 전환:** 주원인은 C1이다. C1을 고치면 n₀ 전환은 sweep당 1회 미만이다. n₀ 고정과 검출기 추종의 기울기 중앙값 차이는 0.05–0.25 ns에서 약 0.05(1.908 vs 1.959)다.
- **PHYSICAL 모드:** 구현이 ψ = −2π·f_c·δ를 추가로 넣어 반송파 위상을 **이중으로 반영**했다(C1과 같은 사양 혼동). 보고 전용이라 판정에 영향은 없지만, 이 표는 무효로 표시한다.

## 3. R-03 REDESIGN_REQUIRED 견고성

| 채널 구성 | q_ref | LoS q95 / q_ref | 판정 |
|---|---|---|---|
| frozen (절대 f) | 0.0010961014 | 5.665 | REDESIGN_REQUIRED |
| 대역 하단 기준 | 0.0010961017 | 5.665 | REDESIGN_REQUIRED |
| 대역 중심 기준 | 0.0010961014 | 5.665 | REDESIGN_REQUIRED |

- q_ref는 ψ 16점 평균이라 일정한 위상 이동에 사실상 불변이다. −10 dB에서는 근접 상쇄 제외도 발생하지 않는다(|a + b·e^{jψ}| ≥ 0.68|a|).
- **결론:** R-03 판정은 C1–C3과 무관하게 유지된다. **REDESIGN_REQUIRED를 확인한다.**

### 해석에 필요한 부가 수치 (EXPLORATORY, label 미사용)

| 항목 | 값 |
|---|---|
| floor 등가 반사 강도(δ = 1 ns, 평균 q_W가 LoS q95에 도달하는 \|b\|/\|a\|) | wedge 0.3: **−3.7 dB** · wedge 1.0(직교 Jones): **−13.0 dB** |
| 방향 무관 포트 등화기 c(f)(LORO, LoS 중앙값) 적용 후 LoS q95 | 0.00614 → 0.00572 (−6.8%), 중앙값은 0.00133 → 0.00155 (악화), q95/q_ref = 5.2 |
| S0 noise floor(구현자 결과) | 포트 시간 오프셋 250 ps에서 합성 LoS q95 = 0.0071 ≈ 실측 LoS floor 0.0062 |

해석:
- LoS floor는 **방향에 따라 변하는 포트 응답 분산**(F1′)이다. 크기는 포트 간 약 200 ps의 등가 시간 오프셋에 해당한다.
- 정적 보정으로는 거의 줄지 않는다.
- 현재 q_W로 floor 위에서 보이는 반사는 강한 반사(≥ −3.7 dB, wedge 0.3)나 강하게 탈편파된 반사(직교 성분 ≥ −13 dB)뿐이다.

## 4. Verdict

- **S0 실행:** `ACCEPT_WITH_BOUNDARIES` — 구현이 사양에 충실하고 기록이 완전하다.
- **H1:** 기계 판정 `H1_FAIL`을 유지하고, 원인을 `SPEC_DEFECT_C1_C2_C3`로 분류한다. 수정 LAW 결과(기울기 1.997)는 EXPLORATORY 근거로만 쓴다(결과를 본 뒤의 재정의이므로).
- **R-03:** `REDESIGN_REQUIRED` 확인. M1(q_W, ε_ρ)·M2를 E1/E1b/E1c/E2에 쓰는 것은 v1.0 규칙대로 **STOP**한다.
- 서명: Claude (Opus 5.5), session `session_01X1n7vLtVgpf8CKd7wVoL2f`, 2026-10-30 KST — **SELF_REVIEW_ONLY**.
