# DLP-EKF-GAPS-001 / P3 — 비공선 제3 앵커 SourceFFD Direct-LoS Canary 결과

**2026-11-02 KST**  
**판정: `P3_SOURCE_ONLY_CANARY_PASS` — `NATIVE_SIONNA_RT=NOT_RUN` — `P4=BLOCKED`.**  
이 보고서의 PASS는 **기하 및 FFD 직접경로 계산/관측 추출 canary**에만 해당한다. 기존 C0에는 세 번째 앵커의 native 복소 H, 실제 Sionna 다중경로 ray path 수 또는 동기화 RF packet이 없다.

## 1. 체인 및 SHA 동결

- [P2 전체 재귀 및 보존된 결과](https://github.com/myoungsunk/sionna-resimulation/blob/research/dual-lp-p2-frozen-run-20261101/research/DUAL_LP_PAPER_GAP_20261030/reports/P2_RANGE_ONLY_RECURSIVE_RESULT_20261102_KO.md): 28 route/channel/bias NPZ, 84 metric, 3개 방법, GitHub 영구 ZIP/수치 receipt 보존.
- P3 원 제안자 contract SHA256 `24a5e0581c86a8b99659ebbea30b456fb79b6f4e88ee31860db04df85fafb588`, config `49658dc5532e990a9f8bc0968f96b46ce236167244762cbc817092ff34ce3fc8`, tolerance `11a4adcdf15e7e884b4290e55b8e997b069ce9c8897902b0c41ca47983899b72`.
- 초기 `P3_PROPOSER_LOCK_RECEIPT.json`에 사용된 스크래치 SHA 함수의 self-test 오류를 발견하여, 실험 **이전** 올바른 해시가 기록된 [V2 영수증](../contracts/DLP-EKF-GAPS-001/P3_20261102/P3_PROPOSER_LOCK_RECEIPT_V2.json)을 **append-only**로 발행했다. 잘못된 초기 영수증도 기록상 보존하고 정식 근거로 사용하지 않았다.
- [사전 GitHub Actions #41389798998](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41389798998): 원본 C0 39개/FFD bank 2개, 이전 P2 archive, 기하 및 outcome-blind 39 pose pilot selection, **9/9 PASS**. [별도 수치 감사 영수증](https://github.com/myoungsunk/sionna-resimulation/blob/audit/dlp-p3-preflight-20261102/research/DUAL_LP_PAPER_GAP_20261030/audits/P3_20261102/runs/41389798998/P3_PRE_RUN_AUDIT.json); auditor receipt SHA256 `c658b6e30ff6d5b5011a70333e14b1ddfe93d22406a8adc881b435e57537b202`.
- [P3 FROZEN source-only 비준](../contracts/DLP-EKF-GAPS-001/P3_20261102/P3_FROZEN_SOURCE_ONLY_RATIFICATION.json): 사용자 실행 승인 및 preaudit receipt/pilot SHA 링크. 사람의 별도 GitHub APPROVE로 가장하지 않음.
- [본 P3 source-only GitHub Actions #41390364274](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41390364274) **SUCCESS**. 고정된 13개 source/기하 검사 **13/13 PASS, 0 FAIL**. [원시 QA receipt](../runs/P3_SOURCE_ONLY_CANARY_41390364274/P3_SOURCE_ONLY_EXECUTION_QA.json) 및 [출력 파일 SHA manifest](../runs/P3_SOURCE_ONLY_CANARY_41390364274/P3_MANIFEST.json).

## 2. 고정된 세 앵커 배치

| 항목 | A (기존) | B (기존) | C (이번 P3 source-only 신규 후보) |
|---|---:|---:|---:|
| x [m] | 4 | 10 | **16** |
| y [m] | 0 | 0 | **0.8** |
| z [m] | 2.65 | 2.65 | **2.65** |

C0의 크기는 20×2.4×2.7m, robot/tag antenna z=0.45m, 앵커 천장 standoff 0.05m. C의 가까운 측벽까지 수평 여유 0.4m. A-B-C의 수평 삼각형 면적 **2.4m²**. 원 Corridor 직육면체의 9개 내부 선분 검사점(원점·끝점 포함 11개)을 통과했으며, 이것은 **empty-prism LoS geometry** 검증이다. 벽 이외 로봇 자체 등의 occlusion을 RT로 검증했다고 주장하지 않는다.

기존 R2/R4/R5 3개의 route timeline 고유 pose-time 총 **3,136개**에서 3×2 range Jacobian의 가장 작은 특이값 전역 최소 **0.0335251**; 전수 rank-2. 중앙차분 거리 기울기 최대 오차 `1.78405e-9`. 따라서 기존 A/B와 달리 C를 수평 비공선으로 배치하는 것이 XY local range-geometric observability에 도움이 될 수 있는 설계이다. 실제 필터 RMSE 개선은 아직 계산할 물리 C RF가 없다.

## 3. FFD 단일 직접경로 Canary의 실제 계산

사전 고정된 [pilot pose 목록](https://github.com/myoungsunk/sionna-resimulation/blob/audit/dlp-p3-preflight-20261102/research/DUAL_LP_PAPER_GAP_20261030/audits/P3_20261102/runs/41389798998/P3_FROZEN_PILOT_SELECTION_PLAN.json)에서 R2/R4/R5 각 13개, 합 **39개**. 각 pose의 A/B/C FFD 모델 응답을 계산하여 **117개 model-source observations** 생성. 원본 A/B Native LoS H의 78개 실제 참조 표본을 사용했으며, C에 원본 Native H는 **0개**이다.

| 검증량 | 실제 값 |
|---|---:|
| A/B Native LoS 표본 수 | 78 |
| A/B SourceFFD vs Native H 복소 상대 최대차 | **1.92273e-4** |
| A/B SourceFFD vs Native signed s 최대 절대차 | **4.29544e-6** |
| A/B first-path tap mismatch | 0 |
| A/B/C source-only H vs 별도 direct-vector 모델 상대 최대차 (offpole) | **5.24317e-13** |
| 독립 Hann→1028-IFFT→30% first-edge signed s 최대차 | **5.55e-16** |
| 독립 first-edge range 최대차 [m] | **1.78e-15** |
| 전체 Source-only first-path mismatch | 0 |
| (\psi+2\pi) signed s 최대차 | **2.22e-15** |
| Invalid packet / 극점 cap 표본 | 0 / 0 |

모든 117개가 P3에 사전 정의한 offpole 범위이다. **C 신규 직접경로 모델 배열은 shape=(39,257,2), dtype complex128**로 원래 FFD bank의 TX +45°, RX ±45° 한 열만 저장한다. H에는 **단일 SourceFFD 직선 경로 1개를 모델 가정으로 적용**했으며, native Sionna RT에서의 ray path count=1이라는 측정 주장을 하지 않는다.

- [C 직접경로 모델 H `.npy`](../runs/P3_SOURCE_ONLY_CANARY_41390364274/P3_C_SOURCE_ONLY_H_39_POSES.npy)
- [C Source array의 원본 pose ID/시간 대응](../runs/P3_SOURCE_ONLY_CANARY_41390364274/P3_C_SOURCE_ONLY_ARRAY_KEYS.csv)
- [A/B/C 117행 관측·지오메트리·FFT 출처](../runs/P3_SOURCE_ONLY_CANARY_41390364274/P3_SOURCE_ONLY_OBSERVER_ROWS.csv)
- [오차 및 경계 ledger](../runs/P3_SOURCE_ONLY_CANARY_41390364274/P3_BOUNDARY_AND_INVALID_LEDGER.csv): 0행, 시도된 pilot에서 실제 invalid 발견되지 않음.
- [상세 판정 JSON](../runs/P3_SOURCE_ONLY_CANARY_41390364274/P3_SOURCE_ONLY_EXECUTION_QA.json).

## 4. 무엇이 해결됐고, 무엇을 여전히 주장하면 안 되는가

**해결:** (1) 세 번째 anchor의 명시적 물리 좌표와 비공선 배치; (2) 기존 C0 route pose/time과 결합 가능한 outcome-blind pilot 목록; (3) 실제 두 source-FFD bank로 계산되는 C direct-only field; (4) 별도 수치 구현의 complex field 및 [r,s] leading-edge parity; (5) 실제 A/B NativeLoS 본문 RF와 P1 범위 내 parity; (6) 파일 SHA, 실패 ledger와 실행 재현성.

**미검증:** 실제 C의 Sionna RTX/RT path 수·diffraction/reflection/full H, hardware/simulator 다중앵커의 packet synchronization, 공통 clock/상호 앵커 noise covariance, 3-anchor self-gated range-only EKF, 공정한 동등 packet/에너지 비교. 기존 A/B의 같은 trajectory timestamp가 있다고 **C가 실제 동일 epoch에 측정됐다는 뜻은 아니다**.

Native C Full/NativeLoS generation은 기존 원본 C0를 확장하는 **C0+ 새 물리 데이터**로 다뤄야 하며, 원본 C0를 덮어쓰지 않는다. 소규모 실측 RT canary도 별도 실행비용/재료 선택·Sionna solver provenance, ray path count와 원시 H 비교, 별도 감사·비준이 선행되어야 한다.

**현재 한정된 판정:** `P3_GEOMETRY=PASS`, `P3_SOURCE_DIRECT_LOS_CANARY=PASS`, `P3_NATIVE_SIONNA_RT=NOT_RUN`, `P3_NEW_C_MULTIPATH_H=MISSING`, `P4=BLOCKED`.

이 결론은 P1/P2가 보여준 Full multipath/posterior overconfidence를 해결했다는 주장이 아니며, 기하학적 국소 rank 증가만으로 Heading/XY RMSE 향상을 예상·확정하지 않는다.
