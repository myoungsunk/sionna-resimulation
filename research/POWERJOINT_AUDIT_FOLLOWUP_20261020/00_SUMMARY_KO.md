# S0 사후 정정·모집단 감사 결과

S0 완료. S1/S2/S3, 새 재귀 필터 계산, RF 시뮬레이션은 실행하지 않았다. S0-5 보존 완료를 먼저 확인한 뒤 나머지 정정과 통계를 수행했다. 아래 작업 상태와 과학 판정은 별개다.

| 세부 과제 | 주장/검사 | TECHNICAL | 작업 상태 | 과학·유효성 판정 | 핵심 결과 | commit / run / artifact |
|---|---|---|---|---|---|---|
| S0-5 | 원래 감사가 참조한 입력·trace 보존 | PASS | COMPLETE | 보존 사실만 확인 | 44개, 1,883,401,358 bytes; 원본 API digest·전체 다운로드·release 전체 재다운로드 일치 | lock a37364c; 실행9354b20; receipt f7a0ef3; run39367272729 /12239593294 |
| S0-1 | SRC_TAP 적용성 정정 | PASS | COMPLETE | INVALID_DESIGN_ZERO_RANGE_JACOBIAN | 기존 CSV·판정 보존; B_OLD/B_REFIT_ONLY 유효 | VALIDITY_INDEX.json; 결과 commit은 PUBLICATION_RECEIPT.json |
| S0-2 | Native LoS 9,519점 B_OLD 잔차 | PASS | OPEN | NOT_ESTABLISHED | R2 A M45 mean −0.010192554m: 고정 abs(mean)<0.01m 실패 | lock c2bf8b8; run39368572991 /12239939880 |
| S0-3 | 슬라이드2 모집단·관측식 구분 | PASS | COMPLETE | SOURCE_CONFIRMED; 인과 NOT_ESTABLISHED | 구1303행 전체/FrozenLut; 새829행 t≥30/SourceFFD; 새 슬라이드 모집단 하나 선택 | 구run38711275905 head7d8d20c; 통계run39368572991 |
| S0-4 | D4 제외한 D3/D6 사후 T4 재집계 | PASS | COMPLETE | NOT_ESTABLISHED → NOT_ESTABLISHED | 지지0/5, 채널 전용 회수2/5; 모든 유익 이벤트 안전성 D3/D6 모두 false | POST_HOC_REVISED_ANALYSIS_T4.json; 기존run39359599833 등 |
| S0-6 | 엔진·정책 판정 명칭 | PASS | COMPLETE | 범위 정정 | 구현1 검증된 실행 기준; 구현2/3 DEFERRED_SOURCE_UNAVAILABLE; v2 정책 NO-GO | VALIDITY_INDEX.json |

## 입력 보존

기존 root summary, task/nested manifest·receipt 153개를 스캔하고 참조 run23개의 전체 artifact를 확장해 44개를 보존했다. 입력 전용·요약 전용·실패 실행 artifact도 포함했다. release `audit-traces-20261020-r01`의 자산을 덮어쓰지 않았다. 원본 API digest 누락·만료·검증 실패는 0건이다. `TRACE_INVENTORY.json`과 `TRACE_RECEIPT.json`에 전체 원본 artifact ID, release asset ID/URL, SHA256, bytes, source/run을 기록했다. 후속 S0 자신의 receipt·통계 artifact는 순환 참조를 피하기 위해 이 과거44개 모집단에 추가하지 않고 별도 실행 manifest에 기록했다.

Inventory SHA256 `0379b2668c0ab0ccef70732134c1037780f2cd637994d6672d41a8ee21c73c43`. Receipt SHA256 `dfca7790cbf4ed277eeef73ae47aeb79aa13ecc8b4f8391aa79b8874c1d995c8`. 보존 결과 artifact12239593294 전체 ZIP SHA256 `2998da585eabf1d1b4b9510de0586ffdcacdd70dd03bba4dbc18ff14f9edb3e4`. 통계 결과 artifact12239939880 전체 ZIP SHA256 `ef4d7d1c9925780b9593344a498b0afe2d8385c09c621426a30a9771071bf068`.

## SRC_TAP 무효화와 보존

**INVALID_DESIGN_ZERO_RANGE_JACOBIAN. Range 행 Jacobian = 0으로 직접 Range 감도 제거, C_rs·gate 영향만 남음. Range 교정 근거로 사용 불가**

R5 A B0 Heading 4.556146→17.904643° 및 T3/SRC_TAP, T4/SRC_TAP·POST30_SRC_TAP의 원래 수치는 남겨 두되 Range 교정·F1 검증 근거에서 제외했다. SRC 재학습 파라미터·파생 `_src`/`_delta` 열도 같은 적용성 제외 대상이다. B_OLD와 B_REFIT_ONLY는 유효하다. 원래 lock 조건과 decision은 변경하지 않았으며 추가 metadata가 사전등록 조건을 소급해 바꾸지 않는다. 수정 전37개 텍스트 파일은 ORIGINALS/와 RECEIPTS에 bytes·SHA로 보존했다. 기존 CSV357개와 DECISION27개는 byte-identical이다.

기존 “9,519점 중2,268점 미확보로 T6 BLOCKED_INPUT”은 철회한다. 전체 RF archive9,519점과 재귀 clock7,251점의 모집단 혼동이었다. 당시 실패·판정·오류는 이력으로 남긴다. SRC_TAP의 제외 사유는 입력 미확보가 아닌 설계 무효다.

## Native LoS B_OLD 잔차

원본 PACKETS_SOURCE_LABELS.csv.gz SHA256 `02038c4c967750905a80dde31b0bcd0b667bd5d11df1cb02e05023e06893ee4d`, channel=los만 사용했다. SRC 조정 cache를 사용하지 않았다. GT x/y·anchor/height로 거리를 독립 계산하고 e = range − (d + B_OLD), B_OLD=−0.5315983906250129m를 적용했다. 원본 e_r와의 최대차2.22e−15m, tap grid 최대차2.84e−14다.

Δ = 0.149552258804749m; σq = 0.043172018439419m.

| case | n | mean m | RMSE m | RMSE/σq | abs(e)>Δ/2 비율 |
|---|---:|---:|---:|---:|---:|
| R2_aA_m0 | 1303 | -0.001699179 | 0.043815719 | 1.014910 | 0.078281 |
| R2_aA_m45 | 1303 | -0.010192554 | 0.046306670 | 1.072608 | 0.099770 |
| R2_aB_m0 | 1303 | 0.004405312 | 0.047471367 | 1.099586 | 0.118956 |
| R4_aA_m0 | 922 | 0.002839029 | 0.046254528 | 1.071401 | 0.101952 |
| R4_aB_m0 | 922 | -0.000465030 | 0.047372220 | 1.097290 | 0.069414 |
| R5_aA_m0 | 1883 | -0.006111342 | 0.046016419 | 1.065885 | 0.080191 |
| R5_aB_m0 | 1883 | -0.001089568 | 0.045119636 | 1.045113 | 0.073287 |

7조건 모두 RMSE/σq는[0.8,1.2] 안에 있지만 R2 A M45 평균의 절댓값이0.01m보다 커서 전체 AND 기준은 실패했다. **OPEN / NOT_ESTABLISHED**로 남긴다. 반올림으로 PASS 처리하지 않았다. q01/q05/q50/q95/q99와 사전 고정 거리·polar theta·tap전환 그룹은 NATIVE_LOS_CASE_STATS.csv와 NATIVE_LOS_GROUP_STATS.csv에 포함했다. 빈 bin도 보존했다.

7,251행은 exact case/pose_id로 원본 RF 행과 대응하며 관측 range 최대차5.33e−15m다. 다만 RF SAMPLES의 x/y와 yaw(deg)가6자리로 반올림되어 있다. clock GT를 똑같이 반올림하면 전 행 일치하며, 원래 clock 잔차·거리도 독립 재계산으로 확인했다. 이 정밀도 차이로 잔차가 최대5.036603e−7m 달랐다. 표에는 RF_ARCHIVE_9519, RECURSIVE_CLOCK_7251(원래 clock 잔차 유지), RF_ARCHIVE_SUBSET_7251 세 모집단을 구분했다. 통계에서 새 offset을 맞추거나 행을 빼지 않았다.

## 슬라이드2: 선택한 단일 모집단

**SLIDE_SOURCEFFD_T30_829: R2 각829행, frozen clock t≥30s의 exact pose_id를 원본 RF SAMPLES 행에 대응한 SourceFFD/B_OLD 통계**를 슬라이드의 모집단으로 지정한다. GT 정밀도는 원본 RF SAMPLES(x/y6자리, yaw degree6자리)이며, 과거 T3가 사용한 unrounded clock GT와의 작은 차이를 CSV에 별도로 기록했다. 원래 관측 r·s와 exact pose ID, 반올림 좌표를 모두 검사했다. 전체1303행 비교는 감사 열이다. 수치를 보고 모집단을 선택하지 않았다.

| case | 모집단 | n | μr m | Vr m² | ρ(er,es) |
|---|---|---:|---:|---:|---:|
| R2_aA_m0 | ORIGINAL_ALL_RF_1303 | 1303 | 0.052245227 | 0.017081053 | 0.520767452 |
| R2_aA_m0 | SLIDE_SOURCEFFD_T30_829 | 829 | 0.051939957 | 0.012470482 | 0.513219180 |
| R2_aA_m45 | ORIGINAL_ALL_RF_1303 | 1303 | 0.071871809 | 0.016581825 | 0.060916713 |
| R2_aA_m45 | SLIDE_SOURCEFFD_T30_829 | 829 | 0.083510096 | 0.015806551 | -0.015300781 |
| R2_aB_m0 | ORIGINAL_ALL_RF_1303 | 1303 | 0.030688863 | 0.008066567 | 0.089960699 |
| R2_aB_m0 | SLIDE_SOURCEFFD_T30_829 | 829 | 0.019884885 | 0.007777469 | 0.114542263 |

구 보고서의 A0/A45/B0 μr(.05225/.07187/.03069), V(.01708/.01658/.00807)은 전체1303행이다. 구 e_s는 FrozenLut, 새 e_s는 SourceFFD다. 따라서 구 수치와 새829행의 차이를 관측모델 효과 하나로 설명할 수 없다. 동일1303행 SourceFFD 상관은 A0 .520767452, A45 .060916713, B0 .089960699이며 구 LUT .525/.062/.096과 구분한다. 원본 전체1303행에 timestamp가 없어 실제 초 단위 구간은 NOT_ESTABLISHED다. nominal dt로 시간을 만들어 넣지 않았다. 자세한 pinned source·line 근거는 SLIDE2_PROVENANCE_KO.md와 SOURCE_PROVENANCE.json이다.

## 사후 T4 재집계

**결과를 본 뒤 개정한 판정이며 사전등록 검증이 아님.** 원래 B_OLD INTERVENTIONS의 POST30 기술 성공 행만 집계했다. 평가 마스크는 이벤트 마지막 RF timestamp부터+30s까지 inclusive다. 이벤트5+5, 효과 정의, ≥50% 회수·전체 유익 안전성 기준은 유지했다. D4는 공분산 PSD를 보장하지 못해 제외했으며 실패를 효과0으로 대체하지 않았다.

| 유해 이벤트 | skip 개선 ° | D3 회수율 | D6 회수율 | 유효 진단으로 지지 |
|---|---:|---:|---:|---|
| R5_A_M0_x10_16_V1 | 7.740819 | 0.004375 | 0.376813 | 없음 |
| C01_A_x16_21_V1 | 5.389283 | -0.097549 | 0.313264 | 없음 |
| O03_y4_8_V1 | 1.803351 | -0.091902 | 0.779865 | 없음 |
| C01_B_x16_21_V1 | 4.318979 | 0.092046 | 0.159339 | 없음 |
| C02_A_x4_10_V1 | 1.770663 | -0.041722 | 0.065376 | 없음 |

D3/D6의 전체 유익 이벤트 안전성은 모두 false이므로 지지0/5다. 채널 제거 회수≥50% 및 D3/D6 모두<20%를 만족한 이벤트는 C01 B x16–21 V1, C02 A x4–10 V1 두 개로, 반증 기준3/5에도 미달한다. 원래 NOT_ESTABLISHED → 사후 NOT_ESTABLISHED다. 원본 DECISION.json은 SHA 동일하다. D3는 진입 시 ψ 평균만 GT로 보정하고 P와 다른 상태 오차를 유지했으므로 prior 경로 전체의 반증으로 읽을 수 없다. 개입은 ORACLE_DIAGNOSTIC이다.

## 사후 정정 목록·이름·오류

1. SRC_TAP의 적용성을 무효로 표시했고 기존 수치·조건·판정은 보존했다.
2. 과거 T6의 입력 누락 해석을 모집단 혼동으로 정정했다.
3. T4의 D4를 제외한 별도 사후 분석을 추가했다.
4. 구현1/canonical_engine.py는 **검증된 실행 기준**이며 유일한 정본 확정이 아니다. 구현2·3의 차이는 **DEFERRED_SOURCE_UNAVAILABLE**로 남는다. 파일명은 원래 식별자로 보존한다.
5. T7B의 결과는 **v2 정책 NO-GO**다. Full52/64 및 Native8/8 한도 위반은 해당 고정 정책의 결과이며 효용 target 접근 전체 기각이 아니다.

최초 lock a37364c, theta schema 보완 eaaf66f, 좌표 정밀도 인증 lock c2bf8b8을 모두 보존했다. 실행39368233370은 행 대응 불변조건에서 exit1로 멈췄다. 통계 분포 계산 전에 실패했으며, 원인은 GT 저장 정밀도였다. ERROR와 실패 artifact12240406030을 보존한 뒤 좌표 반올림의 exact 인증을 추가해 run39368572991에서 성공했다. 과학 임계값·행 선택·실패 case는 바꾸지 않았다. 게시 preflight도 로컬 다운로드 ZIP의 Git 포함을 거절해 exit1로 멈췄으며, 원격 변경 전에 archive 제외 allowlist로 바로잡았다. ZIP은 로컬에 보존하고 전체 SHA·bytes 회수 영수증을 Git에 남겼다. 원래 JSON lock 필드·original decision과 사후 metadata를 구분한다.

## 남은 미확립·제외 범위

- Native LoS 잔차는 OPEN이다. 본 단계에서 Range 모델을 고치거나 재학습·재귀 계산하지 않았다.
- 구현2·3 원본 코드 미확보로 완전 diff는 DEFERRED_SOURCE_UNAVAILABLE다.
- 구 전체1303행의 실제 timestamp 범위는 미확립이다.829 subset의 frozen clock 대응은 별도로 인증했다.
- SRC_TAP 파생 결과와 D4 진단은 검증 증거에서 제외한다.
- 독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증, s 오염 대 필터 경로의 인과 분리, q의 물리 메커니즘, 양자화의 유일 원인·조건부 불편성은 주장하지 않는다. 조건 수를 독립 표본 수로 쓰거나 p-value를 붙이지 않았다.

## 산출물 검증·검토 진입점

FINAL_QA.json: 기존 CSV357·DECISION27 byte identity, 원문37개 SHA/bytes, 기존 JSON 값 보존, JSON/CSV parse, Python 구문, 파일당20MB, 원본·release hash44개,9519/7251행 인증을 검사했다. 새 RF·재귀 실행은 없다. 적용성 범위는 VALIDITY_INDEX.json, 원문은 ORIGINALS/RECEIPTS.json, 통계 provenance는 statistics_execution/STATISTICS_MANIFEST.json, 전체 artifact 회수 SHA/CRC는 statistics_execution/ACTIONS_ARTIFACT.json을 참조한다. 결과 Git commit·원격 bytes 검증은 PUBLICATION_RECEIPT.json에 기록한다. S0에서 종료한다.


## S1 N1 이벤트 검증 — BLOCKED_INPUT

S0 감사의 ACCEPT_FOR_S1 이후 입력을 확인했으나, 고정 원본77개(기존30/신규47) 열거 CSV·재귀 코드가 미확보다. 확인된 신규 물리 이벤트는61개이며 SPEC/aggregate 선택12개도 전체 명단이 아니다. 임의 대체·선택 없이 중단했다.

| 과제 | TECHNICAL | 과학 판정 | 실제 실행 | 근거 |
|---|---|---|---|---|
| S1 N1/D7 | BLOCKED_INPUT | NOT_ESTABLISHED | 입력 감사 exit0; 새 재귀0; Actions/artifact 없음 | S1_N1_EVENTS/RESULTS_KO.md, INPUT_AUDIT.json, EVENT_PROVENANCE_DRAFT.json |

엔진034e57a 원본 byte identity 및 T2 센서 lock b05e7ead… 일치는 확인했다. 기존 주로의 실제 los_exists 원본 플래그는 미인증이다. 필요한 입력은 원래 legacy30/new47 이벤트 명단·enumerator·행/clock 매핑과 legacy LoS 존재 근거다. 미확보 상태에서 PROTOCOL_LOCK 또는77행 EVENT_TABLE을 만들어 실행하지 않았다. POWER1 재현·독립 scorer·D7 parity는 NOT_RUN이다.

S0 본문·수치·기존 판정은 위에 그대로 보존한다. S0 잔차 평균은 OPEN / NOT_ESTABLISHED이며 S1 입력 감사로 이를 닫지 않는다. S2/S3, RF 시뮬레이션, T6 tap EKF, D4 대체, 새 gate·기억 모델은 실행하지 않았다.


## S1 사용자 개정 명단 사전등록

원래30+47 목록은 BLOCKED_SOURCE_UNAVAILABLE로 확정하고 격자로 새 열거했다. 후보110개 → 포함79개(기존35/신규44), 제외31개는30초 부족. 신규 물리61행은61/61 대응한다. EVENT_LIST.csv와 PROTOCOL_LOCK.json을 재귀 실행 전에 커밋한다. 아래 후속 결과가 앞선 입력 차단 상태를 대체할 예정이며 S0 본문·판정은 보존한다.


## S1 최종 개정 격자 실행 결과

| 과제 | TECHNICAL | 과학 판정 | 핵심 수치 | commit / run / artifact |
|---|---|---|---|---|
| S1 N1/D7 | TECHNICAL_PASS_CORE | NOT_ESTABLISHED | 79개; B0 유해 D2회수≥50% 12/18; 유익 안전성 9/48 | lock cccac1f/v2 3062701; runs39370673576,39370942876; 각artifact는 S1 MANIFEST |

앞선 S1 입력 차단은 원래77개 source에 대해 유지하되, 사용자 승인 개정 격자79개 실행은 완료했다. 원래30+47 복원을 뜻하지 않는다. 첫 CSV parser 오류와 재실행을 모두 보존했으며 과학 기준은 동일하다. D7 미평가80개 event×bias 행과 특징 대응 분모는 S1 보고서에 명시했다. S0 수치·판정은 위에 그대로 유지한다. S2/S3로 진행하지 않았다.

S1 수치·패킷 CSV 게시 커밋: `4a79ab3490326c10e8bcabc9c2dbcce46f5ad5b6` (42개 분할 커밋, 약226MB). 게시 내역은 S1 PUBLICATION_RECEIPT.json에 보존했다.
