# DLP-R1B-CH4-001 / LOCAL-RUN-001 — Snowball 로컬 서버 실행 의뢰서

**상태: HANDOFF_READY / P0_APPROVAL_REQUIRED. 전체 917개 Native RF·EKF 아직 시작 금지.**
**작성: 2026-11-03 (KST)**

## 1. 목표와 예상 소요시간

R1 원본 y0.35/Tnone 917개 pose × 257 frequency bins × 독립 Native LoS/Full PathSolver 2회 = 총 **471,338회** Native solver 호출. Anchor B=(10,0,2.65)m, tag z=0.45m, mount=0°.

- 8개 기존 canary 실제 기록: 첫 pose 246.080초, 뒤 7개 평균 **37.585초/pose**, 917개 순차 외삽 **약 9.6시간**.
- 4개 신규 pose 실제 GitHub Actions #41599666331: 첫 pose 약 559.6초, 뒤 3개 평균 **73.720초/pose**, 순차 외삽 **약 18.9시간**.
- 두 시간 모두 다른 runner에서 얻은 측정값을 외삽한 것. Snowball 성능이나 병렬 처리량은 **실측 전 미확정**.
- 2시간 이상이므로 GitHub-hosted runner 대신 로컬 Snowball(KMS 환경)에서 의뢰. 단 2시간 완료 자체를 보장하지 말 것.

| 실효 worker 수 | 기존 runner 속도 기준 이상적 시간 | 신규 runner 속도 기준 이상적 시간 |
|---:|---:|---:|
| 1 | 9.6 h | 18.9 h |
| 4 | 2.4 h | 4.7 h |
| 8 | 1.2 h | 2.35 h |
| 12 | 0.80 h | 1.57 h |

위 병렬 수치는 CPU 경합·초기 컴파일·입출력/감사·조립 시간 제외. 근거 파일 원본 P0_COST_MEASUREMENT.json 및 신규 run #41599666331 로그.

## 2. 정확히 고정할 소스·입력

- 저장소: https://github.com/myoungsunk/sionna-resimulation
- 원래 8개 RF 및 과거 HOLD: commit **defcb2667e2357a750c0117135d136fd21c5eff3**.
- 기존 12개 정밀도 비교 수정: commit **3732f101c707832e6aa2fa8bc8446d3cd06749d3**, 파일 research/DLP_R1B_CH4_20261103/precision_v2/solver_matched_delay.py.
- 원래 P0 input/QA: research/DLP_R1B_CH4_20261103/00_REQUEST_CONTRACT_FROZEN_V2.json, SHA-256 a31a537dd35823d10c1d74ee0cf488d439b7ba2c70114309e024b451a9468596.
- 원본 timeline: results/DRIVE_SIM_20261007/S1/timeline_y0.35_Tnone.csv, SHA-256 53e76f41cb95b32b25f2cc58844bac09c09ffd0803aa287cc69e025bb97225c4.
- 원본 LP+ bank SHA-256 b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b.
- 원본 LP- bank SHA-256 39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9.
- Original 495 MB banks: Actions run 38875080492, artifact ffd-verified-original-38875080492. Artifact 만료 전 영속 보존할 것.
- 신규 4 pose raw: Actions #41599666331, artifact r1b-precision-v1-prospective4-41599666331.
- 검증: #41600953304 (기존 8개 DrJit V2), #41604842904 (신규 4개 V2·별도 산술 검산) 모두 PASS. **수치 정합 PASS이지 원래 V2 과학적 HOLD의 해제 아님**.
- 실행자 SHA와 과학 계약 SHA를 각각 원시/derived manifest에 남기고, 기준 브랜치를 무단 최신화하지 말 것.

## 3. 실행 불변 조건

1. 장면 C0 원래 6 mesh/재질, TX+45°, RX±45°, 257 bins f[k]=6,250,400,000+1,950,000*k Hz (k=0…256); Full max_depth=3, LoS max_depth=0. 동일 pose에서 Native Full/LoS 각각 독립 solver 실행. Full 직파를 LoS 대신 재사용 금지.
2. 원시 H shape (257,2,2), path별 a/τ/interaction/object/offset, CIR/검출 tap/포트별 전력 보존. Hann window symmetric, IFFT 1,028, strongest RX 30% leading-edge, 두 RX 공통 tap. LoS와 Full 각각 FP 독립 검출. signed s=(P+−P−)/(P++P−).
3. 실제 Sionna-RT 2.0.1의 DrJit 직접경로 지연 연산(mi.Vector3f → dr.norm → dr.rcp(c))을 Source-only 복소 parity 비교에 재현. Native τ를 피팅 입력으로 쓰지 말 것. **4상태 EKF의 SourceFFD h,H/f,F,Q/R은 변경하지 말 것**.
4. 기존 비교 기준 그대로: 복소 상대오차 max <=5e-4, RMS <=1e-4; signed s max <=2e-5, RMSE <=2e-6; tap/strong-port mismatch 0. 추가 원시 H 재구성, full 직접경로 및 기하·Jacobian 검사 포함. 나쁜 pose 삭제나 임계값 완화 금지.
5. 평가 t>=30 s 총 767개 pose, rejected updates도 포함. 4-state [x,y,ψ,bg], R0=diag(0.0068578637m²,0.0081), 추가 평균/분산=0, NIS chi²_2(0.99)=9.210340371976184, Joseph covariance, yaw wrap, 동일 초기값/제어열/seed를 LoS/Full에 적용. B0 필수, L2 선택.

## 4. 절대 우회하지 않을 P0 차단 조건

**원본 runtime/r1b_acquire.py는 현재 직접 생산 실행 불가.** 원래 HOLD였던 canary에서 status PASS를 요구하고, 정확히 8개 재사용+909개 신규만 허용하며, anchor를 np.array_equal로 비교해 원시 좌표 표현 차이 약 4.44e-16m에도 잘못 거절한다.

새 LOCAL-P1-V1 amendment에서 다음을 먼저 구현·독립 사전 승인한다.

- 원래 8개 실패 기록과 정확한 SHA를 보존한 **신규 V2 표현 정합 게이트/receipt**. 기존 QA PASS로 조작·변경하지 말 것.
- 재사용 12개 (기존 8+신규 4) raw의 동일성·환경·FFT/solver/scene/seed·SHA를 감사하여 **12개 재사용+905개 신규**, 또는 재사용 불가 시 **917개 새 계산** 중 하나만 계약 동결. 기존 driver shard 8+909 가정을 이 계약과 정합되게 수정.
- raw 조립기의 anchor geometry 검사를 shape·finite + atol=1e-12m, rtol=0로 정합시키고 다른 gate/임계값은 유지.
- shard별 append-only 쓰기, 전 작업자 global-stop, 실패 partial 보존, SHA 검증된 pose만 resume, overlap/누락 없는 전 917 ID 조립, independent auditor 별도 role/승인.
- P0 사전 승인과 production plan SHA freeze 없으면 P1 917 계산 **NOT_RUN**.

## 5. Snowball(KMS) 사전점검 및 벤치마크

이전 기록에 Snowball은 KMS 계정·128 logical CPU·Linux 3.10 계열 커널이 등장하지만 현재 사양은 다시 검사해야 한다. 현재 RAM/GPU 및 moderne Python/LLVM 호환성은 모른다. 접속 가능한 사용자 단말에서만 기존 승인된 SSH 명령을 사용한다.

~~~bash
ssh -o BatchMode=yes -o PasswordAuthentication=no Snowball
whoami; hostname; uname -r; nproc; free -h; df -h
~~~

- Linux 구형 커널에서 Sionna-RT/Mitsuba/DrJit의 필요한 wheel/LLVM이 실행되는지 먼저 smoke test. 실패하면 HOLD_ENVIRONMENT, 시스템 Python 무단 수정 금지.
- Python3.11.17(신규) 또는 기존 3.12.14(기존) 선택 후 버전 동결: numpy=1.26.4, scipy=1.14.1, sionna-rt=2.0.1, mitsuba=3.8.0, drjit=1.3.1, llvm_ad_mono_polarized. 각 worker BLAS/DrJit threads=1부터 시작.
- 원래 한 worker 최대 RSS 약 1.18 GiB. 초기 예산은 4 GiB/worker + OS/캐시/assembly 여유(확정 하한 아님). 디스크는 실측 검증하고 여유 20 GiB를 운영 권장. 서버 RAM 모른 채 8/12개를 한 번에 시작하지 말 것.
- 사전 지정 서로 다른 pose를 이용해 1,2,4,8 workers의 실제 pose/min, RSS, CPU/IO wait, 초기 cold 비용과 warm p50/p95를 측정. 여유가 있을 때 12/16 workers. 목표 ETA = 초기화 + 미완료 pose/측정된 **총 합산 처리량** + 조립/독립감사 비용.
- 개별 작업자는 전체 pose(257bin, 2 arms)를 처리. 병렬화가 물리 solver 설정을 바꾸면 안 됨.

## 6. 독립 승인 이후 P1 / P2 / P3 순서

- P1: 정확히 917 unique pose의 LoS/Full 원시 H·경로·CIR·관측 계산, pose ID 및 timestamp/order·SHA·각 worker runtime 기록. 한 개라도 부적합하면 모든 worker 신규 예약 STOP, raw/partial 보존. 시작한 shard 수와 성공/실패를 manifest로 남긴다.
- P2: 보정 전 e0=z_Full−h(x_GT), delta_z=z_Full−z_LoS, e_LoS=z_LoS−h(x_GT)를 계산하고 e0=delta_z+e_LoS packet 항등식 재검증. 전 기간/평가 767개 및 drive_out/turn/drive_back, 거리 bins별 mean/RMS/std. GT는 offline only.
- P3: 두 개 4상태 EKF의 동일 제어/seed/초기화로 실제 재귀, pre-gate ν=e+[h(GT)−h(x^-)], Kν=Ke+Kδh, P−/P+/H/K/S/NIS/accepted 전 기록. t>=30 s Heading wrapped RMSE(°)·XY RMSE(cm), rejected 포함. 성능 악화도 보고.
- P4: R1에 대한 신규 평균 보정 학습/평가, MB_VAR 관련 모델 및 성능 주장은 **이번 범위 제외**. 별도 frozen predictor와 학습·평가 분리 계약이 있을 때만 추가.
- 최종 AUDITOR가 원시 a/τ→H→CIR→r/s→관측오차→EKF update→RMSE를 별도 과정으로 검사; 구현자 자체 PASS와 과학적 SCIENTIFIC_SUPPORTED를 혼동하지 말 것.

## 7. 필수 산출물 및 제출 형식

새 경로 /home/KMS/SIONNA_R1B_CH4_LOCAL_20261103/<RUN_ID>/ 하에 최소:

- 00_LOCAL_EXECUTION_CONTRACT_FROZEN.json
- 01_ENVIRONMENT_AND_RESOURCE.json, 02_INPUT_HASHES_AND_LINEAGE.json
- 03_SHARD_PLAN_AND_PREAUDIT.json
- 04_BENCHMARK_1_2_4_8_WORKERS.csv / ETA_REPORT_KO.md
- per_pose/pose_0000...pose_0916.npz 및 JSON (선택된 reuse의 SHA·출처 포함)
- data/channel_full_and_los_manifest.json, rf_observations.csv, raw_observation_errors.csv
- data/ekf_packet_log_los.csv, ekf_packet_log_full.csv, ekf_scores_los_full.csv
- figures/R1_GEOMETRY, R1_FULL_LOS_OBSERVATIONS, R1_RAW_ERROR_DISTANCE_PHASE, R1_HEADING_XY_TIME_AND_RMSE (PNG와 PDF/SVG 및 입력 CSV)
- 05_P1_REPORT_KO.md, 06_P2_REPORT_KO.md, 07_P3_REPLAY_KO.md
- 08_INDEPENDENT_AUDIT_REQUEST_AND_RESULT_KO.md, 09_FINAL_MANUSCRIPT_USE_KO.md
- SHA256SUMS.txt, 실제 UTC 시간/CPU/wall/RSS/log, 통과/실패/재시도 이력.

원시 RF는 만료 가능한 Actions artifact에만 두지 말고 별도 영속 경로로 보관한다. GitHub에는 manifest/checksum/최종 결과와 적절히 관리되는 대용량 원본 위치만 게시한다.

### 최종 로컬 Codex 지시

당신은 DLP-R1B-CH4-001/LOCAL-RUN-001의 Snowball IMPLEMENTER다. **먼저 소스/계약/환경 P0 프리플라이트를 진행하고 수정 제안과 독립 auditor 사전 PASS를 확보**하라. 기존 HOLD를 PASS로 위조하지 말고 새로운 V2 parity 계약을 append-only로 만든다. 그 뒤 1/2/4/8 worker 로컬 벤치마크, 917 paired RF, 오프라인 P2 보정 전 오차, 동일 4상태 P3 LoS/Full EKF 비교를 순서대로 수행한다. 실제 계산 시작 전의 예측치나 미실행 스크립트는 완료라고 보고하지 않는다.

**인계:** 이 문서는 GitHub의 인계 브랜치에서 받을 수 있다. GitHub 게시만으로 Snowball에 SSH 전송 또는 로컬 Native 실행이 완료된 것은 아니다.
