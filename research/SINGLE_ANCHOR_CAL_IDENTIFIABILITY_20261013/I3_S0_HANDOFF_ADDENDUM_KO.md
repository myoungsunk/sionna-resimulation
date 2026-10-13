# I3 인계 보충 — I2 S0 실행 이후

이 문서는 기존 `I3_HANDOFF_PROMPT_KO.md`와 함께 전달한다. 후속 단계나 새 스레드를 자동 실행하지 않는다.

S0 정의는 `S0_CONTRACT_KO.md`로 확정되었고, 추가 실험은 `I2_S0_DESIGN.json`과 `out/i2_s0_run_01/`을 기준으로 수행한다. 과거 I2 S1의 S0 입력 대기 문장은 현재 상태가 아니다. 기존 S1 및 D6/I0/I1 증거는 변경하지 않았다.

다음 담당자는 `I2_S0_REPORT_KO.md`, `out/i2_s0_run_01/I2_S0_GATE.json`, `I2_S0_REFERENCE_VALIDATION.json`, `I2_S0_PRIOR_SENSITIVITY.csv`, `I2_S0_BATCH_PRIOR_SENSITIVITY.csv`, `out/I2_S0_VERIFICATION.json`을 먼저 읽고 실제 업로드 영수증 `I2_S0_PUBLISH_RECEIPT.json`과 원격 커밋을 확인한다. S0 실행 완료와 posterior 참조 승인 여부를 반드시 구분한다.

S0 Range 입력에는 pose prior가 없다. 앵커 수평 원점과 초기 방사방향 +x는 gauge이고, 반경은 첫 noisy range posterior, Heading은 Uniform(-pi,pi]이다. 후속 Range likelihood는 k=1부터 사용한다. I3 추정기에도 이 초기정보만 동일하게 제공한다. 초기 Gaussian pose prior를 다시 넣거나 참 rho/delta를 제공하지 않는다. DR 대조군의 초기 pose (0,0,0)는 상대좌표 gauge이고 range 기반 초기화를 받지 않는다.

수렴 검증 후보는 Gaussian R2/R4 d2 seed8000의 DR 및 Range 0.05m/5Hz이다. 각 폴더의 `*_public.npz`와 `*_config.json`을 사용한다. 해당 S0 public 파일에는 기존 S1 `x0`가 없으며 config의 첫 3개 pose 표준편차는 0인 gauge 표시이고 Calibration 표준편차만 사용한다. 20k/80k PF 독립 반복과 full-horizon Batch 결과를 보존한다. Batch의 모든 관측 horizon을 online filter의 terminal horizon과 맞춘다.

Prior 민감도는 면적 균일 기본값과 반경 균일, half-normal scale 10m/100m 대안이다. 대안은 의도적인 prior 변경이며 유일한 무정보 prior라는 주장을 하지 않는다. 수치 상한 6/10 sigma 비교는 물리적 위치 경계가 아니다. 수치 꼬리 질량 검사 통과만으로 Calibration posterior가 prior에 강건하다고 주장하지 않는다. 참조 미승인 상태에서는 PF 퇴화와 MCMC 혼합 실패가 prior 효과와 섞일 수 있다.

I3가 승인되면 참조 수렴 개선 설계를 먼저 동결하고 진행한다. Target을 보존하는 방법이어야 하며, 임의 jitter·공분산 inflation·PSD repair·임계값 변경으로 승인하지 않는다. 수렴 미달이면 계속 REFERENCE_NOT_VALIDATED로 남긴다. 실용적 오차 예산은 미정이므로 충분/부족 판정은 보류한다. PF 실패를 구조적 관측 불가능성으로 해석하지 않는다. I4/I7/V5는 별도 지시 없이 실행하지 않는다.
