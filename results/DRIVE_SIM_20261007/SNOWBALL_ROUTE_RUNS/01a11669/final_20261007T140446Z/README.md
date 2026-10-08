> **G3 정정 (2026-10-08):** 이 스냅샷의 기존 G3 보고서 6개는 `stations: 0`이어서 무효입니다. [유효한 재검사](../g3_recheck_20261008/README.md)에서 엄밀 기준은 모두 FAIL, 승인된 2e-13 s 기준은 모두 PASS입니다. 기존 JSON/묶음은 역사적 증거로 보존하며 G3 PASS 근거로 사용하지 마십시오.

# Snowball R2/R4/R5 최종 실행 결과

2026-10-07 22:58:19 KST에 S6 및 분석 완료. 실행 소스 `0d4588f79116e221d874307f233d69ff0b13d99c`. 기존 중간 스냅샷을 보존하고 최종 증거를 추가합니다.

## 실행과 판정

- Preflight: 82 passed. Anchor B parity `all_passed: true`; H 상대오차 최대 5.90231071171093e-5, |Δs| 최대 1.5091684435850072e-5, first-path index 100% 일치.
- Trace: R2 925, R4 547, R5 1343 위치 × A/B, 총 5,630개 완료. 감사에서 누락/비정상 없음.
- 기존 G3: 6개 모두 stations=0 검사로 무효. 새 재검사에서는 strict 6개 모두 FAIL, 승인된 relaxed 6개 모두 PASS. 기존 JSON은 무효한 역사적 증거로 보존.
- B apply: H 저장소 12개 완전성·shape·유한값 검증 완료. 원시 H/NPZ는 게시물에서 제외.
- Route mismatch sigma 0.16095229605409875는 S6 전에 한 번 측정·고정. 평가 경로 사용을 공개함.
- S6: SNR 30/10 dB, pos-process-std 0.01, seeds 50, 12블록 × 4,500 rows = **54,000개 결과, 실행 실패 0개**. 분석 파일 13개 생성. EKF 분석 대상 32,400개.
- RF 16→32, S6 4→32는 사용자 승인. 프로세스당 1 thread. 재개 전 완료 receipt 4,479개 해시 동일 확인. 기존 wrapper/로그/결과 보존.

## 진단 결과의 한계

**과학/production PASS가 아닙니다.** L1 FAIL max 0.023972114650869493, median 0.0005302414729959071 및 L2 FAIL max 0.010448905754996851 > 0.005 (8 cases)는 유지됩니다. 센서 파라미터는 placeholder이고 시뮬레이션 결과입니다. `s`는 q_clean이 아니며 경로의 물리적 유일성/등가성은 입증되지 않았습니다.

A10/A10b/A10c에 따라 사라지는 경로 진폭 screen은 참고용입니다. Anchor B screen 초과 R2 507, R4 299, R5 704 위치, 최대 상대진폭 약 4.80684%를 audit와 receipt에 보존했습니다. Anchor B의 parity 기준은 그대로 유지했습니다.

방법이 모든 조건에서 우월하다는 결론도 아닙니다. 예를 들어 H2 비교에서 R4 anchor A는 12조건 중 3개 개선/6개 악화, anchor B는 0개 개선/6개 악화였습니다. 상세 결과는 `results/S6_routes/ANALYSIS/ANALYSIS.md`와 조건별 CSV를 확인하십시오.

## DEV 비교와 누락 표시

실행 소스에 포함된 DEV_RESULTS는 이전 y0/y0.35 경로와 5-seed smoke 자료이며 이번 R2/R4/R5×A/B 50-seed 결과와 조건이 다릅니다. 대응되는 동일 조건 DEV route S6 및 주요 gate 참조는 **MISSING**입니다. 별도 `DEV_COMPARISON.json`에 비교 가능성·참조 범위를 기록했으며 정확한 수치 재현을 주장하지 않습니다. 실행 결과 CSV·manifest·분석은 이번 run의 실제 생성물만 사용했습니다.

## 증거 및 무결성

전체 증거 묶음: `final_20261007T140446Z.tar.gz`. SHA-256: `2d2321599ae08e7b98a8652133e22173eaed7731d11e5cb89863b5c91b4bde06`.

묶음 전송 해시와 TRANSFER_MANIFEST의 5,751개 파일 해시를 로컬에서 검증했습니다. 모든 trace receipt JSON, S6 CSV/manifest/분석, 사전등록·수정 기록, source runner/S1 hash, 실행·재개·상태·로그와 wrapper가 포함됩니다. 원시 H/NPZ, 자격증명 및 experiment ledger는 제외했습니다.

파일 경로는 현재 최종 실행 또는 명시적인 DEV_REFERENCE 자료를 구분합니다. 결과를 과학적 PASS로 바꾸기 위해 기존 gate나 원본 증거를 수정하지 않았습니다.
