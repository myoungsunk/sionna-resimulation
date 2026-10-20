# S0-3: 과거 Slide2 모집단·잔차 정의의 출처

SOURCE_CONFIRMED: 과거 R2 A M0 / A M45 / B M0 표는 각 조건의 **1,303 RF pose 전부**를 사용한 FrozenLut 기준 통계다. 신규 T3의 SourceFFD·재귀 t≥30 s·829행과 모집단 및 s 예측 기준이 다르다. 통계값이 가까운 것으로 행 대응을 인증하지 않는다.

과거 보고서 commit `f1be3f458bb4746f8a0868dd874343da7081386c`의 `research/R5_N4B_REPORT_20261015/RESULTS_KO.md:23`–25에 (μr,Vr,ρ)는 A0 (+.05225,.01708,+.525), A45 (+.07187,.01658,+.062), B0 (+.03069,.00807,+.096)로 기록되어 있다. 동일 문서 7–10행이 Actions run38711275905와 실제 실행 commit을 연결한다. GitHub API의 run head_sha도 **`7d8d20c9a95364fb6a9ae7caa720b2b22019ecab`**로 확인했다.

이하 locator의 commit은 별도 표기가 없으면 이 실행 commit이다. 원문 필요 부분, GitHub blob SHA, 전체 해당 source byte SHA256/크기는 [SOURCE_PROVENANCE.json](SOURCE_PROVENANCE.json)에 보존했다.

| 확인 항목 | 공식 source locator | 확인 내용 |
|---|---|---|
| 입력 및 실행 연결 | `.github/workflows/r5-n4b-rf-errors.yml:24`–38, 49–59, 65–69 | manifest·FrozenLut·Full/LoS H·SAMPLES를 exact checkout; artifact11782748118 원 ZIP SHA256 `88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63`; `n4b_rf_errors.py --phase run` 실행 |
| 각 R2 n·파일 | `research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json:183`–245 | A0/A45/B0 각각 rf_count=1303, H 첫 차원=1303; Full/LoS/SAMPLES 경로 명시 |
| 행 대응 | `research/R5_FULLRF_B0_GATES_20261015/r5_b0_hard_soft.py:174`–190 | SAMPLES list의 j번째 pose_id·GT와 H의 j번째 row를 같은 순서로 조합; case/channel/pose_id 키를 사용 |
| 누락·필터 규칙 | 같은 파일 178–197행 | pose_id 유일성·H_shape 검사; 모든 packet valid가 아니면 오류. empirical 통계 전 시간·RF row drop 없음 |
| s 잔차 모델 | 같은 파일 169–179, 188–190행; `research/R5_N4B_20261015/n4b_rf_errors.py:250`–256 | e_s=`features.extract`의 관측 s_fp−GT pose의 FrozenLut.model s. **SourceFFD 기준이 아님** |
| range 잔차 모델 | `research/R5_N4B_20261015/n4b_rf_errors.py:258`–266 | e_r=관측 range−(GT 3D distance+B_OLD), B_OLD=−.5315983906250129 m |
| empirical 포함 범위 | 같은 파일 396–415행 | 전체 Full9519·Full/LoS paired source에서 case/channel별 group_stats. R2 각1303행 모두 포함 |
| 통계 정의 | 같은 파일 338–351행 | empirical group_stats는 균등 가중 row_cov, 전체 n 및 signed mean·centered variance·correlation 사용 |
| 학습 split과 구분 | 같은 파일 321–336, 418–427행 | 나중 likelihood 모델만 R2/R4/R5 held-route와 held xy까지 거리>1e−4 m의 train 배제 규칙, train site 가중치 적용. 위 empirical 표에는 이 split을 적용하지 않음 |

세 SAMPLES 파일은 모두 `results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/<case>/SAMPLES.json:1`의 한 줄 JSON list다. 필드는 정확히 `pose_id,x,y,yaw_body_deg`, 각1,303개, pose_id는 list 순서대로0–1302다. **timestamp가 없다.** 이 source만으로 실제 초 단위 시작·종료 시각이나 신규829행의 정확한 membership을 인증할 수 없다. 재귀 clock을 임의로 pose_id에 곱하지 않았다. 이 gap은 Mother의 별도 clock/membership 감사 대상이며 본 source-only 결과는 `CLOCK_MAPPING_NOT_ESTABLISHED`다.

Full H 경로는 `.../BLOCK_C/FULL_RF/H_<case>.npy`, Native LoS는 `.../BLOCK_C/H_LoS_<case>.npy`; `freqs_hz.npy`는 동일 BLOCK_C에 있다. 각 조건의 정확한 full path와 source SHA는 JSON에 있다. 기존14개 archived trace와의 range/s parity는 `n4b_rf_errors.py:301`–318에서 `(case,channel,pose_id)`로 join하여 검증하며, 이14,502행 parity 모집단을 empirical Full/LoS19,038행과 혼동하지 않는다.

이번 확인은 공식 pinned source/API와 JSON schema·row metadata만 읽었다. RF 생성·추출·수치 통계·필터·재귀를 실행하지 않았다. 독립 장면 일반화나 구/신 통계의 직접 변화량을 주장하지 않는다.
