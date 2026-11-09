# GitHub Actions 원격 실행 독립 대조

**판정: PASS_REMOTE_REPLAY_AND_LOCAL_RECONCILIATION.** 원격 OFF/ACTIVE_RS 12개 stream과 같은 구성의 canonical 로컬 12개 stream, 총 12,544행의 대조를 통과했다. 원본 SourceFFD baseline 6개도 과거 archive와 재현성을 확인했다.

- Run: [42600632209](https://github.com/myoungsunk/sionna-resimulation/actions/runs/42600632209). R2/R4/R5 job 모두 success.
- 실행 commit: `e3ddc9fa4371d899a08a2a873d2ee5cf32074a01`.
- 원본 입력/source commit: `c141839093d1a2e4a76f91eea632cb6467163e28`.
- 이 감사의 JSON SHA256: `743e5cd7c2848d6503af9dacd15b1639b4fc060cf62858d05c5b121202444980`.

## 확인 범위와 수치 기준

각 ZIP을 GitHub API digest·size와 재검증하고 CRC 및 추출 파일 270개의 bytes를 확인했다. Runtime 3개는 exact Git commit의 파일을 별도로 읽어 Git blob SHA와 SHA256을 계산한 후, 원격 artifact·실행 전후 receipt·로컬 소스와 대조했다. 원본 모델 source 11개 해시, 원본 입력 8개·staged 입력 11개, archive member, protocol·config·contract도 확인했다. 각 job의 unit 27개와 calibration test 5개 성공 로그가 있다. 같은 32개 테스트가 세 runner에서 반복된 것이다.

수치 비교는 기존 baseline parity와 같은 `abs(remote-local)/max(1,abs(local)) <= 1e-10`을 사용했다. Gate, guard status/reason, 채널 사용, 인덱스 및 beta의 개입 여부는 exact 비교다. NaN/Inf 위치도 같다. 실행 state·공분산·actual update는 finite이고 PSD, 기존 거절 구간의 관측 수용은 없다.

- 상태 x 원소별 최대 절대 차이: `1.146305272925474e-14`.
- beta 최대 절대 차이: `1.521005543736464e-14`.
- 전체 수치 필드 최대 scaled 차이: `3.127609282671528e-12`.

| Route | Stratum | Arm | Rows | max abs x 차이 | max abs beta 차이 |
| --- | --- | --- | ---: | ---: | ---: |
| R2 | B_FROZEN | OFF | 979 | 1.07e-14 | 0 |
| R2 | B_FROZEN | ACTIVE_RS | 979 | 1.15e-14 | 0 |
| R2 | B_BIAS_COV | OFF | 979 | 8.88e-16 | 0 |
| R2 | B_BIAS_COV | ACTIVE_RS | 979 | 8.88e-16 | 0 |
| R4 | B_FROZEN | OFF | 742 | 2.44e-15 | 0 |
| R4 | B_FROZEN | ACTIVE_RS | 742 | 3.55e-15 | 1.52e-14 |
| R4 | B_BIAS_COV | OFF | 742 | 8.88e-16 | 0 |
| R4 | B_BIAS_COV | ACTIVE_RS | 742 | 8.88e-16 | 0 |
| R5 | B_FROZEN | OFF | 1415 | 0 | 0 |
| R5 | B_FROZEN | ACTIVE_RS | 1415 | 4.44e-16 | 9.77e-15 |
| R5 | B_BIAS_COV | OFF | 1415 | 0 | 0 |
| R5 | B_BIAS_COV | ACTIVE_RS | 1415 | 0 | 1.39e-15 |

Anchor digest는 플랫폼별 prior float bytes의 SHA이므로 양쪽 raw hash가 모두 같을 필요는 없다. 각 stream 내부의 저장 anchor hash를 해당 과거 prior로 다시 계산해 모두 확인했다. 양쪽 anchor index는 정확히 같고 prior 수치는 위 기준을 통과한다.

## 실행 지연: 현재 동기 구현의 제한

관측 간격 중앙값은 200ms다. ACTIVE_RS의 모든 route/stratum에서 total latency p99가 이를 초과했고, 상당수 행에서 실제 처리시간도 관측 간격보다 길었다. 아래는 CI 측정값이며 최적화·비동기 구현의 성능을 추정한 수치가 아니다.

| Route | Stratum | Total p50 ms | Total p99 ms | 200ms 초과 행 비율 | 실제 damping accepted |
| --- | --- | ---: | ---: | ---: | ---: |
| R2 | B_FROZEN | 328.93 | 446.10 | 98.57% | 1 |
| R2 | B_BIAS_COV | 315.73 | 437.59 | 98.37% | 0 |
| R4 | B_FROZEN | 318.60 | 421.94 | 98.11% | 2 |
| R4 | B_BIAS_COV | 315.32 | 425.08 | 98.11% | 0 |
| R5 | B_FROZEN | 240.00 | 335.47 | 84.88% | 9 |
| R5 | B_BIAS_COV | 249.91 | 334.02 | 84.73% | 11 |

Job 전체 시간은 R2 739s, R4 528s, R5 785s다. 각 CI route의 baseline+4 arm 실행 시간은 각각 678.00s, 505.62s, 747.45s다.

## 기록된 provenance 차이

1. CI는 dispatch commit에 포함된 primary-only policy lock `7b92acfbd222e4bbcdfe206ca9224be82a768ffd3dc67edd11653ebbca6393da`를 기록했다. 로컬 secondary는 이후 both-strata lock `bf84d6ccf948d20556e2cd81dcbef2c10d3350c8806ea6de4956f6acfe164bcd`를 기록했다. 고정 τ=2 diagnostic 실행에서 lock은 SHA receipt만 남기며 parameter fitting/선택된 정책 dispatch를 수행하지 않는다. 두 실행의 실제 config와 beta/gate 경로를 직접 대조했다.
2. CI의 OFF/ACTIVE_RS role label은 `predeclared_diagnostic`, 로컬은 각각 `parity_baseline`/`predeclared_tau2_diagnostic`이다. Role은 기록용이다.
3. 로컬로 복원한 RELEASE_INPUT_LOCK에는 terminal newline 1개가 추가되어 4,443 bytes이며, Git commit의 원격 원본은 4,442 bytes다. JSON 내용과 8개 asset hash/size는 정확히 같다. 원격 lock은 exact commit blob으로 검증했고 실제 입력은 별도로 다시 해시했다.

## Artifact

| Route | Artifact ID | Bytes | SHA256 | 만료 UTC |
| --- | ---: | ---: | --- | --- |
| R2 | 13666845152 | 4,029,013 | `e4a805b0afab727158217e20323d457ba738818f7a55836015b9db2825bd5b4b` | 2027-02-07T10:24:20Z |
| R4 | 13665704068 | 3,170,886 | `8408adb7f61c6813e805a369cfcda18257a437e4a1cf008ca90781dc9193ec23` | 2027-02-07T10:24:20Z |
| R5 | 13665868091 | 5,618,339 | `be37ab4c4b6982ab613a8f6f5db99bf15c1882942b4fa561e778638a2c980e32` | 2027-02-07T10:24:20Z |

## 해석 범위

이 결과는 12개 OFF/ACTIVE_RS 원격 stream 및 6개 source baseline의 실행·무결성·로컬 재현성을 검증한 것이다. 42개 로컬 arm 전체, 전체 보정·투영·회복·합성실험을 원격에서 다시 수행했다는 뜻이 아니다. 성능 개선이나 정책 채택을 승인하지 않으며, 활성 정책의 별도 유용성·회복 평가 및 현재 구현의 지연 제한은 그대로 남는다.

계산 코드는 `review/audit_ci_remote.py`, API evidence는 `API_EVIDENCE.json`과 `COMMITTED_RELEASE_LOCK.json`, 모든 행·필드의 최대 차이는 `CI_REMOTE_AUDIT.json`에 있다.
