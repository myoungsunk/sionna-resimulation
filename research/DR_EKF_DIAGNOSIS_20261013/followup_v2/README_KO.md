# DR-only EKF 인과 진단 V0–V5 — 실행 패키지

**상태: V0–V2 감사 및 V3–V4 전체 개발 실행 완료 / V5 NOT_RUN**  
최신 결과: [V3–V4 실행 보고서](development_20261013/REPORT_KO.md), [D6 최종 감사](audit_20261013/evidence/remote_f1d6d9fc/FINAL_AUDIT_KO.md). 개발 진단 완료는 원인 확증 또는 배포 합격을 의미하지 않는다.  
**기준:** 원래 중간 보고 4266cc9e, 이후 안전 실행기·PF 검사 반영 bfbbead3.  
**별도 개발 브랜치:** codex/dr-ekf-causal-followup-v2-20261013

**절대 변경 금지:** D6_SPEC.json, D6_PREREG_KO.md, 동결 dr_harness.py, 실행 중인 cache/, 기존 out/ 파일.

## 1. 구현 범위

| 단계 | 파일 | 수행 내용 |
|---|---|---|
| V0 | common.py, v0_cache_audit.py | D6 7 arm × 9셀 × 300 seed 캐시를 **읽기 전용** 검사, 오류가 있으면 NO_VERDICT |
| V1 | v1_verdict_audit.py | 원래 D6 공식 평가 파일이 생성된 뒤에만 캐시를 읽어 사전등록 판정 재계산값과 원본을 대조 |
| V2 | v2_pf_reference_audit.py | 기존 validate_dr_pf.py가 만드는 proposal/SIS/20k–80k/gate 진단 결과 감사 |
| V3 | v3_second_order.py | BASE, MEAN2, COV2, BOTH2의 비선형 상태–odometry joint moment 비교 |
| V4 | v4_calibration.py | gyro bias / scale factor / wheel asymmetry 각 상태의 subset oracle 및 속도 변화 정보행렬 |
| V5 | v5_independent.py | 후보 하나를 코드·기준·seed까지 사전등록한 뒤 새 seed 300개로 9셀 확증, 원본 D6와 별개 |

기존 Frozen 코드는 수정하지 않는다. 모든 V0–V5 출력은 새 runs/ 디렉터리에만 기록한다.

## 2. 오프라인 통합 QA

저장소 루트에서 아래 세 명령을 실행한다. GitHub Actions의 dr-ekf-followup-v2-check.yml에도 같은 검사를 등록했다. 실제 CI 상태가 확인되지 않았다면 PASS라고 기록하지 않는다.

    python3 -m pip install numpy pandas scipy pytest
    python3 -m compileall -q research/DR_EKF_DIAGNOSIS_20261013/followup_v2 tests/test_dr_ekf_followup_v2.py
    python3 -m pytest -q tests/test_dr_ekf_followup_v2.py

## 3. V0: 실행 중인 D6를 건드리지 않는 캐시 검사

    python3 research/DR_EKF_DIAGNOSIS_20261013/followup_v2/v0_cache_audit.py --out research/DR_EKF_DIAGNOSIS_20261013/followup_v2/runs/v0_check_001

- 최종 수정 시각 120초 미만의 캐시는 분석하지 않는다.
- seed·배열 shape·오차 유한성·Pose 공분산 양정정부호·저장 NEES 정합을 확인.
- --full-psd는 모든 시점에 PSD를 검증하며 --hash-ready는 유효 캐시의 SHA256을 기록.
- READY_FOR_D6는 **캐시 구조 완전성**이지 C1–C7/S1의 공식 통과가 아니다.

## 4. V1: 공식 D6 결과가 생성된 다음에만 읽기 전용 판정 감사

    python3 research/DR_EKF_DIAGNOSIS_20261013/followup_v2/v1_verdict_audit.py --out research/DR_EKF_DIAGNOSIS_20261013/followup_v2/runs/v1_check_001

미완료 캐시 또는 D6_CONFIRMATION_s8100-8399.json 부재시 NOT_READY. 계산을 시작하거나 누락 arm을 실행하는 코드를 호출하지 않는다. 별도로 저장된 S1 판정은 원인 판정 C1–C7에 섞지 않는다.

## 5. V2: PF 참조 신뢰성 검사

기존 연구 폴더의 validate_dr_pf.py가 담당하는 실험은 다음과 같다.

- V1: 단일 스텝 locally optimal proposal vs 독립 bootstrap importance sampler
- V2: 짧은 구간 SIS vs PF, ESS·재표집 효과
- V3: 20k vs 80k 입자수 검사 (개발 seed)
- V4: odometry innovation gate 민감도

실행된 보완자료만 감사:

    python3 research/DR_EKF_DIAGNOSIS_20261013/followup_v2/v2_pf_reference_audit.py --out research/DR_EKF_DIAGNOSIS_20261013/followup_v2/runs/v2_check_001

자료가 없는 항목은 NOT_RUN. 단일 스텝 V1 합격을 장거리 posterior 정확도의 확증이라고 주장하지 않는다.

## 6. V3: 2차 평균과 공분산 기여 분리

    python3 research/DR_EKF_DIAGNOSIS_20261013/followup_v2/v3_second_order.py --out research/DR_EKF_DIAGNOSIS_20261013/followup_v2/runs/v3_smoke_001 --world gauss_level --routes R2 --levels 0 2 --seeds 8000:8002 --steps 80

전체 경로에는 --steps 0, 개발 32 seed에는 --seeds 8000:8032 사용.

상태와 측정값에 대한 공동변환은 y=[f(x,d−nd,g−ng),h(x,d−nd,g−ng)+no]로 두고, Gaussian 2차 delta method를 적용한다.

    mean2_i = mean1_i + (1/2) tr(H_i Sigma)
    cov2_ij = cov1_ij + (1/2) tr(H_i Sigma H_j Sigma)

Q/R이나 P에 임의 배율을 곱하지 않음. BASE/MEAN2/COV2/BOTH2는 각 효과의 독립성 및 후처리 NEES/coverage/위치 RMSE를 확인하기 위한 개입이다. Gaussian posterior 자체의 고차 모멘트 문제는 여전히 남을 수 있다. Hessian 유한차분 step과 각도 wrap 정합도 QA 대상.

## 7. V4: Calibration 식별성 및 prior 진단

    python3 research/DR_EKF_DIAGNOSIS_20261013/followup_v2/v4_calibration.py --out research/DR_EKF_DIAGNOSIS_20261013/followup_v2/runs/v4_smoke_001 --world gauss_level --routes R2 --levels 2 --seeds 8000:8004

8개 known-state subset을 각각 평가한다: none / bg / sf / eps / bg+sf / bg+eps / sf+eps / bg+sf+eps.

- --world b0는 실제 B0의 wheelbase·slip까지 포함.
- --known-wheelbase는 **진단용 oracle**, 측위 방법으로 승격 금지.
- speed-excitation Fisher 지표는 공유 입력 교차공분산 C를 무시한 근사. 총 이동거리와 회전량을 통제하면서 속도 분포를 변경하므로 회전/거리 의존성과 함께 해석.

## 8. V5: 후보 선정 뒤 300개의 신규 seed를 이용해 별도 확증

V3·V4 개발 결과를 검토한 뒤 후보 **하나**를 선정. 다음 예시는 BOTH2이고 후보 채택을 사전 결정하는 추천은 아니다.

    python3 research/DR_EKF_DIAGNOSIS_20261013/followup_v2/v5_independent.py init --spec specs/v5_candidate01.json --world gauss_level --candidate BOTH2 --seeds 9000:9300
    git add research/DR_EKF_DIAGNOSIS_20261013/followup_v2/specs/v5_candidate01.json
    git commit -m "prereg: freeze V5 DR-only candidate"
    python3 research/DR_EKF_DIAGNOSIS_20261013/followup_v2/v5_independent.py run --spec specs/v5_candidate01.json --run-dir runs/v5_candidate01 --procs 4
    python3 research/DR_EKF_DIAGNOSIS_20261013/followup_v2/v5_independent.py evaluate --spec specs/v5_candidate01.json --run-dir runs/v5_candidate01

- V5는 사전등록 spec이 Git에 커밋되지 않았거나 코드 SHA가 변경되면 거부.
- 누락 셀은 evaluation에서 재실행하지 않고 에러 반환. run에서 완료된 셀을 검증하여 재사용, 덮어쓰기 금지.
- ANEES 2.4~3.6, coverage 92~98%, 말기 ANEES 2.4~3.6을 9/9 충족하고, 위치 RMSE가 frozen EKF 대비 각 셀에서 10% 이상 악화하지 않아야 임시 후보 통과.
- 원래 D6 사용 seed와 개발 seed를 모두 사용 불가.
- gauss_default 세계의 drift 0/1/2는 실질적으로 route별 동일 세계이므로 9개 독립 실험이 아님.
- V5는 **같은 R2/R4/R5 route의 신규 센서 seed 확증만 수행**한다. 새로운 route/scene과 실측 일반화는 별도 시험으로 남긴다.
- 원래 R2-2/D6의 결과와 scientific_PASS는 변경하지 않는다.

## 9. 보존 규칙

- INTERIM 및 NOT_RUN을 PASS로 바꾸지 않는다.
- 사전등록 C1–C7/S1의 공식 판정은 원래 confirm_dr_independent.py만 생성한다.
- 개발용 intervention은 진단과 배포 가능 개선을 구분한다.
- V2 입자 수 수렴, V3 Hessian 수치 검증, V5 9셀 완료 이전에 EKF 일관성 해결을 주장하지 않는다.
