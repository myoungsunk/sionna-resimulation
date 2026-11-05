# FP-SC-001 E0 실행 결과와 정의 확인

**판정: `PASS_FUNCTIONAL_H0_WITH_REMATERIALIZED_CONTROLS`.** 기존 수신기와 MB_VAR의 수치 재현을 확인했습니다. R4/R5 원 controls의 `ds` 바이트는 복원하지 못했으며, A2에서 원 sensor recipe를 현재 환경으로 재생성한 별도 입력으로 수치 재현을 통과했습니다. 이 제한과 첫 실행의 차단 이력을 보존합니다.

별도 검토자는 **E1-01의 CIR-only 후보 가용성 시험만** 기술적으로 허용했습니다. FP 오선택 탐지·P/M prior 정책·FP 교체·편파 개선·EKF 개선·5Hz 운용 성능은 이 E0 결과로 입증하지 않았습니다.

## 1. 구현·실행·검산 범위

| 항목 | 실행 및 검산 범위 | 결과 |
|---|---|---|
| 원 수신기 재추출 | R2/R4/R5 × B0/L2 × Full/Native-LoS, 12,544행; 고유 RF-pose 스펙트럼 6,272개 | clean H에서 원 range와 signed s를 모두 재현 |
| 원래 저장 W0 산술 | 12,544 update | gain·innovation·NIS·Joseph·range 정의 검산 통과 |
| 첫 원본 재귀 시도 | R2 네 조건 통과; R4/R5 여덟 조건은 ds 해시 불일치 | `RUN_E0_001`의 부분 차단 판정을 보존 |
| A2 추가 수치 재귀 | 12조건, 12,544 update | 실행시간(latency)을 제외한 수치 trace의 정규화 차이 ≤1e-10, mask·pose·timestamp exact |
| G4 | 24정적 조건 × Full/direct 48스펙트럼 | 기존 oracle·섭동 결과 재현 |
| 직접 inverse DFT | 102 frame × 3 tap | 별도 scalar 수신기와 일치 |
| flat-spectrum sub-tap sweep | 2≤d<16m, 1mm 간격 14,000점 | 스펙트럼에 보편적인 상수 mapping 가정의 한계 확인 |

A2 최대 정규화 차이는 **1.1784834719776054e-13**이며 허용오차 **1e-10을 변경하지 않았습니다**. 수용 mask 불일치는 0개입니다. 별도 checker가 A2의 360개 산술·trace 항목과 281개 입력·controls 항목을 확인했습니다. 86개 입력(647,547,760 bytes), 코드 49개와 A2 결과 40개 파일도 재해시했습니다. 기존 첫 실행 결과 44개가 그대로임을 확인했습니다.

검토는 같은 세션의 별도 agent가 수행했습니다. production FP-SC 계산을 import하지 않는 별도 수신기·motion/Joseph checker를 사용했습니다. SourceFFD의 전체 편파 interpolation과 BASE shadow gate engine을 별도 재구현한 것은 아니며, 해당 부분은 원본 코드 재귀의 archive parity와 소스 검토 범위입니다. `external_independent_accept=false`입니다.

## 2. 원본 controls 문제와 A2 처리

R2는 원 NPZ controls를 사용했습니다. R4/R5는 원 NPZ의 네 정확한 OID를 Git LFS 서버에 조회했으나 모두 object-level 404였습니다. 원 recipe·sensor source를 확인하고 여러 산술 환경을 조사했지만 역사적 ds SHA를 복구하지 못했습니다. 원 `gy`, `dt`, `x0`는 해시가 정확히 같았습니다.

A2에서는 첫 실행의 차단을 삭제하거나 허용오차를 늘리지 않았습니다. 단일 primary Linux 환경에서 원 recipe로 만든 네 controls를 **재귀 전에 새 입력으로 동결**했습니다. archived prior에서 역산한 controls, ULP 조정, 재귀 결과에 따른 runtime 선택을 사용하지 않았습니다. 성공 명칭은 `NUMERICAL_REPRODUCTION_WITH_REMATERIALIZED_CONTROLS`입니다. 역사적 바이트 일치는 계속 `UNRESOLVED`입니다.

- [A2 사전 변경 계약](A2_20261105/AMENDMENT.json)
- [새 controls의 출처·형식·해시](A2_20261105/controls/REGISTRY.json)
- [복구 조사 기록](A2_20261105/recovery_investigation/controls_recovery_notes.md)
- [첫 실행 결과](RUN_E0_001/RUN_MANIFEST.json)
- [A2 실행 결과](A2_20261105/RUN_E0_A2_001/RUN_MANIFEST.json)

## 3. 실제 ranging 전제

네 값을 분리했습니다. 기하 거리는 실제 안테나–앵커 거리, 검출거리는 원 leading-edge tap의 출력, 보정거리는 `z_r - mu_MB,r - B_OLD`, 상태 거리는 현재 관측을 쓰기 전 EKF prior 위치의 기하 거리입니다. `B_OLD=-0.5315983906250129 m`입니다. raw detector 거리의 약 −0.5m offset을 실제 보정거리 오차와 혼동하면 안 됩니다.

다음은 **B0 Full의 전체 pose** 결과입니다. `t≥30s` primary subset이 아니며 독립 표본을 가정한 신뢰구간도 아닙니다.

| 경로 | pose 수 | 보정거리 RMSE (cm) | 절대오차 p95 (cm) | 절대오차 p99 (cm) | ±4cm 이내 | 상태 prior radial RMSE (cm) |
|---|---:|---:|---:|---:|---:|---:|
| R2 | 979 | 5.153 | 11.403 | 18.148 | 71.50% | 1.215 |
| R4 | 742 | 5.920 | 11.266 | 17.400 | 62.13% | 1.307 |
| R5 | 1,415 | 7.766 | 9.742 | 19.786 | 70.67% | 1.351 |

기존 보정거리의 전체 오차가 항상 ±4cm 이내라는 전제는 지지되지 않습니다. 이동 제약 4cm와 관측오차 4cm는 별개입니다. 이 표만으로 FP 교체가 range를 개선하거나 악화한다고 결론 내릴 수 없습니다. F00/F10/F01/F11 대조는 후속 단계입니다.

전체 12조건과 네 거리 정의의 bias·MAE·RMSE·tail·개별 행은 [수신기 summary](RUN_E0_001/receiver/SUMMARY.json) 및 같은 폴더의 CSV에서 확인할 수 있습니다.

## 4. detector-domain mapping

원 `SourceFFD.h_r`는 **기하 거리 + B_OLD**인 연속 filter surrogate입니다. 별도 `native_range` 진단값은 같은 source spectrum에 원 receiver를 적용한 검출거리입니다. 두 값을 동일한 tap 예측으로 취급하지 않습니다.

G4에서 SourceFFD native tap/RX는 실제 direct-only receiver와 **24/24** 일치했습니다. range 차이의 최대값은 약 **8.88e-16m**입니다. 반면 연속 h_r를 tap 간격으로 반올림한 값은 **22/24**입니다. 따라서 detector-domain 값의 정의는 해결됐지만, 불확실한 prior·heading·시간적 DR을 포함한 support interval은 별도 검증 대상입니다. 현재 결과는 hard ±4cm gate 또는 half-tap support의 승인이 아닙니다.

단위 flat spectrum 14,000점에서 평균 native detector offset은 −0.694307589m였고, B_OLD를 제거한 평균 잔차는 −0.162709198m였습니다. **B_OLD 자체가 잘못됐다는 증거는 아닙니다.** 단위 flat spectrum에는 FFD 주파수별 복소 응답이 없으므로, 서로 다른 spectrum에 상수 offset·half-tap support를 보편적으로 적용할 수 없음을 보여줍니다.

- [mapping 별도 검토](audit/DETECTOR_MAPPING_REVIEW.json)
- [G4 재현 summary](RUN_E0_001/g4/SUMMARY.json)
- [flat-spectrum sweep](RUN_E0_001/flat_mapping/SUMMARY.json)

## 5. G4와 noise lineage

G4 원 detector 참조 일치는 12/24, 기존 oracle nearest-tap은 22/24였습니다. 복원 11건, 정상 훼손 1건, 여전히 오선택 1건을 보존했습니다. −4/0/+4cm 예측 섭동의 일치는 20/22/8입니다. **정적 예측값 민감도 시험**이며 실제 이동·시간 추적·온라인 정책이 아닙니다.

원시 clean H에서 range와 signed s를 계산하면 12조건 모두 archived packet과 1e-12 이내로 일치합니다. 기존 seed10은 gyro/odom과 초기오차의 역할이며 RF 복소잡음 seed가 아닙니다. 현재 기준선은 clean RF입니다. 새 RF 잡음을 더하는 시험은 새 실현으로 별도 선언해야 하며 원 noisy waveform 재현으로 부르지 않습니다.

[noise lineage](NOISE_LINEAGE_E0_KO.md)에 원 source와 산술 재현을 연결했습니다.

## 6. 재현과 감사 산출물

- 실행기: `scripts/fp_sc_e0.py`, `scripts/fp_sc_e0_a2.py`
- 원 payload 취득기: `scripts/fp_sc_acquire_inputs.py` — 공개된 기존 payload의 OID와 bytes를 검증
- 입력 준비기: `scripts/fp_sc_materialize_controls.py` — A2 전용 원 recipe 재생성
- 원 실행의 input/code/environment/execution locks와 별도 A2 locks를 각 폴더에 보존
- [원 실행 별도 검산](audit/RESULT_REVIEW_001/E0_RESULT_REVIEW.json)
- [A2 별도 검산](audit/A2_RESULT_REVIEW_001/E0_A2_RESULT_REVIEW.json)
- [H0 조건부 관문 판정](audit/H0_GATE_REVIEW.json)
- [초기 로컬 실행 커밋과 원격 게시 커밋의 대응](provenance/SOURCE_PUBLICATION_MAP.json)

결과를 재실행할 때에는 해당 실행의 implementation commit을 checkout하고 실제 LFS payload를 먼저 복원해야 합니다. 출력은 기존 폴더를 덮어쓰지 않는 새 경로로 지정합니다. 초기 로컬 실행 커밋의 정확한 Git 객체는 provenance bundle에 포함했으며 원격 source tree와 동일성도 기록했습니다. A2 구현은 게시된 `7b3d6b368562632ce542b899a87ba7b14190faf6` 커밋에 직접 고정됐습니다.
