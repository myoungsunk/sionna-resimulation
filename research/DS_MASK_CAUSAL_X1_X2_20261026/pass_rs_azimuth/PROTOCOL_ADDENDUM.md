# 단계 0 실행 전 고정 정의 (2026-10-27)

원문 PROTOCOL.md를 보존하며 본 추가 정의가 충돌 항목에 우선한다.

## 사용자 확정 수정
- RS0, RS1, CUT_RT: BB와 MB 모두 A_B 고정. A_M 사용 안 함. 자연 gate는 RS2만.
- 분석 episode는 GT 수평거리 <1.5m 연속 packet. case/bias/arm 공통. R_s 적용만 prior 추정 거리로 결정.
- 첫 episode만 주 판정, 이후 episode는 재노출 기술값.
- pre=[max(0,start-30), start), 최소 길이5초. 미달이면 초기 |MB-BB 접선오차|<0.1cm인 경우에만 pre=0, pre_from_init=true. 아니면 NA.
- pre가 t<10초와 겹치면 init_overlap=true.
- post=(end,min(end+30,next_start,record_end)], 다음 episode 시작 packet 자체는 제외. 길이10초 미만이면 NA.
- 모든 경계는 episode 시작/종료 기준. 확장 intervention 창은 [start-10,end+10], 기록 범위와 교집합.
- 실제 창 길이, packet 수, 첫/마지막 표본 시각 기록. 시간 비교는 1e-8초 반올림해 부동소수 경계 손실 방지.

## 계산 선택 (수치 결과 확인 전)
- P1: 기존 9개 거리 bin [0,.5,1,1.5,2,3,4,6,8,inf]. 전체 시간/거절 packet 포함. B0 BB만 선택해 bias/arm 중복 제거. case×pose_id가 RF 표본 키.
- LORO는 R2/R4/R5를 holdout 단위로 사용. 나머지 route의 B0 BB prior 추정거리로 bin을 배정한다. held-out route의 GT/잔차를 학습에 사용하지 않는다. r_base의 표본평균, ddof=1 분산을 계산한다.
- CV는 각 bin의 3개 LORO 분산 추정값의 표본표준편차(ddof=1)/평균. 각 near bin의 모든 holdout 셀 n>=30, 유한 양의 분산, CV<=0.5를 요구. 불충족 셀은 합치거나 대체하지 않는다.
- P2는 GT episode 존재로 판정. 이전 추정거리 inventory는 별도 preliminary 파일로 보존.
- P3: GT 축 posterior 오차의 MB-BB, 14조건 전체 계산. 주 분석6조건 첫 통과가 모두 |post-pre|>=0.5|post|이어야 Go. |post|<=1e-12cm 또는 유효 창 부재는 NA. 이 비율은 기술적 형성 지표이며 인과 판정이 아니다.
- P4: trace의 전체 2x2 S=H Pprior H^T+R, nu 고정. Rss만 P1 값으로 교체. gate는 원본 m_core.py의 chi2(.99,2)=9.21034037197618. BB/MB 모두 같은 A_B로 비교.
- d_est<1.5는 해당 LORO bin 분산, 1.5<=d_est<2는 1–1.5 bin 분산과 원래 packet V 사이 log 선형 보간. 그 밖에는 V. 필요한 bin n<30 또는 분산 부적합이면 P4 해당 창 NA. P1 전체 No-Go여도 유효 셀의 P4는 기술값으로 계산 가능하나 replay 진행 근거로 쓰지 않는다.
- 신규 거절 수/기존 A_B 수용 수가 P4 주 비율; 전체 창 packet 분모의 비율도 함께 기록. P4>20%이면 gate 지배 경고 및 Go 보류(원문 전 항목 통과 규칙 보수 적용).
- 단계0 No-Go면 실험1/2a/2b 모두 실행하지 않는다. 실패는 검산 오류와 통계/표본 운영기준 미충족을 구분한다.
