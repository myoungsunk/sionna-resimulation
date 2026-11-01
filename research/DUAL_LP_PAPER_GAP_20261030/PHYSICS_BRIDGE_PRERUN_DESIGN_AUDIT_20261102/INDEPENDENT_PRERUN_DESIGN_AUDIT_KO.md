# INDEPENDENT PRE-RUN DESIGN AUDIT — DLP-PHYS-BRIDGE-012-001 v0.1 (DRAFT)

2026-11-02 KST · role=`AUDITOR` · 대상=제안자 DRAFT v0.1 · **판정: `REVISION_REQUIRED`**

이 문서는 제안자 문서 01–06·CONFIG·SOURCE_REFERENCE_LOCK·reference_review에 대한 **구현 전 설계 감사**다. 새 RT·필터 재생·학습은 하지 않았다. 아래 수치는 (a) 이미 보존된 산출물의 독립 재계산, (b) 대수 항등식 검산, (c) 원 코드 정독에서 나온 것이며 새 과학 결과가 아니다.

## 0. 신원·독립성

| 항목 | 값 |
|---|---|
| auditor actor/session | Claude (claude-opus-5-5), claude.ai 세션 `session_01X1n7vKETgA3nteaHg8zEZc` |
| proposer actor/session | 별도 세션. git author `myoungsunk`, 커밋 2026-11-01 20:52–21:19 KST. 모델 정체는 이 감사자가 확인할 수 없음 |
| shared code/helpers | 없음. 제안자 문서에는 실행 코드가 없음. 역사적 `recompute_review.py`는 격리 사본에서 재현 여부만 확인 |
| independent calculation | `calc/ind_recalc.py`, `calc/math_checks.py`, `calc/d2_transcription_check.py` (이 감사자가 새로 작성) |
| 독립성 등급 | `DISTINCT_SESSION_DESIGN_REVIEW`. 제안자도 같은 계열 모델이면 독립성은 세션 수준에 그침 |
| reviewed proposal head | `cc0557410daa56f9cd5df35d687a21fc4a2ef972` (`proposal/dual-lp-physics-bridge-12case-20261101`) |
| base / governance / evidence | `1aac4d38a6fa335116bcecbebc91ba53c876ecfd` / 동일 / `6c7200091028fd3f0e55aa83b777d0f10b7cf063` |
| contract file sha256 | 01 `5ed92e73…2e94`, 02 `3eb6ab47…107f`, 03 `04cae089…085a`, 04 `98338bba…d5fa`, 05 `3ee8b1bd…19da`, 06 `d5c5daa2…3abd`, CONFIG `c9fc9e96…88e7`, LOCK `9447bc74…aa02` (전체 값은 `AUDIT_VERDICT.json`) |

**범위 한계:** ROLE_AUDITOR pre-run 1항은 `FROZEN` 계약을 요구한다. 대상은 DRAFT이므로 이 판정은 **v0.2 freeze candidate를 만들기 위한 설계 검토**다. 06 §3의 3단계(candidate SHA에 대한 pre-run 판정)를 대신하지 않는다. v0.2가 나오면 같은 감사자 또는 다른 독립 감사자가 그 SHA로 재판정해야 한다.

## 1. 독립 확인 결과 — PASS 항목

| 검사 | 기대 | 독립 재계산 | 결과 |
|---|---|---|---|
| 첨부 ZIP 무결성 | `0d261f54…6980`, 47,466 B | 동일 | PASS |
| 업로드 9개 중 byte-identical | 8개 + RA4 외부 | 8/8 SHA256 일치, RA4는 tree에 없음 | PASS (custody는 §3 B7) |
| 12조건 집계 (RA4 → self-gate) | 평균만 4/12·6/12, 분산만 12/12·8/12, 결합 12/12·8/12 | 동일 | PASS |
| 결합이 두 단독보다 H·XY 모두 우수 | 8 (R2·R5) | 8 | PASS |
| R4-B에서 분산만이 결합보다 두 지표 모두 우수 | 4/4 | 4/4 (B0,L0,L1,L2) | PASS |
| SELECTED_12 표와의 차이 | 0 | max 1.8e-15 | PASS |
| D2 전사 48값 vs `D2_GATE_SCORES.csv`@6c720009 (blob `efe55ff9`) | exact | 48/48 exact | PASS |
| 역사적 `recompute_review.py` 재현 | 원 출력 | 격리 사본에서 tables·QA·evidence 모두 byte-identical | PASS |
| SOURCE_REFERENCE_LOCK 코드 blob | `21a3ef82`, `ea1cac65` | 동일 | PASS |
| timeline n | 979 / 742 / 1415 | RA4 `n_packets` 동일 | PASS |
| 추가분산 조회 시점 | motion prediction 이전 | `diag_mbvar.py` L64–68, `exp_pb.py` L105: predict 전에 `hypot(x−a)` | PASS (문구 정밀화 B1) |
| 필터 관측모형 = SourceFFD | PB1의 J가 필터의 J | `reflect_model/common.py::base_model()` = "Original LOS-only SourceFFD" | PASS |
| NIS gate / 갱신 | 9.210340371976184, Joseph | 코드 동일 | PASS |
| 동일 prior gain column 축소식 | Kλe = K0e/(1+λeᵀS0⁻¹e) | 무작위 2,000 PSD 사례 max scaled err 2.6e-15 | PASS |
| range column 불변 아님 | 변함 | 최대 상대 변화 0.59 → 02의 "다른 gain column도 바뀔 수 있다" 기술이 맞음 | PASS |
| mean-only 차이 −Kλ[:,r]Δμr | μs 동일 시 성립 | max err 7.2e-15 | PASS (전제는 B3) |
| g_P = 2[P−,−P+]ᵀ/(P++P−)² | FD 일치 | 3.2e-10 | PASS |
| 공통 복소 스칼라 불변 | 0 | 5.6e-17 | PASS |
| 원고 v4 비변경 | 동일 bytes | sha256 `72bb343e…9362` 동일 | PASS |

**설계 골격은 타당하다.** 12조건 고정, R4-B 유지, 기술 상태와 과학 판정 분리, GT의 offline 한정, fixed/self 분리, 사후 임계값 변경 금지가 모두 명시돼 있다. `REDESIGN_REQUIRED`에 해당하는 수학 오류나 train/test 누출은 찾지 못했다.

## 2. 반드시 고칠 것 (v0.2 freeze 전)

### A1. PB3의 CONST_TRAIN은 거리 "형태"와 분산 "수준"을 섞는다

PB3 질문은 "거리 조건의 고유 가치"다. 그런데 CONST_TRAIN은 **다른 두 route**의 lookup 거리분포로 λ를 평균하므로, 평가 route의 LOOKUP 평균 λ와 수준이 다르다. 그 결과 LOOKUP−CONST 차이에는 (i) 거리에 따른 형태와 (ii) 전체 down-weighting 수준 차이가 함께 들어간다.

기존 거리 bin 자료(`D3_EPS_BY_DISTANCE.csv`, GT 거리, ungated t≥30, B0)로 E[σ²_HAND]의 하한을 근사하면 다음과 같다. **결과(오차·RMSE)는 쓰지 않은 공변량 분포 계산**이다.

| route | 근사 mean σ² (하한) | CONST_TRAIN 근사 (다른 두 route 평균) | 비 |
|---|---:|---:|---:|
| R2-B | 0.0119 | 0.0103 | 0.87 |
| R4-B | 0.0080 | 0.0123 | **1.54** |
| R5-B | 0.0127 | 0.0100 | 0.79 |

특히 R4-B에서 CONST_TRAIN은 LOOKUP보다 약 1.5배 강하게 down-weight한다. R4-B는 분산만 추가한 모델이 유리했던 경로이므로, 이 차이만으로 결과 방향이 바뀔 수 있다.

**요구:** 정책 하나를 추가한다.

- `CONST_LEVEL_SELF`: 평가 route 자신의 B0 `BB_ORIG/self` lookup 위치(t≥30, 유한, gate 무관)에서 계산한 σ²_HAND 평균. GT·오차·RMSE는 쓰지 않는다. 배포 가능한 방법이 아니라 **통제군**으로 표기한다.
- 해석: LOOKUP vs CONST_LEVEL_SELF → 형태 효과, CONST_LEVEL_SELF vs CONST_TRAIN → 수준 효과, ZERO vs CONST_* → down-weighting 자체의 효과.
- 비용: +48 궤적, 프로토콜 총 192. RT 0.

### A2. σ_b 표의 in-sample 성격과 기존 D1 근거를 PB3·C-DIST에 반영

- `PROTOCOL_PB.md` L24: HAND 표와 창 파라미터는 mount 0 B0 경로 통계·시험에서 정했고, 선택 12조건(모두 mount 0)에서는 **in-sample**이다. 원고 v4 L90도 이를 적었다. 반면 01/02/04는 이 사실을 PB3 해석 규칙에 연결하지 않는다.
- 기존 D1(`D1_SIGMA_TABLES.csv`, `README_KO.md` §4): 잔차분산 E[ε_s²−R_ss|ρ]로 다시 적합한 σ_b는 0–6 m에서 floor 0.005이고, 10 m에서만 0.048–0.140이다. HAND 표는 이와 크게 다르다(0.011→0.24). fixed-gate에서 BB_ORIG 대비 H·XY 동시 개선은 HAND 19/24, ALLROUTES 9/24, LORO 8/24, NONE 8/24였다.
- 이 자료는 리뷰 §2.2("누락 잡음분산 복원이 아님")를 **이미 직접 지지한다.**

**요구:** (1) PB0 source map에 D1 산출물(blob)을 추가한다. (2) C-DIST 규칙에 다음을 넣는다: LOOKUP이 CONST들보다 우수해도 허용 문장은 "in-sample로 정한 거리 표의 형태가 이 세 경로에서 유효했다"까지다. "잔차분산의 거리 의존성을 반영했다"는 D1과 모순되므로 금지한다. (3) 05 §2.1에 D1 사실을 추가할지 제안자가 결정한다(아래 §4).

### A3. Range 관측의 tap 양자화 — 물리 설명에서 빠진 가장 큰 항목

- `observation.first_path_batch`: `range_m = index/(4N·Δf)·c`이고, Δf=1.95 MHz, N=257(BW 499.2 MHz), IFFT 4N이다. **native range 격자 간격은 14.955 cm**이고, 균일 양자화 RMS는 **4.32 cm**다.
- `source_model.py` docstring: 필터의 h_r은 "frozen continuous ranging surrogate d+B_OLD"다. 즉 h_r은 FFD 물리가 아니라 연속 거리+offset이고, z_r은 격자값이다.
- 원고 Table 1의 MB Range RMS(4.63–5.58 cm)는 이 양자화 floor 바로 위에 있다. BB(7.97–8.41 cm)에서 MB로의 감소가 **sub-tap leading-edge 정보의 회복**인지, 다른 성분인지 현재 설계로는 구분되지 않는다.

**요구 (모두 RT 0, GT는 offline):**

1. PB0: z_r이 실제로 kΔ 격자(+상수 offset)에 놓이는지 배열로 확인하고 Δ를 기록한다. 격자가 아니면(보간 detector 등) 이 항목을 갱신한다.
2. PB1: e_model,r을 양자화 성분(GT 거리의 fractional tap offset u=frac((d+B_OLD)/Δ))과 나머지로 분해해 보고한다. (μ_M,r−μ_B,r) 및 ε_M,r을 u에 대해 층화한다.
3. 02 PB1의 FD 검산에서 H_r은 연속 surrogate에 대해서만 수행한다고 명시한다. native r은 piecewise-constant이므로 FD 대상이 아니다.
4. 04 C-PHYS에 규칙을 추가한다. μ_M−μ_B가 u와 일관되게 정렬되면 "Range 평균 교체는 첫 경로 sub-tap 위치 정보를 일부 회복한다"를 후보 문장으로 허용한다. 정렬이 없으면 "조건부 평균 교체가 제곱오차를 줄였다"(현행)로 유지한다.

### A4. PB1의 H0/H1은 반증 기준이 없다

H1("일부 구간에서 … 설명된다")은 어떤 결과로도 기각되지 않는다. 다음 중 하나를 고른다.

- (권장) PB1을 **descriptive-only**로 선언하고 H0/H1을 삭제한다. 대신 고정 요약표를 미리 정의한다: route×ρ-bin×bearing-bin×branch별 n, mean·RMS(ε_s), mean(H_sψ), sign agreement rate = P[sign(K_ψs ε_s) = sign(Δ|ψ_err|)] (PB2 trace 필요), linearization error(A6).
- 또는 위 sign agreement rate에 대한 사전 수치 기준을 둔다(예: 세 route 모두 0.5보다 크고 route 내부 bin의 과반에서 일관).

### A5. PB3의 "명확한 per-case 이득"이 정의되지 않음

04 C-DIST의 "명확한 per-case 이득"이 수치로 정의돼 있지 않다. seed 0 결정론적 자료이므로 유의성 검정이 아니라 방향·크기 규칙이 필요하다. 기본안을 제안한다(제안자가 확정).

- `LOOKUP_SUPPORTED`: 12조건 중 ≥10에서 Heading RMSE가 LOOKUP < 비교 정책이고, 세 route 각각에서 4 bias 중 ≥3, 중앙 상대차 ≥1%.
- `MIXED`: 7–9/12, 또는 route 하나가 반대 방향.
- `NOT_SUPPORTED`: ≤6/12.
- XY·coverage·accepted count는 보조 판정으로 별도 기록한다. 같은 규칙을 LOOKUP vs CONST_TRAIN, LOOKUP vs CONST_LEVEL_SELF에 각각 적용한다.

### A6. 리뷰 §3.2의 선형화 연결이 명세에 없다

리뷰 §3.2는 e_s ≈ g_Pᵀ δP와 C_s(k,ℓ) ≈ g_P,kᵀ C_δP(k,ℓ) g_P,ℓ를 **이중 편파 물리에 가까운 설명 틀**로 제안했다. 02 PB1은 P±_Full·P±_Direct를 기록하지만, 이 선형화를 검증하는 단계는 없다. 05 §4도 정성적으로만 언급한다.

**요구:** PB1에 하위 분석을 추가한다.

- δP = P±_Full − P±_Direct, g_P는 Direct 작동점에서 계산.
- e_prop,s(exact)와 g_Pᵀ δP(linear)를 비교하고, |δP|/(P++P−)로 층화한 상대 오차를 보고한다.
- 선형 영역의 비율을 사전 정의한다(예: 상대 오차 ≤20%인 packet 비율). 이 비율이 낮으면 C_s 연결식은 원고에서 "국소 근사"로만 남긴다.
- PB4의 시간 상관은 선형 영역 packet에서 g_P 가중 δP 상관과 raw ε_s 상관을 함께 보고한다(선택이지만 권장).

## 3. 정밀화 항목 (minor)

| ID | 위치 | 내용 | 요구 |
|---|---|---|---|
| B1 | 01 §3, CONFIG `variance_lookup_timing` | 코드의 조회 상태는 "직전 step 종료 상태"다. 갱신됐으면 posterior이고, 미수용·비유한 packet이면 전파된 prior다. `exp_pb.py` docstring L21과 `PROTOCOL_PB.md` L24는 "predicted state"라고 적어 코드와 다르다. | 문구 정정. 역사 문서와 코드의 불일치를 SOURCE_LOCK에 기록. RA4에는 이미 `*_VAR_PRIOR` arm이 있다: 12조건 self에서 PRIOR−LEGACY는 Heading +0.0010~+0.0094 deg, XY +0.000~+0.104 cm다. 조회 시점이 결과를 좌우하지 않는다는 기존 근거로 인용 가능 |
| B2 | 02 PB2 | shadow reference가 BB_ORIG/self·MB_VAR/self뿐이다. R4 질문(분산만 vs 결합)과 R2 질문(평균만의 악화)에는 BB_VAR/self·MB_ORIG/self prior가 직접 관련된다 | reference 4개 × shadow arm 4개로 확장. 추가 비용은 trace 재생뿐 |
| B3 | 02 PB2 Δx_mean | 식은 μ_M,s=μ_B,s일 때만 성립한다. D3에서 s 잔차 통계는 BB/MB 동일(6자리)이지만 배열 동일성은 미확인 | PB0에서 `μM[:,1]==μB[:,1]` exact 검사. 불일치하면 −KλΔμ 전체 벡터식 사용 |
| B4 | 02 PB4 / CONFIG | 첫 bin [0,0.3) s·[0,0.06) m·[0,2.5)°가 lag 0 자기쌍을 포함할 수 있다. 02 본문은 lag 중심값, CONFIG는 edge로 표기가 다르다 | k≠ℓ, lag>0 명시. 02와 CONFIG 표기 통일 |
| B5 | 02 PB0/PB2 | BASE mask는 gyro 수준마다 다르다(`exp_pb.py` L7–10: BASE 필터를 수준별로 재실행) | "fixed"는 bias별 BASE mask임을 명시. bias 간 mask 공유 가정 금지 |
| B6 | CONFIG `use_GT_at_filter_inference` | 초기 상태는 GT pose + seed-0 N(0, diag(0.1 m, 0.1 m, 5°))이다(`exp_pb.py` L69–70) | 초기화에서 쓰는 GT를 명시적 예외로 기록 |
| B7 | SOURCE_REFERENCE_LOCK `external_archived_evidence` | RA4 artifact `12890904334`는 **2026-11-28T10:58:19Z 만료**다(GitHub API `expires_at`). 문서는 보존기간 위험만 언급하고 날짜는 없다 | 이 감사 브랜치에 byte-identical 사본을 보존했다(`preserved_inputs/`, SHA256 `bb19a4f4…b7c0`, git blob `482deda8`). 제안자는 LOCK에서 이 경로를 대체 출처로 참조 가능 |
| B8 | reference_review/recompute_review.py | 실행 시 자기 `evidence/`를 덮어쓰고, `/mnt/data/…zip`이 있으면 그것을 우선 읽는다 | 03에 "사본에서만 실행" 명시. 이 감사에서는 격리 사본에서 byte-identical 재현을 확인함 |
| B9 | 05 §6 | "개선이 0.74%인 R4-B"는 B0 값이다. 네 bias 범위는 0.74–2.54%이고, XY는 10.5–11.8% 악화한다 | bias와 범위 명시 |

## 4. 원고 조정 계획(05)에 대한 의견 — 리뷰 §3 대비

| 리뷰 §3 축 | 05 반영 | 판정 | 추가 권고 |
|---|---|---|---|
| 3.1 상태 의존 물리 관측, H 구조, b_g 간접 관측 | §1, §3에 반영 | 충분 | — |
| 3.2 공통 스칼라 불변·차등 왜곡 | §4 문단 반영 | 부분 | A6 결과 전에는 선형화식을 "국소 근사"로 표기. 결과 후 Figure A에 linear/exact 비교 추가 여부 결정 |
| 3.3 gain 축소 ≠ 정보 생성 | §5에 반영 | 충분 | — |
| (리뷰에 없음) Range tap 양자화 | 없음 | **누락** | §1.2에 지금 쓸 수 있는 사실: 14.955 cm 격자, 4.32 cm 균일 양자화 RMS, MB Range RMS가 그 근처라는 관계. 해석(sub-tap 회복)은 A3 결과 후 |
| (리뷰 §2.2) σ_b ≠ 누락 잡음분산 | §4 금지문장으로 반영 | 부분 | D1 재적합 결과(0–6 m floor)를 §2.1 근거로 인용할지 결정. 원고 v4의 in-sample 문장 유지 |
| 거리 lookup의 가치 | 신설 §3.3 | 설계 수정 필요 | A1 CONST_LEVEL_SELF 포함, A5 판정 규칙 적용 |

05의 "결과 전 금지/결과 후 허용" 구조와 v4 read-only 원칙은 적절하다.

## 5. 과학적 판단

- **Supported exactly (기존 자료 범위):** 선택 12조건 self-gate에서 결합 12/12 Heading·8/12 XY 개선, 분산만도 12/12·8/12, R2·R5 8조건에서 결합이 두 단독보다 우수, R4 4조건에서 분산만이 결합보다 우수. 단일 corridor·seed 0·in-sample σ 표 범위다.
- **Rejected exactly:** 없음(새 실험 없음).
- **Mixed/unresolved:** 거리 형태의 고유 기여(A1·A2), Range 평균 교체의 물리적 의미(A3), 편파 잔차의 선형 전달(A6).
- **Alternative explanations to keep open:** (i) LOOKUP 이득이 형태가 아니라 수준에서 나옴, (ii) μ_M 이득이 sub-tap 양자화 회복, (iii) R4-B의 결합 불리가 Range 평균 교체 후 위치–Heading 결합의 prior 변화에서 나옴.
- **Inadmissible extrapolations:** 거리 표가 잔차분산의 물리적 거리 의존성이라는 주장, 12조건을 12개 독립 환경으로 보는 해석, PB 결과를 prospective validation으로 부르는 것.

## 6. 판정

**`REVISION_REQUIRED`**

- 근거: 수학·누출 결함은 없다. 그러나 PB3 비교군이 형태와 수준을 분리하지 못하고(A1), in-sample 표와 기존 D1 근거가 claim 규칙에 빠져 있으며(A2), Range 물리의 핵심 성분인 양자화가 설계에 없다(A3). PB1·PB3에는 사전 판정 기준이 없다(A4·A5). 리뷰가 제안한 선형화 연결도 검증 단계가 없다(A6).
- 차단 결함과 담당: A1–A6 → PROPOSER (v0.2 freeze candidate를 **새 파일**로 제출, v0.1 보존). B1–B9 → PROPOSER 문구 수정. B7 보존은 이 감사에서 완료.
- **허용 범위:** DRAFT 상태에서 PB0 `PREFLIGHT_ONLY`(source inventory, SHA materialization, z_r 격자 검사, μ_s 동일성 검사, 수학 음성 시험)는 위 수정과 병행할 수 있다. PB1–PB5의 과학 계산은 v0.2 candidate에 대한 재판정 전에는 하지 않는다.
- Claim-register 승격: 없음.
- 서명: AUDITOR = Claude (claude-opus-5-5), session `session_01X1n7vKETgA3nteaHg8zEZc`, 2026-11-02 KST. `DISTINCT_SESSION_DESIGN_REVIEW`. 구현자 서명이나 FROZEN 서명이 아니다.

## 7. 산출물

| 파일 | 내용 |
|---|---|
| `AUDIT_VERDICT.json` | 기계 판독용 판정·SHA·요구사항 |
| `calc/ind_recalc.py`, `calc/RECALC_12_OUTPUT.txt` | RA4에서 12조건 독립 재집계 |
| `calc/d2_transcription_check.py`, `calc/D2_TRANSCRIPTION_CHECK.txt` | D2 전사 48값 대조 |
| `calc/math_checks.py`, `calc/MATH_CHECKS.json` | gain 축소·mean shift·g_P·불변성·양자화 간격 |
| `preserved_inputs/RA4_336_ARMS.csv` | 만료 전 보존한 byte-identical 사본 |

재현: `python3 -I calc/ind_recalc.py preserved_inputs/RA4_336_ARMS.csv ../PHYSICS_BRIDGE_PROPOSER_20261101/reference_review/tables/SELECTED_12_CONDITIONS_RECHECK.csv`
