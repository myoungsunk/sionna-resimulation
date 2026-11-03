# DLP-R1B-CH4-001 — P0 계보 및 실행 타당성

## 고정 범위

IMPLEMENTER가 원본 요청서 §0–9를 실행한다. 신규 R1 Anchor B 실험이며, 기존 R2/R4/R5의 승인 집단에 R1이 포함됐다고 주장하지 않는다. 전체917시점, t≥30초767시점, Anchor B=(10,0,2.65)m, tag0.45m, mount0°, 상태[x,y,ψ,b_g], 동일 mean=0/extraVariance=0 conventional SourceFFD 비교다.

## 원본과 입력

- R1 CSV SHA256: `53e76f41cb95b32b25f2cc58844bac09c09ffd0803aa287cc69e025bb97225c4`.
- 초기 y=0.35m이나 scripted wobble 때문에 실제 y는0.3330850025–0.4390856173m다. 원본917개 pose와 순서를 그대로 보존한다.
- 최소 B 수평거리:0.3422152393930706m, pose221, t44.2s. 원본 GT에서 최소 off-boresight8.841637°로 SourceFFD 극축 cap 바깥이다.
- 과거 final_B는 method B trace/reapply 실행명이다. Anchor B를 뜻하는 증거가 아니다. 해당 원시 H를 B로 재해석하지 않는다.
- FFD 두 bank의 실제 bytes를 GitHub Actions38875080492 artifact12034154094에서 복구했다. 아카이브495,473,098bytes의 SHA256 `cad003e294edc59a4eecdbce39c02bec43d91524ecef37c93978a356ba519e8e`와 개별 bank checksum이 기존 동결 manifest와 일치한다.
- 기존 L1/L2 FAIL은 구형2° HsLut 체인의 실패다. 신규 SourceFFD/Native parity를 대신하지 않으며 새 G1로 검증한다.

## 관측·필터 계약

257개 주파수(6.2504GHz+1.95MHz·k), 대칭 Hann,1028 IFFT, strongest RX30% leading edge, 선택TX+45°, RX±45°의 공통 tap을 사용한다. Full/LoS는 서로 독립 검출한다. Full max_depth3와 LoS max_depth0는 원래 PathSolver 설정 그대로 각각 호출한다.

h_r=d−0.5315983906250129m는 기존 continuous detector bridge다. 추가 평균 보정은0이다. Native/SourceFFD의 검출 거리 비교와 LoS 검출값−continuous h_r의 물리 관측오차를 구분한다. R0=diag(0.0068578637,0.0081)은 동일 관측·단위의 기존 기준선이며 R1 잔차 분산에 적합하다고 미리 주장하지 않는다.

B0 필수와 L2 보조(gyro+0.20°/s, 동일 white-noise stream)를 보존한다. 원래 seed0 SensorV2 입력, 초기화, f/F/Q/P0, 공동 NIS9.210340371976184, Joseph 공분산을 사용한다. GT는 synthetic sensor 생성과 오프라인 진단에 한정한다.

## prospective 허용오차와 canary

P1_NUMERIC_TOLERANCES의 T06–T09/T13 및 P2/P3/P4의 명시적 정량 기준을 인용한다. Native H의 공통 위상/이득 fit은 금지한다. source complex relative max5e−4, RMS1e−4; s max2e−5, RMSE2e−6; tap/branch exact; LoS delay1e−12s; independent observer1e−10. 숫자는 신규 결과를 보기 전에 잠근다.

기하·phase만으로 canary[0,150,221,440,458,476,696,916]을 선택했다. 8개×257bin×LoS/Full=4,112개 Native solver 호출이다. 각 pose의H/CIR/FP/power와 raw path a,tau,interaction/objectID를 보존한다. 고정 canary에서 실패하면 즉시 다음 확장을 중단하며 완료bin까지의부분원시데이터를 남긴다.

## 환경과 계산비용

요청된 sionna-rt2.0.1/mitsuba3.8.0/drjit1.3.1 및 numpy1.26.4/scipy1.14.1을 별도 환경에 설치했다. CPU LLVM polarized variant가 실제 초기화됐다. 이 host의 Python3.12와 LLVM20.1은 과거 Python3.11 runner와 다르므로 bitwise 환경 동일성을 주장하지 않는다. 정확한 실제 버전/소스/mesh hash와 동일 scientific tolerances로 검증한다.

컨테이너CPU quota8cores, 메모리8GiB. Native worker1thread. 실제 canary 시간과RSS가 산출되면 해당03_RF_CANARY_QA를 근거로 P0 비용을 확정한다. 본 문서의 작성 시점에는 생산917pose RF 및P3를 실행하지 않았다. 상세 단계상태는최종보고서와기계판정JSON이우선한다.

## 승인 및 변경 계보

첫 계약·구현은commit15f593e에서보존했고, 별도 검토자의 실행 전 보완은V2계약에분리한다. 과거동결파일·원시데이터는수정하지않았다. 별도AI검토자의 소스/산술 검산은 computational independent review로만표시하며, 인간과학감사서명으로표현하지않는다.
