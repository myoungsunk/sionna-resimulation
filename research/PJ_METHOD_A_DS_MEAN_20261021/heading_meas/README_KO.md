# 보충: heading 측정 오차 자체의 개선 여부 (필터 없음)

정의: 위치를 참값으로 두고 편파 관측만으로 heading을 역산할 때의 오차 \(\varepsilon_\psi=r/g\), \(r=e_s-\hat\mu_s\), \(g=\partial h_s/\partial\psi\)(SourceFFD, GT).
- 패킷 단위: \(|g|\) 상위 50%/25% 패킷의 RMS, 중앙값.
- 공간 구간 WLS: 0.4 m 격자 구간별 \(\hat\varepsilon=\sum gr/\sum g^2\), 정보량(\(\sum g^2\)) 가중 RMS.
- 신뢰구간: 공간 구간 block bootstrap 2000회(구간 재표집), POWER1 대비 비율의 95% CI.
- 평균모델은 CI와 같은 설정으로 route-heldout 재적합(LIN: Ridge Δs+전력, HGB: 기존 특징+Δs).
입력: usage map의 UM_POSE_TABLE.csv.gz. 결과: heading_meas_R.csv, heading_meas_B.csv.
