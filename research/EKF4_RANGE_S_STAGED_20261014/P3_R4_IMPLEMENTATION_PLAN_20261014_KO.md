# P3 구현 사양서 — 동결 RF 입력 적격성·EKF4 관측 어댑터 (2026-10-14)

> **단계:** P3만. P4(one-step 추정 성능), P5(비선형 위치적분 posterior), P6(실제 RF 재귀)는 이 문서의 실행 범위가 아니다.  
> **기준 P2:** `research/ekf4-r4-full-p2-audited-20261014`, commit `85a5d46fcd0cfe41ed46d6e45a19d1d20dd0db8a`. P2 Actions [38568036257](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38568036257): 600/600 paired, 2400/2400 model run, invalid 0. 합성 P2 성공을 실제 RF 정확도로 승격하지 않는다.  
> **본 커밋은 계획 문서 전용:** 실행 코드 변경 없음, 실험 실행 없음, scientific_PASS=false.

## 1. 기존 자산 및 재사용 결론

1. EKF3 P0 동결 `research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json`, Git blob `8bf216cf606f5e3c11139cacbf42f15a44556feb`. 검증 코드 `p0_verify_inputs.py`, blob `507e0f6588d6cddcc358c630c538770ccbaaedbc`. 최신 R4와 기존 P3 검증 브랜치에서 두 blob 동일. 기존 [P3 Run 38556465417](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38556465417)은 39 assets / 7 RF cases / 3 Tnone routes SHA·shape·pose/time 검증 PASS. **바이트 동일 증빙을 재사용**하되, 소스/자산 변경 시 관련 범위를 재검증한다.
2. 원래 EKF3 Frozen RF one-step [Run 38331588521](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38331588521), artifact **11782748118**, ZIP SHA256 `88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63`. 7 case × 2 channels(LoS/Full) = **14 NPZ**, 기록 총 **14,502 시점**, 평가 구간 `t>=30s`는 각 채널 6,201 시점. Sensor-v2 `noise_pair`, seed 0. 이 표본 수를 14개 독립 RF 환경으로 간주하지 않는다. 원 FFT/H/LUT 및 `s` 관측을 다시 생성하지 않는다.
3. 별도 [P3/P4 Run 38562745996](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38562745996)에서는 14 NPZ shape/finite/time 검증과 **동일 prior의 3-state 고정 선형화 one-step** 수치 정합이 PASS. 그러나 최신 R4에 대한 canonical `[r,s]` 어댑터, 4-state interface, **14개 전체 시점의 독립 nonlinear forward `h/H` parity**를 자동으로 PASS시키는 근거가 아니다.
4. 사용할 설계 참고: `research/EKF4_RANGE_S_STAGED_20261014/rf_adapter4.py` (다른 연구 브랜치 `research/ekf4-p3p6-frozen-reuse-20261014`), `rf_p3_p4.py` (`research/ekf4-r3-p2-p6-20261014`), 원 `research/EKF3_INDEPENDENT_20261013/ekf3.py`, 동결 archived `HsLut/s_model`. 무검토 전체 브랜치 병합 금지. 필요한 최소 코드만 provenance/수치 parity 통과 후 이식한다.

## 2. 과학·수학 불변 조건

- EKF4 상태 `x=[p_x(m),p_y(m),psi(rad),b_g(rad/s)]`, 기존 P2 `core.py`의 4-state 및 motion 의미를 그대로 유지한다. P3에서는 상태 업데이트·MAP solver·Q 변경을 하지 않는다.
- **입력 순서의 위험:** 기존 EKF3 archived joint C는 `[s,r_raw]`, 새 P2 MAP `range_first`는 **`[r_raw,s]`**를 기대한다. 순열 `Pi=[[0,1],[1,0]]`로 `z_new=Pi z_old, h_new=Pi h_old, H_new=Pi H_old, R_new=Pi R_old Pi.T`를 **모든 항목에 동일하게** 적용. 원본 저장 C arm row 0=s, row 1=range이다.
- **Range 평균·offset 1회만:** 측정은 기존 `z_r_m` 원시 detected range. 예측 `h_r=sqrt((x-a_x)^2+(y-a_y)^2+(z_tag-a_z)^2)+B_old`; `B_old=-0.5315983906250129 m`. `z_r`을 별도 offset 보정해 놓고 `h_r`에도 보정하는 중복 적용 금지. 대체 `z_r-B_old` / 무보정 `rho` 형태는 정확히 동등한 대조로만 검증.
- **s 전방 모델:** 동결 `hs_lut_2deg.npy` numeric grid 46×180×180, `hs_lut_meta.json`의 실제 theta/phi 축·주기 경계·mount 0°/45°·앵커 및 tag 높이 사용. 로봇 tag 높이 0.45m, 앵커 A=(4,0,2.65)m, B=(10,0,2.65)m. 새 LUT 생성/재보정, inverse-heading 가짜 독립 관측 추가 금지.
- instantaneous RF measurement `h=[h_r,h_s]`, `H_4` shape (2,4): 첫 행 `[(x-a_x)/rho,(y-a_y)/rho,0,0]`; 둘째 행 `[ds/dx,ds/dy,ds/dpsi,0]`. `R_0=[[0.0068578637,0],[0,0.0081]]` in `[r,s]` order. 기존 R0 `R_sr=0`은 **물리적 독립성 미검증 대조군 가정**. `S=H P H^T+R`의 비대각 성분까지 0이라고 만들지 않는다.
- bias 열 `H[:,3]=0`은 *현재 순간 측정함수가 b_g를 직접 사용하지 않기 때문*이다. 재귀 필터에서 `P_{pose,b}`가 생기면 bias도 간접적으로 갱신될 수 있으므로 `b_g가 항상 0 업데이트`라는 잘못된 강제 테스트를 만들지 않는다.
- 원래 첫 경로 데이터는 legacy-Euler truth와 SE2 prediction 사이의 작은 불일치가 있다. truth를 예측기·s/r 모델에 유입시키거나 물리 데이터를 변경하지 않는다. archived `truth_for_offline_scoring_only`는 estimator 객체에서 접근 불가한 별도 offline-scoring 채널에만 노출.
- pole 근방 수평거리 `rho_xy<=0.1m`는 **추정 상태 기반 quality flag**, 참값 기반 샘플 삭제 아님. LUT grid knot/periodic seam/near-pole에서 미분 검사가 비매끄러우면 별도 위치·범위 및 마스크 수를 보고하고 결과를 임의 skip해 PASS 처리하지 않는다.
- 기존 `detected` 마스크와 원본 `t_s/pose_id`를 유지. 기존 A/B의 *미사용 관측 차원 NaN*은 정상 저장 포맷: active slice에만 finite 검사. 원본 A/B/C의 사후 gate 상태는 reference로 보존하되, P4/P6 실제 필터 gate 결과를 truth처럼 덮어쓰지 않는다.

## 3. 구현할 소프트웨어 인터페이스

새 연구 브랜치: `research/ekf4-r4-p3-frozen-rf-20261014`를 최신 R4 결과 commit `85a5d46...`에서 분기. 기존 `core.py`, `synthetic.py`, `P2_SPEC.json` 및 원 P0/실 RF/LUT 파일 수정 금지.

| 파일(예정) | 책임 | 외부 출력 |
|---|---|---|
| `p3_pre_run_audit.py` | 실행 전 정적 source/AST/workflow/manifest/환경 계약 감사. numerical model import 금지 | `P3_PRE_AUDIT.json` |
| `p3_frozen_inputs.py` | 원 artifact 다운로드 후 SHA/CRC 및 14 파일별 hash·shape·`t_s/pose_id`·detected mask 검증, truth 분리 | `P3_SOURCE_RECEIPT.json`, typed `FrozenRFTrace` |
| `p3_rf_adapter4.py` | 동결 LUT + physical range 모델, 원본 `[s,r]`→`[r,s]` 순열, full `h/H/R` 및 pole flag | 순수함수 `model(x,case)`; `ObservationFrame` |
| `p3_parity.py` | archive C-arm `predicted_z/H/R/innovation` 대조, 원본 LUT 독립 호출, finite-difference·negative controls | `P3_PARITY.csv`, `P3_CASE_STATUS.csv` |
| `p3_export.py` | P4가 읽을 adapter identity, immutable case/channel/step 목록, provenance 인덱스와 사후 검증 | `P3_ADAPTER_INDEX.json`, `P3_FINAL.json` |
| `test_p3_*.py` + `ekf4-r4-p3-frozen-rf.yml` | SHA 고정 자동 검증 및 모든 raw evidence 업로드 | Actions run ID/artifact, nonzero failure |

구현 API 예시:
- `load_frozen_rf_trace(case_id, channel, seed=0) -> FrozenRFTrace`
- `make_ekf4_observation(trace,k,x_prior) -> (z_2,h_2,H_2x4,R_2x2,quality_flags)`
- `verify_parity(trace, adapter, all_detected=True) -> ParityReceipt`
- `get_offline_truth(trace_id)`는 **별도 scoring-only API**로 분리하며 estimator 호출에서 사용할 수 없도록 테스트.

순수 인터페이스는 `array order`뿐 아니라 `units`, offset 적용 상태, LUT commit/sha, `case/channel/pose_id`, 나중 P4에서 쓸 variance/gate policy ID를 명시한다. `range_first` 호출은 원본 `z[0]=range`가 보장된 경우만 허용.

## 4. 실행 순서 및 acceptance gates

| 단계 | 실행·테스트 범위 | 통과 요건 / 의사결정 |
|---|---|---|
| **P3-A: 실행 전 감사** | exact HEAD와 의존 소스 diff, 원 P0 manifest/blob SHA, LUT/meta, immutable archive ID, truth 접근 경로·테스트 선택 필드·workflow 실패전파 감사 | 오류 0, `GO` receipt. 오류 시 관련 입력 단계 **HARD BLOCK** |
| **P3-B: 원본 자산 적격성** | ZIP SHA256=`88b0...`, CRC, per-case 파일 SHA, 14 NPZ × 필수 필드, n/t/pose/detected/raw s/r, prior P SPD, active H/R finite, 원본 39 자산과 7 case 목록 대조 | 모든 14 trace 유효, 원본 14,502 시점 및 각 case/channel 수 정확. 과거 P0 hash PASS는 같은 blob 범위에서 재사용; checksum 이탈 시 affected assets 전체 재검증 |
| **P3-C: 어댑터 1차 회귀** | 각 trace t=0, t>=30, 중간, 마지막 고정 인덱스(중복 제거), 7case×2ch 최대 56개의 canary. 독립 원본 forward와 `h/H` 비교, permutation/R0/gate/NIS invariance, offset 단회 적용 확인 | 차이/마스크 수 공개, 예상 외 mismatch 0, 진행 `GO` |
| **P3-D: 전체 입력 parity** | 14개 전 시점 14,502개에 대해 detected+finite 조건별 원 archived C-arm `predicted_z/H/R/innovation` 대조; `H_4[:,3]=0`; LUT 독립 finite-difference는 interpolation-knot 아닌 지점의 별도 unit tests | 동일 원본을 평가한 `h` 최대 오차 **1e−8 이하**(range m/s unitless 각 행 분리), `H` 최대 **1e−5 이하**(원본 h의 물리 단위별 원소). 이 수치는 기존 실험 코드 참고 사전 기준이지 사후 완화 대상 아님. 실패 시 값·조건·step·원인 저장 후 관련 결과 BLOCK |
| **P3-E: 부정 대조·P4 인계** | `[s,r]` 순서 혼동, offset 두 번, yaw deg/rad 혼동, mount 0↔45, truth leakage, 잘못된 LUT shape/SHA, CRC, 중복 pose_id, NaN 활성 차원, 비양정 R, pole edge test | 각 오류는 예외/FAIL로 검출. 모든 stage source SHA·exit code·trace manifest 고정 후 `P3_INPUT_ELIGIBLE_AND_ADAPTER_PARITY_PASS` |

각 수치 parity는 코드 버전 및 사용된 원본/동결 forward 구현에 의존하므로, 소스 SHA가 바뀌면 해당 범위 새 receipt가 필요하다. 테스트만 통과시키기 위해 상대오차 기준을 늘리거나 일부 mismatch를 숨기는 것은 금지한다.

## 5. 수치·과학 판단의 범위

- **HARD_EXECUTION_BLOCK:** 필수 SHA, 원본 파일, 상태·단위, 관측/진실값 분리, sample alignment, likelihood/offset/order 오류. 영향을 받는 trace 불허.
- **CASE_RESULT_INVALID:** 일부 trace만 비유한·pole 특이·정보 누락 등의 문제: 개별 case/step과 사용가능 분모 기록. 전체 14/14 P3 PASS로 표시하지 않음.
- **DIAGNOSTIC_DEFECT:** 선택적 필드 KeyError, 출력 패키지 누락 등은 원 수학적 결과와 분리해서 코드 수정·재실행. 감사 단계에서 먼저 검출.
- **CLAIM_BLOCK:** `R_sr=0`의 물리적 독립성, 실제 Full RF 일관성, 새 RF scene 일반화, P4–P6 성능, position-integrated G3 TV 수렴. 자료가 적격해도 이 주장은 `scientific_PASS=false`.
- P3 결과로 **RF와 DR 중 어느 쪽이 더 정확한지 판단하지 않는다**. 원 one-step Full RF 악화는 기존 근거로 보존하고, P4 이후 실제 fused estimator에서 검증한다.

## 6. GitHub workflow·증거 보존

1. sparse checkout exact source+P0/LUT/meta 및 핀된 버전; **P3 정적 감사가 먼저**. 기존 P3/P4 성공의 P0 증빙을 정확한 blob으로 재사용. 필요성이 입증되지 않은 326MB FFD 재처리 금지.
2. Immutable archived one-step ZIP 다운로드 → SHA256/CRC 확인 → pinned NumPy 설치 → 14 trace 입력검사 → canary → 14,502 전체 parity → negative controls → P3 최종 영수증.
3. 실패 시에도 artifact 업로드(`if:always`), 하지만 `set -euo pipefail` 및 nonzero exit 유지. 과거 `tee` 성공으로 내부 실패가 숨겨진 전례 방지.
4. 결과 디렉터리 덮어쓰기 금지, 입력·코드·원본 archive SHA, audit receipt SHA, per-case/step 에러, optional field coverage, acceptance denominator, case/channel provenance 모두 저장.
5. 최종 필수 파일: `P3_PRE_AUDIT.json`, `P3_SOURCE_RECEIPT.json`, `P3_PARITY.csv`, `P3_CASE_STATUS.csv`, `P3_ADAPTER_INDEX.json`, `P3_FINAL.json`, stdout/stderr/log 및 모든 SOURCE SHA 목록.

## 7. 완료 정의 / P4 진입 조건

**기술적 P3 완료 = 아래 항목이 모두 참일 때만:**

- 실행 전 동일 SHA 감사 GO, 동결 source/LUT/archive identity PASS.
- 7 RF case × LoS/Full = 14 trace, 모든 14,502 저장시점의 정합성/분모/마스크 보고. 사용 가능한 원본 C-arm 조건은 관측·Jacobians 정확히 대응.
- `[r_raw,s]` API, 모델/관측/공분산 행·열 변환 일관성, Jacobian bias=0, original R0 수치·기하학 offset 정합, truth leakage 없음.
- 정의한 canary/전체 parity/negative controls PASS. 기존 P0·P3/P4 증거를 신규 P3의 독립 적격성 영수증과 연결.
- 최종 `P3_FINAL.json`에는 `P3_INPUT_ELIGIBLE_AND_ADAPTER_PARITY_PASS`, `scientific_PASS=false`, `P4_P6_NOT_RUN` 및 적용 범위를 명시.

**P4 인계:** 원본 3-state `xminus/Pminus`와 동일 poses/observations에서 4-state zero-cross-bias same-prior joint, R-first frozen linearization, relinearization 비교를 수행한다. `H_b=0`과 `P_{pose,b}=0`이면 one-step bias가 바뀌지 않는 것이 정상이며, 재귀 bias 효과는 P6 문제다. P3 source eligibility만으로 실제 LoS/Full RF 성능이나 P5 G3 position-integrated reference PASS를 선언하지 않는다.

## 8. 변경 관리

P3 단계에서는 원 RF 자산, 기존 EKF3 P0/P2, R4 synthetic P2 code/results, 원 4-state solver를 수정하지 않는다. 필수 충돌·오류를 발견하면 유형(HARD/CASE/DIAGNOSTIC/CLAIM)과 영향을 받는 주장만 차단하고 로그·실패 입력을 보존. 프로그래밍/수치 API 오류는 자동 수리·독립 회귀하지만 RF 물리모델·분포/우위가설 변경은 별도 사전등록과 사용자 방향 확인 후 처리.

**이번 파일은 계획만 게시하며 P3 코드를 구현하거나 실행한 것은 아니다.**
