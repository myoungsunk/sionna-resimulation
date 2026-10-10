# A23 rev3 실행 보고서: A0/S6 재현과 Q1 오차 구조 진단

작성일: 2026-10-10. **실행 완료, Q1 부분 지지, 수정 모델 채택 보류. F01/F02 미해결 및 scientific_PASS=false 유지.**

## 질문 → 기대값 → 방법

Q1은 실제 s 잔차의 편향·분산·시간 상관을 가진 합성 오차만으로 NEES 팽창과 정확도 악화를 만들 수 있는지 묻는다. 먼저 A0가 원 S6와 일치해야 후속 arm을 해석할 수 있다. A0의 heading RMSE, 위치 RMSE, NEES에는 사전 허용오차 1e-9를 그대로 적용했다. M0/W0에 NEES 3–6 등 새 통과 기준을 부여하지 않았다. 제안 폐쇄율 0.8 구간은 승인된 기준으로 사용하지 않았다.

이번 범위는 R2-A, mount 0°, P0, SNR30, drift 0/1/2, seed 0–49다. A0 150 → M0/W0 300 → Q1 S1–S8 1,200, 총 **1,650회**를 실행했다. Q2, joint arm, mount45, 다른 route/anchor, RF 재생성은 실행하지 않았다. 필터 R/Q/gate/prior/센서 설정을 arm 사이에서 바꾸지 않았다.

M0는 생성 측정오차 분산을 필터 R과 맞춘 대조군이지 전체 센서/process 모델의 완전 정합이 아니다. W0는 영평균 백색, 실제 잔차 RMS² 기반이다. S1은 편향+백색, S2는 영평균 AR(1), S3는 편향+AR(1), S4는 잔차 iid 복원추출, S5는 평균 제거 iid, S6는 평균 제거 시간 정렬 잔차, S7은 블록 부트스트랩, S8은 실제 s+백색 range다.

## 코드·입력·환경 동결과 원본 보존

별도 checkout 브랜치 `codex/a23-execution-20261010`, HEAD `f81b42d541fdf9a37b6868d4901c2a3bb9d8090e`를 확인했다. 실행 source는 이 revision의 committed git archive이며 SHA256은 `14f970938fa971c581eb81fe1d4213a274ec0aa132f4a67ba47ef48ff297636f`다. 초기 clone 과정의 LFS 다운로드 실패는 자체 checkout에서 skip-smudge로 처리했다. 남은 untracked 감사 문서/디렉터리는 보존하고 실행에서 제외했다. 다른 작업의 미커밋 source를 사용하거나 수정하지 않았다.

실행 전 계획·범위·stop gate는 같은 디렉터리의 PLAN.json, branch/HEAD/dirty 기록은 SOURCE_REVISION.json에 있다. 실행 source 내용 해시, 최종 설정과 난수 키는 원자료 OUTPUT/RUN_MANIFEST_q1.json에 저장됐다. 핵심 구현은 `scripts/drive_sim/structured_noise_control.py`, `src/qclean_uwb/drivesim/filters.py`, `experiment.py`, `sensors.py`, `observation.py`, `hs_lut.py`다. 이번 실행에서는 이 파일들을 수정하지 않았다.

원 S6 provenance의 source revision은 `0d4588f79116e221d874307f233d69ff0b13d99c`다. 원 source 대비 변경 내역과 입력 검사는 OUTPUT/PREFLIGHT.json 및 SOURCE_DIFF 자료에 보존했다. 기존 Snowball H와 기존 timeline/rf_poses를 읽기 전용으로 사용했다. 파일명뿐 아니라 해시·shape·finite 값·pose 대응을 확인했다.

| 입력 | SHA256 |
| --- | --- |
| H_R2_aA_m0.npy, 1303×257×2×2 | `1c40aea5ab7af87223f942c0727c0f6aabe7bd60e55a70c68c74d2c115750a51` |
| hs_lut_2deg.npy, 46×180×180 | `711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079` |
| S6 results_R2_aA_m0.csv | `16428ad0ce782193a90d6c0323fb4be05d6ea825bce835f08c62aea575765c13` |
| freqs_hz.npy | `fe0bcfeb1426847ea090668845fe124482086d0510e38ebdb463609e2a1169f8` |

H/S6 원본은 `/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source/results/DRIVE_SIM_20261007/SNOWBALL_ROUTES_01a11669/`의 S2 및 S6_routes에 있다. timeline/rf_poses는 같은 routes 작업의 `source/results/DRIVE_SIM_20261007/S1`이다. LUT/metadata는 `/home/KMS/COOL_DIJKSTRA_20261007_01a11582/source/results/DRIVE_SIM_20261007/S4/`다. metadata·timeline·pose·S6 manifest 해시도 실행 manifest에 있다. 주파수축은 실제 LP_plus45 bank의 freqs_hz와 일치했고 257 bins, 6.2504–6.7496 GHz, 간격 1.95 MHz다. 이는 입력 동일성 확인이며 RF 물리 검증이 아니다. INPUT_PRESERVATION.json에서 실행 전후 원본 해시 불변을 확인했다.

Snowball 접속은 KMS 계정만 사용했다. 기존 Docker image `rt-dual-engine:s2-deps-r2-20260928`, image ID `sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f`, Python 3.11.15, NumPy 2.4.6, pandas 3.0.6을 사용했다. 4 worker, BLAS/OMP/MKL 각 1 thread다. 설치나 RF solver 호출은 없었다. 원본 두 mount는 read-only다.

Git 실행 파일이 없는 환경이므로 별도 wrapper가 git_info() 메타데이터만 동결 archive 정보로 제공했다. runtime_git_available=false를 명시하고 wrapper도 해시로 보존했다. 모델·난수·평가 로직 변경이 아니다. 환경 확인 및 해시 helper의 호환 오류는 준비/기록 단계에서 처리했으며 결과를 맞추는 필터 재실행은 없었다.

최종 적용 range R는 0.006857863713357258, s mismatch variance는 0.025905641605086252(sigma 0.16095229605409875), gate는 6.6349, pos_process_std는 0.01, dt는 0.2 s다. s 분산의 기존 열잡음 처리도 유지했다. prior std는 `[0.1,0.1,0.0872664626,0.0020943951,0.0104,0.0064]`다. defaults와 최종 applied settings를 구분해 manifest에 기록했다. 평가 mask는 t≥30 s, 829 sample/run이다. SNR30은 S6의 snr_idx=0과 대응한다. seed 키와 합성 stream 101–107도 manifest에 저장됐다.

## 실제 실행 결과와 A0/S6 판정

preflight, residuals, check-a0, controls, q1, report가 모두 exit code 0이다. 실행은 한국시간 13:33:24–13:35:22, 전체 phase wall time 약 118.46초다. 이는 합산 CPU 시간이 아니며 전송·로컬 감사는 제외한다. 합산 CPU 사용량은 측정하지 않았다. 정확한 argv, 시작/종료 timestamp와 exit code는 EXECUTION.json에 보존했다.

요청한 A0 150개 키가 모두 존재하고 중복·누락·실패 행이 없다. S6 대비 최대 차이는 heading RMSE 1.7764e-15°, 위치 RMSE 2.2204e-16 m, NEES 2.8422e-14로 모두 1e-9 이내다. A0_CHECK의 inference_valid=true다. 후속 controls/q1은 source/input/settings fingerprint와 요청 범위 검사를 통과하고 A0 결과를 재사용했다. 이는 재현 게이트 통과이며 scientific PASS가 아니다.

로컬 개발 점검의 0.011°/14.6 차이 원인은 이번에 조사하지 않았다. Snowball 재현 성공만으로 그 차이를 H 탓으로 확정하지 않는다. 이번 A0는 production R/seed0–49/drift0–2다. 이전 거리 조건부 R의 NEES≈320.776 또는 감사 2×2 seed4000–4023과 동일 실험처럼 비교하지 않는다.

| arm | drift | 평균 NEES | pose coverage | heading coverage | heading RMSE 중앙값 ° | 위치 RMSE 중앙값 m | s 거절률 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A0_real_real | 0 | 97.56730 | 0.19732 | 0.22581 | 10.77821 | 0.89833 | 0.04217 |
| M0_Rmatched_Rmatched | 0 | 1.74190 | 0.99127 | 0.96828 | 1.21734 | 0.14425 | 0.01033 |
| S1_bias | 0 | 36.97121 | 0.15124 | 0.60926 | 3.08606 | 0.78932 | 0.02077 |
| S2_ar0 | 0 | 121.31225 | 0.22456 | 0.33247 | 5.42220 | 0.62784 | 0.03689 |
| S3_ar1 | 0 | 212.97873 | 0.13539 | 0.27573 | 6.82123 | 1.08353 | 0.05544 |
| S4_iid | 0 | 20.24717 | 0.57172 | 0.89517 | 1.76967 | 0.45072 | 0.02164 |
| S5_iid0 | 0 | 3.98438 | 0.88145 | 0.99216 | 1.57120 | 0.26415 | 0.02029 |
| S6_realdem | 0 | 30.99175 | 0.18439 | 0.52979 | 4.42449 | 0.97510 | 0.02362 |
| S7_block | 0 | 51.81109 | 0.29211 | 0.48024 | 3.44005 | 0.58678 | 0.02714 |
| S8_real | 0 | 95.89053 | 0.22470 | 0.22111 | 11.67937 | 0.90580 | 0.04236 |
| W0_white_white | 0 | 3.29233 | 0.91530 | 0.93206 | 1.45148 | 0.16491 | 0.02164 |
| A0_real_real | 1 | 113.23503 | 0.19551 | 0.22321 | 10.84143 | 0.89626 | 0.04162 |
| M0_Rmatched_Rmatched | 1 | 2.43780 | 0.95513 | 0.92306 | 1.41486 | 0.18174 | 0.00975 |
| S1_bias | 1 | 39.37801 | 0.13785 | 0.57001 | 3.39220 | 0.81318 | 0.02055 |
| S2_ar0 | 1 | 129.98328 | 0.16591 | 0.28803 | 5.99629 | 0.93859 | 0.03274 |
| S3_ar1 | 1 | 202.72969 | 0.10130 | 0.23370 | 7.85126 | 1.21941 | 0.03821 |
| S4_iid | 1 | 35.68579 | 0.53156 | 0.84762 | 2.00045 | 0.45798 | 0.02229 |
| S5_iid0 | 1 | 3.56936 | 0.92072 | 0.98502 | 1.42255 | 0.28324 | 0.02123 |
| S6_realdem | 1 | 29.60817 | 0.18458 | 0.52676 | 4.24545 | 0.96218 | 0.02343 |
| S7_block | 1 | 33.10893 | 0.33221 | 0.54082 | 3.04119 | 0.57477 | 0.02157 |
| S8_real | 1 | 98.62452 | 0.22084 | 0.21614 | 11.86894 | 0.89189 | 0.04191 |
| W0_white_white | 1 | 6.49091 | 0.85493 | 0.88844 | 1.64534 | 0.19323 | 0.02010 |
| A0_real_real | 2 | 108.75831 | 0.16010 | 0.16454 | 10.64314 | 0.89956 | 0.03891 |
| M0_Rmatched_Rmatched | 2 | 2.82141 | 0.95373 | 0.89341 | 1.72155 | 0.17965 | 0.00965 |
| S1_bias | 2 | 51.38520 | 0.12511 | 0.51264 | 3.55054 | 0.87342 | 0.02282 |
| S2_ar0 | 2 | 108.42764 | 0.16405 | 0.30924 | 5.75290 | 0.79819 | 0.03016 |
| S3_ar1 | 2 | 211.25376 | 0.09018 | 0.26381 | 6.61584 | 1.11271 | 0.03990 |
| S4_iid | 2 | 44.22308 | 0.43387 | 0.69780 | 2.40128 | 0.48789 | 0.02188 |
| S5_iid0 | 2 | 3.77647 | 0.90907 | 0.93537 | 1.47838 | 0.27631 | 0.02055 |
| S6_realdem | 2 | 31.94233 | 0.19641 | 0.40704 | 4.68331 | 0.96918 | 0.02454 |
| S7_block | 2 | 31.29014 | 0.31730 | 0.50499 | 3.28395 | 0.52878 | 0.02072 |
| S8_real | 2 | 105.33149 | 0.18101 | 0.16220 | 11.32387 | 0.90704 | 0.03993 |
| W0_white_white | 2 | 5.33241 | 0.83151 | 0.82294 | 1.89648 | 0.20676 | 0.02099 |

NEES·coverage·거절률은 seed별 값의 평균이고 RMSE 두 열은 seed별 중앙값이다. 각 행은 50 run이다. 평가 시간 sample을 독립 반복으로 취급하지 않았다. NEES subspace는 [x,y,heading], 자유도 3이며 heading은 radian wrapping 후 계산한다. sample별 양측 tail 경계는 0.2158/9.3484, pose 95% coverage 상한은 7.8147, heading 자유도1 95% 상한은 3.8415다. 이 경계로 상관된 시간 평균의 독립 chi-square PASS를 만들지 않았다.

M0 drift0의 NEES 1.742, pose coverage 0.991, 하측 tail 0.0603도 자동 정상으로 판정하지 않는다. 과도한 공분산 가능성을 함께 봐야 한다. S1은 A0보다 NEES가 낮아도 pose coverage가 더 낮다. 정확도와 일관성은 별개다.

## 달성 통계와 시간 구조의 한계

원 clean s 잔차: 평균 0.046511, centered variance 0.029915, RMS 0.179103, lag1 0.927037. range: 평균 0.051940 m, variance 0.012470 m², RMS 0.123159 m, lag1 0.803976. clean range–s lag0 상관은 0.522627이다. 실제 입력 통계는 열잡음/추가 range 잡음 포함 값이며 clean 목표와 구분한다.

| arm | s 평균 | s 분산 | s RMS | s lag1 | range RMS | 입력 교차상관 |
| --- | --- | --- | --- | --- | --- | --- |
| A0_real_real | 0.04647 | 0.02988 | 0.17900 | 0.92658 | 0.13387 | 0.47481 |
| M0_Rmatched_Rmatched | 0.00029 | 0.02607 | 0.16153 | -0.00299 | 0.08268 | 0.00291 |
| S1_bias | 0.04682 | 0.03011 | 0.17977 | -0.00297 | 0.13270 | 0.00290 |
| S2_ar0 | 0.00186 | 0.02939 | 0.17374 | 0.92092 | 0.13270 | 0.00026 |
| S3_ar1 | 0.04837 | 0.02939 | 0.18011 | 0.92092 | 0.13270 | 0.00026 |
| S4_iid | 0.04573 | 0.02972 | 0.17752 | 0.00442 | 0.13270 | -0.00291 |
| S5_iid0 | -0.00078 | 0.02972 | 0.17161 | 0.00442 | 0.13270 | -0.00291 |
| S6_realdem | 0.00003 | 0.02997 | 0.17311 | 0.92606 | 0.13270 | -0.00228 |
| S7_block | 0.04629 | 0.02950 | 0.17026 | 0.88715 | 0.13270 | -0.00219 |
| S8_real | 0.04647 | 0.02988 | 0.17900 | 0.92658 | 0.13270 | -0.00176 |
| W0_white_white | 0.00032 | 0.03228 | 0.17973 | -0.00297 | 0.13270 | 0.00290 |

위 표는 run별 통계의 평균이다. RMS의 평균은 pooled RMS와 다르다. S3는 평균 0.04837, 분산 0.02939, RMS 0.18011, lag1 0.92092로 목표와 근접하지만 정확히 같지 않다. 높은 lag의 구조는 더욱 다르다. 실제 s lag10은 −0.02434, lag25는 0.00098인데 lag1=0.927037인 AR(1)의 이론값은 각각 약 0.469/0.150이다. 따라서 같은 통계라는 표현은 선택한 요약 통계 수준에 제한된다. S3의 NEES 과대 재현과 장기 상관 차이의 관련 가능성은 남지만 원인 확정은 아니다. S7 달성 lag1 0.887 역시 실제보다 낮다. Q1은 range–s 교차상관을 함께 맞춘 joint 시험이 아니다.

## 대응 비교·분포·innovation

폐쇄율은 (arm−W0)/(A0−W0)이며 물리적 기여율이 아니다. closure의 heading은 seed별 RMSE의 **평균**을 사용한다. 앞 표의 중앙값과 혼동하지 않는다. 분모 구간이 0을 포함하면 보류, 음수면 해당 없음 규칙을 유지했다. drift0 결과는 다음과 같다.

| arm | 지표 | seed 평균 | 폐쇄율 | bootstrap 구간 | 상태 |
| --- | --- | --- | --- | --- | --- |
| S1_bias | nees | 36.97121 | 0.35724 | [0.3144215920428219, 0.4009273864920159] | defined |
| S1_bias | head | 3.08297 | 0.16989 | [0.14028106873222632, 0.19843342169198844] | defined |
| S2_ar0 | nees | 121.31225 | 1.25187 | [0.7627622409236378, 1.8764181010094256] | defined |
| S2_ar0 | head | 6.25983 | 0.51413 | [0.41115477449418397, 0.6314032333780438] | defined |
| S3_ar1 | nees | 212.97873 | 2.22420 | [1.527717805556058, 3.0972727303374934] | defined |
| S3_ar1 | head | 8.27959 | 0.73299 | [0.5682756857669707, 0.9468949792017943] | defined |
| S4_iid | nees | 20.24717 | 0.17984 | [0.12637019582807327, 0.2448322410888197] | defined |
| S4_iid | head | 1.80580 | 0.03150 | [0.010432196640111774, 0.05037425550405949] | defined |
| S5_iid0 | nees | 3.98438 | 0.00734 | [0.00039091609571722337, 0.015085497859868768] | defined |
| S5_iid0 | head | 1.56345 | 0.00524 | [-0.017606427827834524, 0.02595254394098212] | defined |
| S6_realdem | nees | 30.99175 | 0.29382 | [0.26897866144711713, 0.3204215400620989] | defined |
| S6_realdem | head | 4.34490 | 0.30663 | [0.2859727559845031, 0.32660908150180956] | defined |
| S7_block | nees | 51.81109 | 0.51465 | [0.31672009746127433, 0.7854817238577646] | defined |
| S7_block | head | 3.86526 | 0.25466 | [0.2028908446738551, 0.31114315927527864] | defined |
| S8_real | nees | 95.89053 | 0.98221 | [0.9350835840671647, 1.0296096349580568] | defined |
| S8_real | head | 11.31881 | 1.06231 | [1.0314133009581254, 1.09418762919558] | defined |

보조 분석은 각 seed의 3 drift를 먼저 평균하고 50 seed를 bootstrap 단위로 사용했다. 제외 seed는 없다. S3 NEES 폐쇄율 2.00971 [1.66923,2.39922], heading 0.75640 [0.66482,0.85813]. S8은 각각 0.93525 [0.85468,0.99321], 1.08395 [1.06268,1.10634]다. 임계값 0.8로 채택 판정하지 않았다.

S3 drift0의 seed별 NEES 중앙값 130.806, p95 746.581, 최대 1187.594, heading RMSE 최대 35.580°다. A0 drift1도 평균 113.235, 중앙값 99.704, 최대 693.952다. 평균만으로 안정성을 대표하지 않는다. 전체 seed 분포는 SEED_DISTRIBUTION.csv에 있다.

drift0 A0의 s NIS는 pre-gate 1.47337, accepted-only 0.45609, 거절률 0.04217이고 range NIS는 각각 1.42467/0.89301이다. accepted-only 값이 작다는 사실로 전체 입력 적합성을 주장하지 않는다. 모든 arm의 gate 기준은 같지만 수용 결과는 바뀔 수 있으므로 효과에는 상태 변화와 rejection이 함께 포함된다. gating 효과만 고정한 시험은 이번 범위에 없다. 전체 NIS, 양측 tail, s/range 거절률은 per_drift.csv에 보존했다.

## 독립 검산과 저장 범위

1,650개 요청 키와 finite 지표, 중복·누락·실패 상태를 확인했다. 전송 파일 279개의 원격 SHA256이 모두 일치했다. seed0/1 × 3drift × 11arm의 trace 66개에 전체 6상태·6×6 P·센서/관측·갱신 log·mask를 저장했다. 독립 계산은 P를 regularization 없이 풀어 NEES, wrapped heading/position RMSE, coverage, pre/accepted NIS와 거절률을 CSV와 대조했다. 최대 NEES 차이 6.85e-12다. 129,096 log 행에서 NIS=innovation²/S도 대조했다. trace P 최소 고유값 1.3069e-8, 최대 비대칭 1.7347e-17이다. 나머지 48 seed의 전체 공분산까지 검산했다고 확대하지 않는다.

trace 66개에서 같은 seed/drift의 gyro, wheel distance/yaw, truth, time 입력은 arm 사이에 정확히 같았다. 대응 조건 확인이며 공통 코드의 모든 오류를 배제하지는 않는다. 계산은 verify_outputs.py, 결과는 VERIFICATION.json 및 TRACE_PAIRING.json이다. 필터 수정은 없으므로 기존 48개 테스트를 이번 성과로 다시 인용하지 않았다.

## 원인과 한계 → 다음 검증에 주는 의미

**Q1은 부분 지지다.** 고정 필터에서 편향·시간 상관을 가진 합성 s 오차가 백색 대조보다 NEES와 정확도를 악화시키는 현상은 재현된다. S4→S5 평균 제거, S1→S3 시간 상관 추가는 각각 선택한 생성 모형 안에서 요인 중요성을 보여준다. 그러나 S3는 실제 A0보다 NEES를 약 2배 크게 만들면서 heading 악화는 덜 재현했다. 편향·분산·lag1만으로 실제 실패를 정량적으로 모두 설명했다고 주장할 수 없다.

S8에서 실제 s를 유지하고 range를 백색으로 바꿔도 큰 NEES가 남는다. 이 조건에서 s 구조의 중요성을 보여주지만 range의 물리적 원인·기여율·무영향을 확정하지 않는다. **Q2는 미실행**이며 range 편향·상관·거리/tap 의존 및 joint 비교는 별도 실행 범위로 남는다.

이번 결과는 동일 경로의 조건부 진단이며 독립 held-out 일반화가 아니다. full RF–LUT 잔차에는 L1 오차도 포함된다. A0 재현과 1,650회 실행은 완료했지만 모델 수정 채택은 보류한다. F01/L1/L2, F02 및 scientific_PASS=false는 유지한다. R/Q/prior/threshold 조절은 없었다. 실험 실행 단계에서는 원본을 보존했고 commit/push/merge를 하지 않았다. 이번 별도 게시 작업은 완료된 A23 결과만 새 브랜치에 추가한다. Q2/joint/L2/새 RF/후속 필터 비교는 자동 시작하지 않는다.

## 근거 파일

- [EXECUTION.json](<retrieved/EXECUTION.json>)
- [A0_CHECK.json](<retrieved/OUTPUT/A0_CHECK.json>)
- [ARMS_REPORT.json](<retrieved/OUTPUT/ARMS_REPORT.json>)
- [RUN_MANIFEST_q1.json](<retrieved/OUTPUT/RUN_MANIFEST_q1.json>)
- [PREFLIGHT.json](<retrieved/OUTPUT/PREFLIGHT.json>)
- [A0_ARMS.csv](<retrieved/OUTPUT/A0_ARMS.csv>)
- [ARMS_controls.csv](<retrieved/OUTPUT/ARMS_controls.csv>)
- [ARMS_q1.csv](<retrieved/OUTPUT/ARMS_q1.csv>)
- [ARM_UNIT_STATS_q1.csv](<retrieved/OUTPUT/ARM_UNIT_STATS_q1.csv>)
- [RESIDUAL_R2A_m0.npz](<retrieved/OUTPUT/RESIDUAL_R2A_m0.npz>)
- [RESIDUAL_STATS.json](<retrieved/OUTPUT/RESIDUAL_STATS.json>)
- [ARM_TARGETS.json](<retrieved/OUTPUT/ARM_TARGETS.json>)
- [OUTPUT_MANIFEST.json](<retrieved/OUTPUT_MANIFEST.json>)
- [INPUT_PRESERVATION.json](<retrieved/INPUT_PRESERVATION.json>)
- [verify_outputs.py](<verify_outputs.py>)
- [PLAN.json](<PLAN.json>)
- [SOURCE_REVISION.json](<SOURCE_REVISION.json>)
- [VERIFICATION.json](<VERIFICATION.json>)
- [TRACE_PAIRING.json](<TRACE_PAIRING.json>)
- [SEED_DISTRIBUTION.csv](<SEED_DISTRIBUTION.csv>)
- [per_drift.csv](<per_drift.csv>)
- [paired_closure_per_drift.csv](<paired_closure_per_drift.csv>)
- [paired_closure_seed_mean_over_drifts.csv](<paired_closure_seed_mean_over_drifts.csv>)

원격 작업 경로: `/home/KMS/DRIVE_SIM_A23_EXECUTION_20261010_01a12411`. 보고서와 파생 표의 SHA256은 LOCAL_OUTPUT_MANIFEST.json으로 별도 추적한다. 원격 OUTPUT_MANIFEST는 덮어쓰지 않았다.
