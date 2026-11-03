# DLP-R1B-CH4-001 — P0 계보·실행 타당성 최종 기록

**최종 판정: `HOLD_RF_PARITY`.** 원본 입력 확인, 실행 계약 동결, 8개 pose의 Native LoS/Full canary와 별도 계산 감사까지 수행했다. 동결 복소 채널 RMS 기준을 넘었으므로 전체 917개 pose RF 생성 및 P2–P3를 시작하지 않았다.

이 문서는 실행 전 `01_P0_PROVENANCE_AND_FEASIBILITY_KO.md`를 대체하는 최종 상태 기록이다. 실행 전 문서, V1/V2 계약, 원본 Native QA는 당시 상태와 해시를 보존했다. 최종 판정의 기계 판독 근거는 `08_QA_PARITY_AND_LIMITATIONS.json`이다.

## 1. 원본과 적용 범위

| 항목 | 확인 결과 |
|---|---|
| 기반 저장소 commit | `e365b2f79eb86a3fd53d0d350f8e2d9364f285fe` |
| 사용자 참조 commit | `9e9133ecb46f96d88ee14652d42f43525fdd1b29` |
| 실제 Native 실행 commit | `24d657af7773d1c0347e843ece6b49e9c2d55ac2` |
| 궤적 | 원본 `results/DRIVE_SIM_20261007/S1/timeline_y0.35_Tnone.csv` |
| 원본 표본 | 917개, 5 Hz, 0–183.2 s |
| 예정 평가 표본 | `t >= 30 s`인 767개 전부; 업데이트 거절 시점도 포함 |
| 앵커·태그 | B=(10, 0, 2.65) m, tag z=0.45 m, mount=0°, lever arm=0 m |
| 실제 y 범위 | 0.333085002492–0.439085617347 m |
| 최근접 B 수평거리 | 0.342215239393 m, pose 221, t=44.2 s |
| 최소 off-boresight | 약 8.841637°; 원본 GT에서 SourceFFD pole cap 바깥 |

`y0.35`는 원본 시나리오 명칭이다. 실제 궤적에 포함된 횡방향 변동을 제거하거나 y=0.35 m의 새 경로를 만들지 않았다. 원본 CSV의 SHA-256은 `53e76f41cb95b32b25f2cc58844bac09c09ffd0803aa287cc69e025bb97225c4`이다.

## 2. 기존 결과와의 구분

과거 `final_B_20261007T1017Z`의 B는 method B trace/reapply 실행 명칭이다. 이 디렉터리를 Anchor B 실험의 증거로 사용하지 않았다. 해당 실행의 L1/L2 실패는 구형 2° HsLut 보간과 Native 비교 체인에서 발생했다. 이 기록만으로 현재 SourceFFD의 합격 또는 실패를 판정할 수 없다. 기존 6상태 필터 점수는 현재 4상태 점수로 재사용하지 않았다.

기존 P2 ratification의 집단은 R2/R4/R5이다. R1을 기존 승인에 포함시키지 않고 별도의 요청 계약으로 고정했다. 설정 상속과 코드 검토는 기존 승인 범위의 확대를 뜻하지 않는다.

## 3. FFD 입력 복구와 해시

원래 FFD 두 bank를 GitHub Actions run `38875080492`, artifact `12034154094`에서 복구했다. 495,473,098 byte archive의 SHA-256은 `cad003e294edc59a4eecdbce39c02bec43d91524ecef37c93978a356ba519e8e`이다.

| 파일 | bytes | SHA-256 |
|---|---:|---|
| LP_plus45_bank.npz | 247727983 | `b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b` |
| LP_minus45_bank.npz | 247743979 | `39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9` |

독립 감사는 101개 고유 입력 경로에 대한 201회 해시 비교와 실제 실행 commit에 대한 97개 파일 비교를 수행했다. FFD 원본은 새로 학습하거나 보정하지 않았다.

## 4. 실제 RF·관측 계약

257개 주파수 `6.2504 GHz + 1.95 MHz × k`에서 Native Full과 독립적인 Native LoS solver를 각각 호출했다. Full은 max depth 3, LoS는 max depth 0이다. 나머지 solver·material·mesh 설정은 V2 계약과 실제 `ENVIRONMENT.json`에 기록했다. 원시 H는 `[frequency, RX(+45, -45), TX(+45, -45)]`이며 관측에는 TX index 0을 사용했다.

대칭 Hann(N−1), 1028점 IFFT와 기존 스케일, strongest RX의 30% leading-edge 검출, 두 RX의 공통 tap을 보존했다. Full과 LoS의 tap은 각각 독립 검출했다. SourceFFD의 연속 거리 모델 `h_r=d−0.5315983906250129 m`와 Source 채널에서 산출한 검출 거리를 구분했다. 전자는 P2 관측오차 정의에 사용될 모델이고, 후자는 Native 관측기와의 일치 검증에 사용했다. 추가 평균 보정과 추가 분산은 모두 0이다.

고정 canary는 `[0, 150, 221, 440, 458, 476, 696, 916]`이다. 결과를 보기 전에 기하와 회전 단계로 선택했다. 440·458·476의 XY가 같아도 yaw와 시각은 다르므로 세 표본 모두 유지했다. 총 4,112회 Native solver 호출의 결과를 보존했다.

## 5. 실제 환경과 비용

Python 3.12.14, numpy 1.26.4, scipy 1.14.1, sionna-rt 2.0.1, Mitsuba 3.8.0, DrJit 1.3.1, LLVM 20.1, `llvm_ad_mono_polarized`, DrJit 1 thread를 사용했다. 과거 Python 3.11 환경과 비트 단위 동일성을 주장하지 않는다. 같은 물리·관측 설정과 같은 정량 게이트로 이번 실행을 검증했다.

초기화 이후 8개 canary 루프의 실측 경과시간은 510.400447 s, 최대 process RSS는 1,208.960938 MiB이다. 첫 pose는 초기 컴파일을 포함해 246.080234 s, 이후 7개는 약 35.8–40.2 s였다. 전체 순차 실행 약 9–10시간은 이 표본에서의 단순 외삽이며 실제 917개 실행 시간이나 측정 CPU-hours가 아니다. 병렬 확장도 측정하지 않았다.

원본 QA의 `projected_917_pose_cpu_hours_*` 필드는 실제로 wall-clock pose 시간의 배수다. 원본 파일은 수정하지 않고 `P0_COST_MEASUREMENT.json`에 의미를 바로잡았다. G1 실패로 생산 비용 승인용 lock은 만들지 않았다.

## 6. 판정과 제한

복소 상대오차 RMS `1.0051515145524099e-4`가 동결 기준 `1e-4`를 초과했다. 다른 11개 acquisition 검사와 원시 데이터의 산술 재구성은 통과했다. 최종 독립 계산 감사도 같은 HOLD를 재현했다. 별도 AI 검토자·프로세스가 같은 host에서 수행한 계산 감사이며, 외부 인간 심사나 과학적 승인 서명은 아니다.

전체 결과 해석은 `10_FINAL_RESULT_AND_MANUSCRIPT_USE_KO.md`, 원시 판정은 `runs/P0_CANARY_V2/03_RF_CANARY_QA.json`, 최종 독립 감사는 `audits/P0_CANARY_RAW_AUDIT_FINAL.json`에 있다.
