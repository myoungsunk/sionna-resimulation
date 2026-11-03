VERDICT: REDIRECT

`b2e363d314f34490909493ee2a091f3b8210aab7`에 P1 두 건이 남아 `GO_S1_DEV`를 보류한다.

FINDINGS:

1. **C1-P1-001 — 승인된 계약·입력·환경과 실행을 결속하는 검사가 없다.**  
   `run_stage.py:11–18`은 token 문자열과 S1 소스 여섯 개만 검사한다. 현재 계약·입력 manifest 해시는 기록만 하며 감사 artifact의 승인 해시와 비교하지 않는다. 외부 SourceFFD/기준선 dependency·ENV lock 검증도 없다. 주요 guard가 `assert`이므로 `python -O`에서 제거된다. 독립 무쓰기 mock 시험에서 과거 GO와 서로 다른 계약·입력 해시를 제공해도 실행 manifest 작성 단계까지 진입했다. 동결 변경·잘못된 provenance를 차단해야 한다.

2. **C1-P1-002 — 요구된 측정 잔차 ε²/R 대신 innovation ν²/R을 계산한다.**  
   `score.py:25–26`은 `tr['nu'][:,1]**2`를 사용한다. 계획 §8.1의 잔여 측정오차 ε와 prior 상태오차가 섞인다. `materialize.py:27–28`의 evaluator artifact에도 이를 계산할 `h(truth)` 또는 ε가 없다. 독립 합성 사례에서 `z_s=1, h_true=0, μ_s=0, h_prior=3, Rss=1`일 때 요구된 ε²/R은 1인데 현재 값은 4다. 기존 ν 진단을 명시적으로 유지하고 ε 진단을 추가해야 한다.

EVIDENCE:

- 독립 SPD 합성 60개에서 joint/range-only 평균·공분산이 직접 역행렬 기반 계산과 일치했다. 최대 평균 차이 `1.15e-14`, 공분산 차이 `9.10e-15`.
- Rss 확대의 covariance 순서 검사 최소 고유값 `−3.47e-15`.
- BASE 기각 관측 부활 방지, 정확한 s행 제거, weight 경계, 전체 RVAR 할인, 일관된 Joseph 갱신은 통과했다.
- 실제 입력 35개 prefix에서 truth poison, 관측·제어 future suffix 변경, O/F 출력 일치, `d0=νs+μs` 검사가 통과했다.
- 잘못된 base-R-only 할인, 잘못된 Joseph R, innovation을 d0로 사용, gate 부활, 행 제거 누락의 다섯 mutant를 모두 검출했다.
- materialized 입력 132개 해시 불일치 0개.
- 여덟 입력 조건의 D를 raw H에서 직접 재계산했다. 최대 차이 `9.99e-16`.
- SourceFFD Heading Jacobian은 per-radian 중앙차분과 `2.44e-10` 차이였다.
- τD는 A0의 R2-B calibration 동결값을 사용한다.
- 독립 checker는 frozen Git source를 in-memory로 읽어 실행했다. checker와 결과는 tool stdin transcript에서 보존할 수 있다.

MISSING_EVIDENCE:

수정 SHA에 대한 두 결함의 음성시험·관련 회귀검사와 재감사 결과가 필요하다. scientific treatment 실행은 수행하지 않았다.

REQUIRED_CORRECTION:

- 실행 전에 감사 artifact와 계약·입력·환경·dependency lock을 검증하고, 실제 실행 bytes를 동결 승인에 연결한다. 필수 검증은 optimized Python에서도 유효해야 한다.
- evaluator 전용 측정 잔차 ε를 제공하고, ν 기반 진단과 구분해 두 가지 평균비 통계를 계산한다.
- 새 SHA를 동결해 해당 결함과 영향받는 검사만 재감사한다. 원 C1 HOLD 기록은 보존한다.