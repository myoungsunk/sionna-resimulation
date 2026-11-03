# MBVAR-INFO-001 A010 — A18-01~05 독립 재감사 요청서

**역할:** IMPLEMENTER / SELF_REVIEW_ONLY. **상태:** R5 PROPOSER FINAL_PRE_FREEZE / A010 SCIENCE_DRAFT / INDEPENDENT_AUDITOR_SIGNED=false. DEV3·HOLDOUT2·RT=NO-GO.

## 수정 대상과 코드 증거

- [Draft PR #20](https://github.com/myoungsunk/sionna-resimulation/pull/20) — 기존 PR #18의 독립 감사 `REVISION_REQUIRED` 시정 전용.
- `code/a10_r5.py` — 62개 사전 등록된 H1/H2/H3/CAL/H4/H4_REPRO 검정(8/2/4/8/8/32) 및 고정 5개 LH·3개 RV·2개 XMODEL 셀. 실측/시뮬레이션 관측 데이터로 검정 집합을 역추론하는 코드 삭제. 모든 field×role×cell×sensor_seed×arm 등록 키의 완전성 및 `status=OK` 여부를 샘플 필터링 전에 검사. 결손은 `NOT_EVALUATED_INCOMPLETE`.
- `code/a10_r5.py`, `code/c3v5.py` — C3 원본행, 모든 terminal 및 alternative 저장행의 proposer-policy SHA와 고정 `R5_CERT` key/seed 대조. 의도치 않은 60-bit seed float coercion 거부. 누락/중복/정책 SHA·seed 변경은 `ERR_R5_PROVENANCE`.
- `code/a10_r5.py`, `code/c3v5.py` — stored 10+10 upper triangle을 각각 전체 4×4 covariance로 재구성. 직접 Cholesky SPD/min-eigenvalue/normalized condition/logdet/NEES4 E·alt, ΔNEES4, ΔP, Δsqerr 검산. SPD flag나 양의 대각만 신뢰하지 않는다.
- `tests/test_a10_r5_a18.py` — 정책 SHA 및 1-bit seed 변조, 누락·중복, 비 SPD offdiagonal 2×2 block `[[1,2],[2,1]]`, NEES/cond/logdet/delta 변형, XMODEL/RV 삭제 반례.
- `tests/test_a10_r5_math_equivalence.py` — 기존 `s1v2.decide_v2`와 새 R5를 동일 합성 field 데이터에서 독립 실행, **62개** registered estimate/95% CI/verdict 차이 전체 검증. 동일한 4000 field bootstrap, seed=20261029.

## 재검증 Actions

- [#41606744316](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41606744316): 114/114 빠른 양성·음성 시험 통과(오류 교정 후). 전체 S1→C3 SMOKE는 Actions 원본 최종 결과 확인 필요.
- [#41607204028](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41607204028): 원본 수학과 62개 가설 전수 수치 동등성 29/29 pytest PASS, pinned FFD code + field bootstrap.
- [#41607204271](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41607204271): 최종 테스트 SHA에서 full reduced 900/901 S1V5→C3V5 통합 시험. 10/72 등록 행만 존재하는 *기술 시험*으로 G5 FAIL 유지 필수.
- [#41606839019](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41606839019): 수정 코드로 기존 DEV2 K1·K2 archival 9-start terminal precision 시험. 과거 결과를 새 연구 증거로 재해석하지 말 것.

## 독립 감사자 필수 검사

1. 고정 62개 hypothesis IDs의 정확 집합과 진짜 과학 lock의 field/seed/arm 집합을 직접 재생성. XMODEL 전체 제거 또는 `status!=OK` 1행 변조 시 결과가 FAIL/INCOMPLETE인지 확인.
2. 실행 code SHA 및 `R5_POLICY_SHA256`, `r5_policy_sha256`, `R5_CERT_SEED`, `r5_cert_seed`를 3종 CSV마다 대조하고 1-bit 변형 테스트 실행.
3. 저장된 full C10 4×4 상삼각 10개와 원본 수치의 SPD·NEES·logdet 일치 검산. 대각 양의 비SPD 교차항 공격은 거부돼야 함.
4. `s1v2.decide_v2` 공식과 R5의 H1/H2/H3/CAL/H4/H4_REPRO 62개 추정값·CI·verdict를 독립 계산. Field-block 단위만 재표집하며 개별 start를 샘플처럼 취급하지 않음.
5. 최종 source SHA에서 archived DEV2 K1·K2/900·901 SMOKE를 재실행하고 artifact 원본 해시, code hashes, failure preservation 확인. S1 44/132·C3 10/72, G5 FAIL 및 기존 STATE_STABILITY_FIXED FAIL 보존.
6. 운영 E′ (`code/s1v5.py`) 및 FROZEN A008/A009/A010-P0, `RUN_REQUEST.json`, `contract_lock.py` 변화 여부 별도 Git blob 검증.

## 승인 제한

R5 구현자 기술 PASS와 A010 science freeze는 별도이다. `ACCEPT_WITH_BOUNDARIES`, `REVISION_REQUIRED`, `REDESIGN_REQUIRED`, `BLOCKED_EVIDENCE` 중 **별도 세션 감사자** 판정이 필요하며 구현자·CI가 독립 서명을 대체할 수 없다.

`INDEPENDENT_AUDITOR_SIGNED=false`; `A010_SCIENCE_FROZEN=false`; `DEV3/HOLDOUT2/RT=NO-GO`.
