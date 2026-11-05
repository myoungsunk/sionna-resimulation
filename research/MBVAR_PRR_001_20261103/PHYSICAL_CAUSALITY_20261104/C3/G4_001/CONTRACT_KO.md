# C3-SM2-YAW-001 실행 전 상세 동결 계약

상태: G0 독립 SPEC 감사 제출용. 아직 SPEC PASS / 코드 GO / RT 실행 증거가 아니다.
기준 제안: PR #35 `82a4817415bf71cf2d1f4e9a317c18cb23ab03bc`. 기존 초안은 보존하며 이 문서는 실행에 필요한 수치·QA 정의를 추가한다. 기존 C0–C2 및 SM0 자료는 재실행·수정하지 않는다.

## 질문과 범위

같은 위치에서 RX body yaw만 바꾸었을 때 직접파 안테나 응답과 다중경로의 추가 효과가 각각 어떻게 바뀌는가? 경쟁 설명은 직접파 응답 변화, 동일 tap의 복소 간섭 변화, detector tap 선택 변화이다. 상태추정 성능·온라인 guard·인과 경로 전체의 규명은 범위 밖이다.

Mother는 PROPOSER 후 IMPLEMENTER를 순차 수행한다. 독립 AUDITOR는 별도 읽기 전용 감사자이다. 자기 검사와 독립 감사를 구분한다. 공통 RESEARCH-GOVERNANCE-v1 및 해당 역할 원본의 SHA256을 GOVERNANCE.json에 기록한다. PR35에 별도 버전 고정 governance가 없으므로 로컬 공통 계약을 사용한다.

## 조건·좌표·입력

새 조건 namespace는 `SM2_<coordinate>_Y<signed-yaw>`이며 기존 pose_id로 위장하지 않는다. 아래 SI m 좌표는 소수 6자리 표시를 임의로 반올림한 값이 아니라 원본 SAMPLES.json의 정확한 JSON 숫자와 같다. 원본 SAMPLES·timeline·SM0 RAW/MANIFEST 해시를 INPUT_LOCK.json에 묶는다.

|좌표 ID|x|y|z|출처|
|---|---:|---:|---:|---|
|R4_168|5.251464|0.325895|0.45|R4_aB_m0 pose168, 원 yaw -31.700092 deg|
|R5_982|1.521387|-0.338994|0.45|R5_aB_m0 pose982, 원 yaw 2.990632 deg|
|P10Yp|10|0.35|0.45|사전 제안 공간 대조|
|P10Yn|10|-0.35|0.45|사전 제안 공간 대조|
|P139Yp|13.9|0.35|0.45|사전 제안 공간 대조|
|P139Yn|13.9|-0.35|0.45|사전 제안 공간 대조|

각 위치 yaw 순서 `[0,180,35.7,-35.7]` deg. G2는 R4_168 네 조건만 허용한다. G3 잔여 20조건은 G2 독립 DATA PASS 뒤 별도 사용자 승인 필요. 반복 QA는 새 과학 조건이나 독립 표본이 아니다. 기존 actual-yaw 캡처 2건은 읽기 전용 출처 대조이며 재추적하지 않는다.

Z-up/right-handed; Rz(yaw)는 body/antenna local→world 능동 회전이며 +z에서 볼 때 양의 yaw는 반시계. antenna mount=0이고 ±45는 FFD 포트 자체의 정의이므로 추가 45도 회전 금지. TX rotation diag(1,-1,-1), TX=(10,0,2.7-0.05), RX z=.45. float 계산값 2.6500000000000004를 원본처럼 사용한다. Sionna의 ZYX Euler 라디안 변환은 원본 corridor_sionna_run.euler를 사용한다.

원본 scene은 20×2.4×2.7 m 내부 6개 경계면이다. RT에는 로봇 몸체 산란체가 없으며 yaw는 RX 안테나 자세만 회전한다. 충돌 QA는 footprint 반경 hypot(.6,.4)/2 + .1m clearance로 x 양쪽 끝과 |y|<1.2에 대해 보수 검사한다. 모든 지정 좌표에서 이 검사를 통과해야 한다. 원본 scene/material/PLY SHA를 정확 일치시킨다. 물리적 실측 로봇 형상을 추가하지 않는다.

전체 SOURCE_HASHES.json 및 실제 모든 파일, ±45 FFD NPZ, solver CONFIG 전체 dict, 257주파수 배열, 원본 source scripts/modules, SM0 amended producer/native_math/qa/diagnostics 및 RUNTIME_LOCK을 SHA로 동결한다. Python3.11.17/NumPy1.26.4/SciPy1.14.1/SionnaRT2.0.1/Mitsuba3.8.0/DrJit1.3.1, LLVM·WSL·배포 패키지·환경 모두 기존 RUNTIME_LOCK과 일치해야 한다. DrJit/BLAS/OMP/MKL 1 thread. PathSolver 설정 전체는 원본 CONFIG에서 읽으며 max_depth3/seed20260924/samples_per_src100000 등을 일부만 재작성하지 않는다.

## 저장과 수치 판정: 원본 archive와 신규 yaw를 구분

각 조건 257 bins, TX +45 column0, RX [+45,-45]. native raw a complex64/tau float32와 source index/valid/objects/interactions/primitives/vertices/angles를 그대로 보존한다. 원본 `a[:,0,:]*exp(-2j*pi*np.float64(f)*tau)`의 complex64 per-ray phase를 사용한 semantic group 합(complex128)이 물리 attribution 기준이다. 독립 F64 phase 합은 별도 진단·closure로 저장하며 이를 attribution 기준으로 교체하지 않는다. per-bin native cfr API 출력도 별도 저장한다.

새 yaw에는 archived Full/LoS가 없다. archive 관련 필드는 `NOT_APPLICABLE_NEW_YAW`로 표시하며 가짜 archive나 기존 다른 yaw 채널을 넣어 통과시키지 않는다. 고정된 검사는 다음과 같다. 기준은 새 RF 결과를 보기 전에 동결한다.

1. 원본 per-ray legacy와 F64 vector replay는 저장 배열과 exact equality. 그룹 membership/count/missing/source index와 semantic chain을 원시 objects/interactions/valid에서 다시 계산한다. DIRECT는 bin당 정확히 1개이며 geometry delay 절대오차 ≤1e-12 s. NaN/Inf, 비영 invalid, 미확인 object, 중복/누락 bin, dtype/축 오류, DIRECT 부재는 STOP.
2. 그룹 F64 합 대 scalar compensated trig 합 및 legacy 그룹합 대 scalar compensated legacy 합: joint와 각 RX relative L2·max-normalized ≤1e-8. zero denominator는 임의 floor로 통과시키지 않고 STOP. 개별 bin의 원시 replay는 exact check이므로 global norm이 개별 변조를 숨길 수 없다.
3. 직접파 coefficient(phase 제거 전 a)의 원본 bank 독립 Cartesian projection 검산: TX/RX local 입사각에 원래 FFD complex bilinear interpolation을 적용하고 spherical basis→world 변환 후 내적하여 a_RX,TX=E_RX·E_TX·lambda/(4*pi*r). 원본 los_check와 같은 전기장 정규화 sqrt(2*pi/376.730313668), RX conjugation convention을 따른다. 257 bins 전체 2×2 port coefficient joint relative L2와 각 RX 행 relative L2 ≤1e-4, 각 bin joint relative ≤1e-4; geometric tau ≤1e-12 s. 포트별 오차를 모두 기록한다. 새 direct-only RT 실행 없이 저장 Full trace의 DIRECT ray를 검사한다.
4. 결정론 반복 QA: 각 조건 bin indices [0,128,256]에서만 최초 trace 직후 같은 scene/cfg/seed로 1회 추가 호출한다. 총4×3=12 QA 호출, 본 캡처1028 호출과 별개로 기록한다. raw a/tau/valid/objects/interactions/primitives/vertices/angles/source_index/labels는 exact equality, 채널 relative·max-normalized ≤1e-8. 반복 ray를 새 과학 조건으로 세지 않는다. 실패 시 첫 mismatch를 보존하고 다음 bin/조건 및 확장 STOP. 자동 재시도 금지.
5. 모든 bin에서 scene.frequency, TX/RX position/orientation, source hashes 및 전체 solver cfg가 해당 동결 입력과 같아야 한다. yaw 이외에 조건간 차이가 있으면 STOP. FFD bin index와 frequencies_hz SHA도 동일해야 한다.

실행 전 음성검사: GO 없는 실행/이전 SM0 GO/허용 외 coordinate·yaw/코드·입력·환경·threshold drift/기존 출력 덮어쓰기/deg-rad·mount·RX 미회전/포트·주파수·그룹 변조/legacy-F64 대체/가짜 archive/누락·NaN·zero denominator를 거부한다. RT import·scene 생성·출력 생성 전에 GO·해시·범위 검증을 마친다. 독립 감사자가 코드와 음성검사 범위를 확인한 뒤 exact SHA GO를 발급한다.

## 산출물과 후속 분석

조건별 RAW.npz, bin별 원시 NPZ, scene binding, MANIFEST, QA 및 ARTIFACT_HASHES. 전체 INDEX.csv와 빈 FAILURES.jsonl/실패 원문, 실제 command·code commit·GO SHA·start/end·exit·runtime을 저장한다. 실패해도 원자료 보존, 덮어쓰기 금지. 원본 SM0 파일은 수정하지 않는다.

G2 DATA 감사는 4조건의 입력/원시 closure/direct projection/반복QA/무결성을 판정한다. G4 수치 분석은 저장 ray만 사용하여 다음을 계산한다: Hann257/IFFT1028, RX 양포트 최대전력 CIR, peak30% leading-edge selector, s=(Pplus-Pminus)/(Pplus+Pminus), range=tap*c/(1028*df). LoS 선택 tap에서 fixed-tap 항과 Full selector 추가항을 나눠 eMP=sFull-sLoS와 합이 절대오차≤1e-12인지 검사한다. ±4 tap window·개별 group power·복소 cross term을 보존한다. denominator 0 또는 정의 불가능하면 누락 사유와 STOP으로 남긴다.

원래 source-model h_s와 Hpsi는 G4의 별도 source-model 평가로 한정한다. pinned 원본 FFD 관측모델을 synthetic [x,y,yaw(rad),bias0]에서 평가하며 Hpsi(s/rad)를 s/deg로 바꿀 때 pi/180을 곱한다. 독립 중심차분 eps=1e-5 rad와 eps/2를 사용하고 각 차분 양끝의 tap·interpolation active cell을 기록한다. branch 변경이면 미분 판정 불가를 표시하고 smooth analytic derivative 일치를 주장하지 않는다. 동일 active branch이면 |error|≤1e-6+1e-4|Hpsi|를 두 eps 모두 만족해야 한다. 이 모델 미분을 새 RT 실제 yaw 미분 또는 총 Fisher 정보라고 부르지 않는다. 4개 RT yaw만으로 local physical derivative를 식별했다고 주장하지 않는다. 이 G4 모델 평가가 끝나기 전 G4 완결을 선언하지 않는다.

정규화 지표는 Erel=norm(actual-reference)/norm(reference), Emax=max(abs(actual-reference))/max(abs(reference))이다. reference norm 또는 peak가 0이면 undefined로 STOP한다. repeat raw 비교는 shape/dtype와 모든 원소의 exact equality이며 endian/layout은 저장 메타데이터로 기록한다. 결정론 비교에서 순서가 바뀌어도 임의 정렬로 통과시키지 않는다.

G4 source-model provider는 INPUT_LOCK의 `source_model_g4`에 고정한 C1B 캐시 `legacy/research/FFD_P0P3_20261016/source_model.py`와 `p0_initial.py`, 원래 ENV_LOCK 및 C1B INPUT_LOCK의 전이 의존성이다. G4 진입 전에 해당 전체 전이 의존성과 source-model wrapper CODE를 별도 검증해야 하며 G2 GO는 G4 모델 초기화 권한이 아니다. 따라서 G2의 raw DATA PASS가 G4 모델 계산 완료를 뜻하지 않는다.

같은 위치의 모든 6 unordered yaw pairs를 표시하고, signed difference는 PLAN의 yaw 순서에서 뒤-앞으로 정의한다. eMP 변화·same-tap/selector·복소 직접/반사파를 모두 보고한다. 오프라인 stored-ray group 제거는 실제 벽 제거와 구분한다. coordinate blocks, 선택된 위치와 정해진 yaw라는 한계를 보존하며 24조건을 독립 환경 표본으로 세지 않는다. 수치 QA를 통과한 null effect도 유효한 DATA ACCEPT이다. 기대 방향·최소 효과크기를 통과조건으로 쓰지 않으며 유의성 검정이나 모집단 성공률을 만들지 않는다. 24조건 완료 전 일부 결과는 canary 1위치/4yaw로 명시하고 전체 C3 완료로 표시하지 않는다.

G0 독립 SPEC→G1 독립 CODE/GO→G2 4yaw DATA→별도 승인 G3→G4→G5 독립 결과/주장/게시 감사 순서. 단계 통과, 실행 성공, 독립 감사, 물리 해석, 알고리즘 채택은 별개이다. 첫 실패는 보존하며 G3 및 downstream STOP. 기존 전체 채택 NO-GO/실시간 HOLD 유지.
