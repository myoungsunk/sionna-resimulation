# MBVAR-PRR-001 — S1 독립 재검산 및 S2 별도 범위 승인

**2026-11-03 · 기존 S1 실패판정 보존 · 새 모델 채택 승인 아님**

## 1. 결론과 승인 수준

| 사항 | 판정 |
|---|---|
| S0/A0 기존 사전 설계·원본 감사 | 외부 분리 감사 SPEC_APPROVED (기록 확인) |
| S1 개발/동결 평가 기술적 유효성 | 기존 독립 결과감사 ACCEPT (기록 확인) |
| S1 잠금 평가 점수 재감사 | 독립 계산 코드/별도 GitHub Actions runner PASS |
| S1 전체 개선·채택 | **NO-GO; 사전 기준 4/4 FAIL** |
| S2 별도 진입 | **APPROVE_NEXT_STAGE_S2_SCOPED_RESEARCH_PREPARATION** |
| S2 실제 개발 실험 토큰 | **GO_S2_DEV 미발급** |
| S2 잠금 평가 토큰 | **GO_S2_LOCKED_EVAL 미발급** |
| S3 체크포인트 단계 | HOLD |

**중요:** S1의 실패를 성공으로 바꾸어 S2를 통과시킨 것이 아니다. 원래 계획 §3/§4가 허용한 ‘원인 가설이 미해결이면 책임자 별도 승인으로 다음 단계 조사’ 조항을 사용한다. 승인 범위는 S2 가설·입력·개발용 read-only feasibility 및 격리 구현 준비이다. 별도 독립 S2 사전/코드감사 및 SHA 동결 전 S2 DEV/LOCKED-EVAL 실행 금지.

## 2. 검증 기준점

- S1 실제 코드: c4f7394842a808b59f3e14f3c5eb985250c0c5cd
- S1 잠금 평가 발표: 5b82a7d15cb515285ad3e37a4db7976ce43286e2
- 기존 S1 독립 결과 감사: e3dfbe8e2d7216ddfa5bf754edb991989856dfd5
- 기존 A0 SPEC 승인: 6fecf36b3b206b87a9672243be8ed1be5a69e3c8
- 신규 독립 검산: [GitHub Actions #41636627036](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41636627036), Linux 별도 runner, Python 표준 라이브러리 독립 스코어 코드. production score/update helper 미사용.
- 재검산 범위: per-seed scores 1,600행, paired summary 320행, 320 trace index, LFS pointer SHA, manifest·승인 코드 SHA 및 score 구성.
- **제한:** 이 신규 runner는 LFS NPZ의 실제 payload 320개 또는 내부 345,120개 Kalman update를 다시 실행하지 않았다. 기존 /root/a0의 결과감사 보고서가 해당 별도 원시 검산을 주장하며, 이번 신규 감사는 그 범위의 재감사를 대신하지 않는다.

## 3. Full 잠금 평가의 사전 판정 (primary t>=30 s, seed 10~29)

| route/bias | Heading RMSE paired ratio median | 사전 목표 | verdict | XY paired ratio | 새 arm Heading95 median |
|---|---:|---:|---|---:|---:|
| R4-B B0 | **0.9215142735** | <=0.90 | FAIL | 1.036071 | 0.397804 |
| R4-B L2 | **0.9055490319** | <=0.90 | FAIL | 1.046165 | 0.407939 |
| R5-B B0 | **1.0622484658** | <=1.05 | FAIL | 0.983659 | 0.977866 |
| R5-B L2 | **1.0504346648** | <=1.05 | FAIL | 0.968463 | 0.994071 |

Source: [동결 평가 SCORES_PER_SEED](../S1/runs/EVAL_001/SCORES_PER_SEED.csv), [동결 summary](../S1/runs/EVAL_001/PAIRED_SUMMARY.csv). 재검산 코드: [verify_s1_scores_independent.py](verify_s1_scores_independent.py).

R4에서 Head coverage 약 40%라는 잔여 과신과 R5에서 Head 보호기준 위반이 확인돼 S2의 *이미 손상된 상태 복구*는 독립적인 연구 질문으로 남았다. S1의 예방 성공·전역 채택 주장은 계속 금지된다. S1 Native-LoS 결과는 본래 R1 보고대로 일부 NEES 최악 seed 악화를 보존한다.

## 4. S2에 한해 허용한 가설과 실험

**S2-H:** 오염 관측에 대한 기존 대비 작은 영향력을 주는 것과 별도로, 이미 오염으로 인해 작아진 상태 공분산의 관련 방향을 넓혀 *실제 평균 상태*가 후속 관측으로 교정되는지 검사한다. 단지 P를 키워 95% coverage만 높이는 것은 복구 성공 아님.

- 앵커 B 단독 R4-B/R5-B, B0/L2, Full/Native-LoS, Mount 0°, 원래 MB_VAR 및 기존 RF·운동모델·FFD·평균·VAR 표 유지.
- A: W0 / B: 동결된 S1 W-d0-DS / C_P: W0+선택적 P 복구 / D_P: W-d0-DS+선택적 P 복구.
- **M:** 이미 잘못된 동일 (x,P) snapshot에서 공통 인과적 trigger/schedule로 복구 비교. **P:** t=0부터 각 arm의 자연 재귀, arm별 trigger 변화까지 포함.
- P 복구는 접선+Heading 방향의 PSD 증분을 주 처치. 기존 상관, 평균·자이로 바이어스 평균, 고정 Q 유지. Heading-only 및 bg 분산은 별도 사전 ablation에만.
- 성능/채택 기준은 원래 계획 §8.2를 수정하지 않는다. 특히 R4 개선 및 R5/LoS 보호를 필수로 유지. GT·oracle RF는 진단·사후 평가 전용.
- S1 locked seed 10~29의 결과를 이미 확인했으므로 새로운 독립 환경·완전히 미사용 데이터 일반화라고 주장하지 않는다. S2 정책 계수를 S1 locked 결과로 튜닝하지 않는다.

## 5. S2 사전 감사의 P0 blocker

1. **실제 작동 가능성:** S1 DEV seed 0~9에서 완전 온라인 기준의 SUSPECT_LATCH → 낮은 위험 1초 → B 수평거리 <=1.5m → 2초 geometry guard 순서를 가상 계수. R4/R5, Full/LoS, bias별 trigger 후보와 미발동을 공개. GT를 trigger에 사용 금지. 후보 0이면 복구 유효성은 NA/HOLD; 잠금 데이터를 보고 threshold 변경 금지.
2. **P 주입의 인과·수학:** delta P PSD, 단위 rad²와 m², 접선 부호/near-axis rho<0.25m fallback, 기존 cross-cov 유지, 1 episode 1회, cooldown 및 최대 횟수. ν=0 / 측정 OFF면 평균 변화 0.
3. **게이트 분리:** P 확대는 NIS도 줄일 수 있다. 고정 BASE 마스크의 F-기전 시험과 새 정책 자체의 O-운영 시험 구분. 현재 packet으로 P를 확대해 오염 수용을 유발하지 않는지 검사.
4. **관측성:** 최근 2초 HΦ와 nuisance bg를 고려한 4상태 정보량. 임계 λmin>=1e-6은 사전 guard 제안일 뿐 성공 보증이 아니다. 조건 부족은 INSUFFICIENT_GEOMETRY로 보류.
5. **누출/공정 비교:** S1 예방 w의 재학습·재튜닝 금지. B0/L2가 동일 RF를 공유함을 명시. trigger 빈도·false recovery·미복구·보호조건·계산비용을 삭제 없이 보고.
6. **진짜 복구 판정:** 동일 손상 snapshot에서 Heading/XY의 실제 오차·회복시간 감소와 coverage/tail 보호가 함께 필요. P만 크게 만들어 coverage가 높아지면 UNCERTAINTY_RELAXED_ONLY.
7. **별도 승인 토큰:** 독립 S2 설계감사·코드감사, code/contract/input SHA freeze, reviewer/session/runner/검산 로그 확보 전 GO_S2_DEV 금지. S2 개발 결과감사 후 GO_S2_LOCKED_EVAL을 다시 별도 발급한다.

## 6. 지금 허용/금지

**허용:** S2 사전 설계 독립 감사 의뢰 및 준비, 별도 브랜치의 격리 구현·합성 유닛테스트, 개발 seed 0~9 read-only trigger census. 결과는 DEBUG/FEASIBILITY, S2 성능 시험이 아님.

**금지:** 새 S2 정책의 DEV/LOCKED_EVAL 전체 실행, S1 통계 재라벨, 채택 PASS, S3 자동 진입, 새 학습 RF 또는 경로 생성, 결과를 보고 경계/게이트/지원 seed 변경.

**최종 책임자 별도 범위 승인:** APPREVE_NEXT_STAGE가 아니라 정확히 **APPROVE_NEXT_STAGE_S2_SCOPED_RESEARCH_PREPARATION**. 이 문서는 책임자 의사의 기록과 runner 기술 증거를 묶으며, 아직 별도 S2 감사 에이전트의 결과 또는 S2 실행 GO 토큰을 의미하지 않는다.

[원래 MBVAR-PRR-001 계획](../MBVAR_PRR_001_PLAN_20261103/01_EXECUTION_PLAN_KO.md) · [기존 S1 독립감사](../S1/audit/R1_S1_INDEPENDENT.md) · [S2 독립 사전감사 요청서](S2_INDEPENDENT_PREAUDIT_REQUEST_KO.md)
