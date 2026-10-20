# T7 온라인 특징과 효용 target 정책

T7A TECHNICAL_PASS / SUPPORTED_BUT_LIMITED. 원본5ac914f의 run39354151551, artifact12233874874를 회수했다. 고정12이벤트·2647패킷에서 Full-only abs_s rank AUC=.742857, 포화=.700000이다. 역사적 이벤트 label에 대한 기술 통계이며 T2 정본의 인과효과나 장면 일반화를 인증하지 않는다.

T7B TECHNICAL_PASS / NOT_ESTABLISHED; NO_GO. 원본 실행 source4eb01aa85344553dfb5111e1369d7658522ef277, run39361956622, artifact12238630433이다. 16 Full조건×4bias와 Native LoS2조건×4bias, 총72셀을 POWER1/R0/POLICY로 실행했다. motion/radio 각각 11개 지표를 보존한 POLICY_RESULTS.csv는432행이다. Full64셀 중52개, Native LoS8셀 중8개에서 사전 등록10% 악화 한도를 초과했다. POLICY_COMPARISON.csv에 모든 셀을 보존했다.

예: O01 L2 motion에서 POWER1 .452926° → POLICY9.363465° (20.673291배). 최대 악화 셀을 지우거나 파라미터를 다시 맞추지 않았다. 재귀 정책 채택은 하지 않는다.

Nested route-heldout P1 prior와 offline10s counterfactual utility label을 사용했다. 신규9조건은 학습에 쓰지 않았다. 온라인 행동은 현재 Full RF 특징과 해당 정책의 prior NIS/sigma/Pψb/Hsψ만 사용하며 원래 gate를 유지한다. GT·미래는 offline label 생성·평가에만 사용한다. 학습 label·fold·모델 SHA·CSV 행동 로그를 보존했고 큰 NPZ trace는 artifact에 보존하고 원본 학습 pickle은 TRAINED_MODELS_BASE64.json에 byte 그대로 인코딩해 git에도 보존한다. restore_models.py로 hash 검증 후 복원한다.

POWER1 기준선64셀의 Heading 최대 차=9.72555369571637e-14°, gate 불일치0. 모든 평가에서 독립 scorer≤1e−9를 요구했고 오류는0건이다. Native LoS는 별도 안전성 대조로 평가했다. 모델 학습/인터페이스 시험/최종 재귀는 단계별 manifest로 구분한다. T4 완료 dependency는 원래 GLOBAL 집계에서 확인했으며 후속 POST30 판정 범위 수정은 정책 label·feature·학습·파라미터를 바꾸지 않는다.

## 주장하지 않는 것

독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증, 효용 label의 온라인 접근을 주장하지 않는다. 원래 복도와 C조건은 같은 장면이며 O조건도 한 오피스다. 조건 수를 독립 표본 수로 사용하거나 p-value를 제시하지 않는다. NO-GO를 보존한다.
