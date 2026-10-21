# 보충: heading 측정 오차 자체의 개선 여부 (필터 없음)

정의: 위치를 참값으로 두고 편파 관측만으로 heading을 역산할 때의 오차 \(\varepsilon_\psi=r/g\), \(r=e_s-\hat\mu_s\), \(g=\partial h_s/\partial\psi\)(SourceFFD, GT).
- 패킷 단위: \(|g|\) 상위 50%/25% 패킷의 RMS, 중앙값.
- 공간 구간 WLS: 0.4 m 격자 구간별 \(\hat\varepsilon=\sum gr/\sum g^2\), 정보량(\(\sum g^2\)) 가중 RMS.
- 신뢰구간: 공간 구간 block bootstrap 2000회(구간 재표집), POWER1 대비 비율의 95% CI.
- 평균모델은 CI와 같은 설정으로 route-heldout 재적합(LIN: Ridge Δs+전력, HGB: 기존 특징+Δs).
입력: usage map의 UM_POSE_TABLE.csv.gz. 결과: heading_meas_R.csv, heading_meas_B.csv.

## 정정 (robust 재분석, heading_meas_robust.*)
첫 분석의 공간 구간 RMS는 선형 역산 \(r/g\)가 깨지는 소수 구간에 지배되었다(R2 A M45: 106개 중 상위 5개 구간이 가중 MSE의 44%, 구간 오차 +96°/−82°). 따라서 "HGB가 6/7 case에서 확실히 개선"은 과대 주장이다.
재분석: 오차를 보지 않고 \(g\)만으로 유효 구간을 선택(구간 내 모든 패킷 \(|g|\ge0.4\)/rad, 부호 일정; 패킷의 19–51%). 결과(HGB 대 POWER1, 95% block bootstrap CI):
- RMS 비율이 CI 전체 1 미만: R2 A M45 0.65 [0.51,0.77], R4 A 0.73 [0.63,0.81], R4 B 0.72 [0.58,0.86] → 3/7.
- 점추정 1 미만이나 CI가 1 포함: R2 A M0 0.79, R5 A 0.61, R5 B 0.72. R2 B는 1.16 [0.79,1.51].
- 중앙값 비율이 CI 전체 1 미만인 것은 R4 B(0.50)뿐.
- LIN: RMS CI<1은 3/7(M45, R4 A, R4 B), R2 B는 유의하게 악화(1.55 [1.04,2.06]).
