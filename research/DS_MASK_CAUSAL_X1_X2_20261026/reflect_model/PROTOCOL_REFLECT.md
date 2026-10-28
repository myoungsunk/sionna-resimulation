# 실험 프로토콜: 반사 포함 편파 관측 모델 (V0–V3)

- 기준 commit: `9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13` (branch `research/ds-x1-x2-results-20261026`)
- 제안 산출 폴더: `research/DS_MASK_CAUSAL_X1_X2_20261026/reflect_model/`
- 코드: `refl_model.py`(모델), `common.py`(경로·필터 원형·manifest), `exp_v01.py`(V0·V1), `exp_v2.py`(V2), `exp_v3.py`(V3), `fetch_inputs.sh`(입력), workflow `.github/workflows/reflect-model-v0-v3.yml`
- 상태: 코드 작성 완료, **한 번도 실행하지 않음**. V0가 첫 실행이다.

## 1. 목적과 가설

**배경 (확인된 사실, 9bcd5da 기준 재계산).**
- 필터 입력 편파 s는 잡음 없는 전체 채널(H)의 first-path 값과 같다(최대 차이 2e-16).
- 필터의 편파 모델 SourceFFD를 GT 자세에 넣은 값은 LOS 단독 채널(H_LoS)의 s와 같다(7e-6).
- 따라서 편파 오차는 100% 정반사 다중경로다. 이 오차의 느린 성분이 Heading 오차의 주원천이다(편파 오차 0 oracle에서 Heading RMSE 0.7–1.6° → 0.1–0.4°).

**가설.**
- **H-R1:** 측정을 만든 장면(평면 6개, ITU 재질, 정반사 ≤ 3회)과 같은 물리로 편파 관측 모델을 확장하면, GT 자세에서 측정 s를 재현한다.
- **H-R2:** 그 모델을 필터에 넣으면 Heading 오차가 편파 오차 0 oracle 쪽으로 줄고, RF range 평균 보정(Δs 보정)이 BASE보다 이득이 된다.
- **H-R3:** 모델은 자세의 함수이므로 경로와 무관하게 작동한다. 다만 장면 기술 오차에 대한 민감도는 따로 측정한다(V3).

## 2. 모델 정의 (`refl_model.ReflectiveFFD`)

**채널 (생성기 계약과 같은 형태).** `rf_b_apply.py` / `pattern_apply.channel_from_jones`와 같은 식이다.

```
H_port(f) = Σ_paths  F_rx,port(f, 도착 방향)ᵀ · J_path(f) · F_tx(f, 출발 방향) · exp(−j2π f τ_path)
J_path(f) = λ/(4π L) · M_k(f) ··· M_1(f)        (LOS: M = I, SourceFFD와 같음)
M = r_TE(f) s sᵀ + r_TM(f) p_out p_inᵀ,   s = unit(k_in × n),  p_in = s × k_in,  p_out = s × k_out
```

- **안테나 패턴:** F는 SourceFFD의 `_cartesian_field`(polar cap 처리 포함)로 얻은 world 좌표 전계 벡터다. 앵커는 bank 0(+45° LP)을 ANCHOR_ROTATION으로 돌려 쓰고, 태그는 bank 0과 1을 yaw = ψ + mount로 돌려 쓴다.
- **경로:** 평면 6개에 대한 거울상(image) 방법으로 찾는다. 같은 평면 연속 반사는 제외하고, 반사점이 평면 직사각형 안에 있어야 유효하다. 상자가 볼록하므로 가림 검사는 필요 없다.
- **Fresnel 계수:** 공기에서 매질로의 계면 계수를 쓴다. 매질 유전율은 η = ε_r − jσ/(2πf ε₀)이다. 부호 규약은 수직 입사에서 r_TM = −r_TE가 되도록 잡았다.
- **재질 모델:** `slab`(두께 d의 단일층, R = r(1 − e^{−j2q})/(1 − r²e^{−j2q}), q = 2πfd/c·√(η − sin²θ)) 또는 `halfspace`.
- **재질 상수 (ITU-R P.2040 표 3, Sionna ITU 재질):**

  | 재질 | ε_r′ = a f^b | σ = c f^d (f in GHz) |
  |---|---|---|
  | concrete | a 5.24, b 0 | c 0.0462, d 0.7822 |
  | plasterboard | a 2.73, b 0 | c 0.0085, d 0.9395 |

- **장면:** 길이 20 m(x 0–20), 폭 2.4 m(y ±1.2), 높이 2.7 m. 바닥·천장·양 끝벽은 concrete 0.2 m, 측벽은 plasterboard 12.5 mm. 앵커 z = 2.65 m, 태그 z = 0.45 m.
- **투과:** 투과된 광선은 상자 밖으로 나가 수신되지 않으므로 모델링하지 않는다.
- **관측:** 측정과 같은 처리를 쓴다. Hann window, 4배 zero-pad IFFT, 더 센 포트 peak의 30%를 처음 넘는 tap에서 s를 구한다.
- **range:** `geometric`(원래 계약: 3D 거리 − 0.5316 m) 또는 `fp`(모델 CIR의 first-path range).
- **Jacobian:** s 행은 x, y, ψ에 대한 중앙차분이다(2 mm, 0.1°). 이때 first-path tap은 기준 상태의 tap으로 고정한다. SourceFFD의 해석적 Jacobian도 고정 tap에서 미분하는 것과 같은 규약이다. range 행은 원래와 같은 해석식이다.

## 3. 단계와 판정

### V0 단위 검사 (`exp_v01.py --stage V0`, 데이터는 bank와 LOS 채널만)

| 검사 | 통과 기준 |
|---|---|
| Fresnel 극한: PEC(η → ∞)에서 r_TE = −1, r_TM = +1 | 오차 1e-5 |
| 수직 입사에서 r_TM = −r_TE (규약 확인) | 1e-12 |
| 손실 매질에서 \|r\| ≤ 1 | 위반 없음 |
| 두껍고 손실 큰 slab이 halfspace와 같음 | 1e-6 |
| 거울상 경로의 반사 법칙, 경로 길이 = 구간 길이 합 | 1e-9 |
| depth 0 모델 = SourceFFD (관측값, tap, Jacobian), mount 0°/45° | 관측값 1e-9, tap 동일, Jacobian 상대오차 중앙값 < 1% |
| depth 0 모델 = 저장된 H_LoS 관측값 (7경로 전 packet) | s 1e-4, tap 일치 > 99.9% |

하나라도 실패하면 중단한다. 결과는 `V0_CHECKS.csv`와 `V0_GATE.json`.

### V1 모델 검증 (`exp_v01.py --stage V1`, 필터 없음)

- **입력:** 7경로의 B0 control trace packet 자세(GT)와 그 pose_id의 저장 채널. 먼저 전체 채널 관측값이 필터 입력과 1e-12 이내로 같은지 확인한다.
- **변형:** 반사 차수 1, 2, 3 × 재질 모델 slab, halfspace. 기준선은 depth 0(LOS)이다.
- **지표** (거리 구간 0–1.5 / 1.5–3 / 3–6 / ≥ 6 m, 수용 packet):
  - s 잔차(측정 − 모델)의 RMS와 평균
  - 느린 성분 RMS (25 packet = 5 s 이동평균)
  - first-path tap 일치율
  - FP range 잔차 RMS
  - 채널 NMSE (raw / 복소 스칼라 하나로 정렬한 값)
  - 자세당 유효 경로 수
- **판정 (사전 고정).** 주 변형은 depth 3, slab이다. 각 경로의 3 m 밖 구간에서 다음을 모두 만족하면 **PASS**다.
  - s 잔차 RMS ≤ 0.02 또는 LOS 모델 대비 90% 이상 감소
  - 느린 성분 RMS ≤ 0.01
  - tap 일치 ≥ 95%

  허용되는 대체는 slab → halfspace 하나뿐이다. 둘 다 PASS가 아니어도 모든 경로에서 70% 이상 줄면 **APPROXIMATE**로 V2를 진행하고, 결과에 근사 모델임을 표시한다. 그 밖은 **FAIL**이며 V2를 실행하지 않는다.
- **산출:** `V1_OBSERVABLES.csv`, `V1_RS_BY_BIN.csv`(주 변형의 경로·거리별 잔차 분산, V2의 LORO R_s 입력), `V1_SERIES.npz`, `V1_DECISION.json`.

### V2 필터 replay (`exp_v2.py`)

- **고정 조건:** 원래 E1과 같다. controls(저장된 OFF_BB arm에서 정확히 복원), z, μ_r, mask A_B, 2×2 joint 갱신, Joseph 공분산. 바뀌는 것은 편파 관측 모델뿐이다(*_RS arm은 R_ss도).
- **parity gate:** 조건마다 LOS_BB와 LOS_MB가 OFF_BB, OFF_MB 상태를 1e-10 이내로 재현해야 그 조건의 나머지 arm을 채점한다.
- **arm:**

  | arm | 편파 관측 | μ_s | R | 목적 |
  |---|---|---|---|---|
  | LOS_BB / LOS_MB | SourceFFD | 저장값 | 저장값 | parity, 기준선 |
  | REF_BB / REF_MB | 반사 모델 | 0 | 저장값 | 주 판정 |
  | REF_BB_MUS / REF_MB_MUS | 반사 모델 | 저장값 | 저장값 | 학습 평균의 이중 계산 여부 |
  | REF_BB_RS / REF_MB_RS | 반사 모델 | 0 | R_ss = 다른 경로 V1 잔차 평균제곱(추정 거리 구간별, 하한 0.01²) | R 재설정 효과 |
  | ORPOL_BB / ORPOL_MB | SourceFFD, z_s := LOS 모델(GT) + μ_s | 저장값 | 저장값 | 편파 오차 0 oracle 기준 |
  | REF_FPR (`--fp-range`) | 반사 모델 s + 모델 FP range | 0 | 저장값 | 탐색: range도 모델 기반 (μ_r = 0) |

- **조건:** 7경로 × B0/L2 = 14조건. 주 분석 경로는 R2_aA_m45, R4_aA_m0, R4_aB_m0이고, B0와 L2는 쌍으로 보고하며 독립 표본으로 세지 않는다.
- **지표:**
  - t ≥ 30 s: Heading RMSE, signed bias, XY RMSE, 앵커 거리 RMSE(3D)
  - 편파 NIS 평균
  - 첫 통과 후 60 s: Heading 평균, GT 접선 오차 평균, XY RMSE
- **판정 (사전 고정, bias별):**
  - **D1:** REF가 LOS보다 Heading RMSE를 BASE와 Δs 보정 모두에서 낮춘 경로가 7개 중 5개 이상.
  - **D2:** 주 3경로 중 2개 이상에서 REF_MB의 Heading RMSE와 XY RMSE가 모두 REF_BB 이하. RF 보정이 이득으로 바뀌었는지 보는 판정이다.
  - **D3:** 어떤 경로에서도 REF의 Heading RMSE가 LOS보다 10% 넘게 나빠지지 않음.
  - 보조: REF와 ORPOL의 거리(상한 대비 몇 %를 회복했는가), MUS와 RS arm의 차이.
- **산출:** `V2_SCORES.csv`, `V2_RESULT.json`(parity, LORO R_s 표, 판정).

### V3 장면 기술 오차에 대한 강건성 (`exp_v3.py`, 필터 없음)

V1에서 선택된 변형을 기준으로 장면 기술을 일부러 틀리게 해서, 측정 재현이 얼마나 남는지 본다.
- **교란:** ε_r ×0.8 / ×1.2, σ ×0.5 / ×2, 바닥 +5 cm, 측벽 ±5 cm, 천장 제외, 끝벽 제외, 바닥·측벽만, 반사 1회만.
- **지표:** 3 m 밖 s 잔차 RMS, 느린 성분 RMS, tap 일치, LOS 대비 감소율 유지 비율.
- **판정 없음 (기술값).** 실제 환경에서 필요한 장면 정확도를 가늠하는 용도다.
- **산출:** `V3_ROBUSTNESS.csv`.

## 4. 실행 순서

**GitHub Actions (권장).** workflow `.github/workflows/reflect-model-v0-v3.yml`은 코드 푸시만으로는 실행되지 않는다. 이 폴더에 `RUN_REQUEST.json`을 커밋하거나 수정해서 브랜치 `research/ds-x1-x2-results-20261026`에 푸시하면 실행된다. 형식은 `RUN_REQUEST.example.json`을 따른다.

1. 첫 실행은 `"stages": ["V0", "V1"]`로 한다.
2. V1이 PASS 또는 APPROXIMATE이면 `"stages": ["V0", "V1", "V2", "V3"]`로 바꿔 다시 푸시한다. V2는 V1 결과를 같은 run 안에서 다시 만들어 쓴다.

job 구성:
- `inputs`: fetch_inputs.sh로 입력을 받고 해시를 기록해 artifact 하나로 올린다. LFS 대역폭은 run당 한 번만 쓴다.
- `v01`: V0 → V1
- `v2`: 경로 7개 matrix로, 각 job이 B0·L2를 병렬 2개로 돌린다.
- `v2-aggregate`: shard를 합치고 D1–D3를 판정한다.
- `v3`

모든 결과는 artifact(`reflect-*-<run_id>`, 보존 30일)로 남는다. 저장소 커밋은 하지 않는다.

**로컬.**

```bash
bash fetch_inputs.sh                       # 입력과 해시 기록 (out/INPUT_LOCK.sha256)
python exp_v01.py --stage V0               # 실패 시 중단
python exp_v01.py --stage V1 --cases all --variants all
python exp_v2.py --cases all --biases B0,L2 --workers 4        # V1이 PASS/APPROXIMATE일 때만
python exp_v3.py --cases primary
```

`REFLECT_ROOT` 환경변수로 작업 폴더를 바꿀 수 있다. 기본값은 스크립트 폴더다.

**산출 manifest.** 단계마다 `MANIFEST_<stage>.json`을 쓴다(AGENTS.md 요구사항). 내용은 설정 스냅샷과 해시, 입력 해시 목록, 코드 해시, 출력 해시, 시각, 명령행, GITHUB_SHA·run id다.

## 5. 알려진 위험과 확인할 것

1. **slab 규약:** Sionna RT 2.0.1이 얇은 plasterboard 벽(12.5 mm)의 반사를 slab으로 계산하는지 halfspace로 계산하는지 문서로 확인하지 못했다. 그래서 두 모델을 모두 V1에 넣었다. 측벽 반사 계수는 이 선택에 크게 좌우된다.
2. **TM 부호 규약:** V0에서 수직 입사로 확인하지만, 비스듬한 입사에서 Sionna와 같은 결과가 나오는지는 V1의 채널 NMSE로만 검증된다. NMSE가 나쁘고 tap은 맞는 경우 이 규약을 먼저 의심한다.
3. **위상 기준:** 경로마다 절대 지연 τ = L/c의 위상을 쓴다. 생성기도 Sionna의 절대 τ를 쓰므로 raw NMSE가 같은 기준이어야 한다. raw NMSE와 정렬 NMSE의 차이가 크면 공통 위상 기준이 다르다는 뜻이다(이 경우 s와 tap에는 영향이 없다).
4. **주파수 보간:** 생성기는 17개 주파수 노드에서 Jones 행렬을 3차 보간했다(상대 오차 5.4e-7). 모델은 257개 주파수를 모두 직접 계산하므로 이 차이는 무시할 수준이다.
5. **수치 Jacobian과 tap 경계:** tap을 고정해 미분하므로 tap 경계 근처에서는 실제 관측의 불연속을 반영하지 않는다. 원래 모델과 같은 성질이다.
6. **실행 시간:** REF 관측은 packet마다 상태 7개(기준 1 + 차분 6)를 한 번의 벡터화 호출로 계산하고, 경로 후보는 186개다. 측정 전이라 시간은 추정치뿐이다. job 시간 제한은 v01 180분, v2 360분이다.
7. **R_s 하한:** 모델이 정확하면 잔차가 거의 0이 되어 R_ss가 지나치게 작아질 수 있다. 하한 0.01²를 두고, 수치 Jacobian의 차분 오차보다 작아지지 않게 한다.
8. **일반화:** 장면이 하나이고 RF 잡음이 없다. V2가 통과해도 실제 환경에서의 성능은 V3의 민감도와 실측으로 따로 확인해야 한다.
