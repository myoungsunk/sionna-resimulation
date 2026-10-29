# G3 26-ray 원본 복원·물리 기하 검증·H 재합성 및 RA4 336-arm 종료 감사

**범위·기준일:** 2026-10-29. 원본 read-only: `9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13`; 23개 NPZ delivery: `codex/g3-original-raw-delivery-20261029`, original ZIP SHA-256 `4f625c84172fecd7539273eb8d19c841fd2eb204b61d9062a3b901cca6dc4a62`.
**판정:** `G3_G3-SPECIFIC-ACCEPT_WITH_BOUNDARIES / NO_H_LOCAL_PATCH / NO_BB_MBVAR_RERUN_FROM_G3 / RA4_TECHNICAL_QA_PASS / SELF_REVIEW_ONLY`. 전체 RF 전자기 물리와 논문 주장 `SCIENTIFIC_PASS`는 승인하지 않는다.

## 1. 26개 ray의 물리·수치 원인 (역사적 strict threshold 불변)

| 경로 | 원래 strict 초과 ray | 병합 artifact | 병합 전에도 >5e-14 s | 재현 근거 |
|---|---:|---:|---:|---|
| R2_aA | 1 | 0 | 1 | 원 `STORED_PATH_TRACES_R2_aA` ray 62 / pose 915 |
| R2_aB | 1 | 1 | 0 | 업로드된 1 trace |
| R4_aA | 3 | 3 | 0 | 업로드된 3 trace |
| R4_aB | 3 | 3 | 0 | 업로드된 3 trace |
| R5_aA | 9 | 9 | 0 | 업로드된 9 trace |
| R5_aB | 9 | 9 | 0 | 업로드된 7 trace |
| **합계** | **26** | **25** | **1** | 24 위치, 전체 5,630위치/354,410 ray |

- 원 G3는 `TIE_S=1e-13s`로 image delay들을 묶고 **한 class의 가장 작은 delay만 대표값**으로 사용한 뒤 `strict=5e-14s`로 검사했다. 25개 실제 raw `tau`는 병합 전 가까운 image delay와 `max |Δτ_unmerged|=6.38724e-15s` 이내로 일치하지만, 병합 대표 delay와 비교하면 `5e-14s`를 넘는다. **25/25 실제 원인은 class 대표값에 의한 검증기 false reject로 확정**.
- R2_aA의 `pose_id=915, ray_index=62`: original `tau=2.412728008494014e-7s`; image `end_x_max>end_x_min>end_x_max`의 병합 전·후 잔차가 모두 `5.1090357159952736e-14s`. source float32 격자값과 같으나 잔차는 half-ULP를 넘어선다. 원 solver 내부 어느 단계의 오차인지 **미확정**. 의미: 현재 strict 규칙에서 실제 1개가 FAIL이며 원 원자료를 수정/삭제하지 않는다.
- 새 `UNMERGED_STRICT` 계산을 기존 G3와 **다른 별도 감사 지표**로 보고하면 strict 초과는 26→1, relaxed=2e-13s 초과는 0. 원 역사적 `G3_STRICT=6/6 FAIL` 기록은 그대로 보존; 엄밀 기준을 사후에 완화했다고 주장하지 않는다.

## 2. 실제 ray 정반사 경로의 물리 기하 검사

- 새 25개 모두 6개 유한 평면에 대해 정반사 반사점이 유효하고, TX 출발 방향을 original `theta_t/phi_t`와 대조했을 때 최대 `0.0365665°`; 원 R2_aA 1개는 valid 3-bounce, 오차 `0.0000133°`. **26/26의 제한된 기하학적 일관성 확인**.
- **25개 중 16개**는 지연값만 가장 가까운 sequence를 선택할 때 정반사 기하가 유효하지 않다. 실제 finite-face valid sequence를 따로 찾아야 원 original ray 방향과 일치한다. 이 검사기의 **path sequence attribution** 문제를 별도 수정 대상으로 등록한다.
- 이 검사는 기하/출발 방향 검사다. 재질의 Fresnel 계수, 실제 amplitude, phase, path loss, FFD bank 물리 측정, 354,410 모든 ray의 독립 EM 진실성을 보증하지 않는다.

## 3. 원본 H 최종 판단: 국소 교정 불필요, 전역 EM 승인과 분리

- 원 ZIP 23 trace·23 receipt SHA와 NPZ 내용, 2 FFD 은행 SHA 검증. 원 original H 5개 저장소(R2aB m0, R4aA m0, R4aB m0, R5aA m0, R5aB m0) SHA를 검증했고 **G3 해당 23개 H pose row**를 original Jones+tau+FFD에서 전주파수 257×2×2 복소값으로 다시 합성. 원 저장 H와 **최대 상대오차 3.6913e-16**. 해당 원 trace가 저장 H 입력으로 쓰였다는 source provenance 강한 증거.
- 역사적 R2aA 원 1개 ray의 0°/45° H 재합성도 이전 Actions #40851669162에서 PASS, 해당 지연 한 개를 가상 정상화했을 때 `|Δs|<=2.18e-14`, `Δr=0`.
- 나머지 25개에 대해 원 `tau`를 가장 가까운 image delay로 **가상 변경**하면 max `||ΔH||₂/||H||₂=4.41379e-5`, max `|Δs|=5.59109e-6`, 거리 변화 0, first-path switch 0. **이러한 교정은 실제 물리 모델 오류를 찾은 조치가 아니며, 오히려 올바른 source H를 불필요하게 변경할 수 있다**.
- **G3 때문에 H 국소 patch: `NO_CHANGE_REQUIRED`**, 기존 H/packet 변경 없음 → 기존 BB/MB_VAR의 대규모 재실행 불필요. 단, 다운스트림 RA4 필터 구현 실험은 그 자체의 비교로 계속 유효.
- 원 실험 m45 H 저장소 5개(R2aB,R4aA,R4aB,R5aA,R5aB)의 binary 독립 재합성 parity는 공개 BLOCK_C가 m0만 제공하여 **별도로 미완료**. 전체 12 H store physical acceptance가 요구된다면 이 5개 m45 원본을 추가 제출해야 한다.
- 원 Snowball 2026-10-07 S6 과학 결과는 `L1 FAIL`, `L2 FAIL`, anchor B에서 dropped-path amplitude screen 초과 등을 기록했다. G3의 false reject를 정정해도 이들 independent gate가 자동 PASS가 되지 않는다.

## 4. RA4 336-arm 효과 분리: 3개 Action 종료 후 확인

| Arm (각 gate에서 BB_ORIG 대비) | Heading 개선 | XY 개선 | 동시 개선 |
|---|---:|---:|---:|
| MB_ORIG, BASE_FIXED | 9/28 | 17/28 | 8/28 |
| MB_VAR_LEGACY, BASE_FIXED | **23/28** | **20/28** | **19/28** |
| MB_VAR_PRIOR, BASE_FIXED | 23/28 | 20/28 | 19/28 |
| MB_ORIG, SELF_NIS | 7/28 | 13/28 | 6/28 |
| MB_VAR_LEGACY, SELF_NIS | **12/28** | **12/28** | **8/28** |
| MB_VAR_PRIOR, SELF_NIS | 12/28 | 12/28 | 8/28 |

- 2 평균(`mu_B`, `mu_M`) × 3 variance(no/previous posterior legacy/current predicted prior) × 2 gate(BASE_FIXED/SELF_NIS) × 7 case × 4 gyro = 336 trajectory-arm. `112` full state/P source parity rows error 0, `224` factor-metric contrasts, `168` self-versus-fixed gate contrasts. 원 데이터/조건 분모 동결.
- **MB_VAR_LEGACY 자체 gate − BASE_FIXED 동일 Arm**: Heading·XY가 **동시에 악화 24/28**, 평균 ΔHeading `+0.760681°`, 평균 ΔXY `+7.34186cm`; gate가 바꾼 packet 선택 정책과 variance/mean 효과를 혼동하지 않는다.
- 원 BB_ORIG 기준 동일 고정 gate 28조건의 개선 23/20/19는 재현됐지만 자체 gate에서는 12/12/8. 원 결과는 `MB_VAR_LEGACY` 명칭으로 보존하며 `MB_VAR_PRIOR`는 별도 실험. 원 결과가 완전한 온라인 estimator 또는 독립 환경 일반화라는 주장은 금지.
- 성공한 Actions #40858122545, #40859254511, #40859507594의 원 `RA4_QA.json`은 비트 동일, 분류 결과 모두 동일. 첫 두 CSV 비트 동일; 세 번째와의 최대 RMSE 차이 Heading `2.04e-13°`, XY `1.82e-12cm`; gate 수용 packet 수 차이 0. 동일 corridor의 gyro 반복 조건은 독립 RF realization이 아니다.

## 5. 재실행과 후속 작업

| 조건 | 실제 필요한 작업 |
|---|---|
| G3 class matching/경로 명명만 고침 | original raw H 및 7 case BB/MB_VAR **재실행하지 않음**; 수정된 G3-v2 감사 지표 새 report 추가만 |
| R2A 숫자 정밀도를 더 따짐 | 저장된 단일 ray의 precision/solver 수학적 원인만 추적; 선행 H 교정 금지 |
| 원본 H 복소 생성기가 물리적으로 부정확함이 별도 증명 | upstream solver/EM/FFD/재질·원점 등 영향을 새 계약에 동결하고 H 12 store 전수 차이 스캔 후 영향을 받은 packet/필터만 재실행 |
| 원 12 H store 전체 독립 source-parity 필요 | 공개 저장소에 없는 **나머지 5개 m45 H**의 original bytes와 source sha를 전달받아 기존 trace와 비교 |

## 6. 제안자·구현자·감사자

**PROPOSER:** source ZIP SHA, G3 strict/relaxed 단위, 원점/plane 및 RA4 2×3×2 행렬을 동결. 최초 과학 주장과 검증기 주장 분리.
**IMPLEMENTER:** 원 23 NPZ → ray별 τ 재계산 → 23 original H row 재합성 → finite-face/방향검사; RA4 336 arm의 SHA/상태/P/공분산 parity 3회 검증. 원본 raw/H/점수 변경 없음.
**AUDITOR:** 별도 NumPy·pandas 집계에서 ray 25분류, H 23 parity, 26 finite specular, 336×3 action 변동·mask 수·metric interaction 재검산. 동일 AI 세션에 의한 계산이라 **`SELF_REVIEW_ONLY`**, 사람 독립 심사 `PENDING`. 실물 측정과 전역 EM 정확성 판단은 본 연구 gate의 범위를 벗어난다.

## 7. 출처 링크

- [원본 ZIP과 전송 잠금](https://github.com/myoungsunk/sionna-resimulation/tree/codex/g3-original-raw-delivery-20261029/research/RA0_RA1_RA2_AUDIT_20261029/g3/original_source_delivery_20261029)
- [25 ray·원 H 재합성 Action #40861686275](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40861686275)
- [25+1 유효 정반사 반사면·출발방향 Action #40862630495](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40862630495)
- [RA4 336-arm Action #40858122545](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40858122545)
- [RA4 336-arm Action #40859254511](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40859254511)
- [RA4 336-arm Action #40859507594](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40859507594)
- [기존 G3 0행 PASS 정정 및 독립적 L1/L2 한계](https://github.com/myoungsunk/sionna-resimulation/blob/9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13/results/DRIVE_SIM_20261007/SNOWBALL_ROUTE_RUNS/01a11669/final_20261007T140446Z/README.md)

**최종 결론:** 이번 G3 실패 25건의 직접 근본 원인은 class delay 병합 오매칭으로 확정. 나머지 1건은 엄밀 수치 오차지만 3회 반사와 방향은 물리적으로 일치. G3만을 이유로 원 H 수정이나 BB/MB_VAR 재실행은 과학적 정당성이 없으며, RA4의 336-arm 결과는 원 H 고정 조건의 기술적 인과 비교로 승인 가능. **전체 EM 물리·독립 환경·논문 과학 통과는 별도 평가 필요**.