# G1-INT-001/EXPOSURE · 고감도 노출 가설 검증 사양 (M1–M4)

- **상태:** DRAFT · SPEC · 2026-11-16 · DIAGNOSTIC_ONLY
- **브랜치:** `research/g1-sweep-heading-floor-spec-20261113`
- **기준 커밋:** `3b2bc76` (기전 진단 `audit_m45_donor/mech.py` 포함)
- **범위:**
  - 대상은 mount 0, 앵커 B, B0, Full RF, seed 10의 R2/R4/R5다.
  - 앵커 A와 L2는 이 검증에서 제외한다.
  - mount 45° 자료는 사용하지 않는다 (사용자 결정).
- **봉인:**
  - G-T2/G-V 봉인과 S2′ STOP, Step 3 보류를 유지한다.
  - innovation 기반 온라인 판별·적응은 이번 범위에서 제외한다.

## 1. 질문과 가설

**질문.** R4의 integrity 실패를 일으키는 것이 "느린 분산의 크기"인가, "고감도 상태에서 상관된 편파 측정을 독립으로 누적한 것"인가?

**H-EXP (주 가설).** 고감도(|∂s/∂ψ| 큼) 상태가 오래 이어지면 다음이 차례로 일어난다.
1. 필터는 이동거리 약 0.5 m 안에서 같은 값을 갖는 느린 편파 오차를, packet마다 독립인 정보로 누적한다.
2. 그 결과 P_ψψ가 과도하게 줄고, heading이 편향을 추종한다.

H-EXP가 맞다면, 측정의 실효 독립 수를 상관 길이에 맞춰 줄이는 것만으로 회복된다. 분산 크기 정보는 필요 없다.

**근거 (기존 자료, E0-LORO).**

| 항목 | R4 | R2/R5 고감도 구간 |
|---|---|---|
| packet당 heading 정보 g²/R | 329 rad⁻² | 84–88 rad⁻² |
| σ_ψ | 0.29° | 약 1° |
| 느린 성분의 heading 환산 편향 | 1.29° | 3.5–4.9° |
| 실제 heading RMS | 1.60° | 0.13–0.29° |
| 고감도 체류율 ≥ 0.6인 시점 | 641개, 평균 z² 14.9 | 짧은 구간 (22–34 packet) |
| heading 오차 10 s 자기상관 | 0.63 | 0.26–0.28 |
| 고감도 구간 heading95 | — | 100% |

C3에서 oracle 크기를 줄 때 길이 0.5–4 m에 결과가 둔감했다(94–99%). C1에서는 같은 분산을 백색으로 넣으면 실패했다(26–45%).

**대립 가설 H-MAG.** R4 회복에는 bin별 느린 분산 크기 정보가 필요하다. M1이 실패하면 이쪽으로 판정한다.

## 2. 고정 요소

다음은 모든 arm에서 E0-LORO-σ_b와 같다.
- SourceFFD 관측식과 Jacobian, μ_B·μ_M, 초기값, Q, 운동 모형, controls
- packet별 R_ref: E0-LORO의 Reff. σ_b는 하한값 그대로 둔다.
- 주 gate: E0 고정 mask (R2 971/979, R4 728/742, R5 1384/1415). E0가 거절한 packet은 predict-only다.
- 점수 격자: 거절 시점을 포함한 전체 packet

정의는 다음과 같다.
- **g_i:** 현재 재생 prior의 |H_i[1, 2]|. 단위는 s/rad다. 고감도는 g_i ≥ 1.5다.
- **이동거리 arc:** |ds|의 누적값이다(기존 `motion_arcs`와 같다).
- **누적 회전 yaw:** 재생 prior heading 증분의 절대값 누적이다(자이로 증분에서 b̂_g·dt를 뺀 값).
- **체류율 D_i:** 직전 10 s 동안 g ≥ 1.5였던 packet 비율이다. M3와 기술 통계에만 쓴다.

## 3. arm 정의

### M1 · 노출 조작 (R2/R4/R5 전부, R2/R5 결과는 M4로 보고)

**M1-D(ℓ) · 솎아내기 (주 arm).** E0 mask가 수용한 packet마다 규칙을 적용한다.
- 거리 채널은 매 packet 갱신한다.
- 편파 채널은 아래 조건이 하나라도 맞을 때만 2-D(거리 + 편파)로 갱신한다.
  - 마지막 편파 갱신 이후 Δarc ≥ ℓ
  - 마지막 편파 갱신 이후 누적 |Δyaw| ≥ 10°
  - 첫 수용 packet
- 조건이 맞지 않으면 거리 행만으로 1-D Joseph 갱신을 한다(H[0], R_ref[0, 0]).
- 편파 R은 R_ref[1, 1]을 그대로 쓴다.
- ℓ ∈ {0.5 (주), 1.0, 2.0, 0.25 (민감도)} m. yaw 문턱 10°는 D3 창 전체 폭과 같다.

**M1-G(ℓ = 0.5) · 고감도 한정 솎아내기.** 규칙은 M1-D와 같다. 다만 솎아내기는 g_i ≥ 1.5인 packet에만 적용하고, 저감도 packet의 편파는 매번 갱신한다.

**M1-I(ℓ = 0.5) · 밀도 팽창 (참고 arm).** packet을 버리지 않는 대신 편파 분산을 키운다.
- 편파 분산은 R_ref[1, 1] × F_i이고, F_i = 1 + 2 Σ_{j<i} exp(−(arc_i − arc_j)/ℓ)이다.
- 합은 같은 mask의 수용 이력에서 직전 10 s, 최대 100 packet으로 계산한다. 기존 KI kernel과 같은 제한이다.
- 분산 크기 정보는 쓰지 않는다. R_ref 전체를 상관 성분으로 취급하는 것과 같다.

### M2 · 보정 위치 (R4)

C1 KI(oracle 고정 스케줄)를 기준 arm으로 둔다. C1 KI의 패킷별 편파 분산은 V3(a) trace의 Reff[1, 1] + V_l_op + causal_l이다.

| arm | g_i ≥ 1.5인 packet | 그 밖의 packet |
|---|---|---|
| M2-H | C1 KI 분산 | E0-LORO R_ref |
| M2-L | E0-LORO R_ref | C1 KI 분산 |
| 대조 1 | C1 KI 분산 | C1 KI 분산 (= C1 KI) |
| 대조 2 | E0-LORO R_ref | E0-LORO R_ref (= E0-LORO) |

g_i는 각 재생 자신의 prior에서 계산한다. 고정 스케줄 값은 packet index로 가져온다. 이 arm은 oracle이며 진단에만 쓴다.

### M3 · 정보 회계 (기존 자료, 재생 없음)

E0-LORO trace와 arc, mask로 packet마다 F_i(ℓ)를 계산한다. 정의는 M1-I와 같고, ℓ ∈ {0.5, 1, 2} m다.

다음을 보고한다.
- 궤적별, 체류율 구간별(D < 0.2, 0.2–0.6, ≥ 0.6) F의 중앙값과 95분위
- C1 KI의 실현 팽창비(수용 packet의 R_eff/R_ref 중앙값 20.4, 95분위 42.8)와의 비교
- 팽창 후 예측 heading σ와 실제 |e_ψ|의 비교. 이 σ는 선형 근사로 구한다: 고정 gain 경로에서 Σ g²/(R·F)로 정보를 다시 합산한다.

## 4. 지표

1. **포함률·정확도.** heading95, XY95, Pose95, 평균 NEES3, heading RMSE, XY RMSE를 궤적별과 pooled로 낸다.
2. **branch 지표 (앵커 통과마다).** 통과는 참 x가 앵커 x = 10 m를 지나는 시점이다.
   - **MIRROR_FAIL:** 통과 후 2 s 이상 cross-track 부호(y − 0)가 참값과 다르고, 그때 |y_참| ≥ 0.2 m인 경우
   - **PRE_PASS_OVERCONFIDENT:** 통과 5 s 전 |y 오차|/sd_y > 3인 경우 (경고)
3. **정보 지표.**
   - 편파 갱신 유지율(갱신 수 / 수용 수)
   - κ_s: 편파의 heading 정밀도 기여 몫. D2 정의를 쓴다.
   - 체류율 구간별 heading95와 z²
4. **통계.**
   - 이동 블록 bootstrap: 5, 10, 20 s, 각 1,500회, seed 20261115
   - 같은 궤적 안의 arm 비교는 같은 블록 index로 짝을 짓는다.
   - 비중첩 완전 블록이 8개 미만이면 그 구간은 참고로 표시한다.

## 5. 판정 (사전 등록)

| ID | 판정 규칙 | 결과 표기 |
|---|---|---|
| **M1 (R4)** | M1-D(0.5)에서 R4의 heading95·XY95·Pose95가 각각 ≥ 0.75이고, 10 s 블록 하한 ≥ 0.60이며, heading·XY RMSE가 E0-LORO 대비 각각 +25% 이하이고, MIRROR_FAIL이 0건 | `M1_PASS` / `M1_FAIL`. ℓ = 1, 2에서만 통과하면 `M1_LENGTH_SENSITIVE` |
| **M4 (R2/R5)** | 같은 arm에서 R2와 R5 각각 세 포함률 ≥ 0.75, 블록 하한 ≥ 0.60, RMSE +25% 이하, MIRROR_FAIL 0건. pooled는 heading95·Pose95 ≥ 0.90, 10 s 하한 ≥ 0.80, NEES3 ∈ [1.5, 6.0], RMSE +10% 이하 | `M4_PASS` / `M4_ACCURACY_FAIL` / `M4_INTEGRITY_FAIL` |
| **M2** | ΔH = M2-H − E0-LORO, ΔFull = C1 KI − E0-LORO (R4 heading95). ΔH ≥ 0.9·ΔFull이고 ΔL < 0.5·ΔFull | `LOCATION_HIGH_G`. 둘 다 0.5·ΔFull 이상이면 `LOCATION_BOTH`, 그 밖은 `LOCATION_OTHER` |
| **M3** | R4의 D ≥ 0.6 구간에서 F(0.5)의 중앙값이 C1 KI 실현비 20.4의 0.5–2배 | `ACCOUNTING_CONSISTENT` / `ACCOUNTING_INCONSISTENT` |

**분기.**

| 결과 | 결론과 다음 단계 |
|---|---|
| M1_PASS, M4_PASS | 크기 정보 없이 상관 길이만으로 세 궤적의 integrity를 얻는 후보. 다음: seed 5개, 자체 NIS gate, ℓ 민감도 확정 |
| M1_PASS, M4_ACCURACY_FAIL | M1-G로 같은 판정. M1-G가 둘 다 통과하면 "고감도 한정 솎아내기"가 후보 |
| M1-D·M1-G 실패, M1-I 통과 | packet을 버리지 않는 밀도 팽창이 필요. M1-I를 주 arm으로 다시 판정 |
| M1 전부 실패 | H-MAG 지지. 근거리 크기 문제로 돌아감(bin 분리 대조, 새 자료) |
| MIRROR_FAIL 발생 | 포함률과 무관하게 해당 arm 실패. 통과 전 y 오차/sd 시계열을 보고 |
| M2 = LOCATION_OTHER | H-EXP의 위치 가정이 틀림. 저감도 구간 기여를 따로 분석 |

## 6. 구현 검사 (실행 전 필수)

- **parity.** 솎아내기를 끄면(ℓ = 0, 모든 packet 2-D 갱신) E0-LORO trace와 상태·공분산·gain이 ≤ 1e−10으로 일치해야 한다. M1-I에서 F ≡ 1이면 같은 parity를 요구한다.
- **1-D 갱신.** 거리 행만의 Joseph 갱신에 대해 다음을 독립 재계산한다.
  - S = H_r P H_rᵀ + R_rr
  - K S = P H_rᵀ
  - Joseph 대칭과 PSD
- **mask.** E0가 거절한 packet은 predict-only다. 솎아낸 packet의 기록 필드 `s_updated = False`가 규칙과 일치해야 한다.
- **정보 차단.**
  - 온라인 경로(g, arc, yaw, F)에는 참값을 쓰지 않는다.
  - M2만 V3(a) 고정 스케줄을 쓴다. M2는 oracle로 표시한다.
- **branch 지표.** 참 궤적의 통과 시점 목록이 R2 2회, R4 1회, R5 3회로 감사 결과(`audit_c1_c8/audit_traces.py`)와 일치해야 한다.

## 7. 산출물

- 새 `RUN_CONTRACT.json`. 다음을 동결한다.
  - 입력과 코드의 SHA-256
  - ℓ grid, yaw 문턱, 고감도 문턱 1.5, 체류 창 10 s, KI 제한(10 s / 100 packet)
  - bootstrap 설정
- arm별 trace NPZ. 기존 필드에 `s_updated`, `F`, `g`, `dwell`을 추가한다.
- `M1_M4.json`: 궤적별·pooled 점수, 블록 구간, branch 지표, 판정 표기
- `M2.json`, `M3.json`
- `REPORT_KO.md`와 재집계 검증 기록

## 8. 한계

- **표본.** seed 하나에 궤적 셋이다. R4의 독립 블록은 10여 개다.
- **분기의 단일 실현.** branch 실패는 앵커를 지날 때의 분기로 결정되며, 한 번의 실현만 있다.
- **해석 범위.** M1 통과는 "이 복도, 이 RT 모형에서 상관 길이 기반 처리로 충분하다"는 뜻이다. 상관 길이 0.5 m는 D3 창 폭에서 온 값이고 물리적으로 식별된 값이 아니다(V2 미식별).
- **gate.** E0 고정 mask를 쓴다. 자체 gate의 영향은 M1_PASS일 때 다음 단계에서 확인한다.
