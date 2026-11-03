VERDICT: REDIRECT

R1로 τD와 Full MB_VAR 기준선의 핵심 정의가 확인됐다. `Native_LoS`용 동결 MB 거리 평균 보정 입력이 확보되지 않아 전체 계약 `SPEC_APPROVED`를 발급할 수 없다.

| # | 판정 | R1 근거 |
|---|---|---|
| 1 | BLOCKED | 여섯 Full control 배열에서 MB는 μr만 변경, μs와 R 동일, Rrs=Rsr=0 확인. LoS MB 보정 입력 미확보 |
| 2 | BLOCKED | 입력 부분집합 lock과 기준 source는 확인. 전체 실행 입력 lock은 `complete=false` |
| 3 | PASS_WITH_BOUNDARIES | canonical seed0 및 ctl seed0–9 lineage 확인. 10–29의 모든 과거 사용 여부는 미확정이고 신규 holdout 주장 없음 |
| 4 | BLOCKED | `RULES.md`가 ε, singular nuisance 규칙, PSD 허용오차, 보조 실행 상한, timing 범위를 구체화. 완전한 입력·최종 계약 동결은 대기 |
| 5 | PASS | P/CP factorial과 C_CP 역사 재가중 정의 일관 |
| 6 | PASS | 동일 prior·동일 snapshot·전체 causal replay·수정 과거곡선 구분 |
| 7 | PARTIAL_PASS | Full R4-B/B0/seed0 F64 parity 통과. 전체 조건 parity 및 저장된 독립 checker artifact 미완료 |
| 8 | PASS_DESIGN_ONLY | 상태오차 상쇄·관측 손실·P/Q 구분·history 부족·singular nuisance 보류 정책 정의. 구현 검증은 단계 코드감사 대상 |
| 9 | PASS | 기술·과학·운용 gate와 NULL 보존 명확 |
| 10 | PARTIAL_PASS | 이번 A0는 별도 세션·직접 작성 연산으로 수행. 후속 코드/결과 감사의 독립 source·runner 증거는 각 GO 전에 필요 |

EVIDENCE:

- 독립 τD `0.07138038868537433`
- 원본 Tnone 979개 고유 pose, drive 925개·turn 54개
- raw H에서 재구성한 published fp 불일치 0개
- published s_fp 최대 차이 `5.551115123125783e-16`
- Full R4-B/B0/seed0 742개 시점. canonical exp_pb와 ctl state/P 차이 정확히 0
- 독립 motion/F/G/Joseph 연산과 exp_pb의 state 최대 차이 `3.552713678800501e-15`, P 최대 차이 `7.37257477290143e-18`
- 공유한 SourceFFD, p0_initial, p3_rf_adapter4, sensor_v2, pattern_apply, observation의 로컬 bytes가 pinned `9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13`과 모두 일치
- `RULES.md` SHA256 `ace31404c384eac211015f77ef59150ab20cc2c8f98a2180c6f3c98fc6d2c195`
- `VERIFIED_INPUT_SUBSET.json` SHA256 `73b04b0338f1653c8755d6c7e25bcfcd99409a732e3a4d8d34c4d9ccc7731aa1`
- `SEED_LINEAGE.json` SHA256 `0f609ea887e029c442a24b74b82936f8a2054b60ab0017e60c64a746f5b391ed`

MISSING_EVIDENCE:

`mu_recursive.py`는 held-route 제외 Full 특징으로 model을 fit하며 `MR_SERIES`를 Full에만 export한다. 현재 확인한 artifact 중 Native-LoS용 동결 MB 보정이나 원래 fitted inference object는 없다. Full 보정을 LoS에 적용하면 현재 승인 대상 convention을 추정해 채우게 된다.

REQUIRED_CORRECTION:

해당 기존 LoS artifact를 확보하거나, LoS 보정 convention을 명시적으로 재설계한 계약을 감사해야 한다. 현재 핵심 blocker는 입력이다. 추가 Full parity 실행으로 이 gap을 해소할 수 없다.
