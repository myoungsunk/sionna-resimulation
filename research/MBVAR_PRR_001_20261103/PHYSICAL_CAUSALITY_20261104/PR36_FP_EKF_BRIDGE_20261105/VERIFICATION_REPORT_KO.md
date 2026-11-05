# PR36 신규 RF — FP 선택 오류와 EKF 과신 메커니즘 검증

**2026-11-05 · EXPLORATORY / NONINDEPENDENT · 신규 RT=0, 새로운 C2 재귀 실행=0**

## 0. 근거·출처

- 원본: [Actions #41958274374](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41958274374), [Release pr36-rt-41958274374-1](https://github.com/myoungsunk/sionna-resimulation/releases/tag/pr36-rt-41958274374-1) (838,256,350 B, `sha256:a5ecbbcfde9a9d715a669d3b61afbeafc4965c90cc26b116a0cd61f21292fa52`). 등록된 400개 중 새 계산된 308키만 이 독립 FP 재분석에 포함; 92개 재사용 키 제외.
- 신규 키의 네 Actions shard tar 내 원본 H, `FIRST_PATH`, per-bin complex ray `a/tau/objects/valid`, 257-bin freq, object_map 사용. 구체적인 네 shard SHA는 `SUMMARY.json`의 `sha256_sources`에서 확인.
- 검출기 원전: `src/qclean_uwb/drivesim/observation.py` (`Hann(257) → 1028-point IFFT ×257 → 강한 포트 진폭 peak의 30% leading-edge → signed s`), 포트는 +45/−45, TX0. 직접파 LoS는 탐색기 입력이 아닌 **평가 기준**.
- EKF 기존 감사 실험: [C1a same prior](https://github.com/myoungsunk/sionna-resimulation/tree/experiment/predicted-fp-duallp-pilot-20261105/research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/C1/C1A_001), [C2 fixed/own natural recursion](https://github.com/myoungsunk/sionna-resimulation/tree/experiment/predicted-fp-duallp-pilot-20261105/research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/C2/C2_001). C2 코드·집계·독립 수치 및 게시 감사 기존 **ACCEPT**; 이번 신규 SHARD에 대해 C2를 새로 돌린 것은 아님.

## 1. 독립 검출기 전체 154 pose쌍 재생

- 308/308 새 키 읽기 = R4 118 Full/LoS 쌍, R5 36쌍; R2 신규 키 없음. 누락·짝 불일치 0.
- 저장된 `FIRST_PATH` 대비 signed s 재계산 최대 차이 `6.071532165918825e-16`; index 일치 전수. 보관된 기존 H 대비 상대 L2 차이의 최댓값 Full `1.0502788681270522e-4`, Native-LoS `1.6511698136600491e-7` (source의 허용치 Full ≤1e-3, LoS ≤1e-5 통과).
- FP tap 불일치 Full/LoS: R4 **56/118**, R5 **13/36**, 전체 **69/154**. 이는 직접파 탐색 참조 기준 불일치이며 진짜 첫 도달 경로의 독립 GT 오분류율과 동일하지 않다.
- **분해 항등식:** `s_F(fp_F)-s_L(fp_L) = [s_F(fp_L)-s_L(fp_L)] + [s_F(fp_F)-s_F(fp_L)]`. 첫째는 동일 tap의 Full/LoS 복소 간섭 효과, 둘째는 Full에서 검출기를 바꿨을 때의 편파 선택 효과다. 두 항은 절댓값이 가산되거나 통계적으로 독립적이지 않다.

| 경로 | 쌍 | tap 불일치 | 평균 |전체 Δs| | 평균 |동일 tap| | 평균 |FP 선택| | tap 일치 중 |Δs|>0.05 |
|---|---:|---:|---:|---:|---:|---:|
| R4 | 118 | 56 | 0.141475 | 0.115779 | 0.042475 | 34 |
| R5 | 36 | 13 | 0.117191 | 0.055131 | 0.066296 | 6 |

(원본 per-pose 전수 결과: `FP_154_POSES.csv`; 원본 subset 사후 선택 및 동일 환경/시드 공유.)

## 2. 구체적 RF 반례와 인과 후보

| 신규 원시 사례 | tap Full/LoS | Δr=m | Δs 전체 | 동일 tap | 선택 효과 |
|---|---|---:|---:|---:|---:|
| R4 pose0 | 58/57 | +0.149552 | +0.182070 | +0.208148 | −0.026078 |
| R4 pose497 | 21/21 | 0 | −0.054547 | −0.054547 | 0 |
| R5 pose674 | 13/13 | 0 | +0.006383 | +0.006383 | 0 |
| **R5 pose402 (80.4s)** | **50/47** | **+0.448657** | **+0.494405** | **+0.076085** | **+0.418320** |

R5 `hot79` 창 79–81s pose395–405 중 이번 신규 셋에 들어온 **10쌍**: 7쌍 tap 불일치; 평균 |Δs| `0.26232`, 평균 |선택 효과| `0.16663`, 평균 |동일 tap| `0.09569`; FP 선택 오류가 크지만 동일 tap 오염도 남는다. pose401은 재사용 키로 별도 보존되어 본 10쌍 계산에 넣지 않았다.

직접 원시 ray들의 `(a,tau,f,objects)`를 복소 주파수 응답으로 재합성해 **첫 반사면이 같은 경로군을 일괄 삭제**하는 사후 대조도 구현했다. 원시 합성 H 폐합 상대 L2 오차 R4 pose497 `1.898e-7`, R5 pose402 `1.716e-7`. source와 같은 float32/complex64 위상 연산을 사용했다. 복소장의 제곱으로 전력을 계산하므로 경로별 전력을 산술합하지 않았다.

- **R4 pose497:** 첫 반사면이 `ceiling`인 ray들을 삭제했더니 FP21 유지, signed Δs가 `−0.054547→+0.002038`로 작아졌다. 단일 tap 내 반사파 간섭의 증거.
- **R5 pose402:** 원래 FP50/LoS47, Δs `+0.494405`; 첫 반사면이 `wall_y_pos`인 ray를 삭제하고 재검출하니 tap이 **47로 돌아왔고** Δs `+0.051440`로 감소. `wall_y_neg` 삭제에서도 tap47, Δs `+0.082526`; 반면 `ceiling` 삭제는 tap50 유지, Δs `+0.414667`. `floor`, `end_x_min/max`를 포함한 6면 전체 결과를 JSON에 공개했다.
- **한계:** 이는 저장된 고정 ray의 복소장의 수학적 삭제다. 실제 벽/천장을 제거한 Sionna 재광선추적, 다중반사 경로의 재구성, 물리 환경 일반화와 동치가 아니다. 설명용 선택 사례이며 반사면별 통계 유의성을 주장하지 않는다.

## 3. EKF: 증명된 부분과 아직 아닌 부분 분리

기존 SourceFFD/MB_VAR 4상태 `[x,y,yaw,b_g]`, `z=[r,s]`의 원래 필터:

```
Pminus = F Pplus_prev F^T + G Q G^T
nu = z - h(xminus) - mu
S = H Pminus H^T + R
K = Pminus H^T S^{-1}
xplus = xminus + K nu  (yaw wrap)
Pplus = (I-KH)Pminus(I-KH)^T + K R K^T
NEES = e^T (Pplus)^{-1} e
```

**고정 prior/H/R/수용 gate/K인 C1a 한 시점에서** Full과 LoS의 거리/편파 교체에 따른 Heading 차이는 `Δψ = K_{ψ,r} Δr + K_{ψ,s} Δs`. 같은 gate라면 관측 `z`만 바꿔도 계산된 P는 **변하지 않는다**. 오염으로 상태오차가 커졌다고 그 시점 P 자체가 커진다고 말하면 잘못이다. 실제 편파 오염의 영향을 수치 Heading으로 표현하려면 해당 pose에 기록된 `K_{ψ,r},K_{ψ,s}`가 필요하다. 이번 신규 RT raw shard에는 K가 없다.

기존 **C1a 원본 실험**에서는 기존 Full prior 125,440개에 대해 4-arm 총501,760 posterior행 재생, 4×4 P/Joseph/K/개입 항등식의 최대 재계산 오차 약 `3.55e-15`로 수치검증됐다. 이 결과는 동일-K 1스텝 메커니즘이지 자연 재귀 오차 확대의 검증이 아니다.

기존 **C2 원본 자연 재귀 개입**에서는 120개 원본조건×11창 일부 = 440창 조건, 2,640분기 궤적, 1,528,320 posterior행에 대한 독립 수치감사 ACCEPT (감사 기록은 C2 `audit/C2_RESULT_AUDIT_RESULT.json`). 같은 물리 원본 복도의 Full vs Native-LoS 창 한정 교체 후 이전 state/P/H/K가 매 프레임 달라지도록 경로 끝까지 재귀했다. 아래 값은 `t≥30s` 20개 공개 seed에서의 **각 seed Full 대비 차이의 중앙값**. 성능 개선을 뜻하지 않으며 seed 20개는 독립 환경이 아니다.

| 기존 C2 실험, 원래 MB_VAR, own gate, B0 | Heading RMSE 차이 | XY RMSE 차이 | NEES3 평균 차이 | Pψ 평균 차이(rad²) | 해석 |
|---|---:|---:|---:|---:|---|
| R4 hot33, 편파만 FL (33–35.2s) | −0.294993° | +0.012572m | −1.023146 | −4.961e-7 | Heading은 좋아지나 위치는 악화 |
| **R5 hot79, 거리+편파 LL (79–81s)** | **+0.106024°** | **+0.011167m** | **+0.181771** | **−1.737e-7** | **오차와 NEES는 증가, Pψ는 감소** |

R5 hot79 기존 C2의 **LL/own**은 Full→Native-LoS 관측교체 효과이지, FP 선택만 선택적으로 교정한 효과가 아니다. 따라서 새 원시 RF에서 R5 pose402의 선택 효과 `+0.418320`을 관찰했다고 해서 C2의 Heading `+0.106°`를 **FP 오검출만의 인과 기여**라고 단정하면 안 된다. 79–81초 시간창/원래 archived composite H는 일치하지만 이번 새로운 per-ray 계수와 원래 C2 개별 시점 K/뉴·mask를 직접 맞춰 산출한 수치는 아직 없다.

기존 C2의 결과는 **작아진 명목 공분산에도 실제 Heading·XY 오차와 NEES가 동시에 커질 수 있음**을 직접 보여주므로 *재귀 과신 현상*의 실증에 해당한다. 구체적인 반사면과 FP 선택 개입으로 변화한 이력의 인과 분해, 다른 모델의 오차정의·칼만이득 변화가 얼마나 기여했는지는 별도 짝지어진 packet별 실험이 필요하다.

## 4. 판정·다음 최소 계산

- **PASS:** 신규 원시 RF 308키→154쌍 FP/편파 수치재현·전체 분해, 2개 사례의 per-ray first-surface 제거 대조, 신규 RF H와 원래 archived H 근접 검증.
- **ALREADY VERIFIED IN ORIGINAL C2:** Full/LoS 관측 개입이 본래 4상태 재귀 EKF에서 추정오차·NEES·명목 공분산을 다르게 전파한다는 사례 및 반례; 독립 수치감사 ACCEPT.
- **NOT YET CLAIMED:** 새 per-ray 반사면/FP-only 선택을 **동일 prior/K**에 꽂아 해당 시점 Heading 수치를 재계산한 *이번 연구의 통합 패킷별* 검증. 원본 C1/C2 LFS trace에서 K,H,S,P,Q,gate와 마스킹된 관측 z를 pose-id로 join한 후 새 `z_F(tap=Full)`과 `z_F(tap=LoS)`를 사용하는 세 arm `(raw, FP-fixed, direct-only)`를 구현·검증해야 한다. C1 P 동결·C2 분기 재귀를 구별하고 R4/R5 반례도 함께 검증한다.
- 신규 Sionna RT·신규 모델 학습·전체 400키 재생성은 불필요. 온라인 채택/실시간 guard GO는 없음.