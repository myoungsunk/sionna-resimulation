# EKF4 R4 P3 구현·실행 결과 — 14,502개 동결 RF 관측 전체 정합 PASS

## 0. 판정

**P3_INPUT_ELIGIBLE_AND_ADAPTER_PARITY_PASS**, `P3_technical_PASS=true`. 동결된 Sionna/FFD RF의 원본 데이터와 기존 EKF3 one-step 관측·Jacobian을 최신 R4 EKF4의 canonical `[range_raw,s]` 인터페이스에 손실 없이 연결했다. 이는 자료·수학 구현의 **parity** 결과이며 실제 RF와 DR 어느 쪽이 더 우수한지, 실제 재귀 RF 측위 성능이나 독립 RF scene 일반화를 검증한 결과가 아니다. 따라서 `scientific_PASS=false`를 유지한다.

## 1. Provenance와 실행 감사

- 소스 브랜치: `research/ekf4-r4-p3-frozen-rf-20261014`.
- **실제 실행 소스:** [b244c2e399d9d105972a09ce35a2516c71f7e514](https://github.com/myoungsunk/sionna-resimulation/commit/b244c2e399d9d105972a09ce35a2516c71f7e514); P2 기준 `85a5d46fcd0cfe41ed46d6e45a19d1d20dd0db8a`, 사전 등록 P3 계획 `fa5599e7860cc55c92f3bd8b68af55915ebe137c`.
- GitHub Actions [Run 38583064582](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38583064582), `conclusion=success`; 감사 `GO`, fatal 0, 실제 10개 단위·음성검증 통과.
- 원본 archived one-step RF [Run 38331588521](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38331588521), [artifact 11782748118](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38331588521/artifacts/11782748118), 정확 ZIP SHA256 `88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63`. 재생성이나 새 channel fitting 없이 동일 archived 결과 읽기.
- **P3 결과 artifact:** [11904127597](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38583064582/artifacts/11904127597), ZIP SHA256 `de40cbbef664b064b6c24ac679ffb7238738ceab36995ee4fa156bb99699428b`, 24개 파일, ZIP CRC PASS. 제출된 `P3_PARITY.csv` 14,502개 행을 외부에서 다시 읽어 case/channel/pose_id 중복 0 확인.
- 첫 source [8cae36f8d458](https://github.com/myoungsunk/sionna-resimulation/commit/8cae36f8d4580bd31e789594d98fa9255c7c6a97) [Run 38582874432](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38582874432)는 모델 테스트 전에 `WORKFLOW_AUDIT_NOT_FIRST_OR_STAGE_ORDER`로 **HOLD**. 사전 감사기가 workflow의 `paths` 목록에 있는 `test_p3_adapter.py` 이름을 실제 실행 명령으로 오인한 구현 결함. `b244c2`에서 실행 명령의 정확한 prefix만 검색하도록 수정한 뒤 새로운 실행에서 `GO`. 기존 HOLD를 소급 PASS하지 않음.

## 2. 범위

- 원 P0 manifest: 39 frozen RF/H/LUT assets, 7 case, 3 Tnone route. `P0_INPUT_MANIFEST.json` Git blob `8bf216cf606f5e3c11139cacbf42f15a44556feb`. 기존 검증 [Run 38556465417](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38556465417)과 동일 blob을 재사용하고 P3에서는 FFD 326MB를 재생성하지 않았다.
- **7 case × LoS/Full 두 채널 = 14개의 NPZ**. R2 경로 979×3조건×2채널, R4 742×2×2, R5 1415×2×2 = **14,502시점**, `seed=0` noise_pair, 동결 하나의 corridor RF realization.
- 두 채널 간 `t_s,pose_id,xminus,Pminus`가 각각 **비트 동일**함을 검증. priors는 archived 동일 DR-only 예측 상태이며 recursive fused RF 상태가 아니다.
- tag 높이 0.45m, anchor A=(4,0,2.65)m/B=(10,0,2.65)m, mount 0° 또는 45°, 기존 numeric LUT 46×180×180. 평균 detector range offset `−0.5315983906250129m` 단 한 번만 적용.

## 3. 전방모델·Jacobian 및 알고리즘 인터페이스

- 기존 archived joint C 관측 순서 `[s,r]`를 P2 MAP/EKF4 canonical `[r,s]`로 동일 순열 변환. `z,h,H,R,innovation,S,K` 전체를 일치하게 변환; 원 posterior를 새 필터 결과로 간주하지 않음.
- `x=[p_x,p_y,psi,b_g]`; `h=[sqrt((x-a_x)^2+(y-a_y)^2+(0.45-a_z)^2)+B_old, s_LUT(x,y,psi)]`; 2×4 Jacobian 마지막 bias 직접관측 열=0. 단, 4-state 재귀 필터의 교차공분산을 통한 bias 업데이트가 항상 0이라는 뜻은 아님.
- `R0=diag(0.0068578637,0.0081)` in `[r,s]`; 0 off-diagonal은 **미검증 독립성 R0 baseline**. Innovation covariance `S=HPH^T+R`는 일반적으로 비대각. 기존 joint χ²(2) 99% gate `9.210340371976184` 유지.
- `FrozenRFTrace`는 `truth_for_offline_scoring_only`를 추정기 입력 객체에 복사하지 않는다. Estimated horizontal anchor distance 기반 `rho_xy<=0.1m` pole flag는 유지.
- 새 P3에서는 MAP optimizer 호출, EKF posterior update, RF bias learning, Q/R tuning, 성능 RMSE 계산을 하지 않는다.

## 4. 실제 전수 검증 수치

| 항목 | 결과 |
|---|---:|
| 소스·코드 SHA, frozen LUT 검사 | GO, fatal 0 |
| 입력 ZIP SHA256 / CRC, per-NPZ 해시 | 14/14 PASS |
| frozen input t/pose ID, prior PSD 및 channels common prior | PASS |
| Canaries (시작/30s/중간/끝 4×14) | 56/56 PASS |
| 전체 detected 관측 h,H,R,innovation,S,K,NIS 및 gate parity | **14,502/14,502 PASS** |
| `max |h_new-h_original|` | **0** |
| `max |H_new-H_original|` | **0** |
| `max |S_new-S_original|` | approx. `6.94e−18` |
| `max |K_new-K_original|` | **3.1086244689504383e−15** |
| `max |NIS_new-NIS_original|` | **5.684341886080802e−14** |
| Full RF 원본 joint NIS 거절 | **316건**, 동일 gate 판정 |
| LoS 원본 joint NIS 거절 | **0건**, 동일 gate 판정 |
| 실제 frozen 입력 pole flag `rho_xy<=0.1m` | **0건** (해당 위치에서의 parity 검증 기회는 없음) |
| Python API·시맨틱/오류 대조 테스트 | **10/10 PASS** |
| 최종 `P3_FINAL.json` | `P3_INPUT_ELIGIBLE_AND_ADAPTER_PARITY_PASS` |

`h,H` 일치는 기존 frozen `HsLut` 수학식을 읽기 전용 코드로 동일 재현했다는 의미이며, 독립 채널 측정이나 LUT 물리 모델의 타당성을 입증하지 않는다. Python finite-difference Jacobian 검사와 음성 대조군은 별도로 수행했다.

## 5. 구현 파일 및 사용 규약

- `p3_pre_run_audit.py` — Git SHA·원 frozen blob·LUT SHA·AST·workflow audit-first 강제.
- `p3_frozen_inputs.py` — 원 archived SHA/CRC/14 trace·pose/clock·원본 sensor truth 차단.
- `p3_rf_adapter4.py` — `FrozenLut.model(x,case)`, `make_ekf4_observation(trace,k,x,case,lut)`, `reorder_original_joint` (canonical [range,s]).
- `p3_parity.py` — 전 14,502 시점 추론-전 관측모델 parity 및 gate/NIS 비교.
- `test_p3_adapter.py` — 10개 독립 수학·오류 대조 unit tests, 기존 P2 conftest와 범위 분리.
- `p3_export.py` — `P3_ADAPTER_INDEX.json`, `P3_FINAL.json` 및 P4 인계 계약 고정.
- `.github/workflows/ekf4-r4-p3-frozen-rf.yml` — 감사 → archived SHA → 입력 → 전수 parity → 음성 대조 → 최종 receipt → artifact 업로드 (실패해도 업로드, nonzero exit 보존).

## 6. 중단·미검증 주장

- 이번 P3는 `scientific_PASS=false`. One-step 입력 적격성·재현성 PASS와 P4 EKF4 one-step 최종 정확도/recursive LoS/Full 성능을 구분.
- `Rsr=0` 독립성, RF likelihood calibration, Full multipath signed range bias, 다봉 posterior/G3 위치 적분 TV, 독립 외부 장면의 일반화는 미검증.
- P4/P5/P6는 **이번 P3 branch에서 실행하지 않았고** `P4=P5=P6=NOT_RUN`. 기존의 별개 작업 브랜치 결과를 이 branch의 fresh PASS로 승격하지 않는다.
- 후속 P4는 `P3_ADAPTER_INDEX.json`의 코드/ZIP/LUT source identity를 검사한 후, 같은 archived 3-state prior 복제 → 4-state zero-pose-bias-cross prior joint/sequential/iterated MAP를 비교해야 한다. Refused gates, NaN inactive row and source state/time fidelity를 유지할 것.

## 결론

동결된 14개 실제 Sionna/FFD 채널 trace를 EKF4용 canonical `[range,s]` 관측 인터페이스와 동일하게 연결하여 **전 14,502개 원본 시점의 (h,H,R,
u,S,K,NIS) parity** 및 10개 음성·수치 테스트 통과했다. 원본 자료 재생성/수정 및 P2 솔버 변경 없음. P3 기술적 데이터·어댑터 구성은 P4 입력으로 재사용할 수 있다.
