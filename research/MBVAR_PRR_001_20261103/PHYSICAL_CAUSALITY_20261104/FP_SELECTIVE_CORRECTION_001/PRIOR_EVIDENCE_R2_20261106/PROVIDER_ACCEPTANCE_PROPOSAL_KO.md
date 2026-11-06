# P/M 요구오차와 provider 수용 제안 — 비동결

질문 FP-SC-PROVIDER-ACCEPTANCE-PROPOSAL. PROPOSER / 코드 읽기·산술 자체검사.
기준 94b49a5abe8443b8eacf4a1e3600ad3d52b10e9f, 2026-11-06 KST. 기존 실행결과를 본 뒤의 제안이며 기존 실험의 사전 기준이 아니다.
COMMON_CONTRACT / ROLE_PROPOSER 로컬 v1 적용. 기존 RUN_001/RUN_RECEIPT.json의 governance_hashes에 연결한다.
생산 코드/기존 실패/VAB/승인 파일 변경 없음. E1-02/E2/새 실험 실행 없음.

## 코드로 확정되는 사항
selection.py:88 native_support는 x/y/yaw 공분산의 중심+고유벡터 양쪽 2sigma 7점을 SourceFFD 실제 검출기로 mapping하고 min/max에 0.15m를 더한다.
이는 보정된 95% 구간이 아니다. Pprior의 bias·과신이나 7점 사이 불연속을 포괄하지 못할 수 있다. 폭1.5m 제한도 정확성 보증이 아니다.
contracts.py:Support.residual = distance(r,[low,high])/0.15. score=0.7*(-log support)+max(p,m)^2.
P는 detector-distance 구간을 요구한다. STEP_M=0.149552259m/tap. 구간 밖0.15m이면 잔차1, 점수기여1이며 wrong_cut2에 큰 영향을 준다.
selection.py:TrustedHistory.support의 M 중심=이전detector_m+현재native_offset-이전offset.
반경=max(0.2*age,누적abs(ds))+0.02+0.15m. age상한2초. 정상속도 상한 내에서0.2초시0.21m,2초시0.57m.
이전 FP 오차, 두 offset 차이의 모델불확실성, 누락 이동량 오차가 별도 항으로 표현되지 않는다. 고정slack이 이 모두를 덮는다는 근거가 필요하다.
M도 native offset 때문에 prior/Heading/모델에 의존하며 순수 독립DR 규칙이 아니다.
detection.py:prepare_detection은 P/M active_wrong_score=None; RawDetectionHistory는 reset 후support=None. VALID provider만 추가하면 활성화되는 구현이 아니다.

## 요구오차 정의 제안
P: 위치/Heading의 일률적 오차한계를 발명하지 않는다. 사전 정의된 상태 불확실성 집합 X와 모델오차로부터 실제 검출좌표 f_det(X)의 구간을 계산하고 참조포함을 평가한다.
radial/tangential/yaw/결합 방향별 mapping 오차를 검증한다. 국소미분을 쓸 때도 peak/경로 전환에서는 유효하지 않으므로 직접 envelope 또는 UNKNOWN이 필요하다.
P 위험사건은 VALID_P인데 평가 참조detector-range가 최종P지원구간 밖인 경우로 제안한다. 구간밖0.15m 초과(p>1)는 심각도층으로 별도 집계한다.
M: 이전rawFP오차 E_FP + 이동거리 상계 L_move + offset차이오차 E_delta_offset를 포함하는 구간이 필요하다. 현재 speed/slack를 새 오차항에 중복 합산하지 말고 항별 범위를 정의한다.
M 위험사건은 VALID_M인데 참조가 최종M구간 밖인 경우. 원래rawFP를 믿을 근거가 없으면 P가VALID여도 M은UNKNOWN.
평가용GT/LoS는 provider에 주입하지 않는다. 관측한 참조tap은 offline proxy이며 운용 ground truth 인증이 아니다.

## 오차 수치의 의미
점수기여 허용변동을 가령0.25로 연구목표 설정하면, p=0에서 구간밖으로 최대0.075m 이동할 때 기여0.25다.
그러나 p=1에서 같은 점수변동을 허용하는 추가오차는0.15*(sqrt(1.25)-1)=약0.0177m뿐이다.
따라서 '7.5cm면 항상 충분' 또는 '15cm이내면VALID'는 잘못이다. score margin과 원래 잔차에 따른 민감도를 함께 봐야 한다.
0.25는 코드의margin0.5 절반을 배정한 제안 예시일 뿐 안전성에서 도출된 수치가 아니다.

## 확보 가능한 근거
현재: 원본controls/초기화/기각포함nu,S,NIS/mask/이전posterior로 인과적 일관성 검사는 가능. 상호독립 정확도증거는 아니다.
가능한 신규 근거: UWB와 독립적으로 보정된 절대pose 관측(측량초기화·외부추적·독립기준점 등), 별도 검증된wheel/gyro오차 상계와 시간동기 자료.
이들은 확보 후보이며 현재 연결/보정/정확도/접근권한이 확인된 센서라고 주장하지 않는다. robotSLAM을 자동으로GT로 채택하지 않는다.
rawFP 신뢰는 검증된 과거측정·독립지원구간 포함과 모델범위 근거가 필요하다. 연속2회/high-support만으로 신뢰 부여 금지.
없으면 P/M UNKNOWN 유지. 독립센서가 반드시 유일한 해결책이라는 주장도 하지 않는다. 명시적 모델오차 경계와 초기화근거의 결합으로 제한된scope를 검증할 수 있으나 현재는 미확립이다.

## 수용 기준 제안(새 검증 전 동결 필요)
1. 구조: 미래/GT/LoS누출·현재판정자기인증·cross-arm혼합·근거없는VALID0건. priorID/시각/recipe 불일치 즉시거부.
2. 위험: 연구진입의 잠정목표로 P/M각각 위험한VALID 비율의 단측95%상한≤1% 제안. 운용안전인증 수치 아님.
3. 가용성: 미리 지정한 전체 평가분모에서각각≥10% 제안. 최소실용성 선별선이며 code유도값 아님. 경로별도 적용하고 선택된subset만 분모로 삼지 않음.
4. 포함률+폭: 각provider지원구간의 coverage와 폭전체분포 공개. P폭≤1.5m 유지. M폭상한은현2초이내최대0.57m반경을 안전상한으로 전용하지 말고 새 이동/모델오차계약에서 정함.
5. 시간: 구조오류/만료/재초기화는 다음결정 전에강등. 유한값회복만으로재활성화금지. 물리오류탐지·복구시간은 별도요구예산 미정; 2초를 검증된유효기간으로 취급하지 않음.
6. 표본: 위험분모VALID가0 또는 독립자료부족이면판단불가. 이상적인독립이항/실패0 가정에서1%단측95%상한에299개VALID시험필요. 연속행·20초블록·개입복제는 이표본수로 인정하지 않음.
episode중하나라도위험한VALID면해당episode실패로평가하는보조관문을권고한다. 이는packet조건부위험과별도지표다. 다중경로/개입 동시보장은다중성보정이필요하므로299를모든층공통보증으로사용금지.
모든항목은P/M별·경로별·개입별보고. 빈층은N/A. 공통오류/자기지지합성반례는위험률추정이아닌 구조거부검사로구분한다.

현재 자료로 위숫자를채택하거나통과했다고할수없다. 기존R2/R4/R5는노출개발자료이며새고정검증자료와용도범위를먼저등록해야한다.
다음작업 우선순위는초기화·모델오차·과거rawFP근거확보→P/M지원구간계약→provider/소비경로수정과구성요소검사→별도승인E1-02다.
C-only실패는별도점수보정문제로보존하며provider위험기준을완화하는근거로쓰지않는다.
