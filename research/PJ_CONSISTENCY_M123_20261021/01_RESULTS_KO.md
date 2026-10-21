# M1–M3 replay + H-A·H-D·H-E 결과 (2026-10-21)

실행: [run 39536990635](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39536990635). 7 case × {Full B0, Full L2, LoS B0} × 92 arms. 기계 판정 `results/JUDGEMENT.json`. QA: S_ONLY η=1 κ=1 / REF_POWER1 / REF_JOINT4가 기존 점수 재현(|ΔRMSE| ≤1.2e-13, |Δheading95| ≤1.1e-16).

## 사전등록 판정
| 항목 | 결과 | 판정 |
|--|--|--|
| M (선택 규칙 적용) S1 일관성 | NEES 개선 11/14, median heading95 0.82 (PD 0.64) | FAIL (0.85 미달) |
| M S2 정확도 | median RMSE비 1.10, >10% 악화 7/14 | FAIL |
| M S3 동시 개선 | RMSE 개선 5/14 | FAIL |
| M S4 LoS | 2/7 | FAIL |
| M_E (μ_s=0) | RMSE비 1.64, 악화 9/14 | FAIL |
| H-A 이득–잔차 크기 정렬 | ρ_A(SEP)>ρ_A(PD) 4/7, 저V tertile 최대|d| 0/7, Δρ–ΔlnACT/PHASE Spearman −0.61 | FAIL (기각) |
| H-D 속도 스케일링 | 이동 속도가 모든 case 0.2 m/s, block P90/P10=1.40 | 검정 불가 |
| H-E 부호 불충분 | 두 평균모델 모두 R²_nc≤0.10인 case 3/7 | FAIL |

선택된 arm: R2 held → S_ONLY η=6 κ=1, R4 → COMMON η=3 κ=0.5, R5 → COMMON η=3 κ=1. R2_aA_m0 RMSE 1.84→4.34°가 S2 실패를 주도.

## 가설별 사실
- H-A: 두 모델 모두 V_s 최고 tertile에서 |d|가 최대(7/7), ρ_A는 전부 음수 → V(q)는 잔차 크기를 올바르게 추종한다. D1의 불리한 정렬(SEP)은 크기 정렬이 아니며, 부호(\(K_{\psi s}\,d_s\)의 부호 누적) 쪽으로 좁혀진다. 저V tertile NaN은 V 값이 3개뿐이라 quantile 동률로 빈 bin이 생긴 것.
- H-E: POWER1 평균의 저주파 설명력 R²_nc median 0.03, R4 두 case는 음수(−0.44, −0.17: 평균 보정이 저주파 잔차를 키움). 그러나 μ_s=0은 η=1에서도 coverage 0.64→0.53, RMSE비 1.04로 나빠짐 → 평균 제거는 근거 없음.
- H-D: 속도가 일정하여 검정 불가. 기술적으로 \(\ell_c=\bar v\tau\)=0.39–1.06 m.

## 사후 기술 분석 (사전등록 외, 7 case 전체 사용 → 독립검증 아님)
Full B0+L2 14 case-bias median, 기준 POWER_DIAG:
| 계열 | η | RMSE비 | RMSE 개선 | heading95 | NEES | L2 bias비 |
|--|--|--|--|--|--|--|
| COMMON κ=1 | 3 | 0.943 | 11/14 | 0.941 | 1.46 | 0.88 |
| COMMON κ=1 | 4 | 0.949 | 10/14 | 0.979 | 1.14 | 1.12 |
| S_ONLY κ=1 | 3 | 1.033 | 6/14 | 0.871 | 1.62 | 1.09 |
| 임의 계열 κ=0 | — | 1.5–2.8 | ≤3/14 | — | — | 4–8 |

1. COMMON(η_r=η_s)은 두 채널 상대가중을 유지한 채 측정 대 dead-reckoning 대역폭만 낮춘다 → 정확도·신뢰도 동시 개선 구간 존재(η≈3–4). S_ONLY는 가중을 range+운동으로 옮겨 정확도 악화 — D1의 "상대가중 변경 → 정렬 변경"과 일치.
2. κ<1은 gyro bias를 사실상 관측 불가로 만든다(L2 bias 4–8배). M3 전제(이득 축소=누설 감소)는 bias가 같은 채널로만 빠르게 관측된다는 점을 빠뜨렸다 → 기각.
3. η 상한: η가 크면 bias 학습이 느려져 L2가 악화(R2 held η=24: R2_aA_m0 L2 1.57→4.02°).
4. 필요한 η가 route마다 다르다: R4 B는 η=2에서도 NEES 8.6–9.5, R2는 η=24에서 NEES 0.1–0.9(과소확신). 단일 전역 η + 2-route 선택은 불안정.
5. LoS: COMMON κ=1 η≤2에서 7/7 보존, η=3–4에서 5/7.

## 결론과 다음 단계
사전등록 기준으로는 목표 미달. 다만 원인은 방향이 아니라 η의 route 의존성과 선택 규칙의 불안정성이다. 다음 후보: η를 q가 아닌 온라인 innovation 백색성으로 정하는 적응형 COMMON inflation (\(\hat\eta_t=\max(1,1+2\sum_{\tau=1}^{L}\hat\rho_{\tilde\nu}(\tau))\), 인과 window), 상한은 L2 bias 관측성으로 고정, κ=1. 별도 사전등록 필요.
