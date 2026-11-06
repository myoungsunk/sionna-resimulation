# FP-SC T0/T1 — 미정정 오류 우선, 두 RX 초기 에지 진단

상태: 새 사용자 요청에 따른 탐색적 원시자료 재분석. 기존 운영 코드·점수·임계값·실패 기록 불변. 기존 E1-02/E2/S3 및 FP 교체·EKF 재귀·새 RF·학습은 실행하지 않는다.

원본 SHA: e4930310987ca89c4ce7d71f33f1a7e3d799fddf. 과거 6건만으로 결론을 만들지 않는다. Full 3136의 원래 오류1003(그중 미교체998), 정상2133 및 Native-LoS3136을 전부 포함한다. C/P/M/PM은 반복 평가이지 독립 표본이 아니다. 916/87의 크기 구분은 원시 row에서 다시 산출하고 과거 clean cohort 값을 강제하지 않는다.

## T0
기존 ROWS.csv, 원시 online/evaluator NPZ, S2 결과/영수증, S1 manifest를 pinned GitHub에서 읽고 payload SHA256·시간·pose·원래 detector tap·reference tap을 대조한다. 과거 raw/reference/selected/사유·wrong_score 문턱 미달 등을 각 packet에 연결한다. 분모 불일치면 STOP. 단순 파일명/LFS pointer 존재로 원시 확보를 주장하지 않는다.

## T1: 사전 고정한 CIR-only 신호
동일 Hrf에 원래 Hann257/IFFT1028 관측체인을 적용한다. 기존 CandidateConfig와 VAB의 noise/prominence/left-rise/30%/15%/cap64를 변경하지 않는다. 원본 후보 생성기와 별도 scalar raw detector를 대조한다.

- O0: 기존 strongest-RX 30% raw FP.
- O1: VAB에서 실제 지원되는 가장 작은 tap. e-1이 들어갈 수 있으므로 earliest edge로 부르지 않는다.
- O2: 각 RX의 자체 최대 진폭30% crossing. 해당 포트와 그 crossing이 기존 noise/numeric floor 이상일 때만 유효. 두 포트의 유효 crossing 중 최소.
- O3: VAB 채택 lobe의 실제 edge_tap 중 가장 이른 값. edge 자체가 유효 지원 tap인 lobe만 사용. P/M, GT, 참조는 절대 사용하지 않는다.
- 포트별 crossing/edge 차이, O2/O3와 raw의 불일치를 **오류 경보 후보**로 평가한다. 이는 FP가 실제 틀렸다는 확정이나 교체 실행이 아니다.

GT/LoS reference는 모든 CIR-only 특징 계산 뒤에 평가용으로만 연결한다. 정확 일치, ±1tap, 오류 방향, 탐지 TP/FN/FP/TN, 998미교체 중 경보·참조도달 가능수, 정상 FP 훼손 위험, 보류율을 따로 계산한다. 1,003건은 class-conditional 분석이며 정상대조를 제외한 accuracy로 정책 채택하지 않는다. 임계값 탐색·결과 맞춤 튜닝 없음. 현재 그림에 맞춘 새로운 CFAR/분류기/P중심/M정정은 T2 이후 별도 검토다.

## 저장·범위
전체 packet 특징 및 998건 목록, 에피소드, route/sign/크기/기존사유별 요약, 입력·코드 해시, raw parity, 자체 검산 결과를 새 폴더에만 저장한다. 오류와 정상 모두에서 경보가 늘 수 있으므로 탐지 증가를 성공으로 단정하지 않는다. 대표 사례는 원래 미교체 사건에서 시간순 고정 선택하며 기존6교체만 다시 선택하지 않는다.

CPU affinity 최대3 logical CPU, 수치 라이브러리1 thread, 최대20분. 실행환경은 GitHub Actions Linux이며 기존 Snowball 실행을 했다고 부르지 않는다. GitHub API로 필요한 고정 파일만 가져와 전체 저장소 복제/과거 계산 재실행을 피한다. 원본 LFS·source 접근 불가나 검산 불일치면 실패를 보존하고 분석 결과를 만들지 않는다. 자기검산만 수행, 독립감사 아님.
