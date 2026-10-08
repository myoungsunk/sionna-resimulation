> **G3 정정 (2026-10-08):** 이 스냅샷의 기존 G3 보고서 6개는 `stations: 0`이어서 무효입니다. [유효한 재검사](../g3_recheck_20261008/README.md)에서 엄밀 기준은 모두 FAIL, 승인된 2e-13 s 기준은 모두 PASS입니다. 기존 JSON/묶음은 역사적 증거로 보존하며 G3 PASS 근거로 사용하지 마십시오.

# Snowball 경로 실행 중간 결과 — 2026-10-07 22:47 KST

R2/R4/R5 × anchor A/B 실행에서 실제 생성된 증거의 중간 스냅샷입니다. 최종 결과가 아닙니다.

- 실행 소스: `0d4588f79116e221d874307f233d69ff0b13d99c`.
- Anchor B parity: `all_passed: true`. 35 poses, H 최대 상대오차 5.90231071171093e-5, 최대 |Δs| 1.5091684435850072e-5, first-path index 전부 일치.
- Trace 5,630개: 누락/비정상 없음. 기존 G3 6개는 stations=0 검사로 무효이며 새 재검사로 대체됨.
- H 저장소 12개: 완전성·shape·유한값 검증 완료. 원시 H/NPZ는 이 묶음에서 제외.
- Route mismatch sigma: 0.16095229605409875. S6 시작 전에 한 번 측정·고정했고 평가 경로 사용을 공개함.
- S6: SNR 30/10 dB, pos-process-std 0.01, seeds 50, nproc 32. 스냅샷 시점 실행 중이며 분석 결과는 MISSING.
- 사용자 승인 CPU 증설: RF 16→32, S6 4→32. 완료 receipt 4,479개 해시 보존 확인. 기존 wrapper·로그·원본 증거 보존.

## 판정의 한계

L1 FAIL (max 0.023972114650869493)과 L2 FAIL (max 0.010448905754996851 > 0.005, 8 cases)은 유지됩니다. S6는 진단용 시뮬레이션이며 센서 값은 placeholder입니다. 실행 완료와 과학/production PASS는 별개입니다. s는 q_clean이 아니며 물리적 경로 유일성/등가성은 입증하지 않았습니다.

Anchor B의 사라지는 path 진폭 screen은 A10/A10b/A10c 기록대로 참고용입니다. screen 초과 위치 R2 507, R4 299, R5 704, 최대 상대진폭 약 4.80684%를 숨기지 않고 receipt/audit에 보존했습니다.

동일 조건의 DEV 결과와 수치 재현 비교는 최종 수집 시 수행 예정이며, 현재 정확한 재현을 주장하지 않습니다. S6 최종 CSV/manifest/ANALYSIS 등 미생성 결과는 MISSING입니다.

## 증거 묶음

`snapshot_20261007T134706Z.tar.gz`에는 실제 결과 JSON, trace receipt JSON, 현재까지 생성된 S6 CSV/manifest, S0 사전등록 기록, 실행 상태·로그와 원본/재개 wrapper가 들어 있습니다. 원시 NPZ/H, 자격증명, experiment ledger는 제외했습니다.

SHA-256: `c37f63bd529b69adb795c63414e1a77483924257db3e7d642219a42ff6a03d02`.

전송 묶음 해시와 TRANSFER_MANIFEST의 5,709개 파일 해시를 로컬에서 검증했습니다. 로그와 STATUS는 스냅샷 시점의 값입니다.

생성된 S6 블록: 
- results_R2_aA_m0.csv: 4500 rows
- results_R2_aA_m45.csv: 4500 rows
- results_R2_aB_m0.csv: 4500 rows
- results_R2_aB_m45.csv: 4500 rows
