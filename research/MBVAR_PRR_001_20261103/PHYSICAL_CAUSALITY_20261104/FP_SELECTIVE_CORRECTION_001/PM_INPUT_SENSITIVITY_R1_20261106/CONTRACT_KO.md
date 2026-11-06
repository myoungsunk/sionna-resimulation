# FP-SC-PM-INPUT-SENSITIVITY-R1 — 실행 전 고정 진단 계약

2026-11-06 KST, PROPOSER → IMPLEMENTER → 동일 작업자 자체검사. 기준 commit 94b49a5abe8443b8eacf4a1e3600ad3d52b10e9f.
질문: 고정된 P/M raw 점수와 wrong_cut에서 지원구간 오차가 가상 탐지의 오탐·미탐·보류에 미치는 영향은 무엇인가?
기존 실행결과를 본 뒤 작성한 새로운 진단 계약이다. 과거 실행의 사전 기준을 소급 변경하지 않는다.

## 허용/금지
동적6272개 전부, VAB/TWO_PORT_UNION, 같은CIR/후보/raw FP 유지. static48 제외.
별도 raw-score 계산기는 provider/생산 detect()/select()/trusted history/EKF/SourceFFD를 호출하지 않는다.
UNKNOWN/INVALID 보호와 승인 경로는 변경하지 않는다. VALID를 만들거나 합성 선택 권한을 전달하지 않는다.
selected_tap=raw_tap을 기록한다. hypothetical flag는 실제 P/M 활성화 또는 E1-02가 아니다. E1-02/E2 시작 금지.

## 점수와 입력
기존 Policy SHA, wrong_cut=2, rf_weight=.7, prior_weight=1, mapping_slack=.15, prior폭1.5, history나이2초 고정.
score_C는 실제 prepare_candidate_set(C)의 raw 행 값. 가상 P/M/PM 점수는 score_C + max(p,m)^2, 각 mode의 해당 잔차만 사용.
p/m = 지원구간 밖 거리/.15. 실제 prepare_candidate_set과 합성200개 및 실제전파형nominal 각mode를 대조한다.
P폭>1.5이면 P/PM 보류, M없으면 M/PM 보류. 미사용P가너무넓어도M을보류하지않는다. 경계비교는현재코드의float연산그대로다.
대체gain/margin은선택조건이므로탐지flag에추가하지않는다. flag=raw score>=2만사용한다.

P baseline은SHA잠긴NOMINAL.csv의low/high. M baseline은바로이전원래rawFP*STEP_M + offset[k]-offset[j] 중심,
반경max(.2*실제age,누적abs(ds))+.02+.15. 이전rawFP는신뢰인증되지않은진단입력이며기존trusted history로승격하지않는다.
M의baseline이정답이라는주장없음. 가상flag/selected결과의이력되먹임없음. 첫행은M/PM보류.
현재mapping은관측전prior기반기록이며GT를사용하지않는다. 온라인입력계층에는low/high/offset과원본t/ds만전달한다.
ref_tap/stratum은전체진단출력저장후평가기로만결합한다.

## 64개 대조
nominal1; P중심±.5/1/2tap ×constant/jump/drift18; P폭배율.25/.5/2/4의4;
P중심±1/2tap×폭.5/2의8; M이전FP±1/2tap4; Moffset±1/2tap4;
PM동방향4/반대방향4; M이동상계배율.5/2의2; 이력지연.2/1/2/2.2초4;
이력관측누락1/2/5초와재초기화4; 기존stress7. 합계64. 6272×64×4=1,605,632 packet-scenario-mode행.
jump시점N//2, drift는해당시점부터10초선형증가. 개입전행도포함하고전후분모별도보고.
이력누락은과거raw관측가용성만제거하며현재파형과실제이동량을제거하지않는다. 재초기화시점이전이력사용금지.
기존stress는원래P low/high를그대로재사용하며M은nominaloffset그대로다. 새상태·offset·RF동시재생성이라고주장하지않는다.
interval단계의민감도진단이다. radial/tangential/Heading의새SourceFFD매핑시험이나provider성능시험이아니다.

## 분모·비교·판정
R2개발/R4R5고정평가구분은보존하되이번에는어떤경로에서도튜닝없음. 모두EXPOSED_DEV.
전체6272행, raw/ref유효, 정상0tap/1tap/큰오류2+tap, 경로/채널/개입/전후/연속20초block별보고.
TP/FP/TN/FN은점수가능표본에서정의. 보류는TP/TN성공으로세지않는다.
전체오류분모미탐부담=(FN+오류보류)/전체오류, 활성조건부미탐=FN/(TP+FN) 둘다보고.
전체정상오탐=FP/전체정상, 활성조건부오탐=FP/(FP+TN), 점수가능률/보류율전체분모공개.
C대비및동일mode nominal대비 새탐지/새오탐/탐지소실(음성전환과보류전환구분)을기록한다.
기존43904 stress와narrow exclusion11095를SHA/키/재집계로보존하고해당subset을별도집계한다. 그것만맞추는튜닝금지.
성능PASS/최적arm선택/1%10%기준설정없음. 출력은DESCRIPTIVE_COUNTERFACTUAL_SENSITIVITY_ONLY.

## 검사·자원
기존C-only raw/pool/Cscore재현6272건, 후보eligibility불변, selected=raw전수, 점수모드대조,
미래raw/이력변조불변, stale/첫행보류, VALID spoof거부, 전체키/배열shape/분모/해시, 별도저장출력검산.
논리CPU≤3/BLAS1, managed-processes로실행·종료확인. 실패는새run에보존한다. 기존파일덮어쓰기없음.
