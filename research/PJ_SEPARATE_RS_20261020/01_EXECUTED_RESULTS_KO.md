# 거리·편파 별도 오차모델 및 상관 결합 — 실제 검증 결과

2026-10-20. 요청에 따라 계획 등록 후 실제 재학습, 자연 재귀 EKF, 동일 prior/Gate 대조, 독립 수식 재채점까지 실행했다. **이번 분리모델은 POWER1의 전역 대체 모델로 채택하지 않는다.** 이는 현재 선택한 특징량·Ridge30·분산층화·상관수축 구현의 결과이며, 거리/편파 분리 학습 전체가 불가능하다는 증명이 아니다.

## 1. 실행과 데이터
- 준비/학습 성공: [run 39375640360 prepare](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39375640360).
- 전수 재귀 및 재채점 성공: [run 39376076166](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39376076166).
- 원인분리 요약 성공: [run 39376445261](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39376445261).
- 원본7 조건: R2 A M0/M45, R2 B M0, R4/R5 A/B M0. **신규 C/O·재생성 R4/R5 M45를 이번 첫 모델 비교에 포함하지 않았다. 그 자료가 무효라는 뜻은 아니다.**
- Full9519+NativeLoS9519=19038 레이블. Full만 학습. R2/R4/R5 leave-one-route-out, held-route XY와 1e-4m 이내 train 제외, site multiplicity weight. R2 test의 학습은 R4/R5만.
- 7cases×B0/L2×Full/LoS = **28조건×9arms=252 자연 재귀 trajectory**. 동일 POWER prior/동일 POWER Gate의 단일 업데이트 점수 252개도 별도 저장. 합504개 점수를 독립 실험504회로 표현하지 않음.
- B0 gyro bias0; L2+.20deg/s, 원 Sensor-v2 seed0. 각 방법은 같은 control/prior. 평가 t>=30s. SourceFFD와 기존 Range surrogate d+B_OLD 불변. 새로운 Sionna 계산 없음.
- 1개 복도에서의 개발용 route-heldout 결과다. 물리 특징량 후보는 이전 데이터를 보고 선택됐으므로 untouched test나 독립 환경 검증으로 부르지 않는다.

## 2. 합리적 복잡도만 남긴 모델
- Range QR=[log_fp_power,delay_rms_ns,peak_diff_ns]. peak_diff_ns는 **Rx 포트별 최대 peak 시각 차이**다.
- Polarization QS=[log_fp_power,delay_rms_ns,detector_s_span,s_diff4]. s_diff4=초기 **4tap**, 4ns 아님; detector_s_span은 20/30/40% detector에서 기본 s 대비 최대 변화량.
- 각 평균을 train-only standardized Ridge(alpha30)로 추정. Range 분산은 delay tertile, s 분산은 detector_s_span tertile. 잔차 평균 및 분산을 effective-n에 따라 global로 축소. floor=.1R0. 원 POWER의 학습 철학을 각 관측에 적용하되 특징과 층화를 분리.
- 분리모델 결합: R=[[Vr, rho sqrt(VrVs)],[rho sqrt(VrVs),Vs]]. 원시 r/s가 아니라 **평균 보정 후 표준화된 signed paired residual**의 가중 중심상관 추정. rho=0 / 학습전체 rho / delay×detector 3×3조건부 rho 세 가지. 조건부는 global로 n_eff/(n_eff+200) 수축, |rho|<=.85, sparse bin fallback. 모든 R SPD.
- 글로벌 rho(train only): held R2 .10614, held R4 .04158, held R5 .00499. 이 값들은 각 route 학습집단의 파라미터이지 모든 구간의 실제 rho가 아니다.
- 9 arms: JOINT4, POWER1, POWER_DIAG(Crs만0), SEP_DIAG, SEP_GLOBAL, SEP_BIN, SEP_MU_PWR_COV, PWR_MU_SEP_COV, SEP_BIN_BOX_GATE.
- Mean/cov 교차 교환은 원인분리용 arm이며 그 조합의 calibration을 자동 가정하지 않는다. 시간편향상태/혼합/Student-t/active scan은 새로 추가하지 않았다.

## 3. 상관된 관측의 업데이트와 Gate QA
정상 공동 Gate는 nu=z-h(xminus)-mu, S=HPH'+R, NIS=nu'S^-1nu<=chi2_2(.99). 비교용 BOX는 같은 predictive S의 두 marginal을 chi2_1(.995)로 판정한 whole-packet Bonferroni gate이며, 업데이트는 같은 full R를 유지한다. BOX도 유효한 보수적 검사이고 '수학적으로 잘못된 독립 clipping'이라고 주장하지 않는다. Joint ellipse와 box는 서로 다른 rejection geometry다.

Gaussian 고정 선형화에서 조건부 scalar 형태는 nu_s|r=nu_s-(Crs/Vr)nu_r, H_s|r=H_s-(Crs/Vr)H_r, V_s|r=Vs-Crs²/Vr. **분산만 작게 하고 H/관측을 그대로 두면 같은 정보가 중복될 수 있다.** 원본 동시 업데이트/Cholesky whitened/고정 affine 순차 업데이트 100개 랜덤 SPD 대조 통과. 실제804개 업데이트를 source core와 대조: state max6.66e-16, P max0. 모든252 trace 양의정부호·finite 및 Heading RMSE/95% 독립식 재계산 통과.

## 4. B0 Full RF 최종 Heading 정확도·신뢰도
각 칸 = Heading RMSE(deg) / 명목95% 각도구간 포함 시간비율(%). 독립 반복 확률 아님.

| case | Joint4 | POWER1 | 별도 평균/분산, rho0 | 별도 평균/분산, 조건부rho |
|--|--:|--:|--:|--:|
| R2 A M0 |7.930 /16.9|**1.799 /68.6**|2.121 /54.5|2.110 /55.4|
| R2 A M45 |1.006 /51.4|**.983 /63.6**|1.041 /59.8|1.038 /55.2|
| R2 B M0 |1.419 /73.8|1.516 /64.8|3.443 /17.5|3.470 /20.0|
| R4 A M0 |.847 /44.3|**.659 /46.8**|1.030 /37.0|.943 /38.5|
| R4 B M0 |1.323 /40.0|1.508 /13.2|**1.262 /58.4**|1.275 /59.8|
| R5 A M0 |4.827 /9.3|4.556 /39.7|4.600 /12.8|4.554 /13.3|
| R5 B M0 |2.541 /22.1|**1.056 /97.2**|1.852 /56.6|1.694 /73.6|

R5 A의 4.556→4.554는 실질적인 정확도 개선으로 해석하지 않으며, 포함률은 오히려 크게 악화. R4 B에서는 이득이 있지만 여전히 명목95%에 미달.

L2에서도 비슷한 제한: R2 A M45 POWER .942/64.7% vs SEP_BIN1.047/59.6%; R5 A POWER4.790/33.4% vs SEP_BIN4.796/9.6%; R4 B POWER1.448/13.5% vs SEP_BIN1.179/62.2%.

Full14 case-bias(미세차 포함)에서:
- SEP_DIAG 정확도 개선2/14, >10%악화9/14, 정확도+포함률목표접근 동시개선2/14.
- SEP_GLOBAL 정확도 개선2/14, >10%악화9/14.
- SEP_BIN 정확도 개선3/14, >10%악화9/14, 동시개선2/14. RMSE 비율 중앙값1.207.
- SEP_BIN_BOX_GATE 정확도 개선4/14, >10%악화8/14. 전역 해결책 아님.
- SEP_MU_PWR_COV 정확도 개선7/14이나 >10%악화6/14. 교차 진단에서만 유지.
- POWER_DIAG 정확도 개선6/14, >10%악화0/14, 포함률이95%에 더 가까운 조건10/14. 그러나 다른 조건에서는 원래 Crs가 유익함. 진짜 오차가 독립이라는 결론 아님.

Native LoS control에서는 새분리모델의 Heading RMSE가 원 Full-trained POWER보다14/14 개선했지만, 기본 Joint4가 원 POWER보다14/14 개선하는 조건이며 Full 성능을 우선하는 현재 목표의 성공 판정으로 사용하지 않는다.

## 5. 무엇이 실패했는가 — 새 수치 근거와 추론 구분
### 5.1 절대오차와의 feature 상관이 signed bias 예측 성공을 보장하지 않음
7 Full catalog case에서 새 분리 평균의 Range RMSE 개선3/7, s RMSE 개선4/7, conditional joint NLL 개선3/7. 모든 평균모델을 개선했다고 할 수 없다. R2 A M0 s .1986→.1879, R5 A .1857→.1749는 개선하지만 R4 A .2166→.2311은 악화. **오차크기 지표와 signed mean의 역할을 분리할 필요**가 있다는 추론을 지지하나, 최적 mean/variance feature가 확정된 것은 아니다.

### 5.2 관측오차가 줄어도 재귀 Heading은 악화할 수 있음
R2 A M0: Range12.447→12.392cm, s RMSE .1986→.1879이나 Heading1.799→2.110deg, coverage68.6→55.4%.
R5 A: Range14.560→14.531cm, s .1857→.1749, s95 약95.3→95.6%, joint95 약94.6→93.7%. 하지만 Heading4.556→4.554(거의같음), coverage39.7→13.3%, predicted Heading sigma mean .942→.749deg. 패킷 marginal calibration만으로 재귀 일관성 보장 불가.

### 5.3 새 공분산의 시점별 가중치 변화가 주요 조사 대상
R2 B M0 B0: POWER1 1.516deg/64.8%; 새mean+POWERcov1.390/72.9%; POWERmean+새cov3.775/17.2%; 새mean+새cov3.470/20.0%. 이 조건에서 새 공분산을 적용한 경로가 악화와 강하게 연결된다. covariance의 규모만이 아니라 두 채널 상대가중치·state crosscov·Gate·시간누적이 함께 변하므로 공분산 단일 원인의 기여율로 표현하지 않는다.
R4 B M0는 반대의 사례: 새cov 적용은 Heading/coverage에 도움. 전 case 공통 covariance inflation/deflation 정책은 아직 근거 없다.

### 5.4 같은 prior에서는 작던 차이가 자연 재귀에서 커짐
R2 B B0: POWER sameprior1.516; SEP_BIN same POWER prior+same gate1.539, 자유재귀3.470. POWERmean+새cov 같은prior1.539 vs 자유재귀3.775. R5 B는 SEP_BIN 같은prior1.053 vs 자연재귀1.694.
이는 현재 개별 패킷의 직접 효과와 그 변경이 만드는 이후 prior/Gate 변화가 다른 효과임을 보여준다. 각각의 기여를 완전히 분리하려면 공통 prefix 이후 mean/cov/gate 개입이 추가 필요하며, 이번 실험에서 그 전체 causal attribution까지 확정하지 않음.

### 5.5 조건부 rho를 넣어도 상관모델이 충분해진 것은 아님
R5 A에서 SEP_BIN 예측 rho 평균 .0020인데 정규화/whitened held-route residual corr가+.3068로 남음. R4 A에서도 whitened residual corr−.1359. 단순9bin signed residual correlation은 관계를 일부만 설명한다. pooled empirical corr와 mean predicted rho는 동일 추정량이 아니므로 숫자차 자체를 증명으로 쓰지 않고, whitening 잔차와 조건별 평균을 추가 진단해야 함.

### 5.6 Gate는 중요하지만 교체 하나로 해결하지 못함
같은SEP_BIN/POWERprior에서 R2 M45 B0 415 sampled evaluation packets 중 joint ellipse 통과/BOX거부8개, joint거부/BOX통과2개. 자연재귀에서 SEP_BIN1.038/55.2%→BOX .946/55.7%로 RMSE는 개선해도 coverage 여전히 낮음. R4 A에서는 joint .943→BOX1.219로 악화. 단순 joint gate냐 marginal gate냐를 전역 승자로 고를 수 없음.

## 6. 모델 판정
- 유지: Joint4·POWER1 메인 기준선, POWER_DIAG 상관항 제거 대조군.
- 진단 후보 유지: 관측별 분리 mean(기존POWER covariance 유지), 근거가 있는 조건의 공분산 재설계. 이번 평균교환도6/14에서>10%악화하므로 온라인 후보 승인 아님.
- 현재 파라미터로 NO-GO: 전체 분리 mean/variance + global/bin rho 모델을 POWER1 대체로 전역 적용.
- 보류: 이 실패를 감추기 위한 Student-t/혼합/시간기억/active scanning의 즉시 추가. 이번 결과는 그러한 계열 자체를 기각한 것이 아님.
- 다음 원인 진단은 기존 POWER 주변분산을 고정한 새rho만의 교체, 별도 mean-only/variance-only feature 적합성, 조건별 standardized residual과 first recursive divergence이다. 평가 결과를 본뒤 튜닝하면 새 버전 개발자료이며 독립검증으로 쓰지 않음.

## 7. 사소한 실행 문제 및 QA
처음 YAML runner context 오류와 집계 파일명 필터 오류는 결과식 변경 없이 수정했다. SAMPLES JSON 좌표가6자리 반올림인데 timelineCSV는 고정밀이라1e-9 일치검사가 실패했다. 실제 mismatch x/y최대<=5.1e-7m, yaw<=9e-9rad를 확인하고 그 **검수 허용오차만** 변경; 원본RF/GT/제어열/학습/필터 수식은 수정하지 않음. 전 조건 V3 재실행. 이전 실패 run을 scientific success에 산입하지 않는다.

기존 POWER B0 rounding표와 RMSE 최대차 .000366deg(기존 표의 소수셋째자리 반올림 이내). 원NPZ 비트동일성은 별도 주장하지 않음. Joint/whitened/sequential 수학 QA 및804개 실제업데이트 원소비교,28 NPZ252arms independent formula 점수검산 통과. 별도 사람/기관의 독립검수 아님.

## 8. 산출물
- [전체174파일60.75MB artifact](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39376076166/artifacts/12243278686). SHA256 `265b586283cbd3e50333530463ad1578a41bd0f7932b94b3728dfd87355dd4c1`.
- [실패원인 분리 supplement](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39376445261/artifacts/12243368898). SHA256 `5853fdde94e49c536e3ae9ba3990760c4b2ca9520c40ea465ef8d020a0d0c44c`.
- 전체에는 OOF_PARAMETERS.csv.gz, 원관측 feature/label, train fold receipt, all measurement scores, 자연/고정prior504scores,28NPZ,804coreQA,계획/실행코드/SHA가 있다.
- 연구브랜치만 사용, 원본 source/기존 결과 덮어쓰기 없음. GitHub artifact는30일보존; 코드/프로토콜/이 결과요약은 저장소에 유지.
