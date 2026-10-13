# 업로드 자료 감사 — 03e06b55

- 데이터 브랜치: `claude/pensive-johnson-kxx6t6`.
- 확인한 커밋: `03e06b5541e99ee3bbc680fe421701a126d8418b` (고정 스냅샷).
- 원격 변경, D6 계산 재실행, 공식 판정 계산, 업로드 감시 등록 없음.

## 업로드·파일 검증

- 매니페스트 캐시 61개 / 기대 63개. 43개 whole + 18개 분할 캐시(36 parts), 저장 객체 79개.
- 복원 후 총 5,363,615,658 bytes. 실제 다운로드 파일 SHA256 및 Git blob ID 확인.
- 모든 part 검증 후 원본 package_d6_cache.py restore 실행, exit 0. 복원된 61개 원본 SHA256/크기 재검증.
- 부족한 캐시: `PF_A2_3_s8100-8399/R5_d1.npz`, `PF_A2_3_s8100-8399/R5_d2.npz`.
- D6 공식 JSON은 해당 커밋에 없음. V1은 `NOT_READY`.
- D6 spec 및 harness는 이전 감사 기준과 바이트 동일. PF 결과 JSON 및 매니페스트 입력 22개 해시 일치.

## V0 내용 감사

- 결과: `INCOMPLETE_NO_D6_VERDICT`; 상태별 개수: `{"MISSING": 2, "VALID": 61}`.
- 300 seed, 필수 배열 shape/유한성, 전 시점 pose 공분산 대칭·양정정부호, pose/heading/conditional XY NEES 및 heading sigma를 읽기 전용 확인.
- READY/VALID는 파일 검증 상태다. D6 C1–C7/S1 PASS를 의미하지 않는다.

## V2 PF 보완자료 감사

- V1: 단일 스텝 proposal 비교 COMPATIBLE. 장거리 posterior 정확성 확증은 아님.
- V2: 짧은 120-step SIS/PF 비교 6건. SIS 최소 ESS 약 12,238–30,851. Pose 공분산 고유값 비의 최솟값은 0.88357로 일부 차이가 남아 REVIEW.
- V3: 아래 수치는 8개 개발 seed 비교이며 D6 300 seed 판정이 아님.

| 셀 | ANEES 20k | ANEES 80k | conditional XY covariance ratio |
|---|---:|---:|---:|
| R2_d2 | 4.85885 | 4.89507 | 1.00991 |
| R5_d2 | 4.30810 | 4.13967 | 1.08153 |
| R4_d1 | 2.59572 | 2.54509 | 1.02075 |

- R2_d2/R5_d2는 80k에서도 ANEES 3.6 초과. 입자 증가만으로 엄격한 일관성을 충족했다는 근거 없음.
- V4: 개발 seed gate 비교에서 strict-consistent 셀 수 2/9 → 3/9. R5_d1만 판정 변화. 기존 D6의 PF 정의·게이트는 변경하지 않음.
- V2 스크립트의 전체 AUDITED는 자료를 읽어 감사했다는 상태이며 PF 신뢰성 PASS가 아님.

## 로그와 provenance 제한

- PF 검증 매니페스트는 research_dir_dirty=true로 기록됨. recorded input 해시를 현재 입력과 대조하여 전부 일치함을 확인.
- D5_PF_VALIDATION_V2-V4.log는 마지막 JSON 필드 coverage_un에서 끝남. 완결 로그/종료코드 증거로 사용하지 않음. 결과 JSON은 정상 파싱되고 기록된 SHA256과 일치.
- D6 PF 로그는 명시적인 PARTIAL이며 7셀만 기록. 최종 성공으로 취급하지 않음.

## 다음 조건

- 같은 브랜치에 남은 PF 두 셀, 63개 매니페스트, 공식 D6 JSON/CSV/manifest 및 최종 로그가 올라오면 새 커밋 기준으로 증분 검증.
- 현재 로컬의 61개 캐시를 재사용할 수 있으며, 기존 결과는 보존한다.
- V5 후보 선정 및 사전등록/확증은 이번 작업에서 실행하지 않았다.
