# C3 G4 실행 인스턴스 — 원래 계약의 물리 분석

질문 C3-SM2-YAW-001. Mother IMPLEMENTER, 별도 읽기 전용 AUDITOR. 기준 PR35 `a9f5285a789d82236c4bdc7e674c28c526801ed9`. governance는 기존 GOVERNANCE.json의 동일 해시를 유지한다. 사용자 2026-11-05 요청: 확보한 24조건으로 기존 계약의 코드·의존성 검증 후 G4 분석, 독립감사, GitHub 게시. 새 RF·학습·EKF·guard·하드웨어 실행은 없다.

CONTRACT_KO.md 원문과 조건·임계값·주장 경계는 변경하지 않는다. 선행 G2 4조건 및 G3 저장 데이터 20조건 ACCEPT만 사용한다. G3 원래 실행 FORCED와 결함 미해결 상태를 보존하며 정상 종료로 소급 변경하지 않는다. G4는 저장 데이터만 분석하는 별도 정상 종료 기록을 갖는다. 원래 actual-yaw R4/R5 2건은 읽기 전용 출처 대조로 연결하며 24조건이나 36쌍에 섞지 않는다.

## 실행 전 관문

INPUT_LOCK은 24개 RAW·MANIFEST·QA·조건별 해시 목록, 선행 감사·복구 기록, C1B INPUT_LOCK의 원래 source-model 전이 의존성 전체(legacy 파일 11개와 ENV_LOCK), FFD bank, 원래 diagnostics.py, governance를 묶는다. 모든 크기·SHA를 확인한 뒤에만 분석 모듈을 초기화한다. SourceFFD를 원문 그대로 로드하고 load_banks의 과거 출력 부작용을 피하기 위해 원래 pattern_apply.Bank 배열을 명시적으로 전달한다. 원래 p0_initial, p3_rf_adapter4, observation, hs_lut, corridor 및 package initializer도 고정하고 실제 import 경로·해시를 확인한다. core.py는 고정하되 EKF 실행·초기화하지 않는다.

Native RT 생성의 WSL 환경과 구분해, 원래 관측모델의 C1B ENV_LOCK에 고정된 Windows Python3.13.15/NumPy2.2.4/SciPy1.15.2 및 나머지 패키지·실제 BLAS 1 thread를 사용한다. 저장 legacy_group_fields complex128과 원래 complex64 per-ray 값을 그대로 읽으므로 새 NumPy 환경에서 float32 RF 위상을 다시 생성하지 않는다. RT 모듈은 import하지 않는다. 이 실행 환경 선택은 원래 모델 재현 환경을 적용하는 것이며 RF 생성 계약 변경이 아니다.

사전 수학 음성검사와 의존성 검사 후 독립 SPEC/CODE GO 필요. GO는 전체 bound_files·SPEC·CODE 수신증·출력 RUN_001과 연결한다. 게시된 정확한 코드·GO를 확인한 뒤 새 출력 폴더에 한 번 실행한다. 첫 실패 STOP, 출력·원본 보존, 자동 재시도 금지. 새 GO 없이 코드 변경·재실행하지 않는다.

## 수치와 출력

각 RAW에서 기존 legacy_group_fields를 raw original_field와 source_group/offsets로 다시 집계해 exact equality를 확인한다. 저장 legacy_native_full도 exact equality. CIR 선형성은 기존 계약의 joint 및 각 RX Erel/Emax 정규화 정의와 1e-8 기준을 사용한다. reference norm 또는 peak가 0이면 STOP한다. 원소별 상대오차를 0 부근 tap에 적용하지 않는다. F64 그룹으로 대체하지 않는다. 같은 semantic chain을 합산하며 서로 다른 yaw의 개별 ray index를 짝짓지 않는다.

원래 diagnostics.cir/detect/signed/decomposition을 사용한다. Hann257/IFFT1028*257, strongest RX의 진폭(magnitude) peak 30% leading edge이며 전력 30%가 아니다. RX peak 동률은 첫 RX(+45), threshold 이상인 tap은 첫 인덱스를 택한다. ±4 tap 창은 modulo1028 순환 인덱스다. s=(Pplus−Pminus)/(Pplus+Pminus), range=tap*c/(1028*df). Full−LoS 편파오차를 LoS tap 고정항과 selector 추가항으로 나눠 잔차≤1e-12. zero denominator·비유한·중복/누락 조건·축/주파수 오류는 STOP.

각 조건의 Full/LoS/reflected 복소 스펙트럼과 CIR·전력, 두 fp 기준 ±4 tap의 모든 group 복소 창·개별 전력, 중앙 tap의 모든 group-pair cross term(2Re(g_i*conj(g_j)), 대칭 행렬의 상삼각만 합산)을 저장한다. 대각 성분은 별도 개별 전력이다. Full power=개별 전력 합+상삼각 cross 합을 각 RX에서 relative1e-8+absolute1e-28로 검사한다. 원래 계약의 복소 폐합 검사에 대응하는 계산 QA이며 RF 임계값을 완화하지 않는다. coherent power allocation과 전체 group/표면 제거 후 fixed-tap·재검출 변화도 별도 CSV로 보존한다. 삭제는 저장 경로 스펙트럼 개입이며 실제 벽 제거를 뜻하지 않는다.

표면 제거는 해당 표면을 포함하는 semantic group의 합집합을 한 번만 제거한다. 같은 표면의 반복 bounce 또는 여러 chain에 의해 한 group이 중복 차감되지 않는다. group/표면 제거 후 고정 tap 또는 재검출의 분모가 0이거나 비유한이면 STOP이며 None·epsilon·임의 누락으로 대체하지 않는다.

모델 입력은 [x,y,yaw(rad),bias0], mount0, anchor(10,0,2.7−.05), z=.45. 원래 SourceFFD h_s와 analytic Hpsi(s/rad)를 기록하고 s/deg=Hpsi*pi/180. eps=1e-5rad 및 eps/2 각각의 양끝과 중심에 대해 h_s·tap·strong port·모든 interpolation cells를 저장한다. 어느 step에서든 branch가 다르면 해당 조건은 UNDEFINED_BRANCH_CHANGE, 미분 일치 주장 제외. 같은 branch인 step은 각각 |FD−Hpsi|≤1e-6+1e-4|Hpsi|를 만족해야 한다. 두 step이 모두 같은 branch이면 VERIFIED_SMOOTH. 부호·단위·분모는 수식 그대로이며 경계 표본을 임의 제외하거나 새 임계값으로 통과시키지 않는다. h_s는 원래 source-model이고 측정 Full s나 새 RT 직접파 미분이 아니다.

6좌표 각각 yaw순서[0,180,+35.7,−35.7]의 6 unordered쌍, 총36쌍을 뒤−앞 signed delta로 보고한다. sFull, sLoS, eMP, fixed, selector, Full/LoS tap·range·포트전력, h_s/Hpsi 차이를 포함한다. ΔsFull=ΔsLoS+Δfixed+Δselector 잔차≤1e-12. 모든 표본·null effect·반례를 보존하며 유의성·모집단 성공률·자연주행 원인 전체·Fisher 정보·EKF 성능·채택/실시간 개선을 주장하지 않는다. 기존 NO-GO/HOLD 유지.

실행 결과·누락/실패 원문·command·runtime·모듈 경로·코드/GO/입출력 SHA·실제 정상 종료를 기록한다. 독립 검산은 구현의 physics.py를 import하지 않는 별도 계산과 원래 모델 API 직접 호출로 검증한다. 결과/주장·게시 감사를 구분해 기록한다. 기존 C0–C2·G2·G3 파일은 바꾸지 않는다.
