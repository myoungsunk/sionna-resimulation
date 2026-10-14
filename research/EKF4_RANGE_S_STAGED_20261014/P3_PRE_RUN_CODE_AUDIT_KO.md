# P3 RF 동결 입력 사전 감사 — R3 P2와 별도 자료 적격성 검증

**목적:** 기존 EKF3 P0에서 고정한 39개 RF/LUT/센서·경로 파일의 SHA/shape, 7 case/time/pose_id alignment를 다시 재사용 가능한 입력으로 검사한다. 기존 과학/효과 PASS가 아닌 **입력 적격성** 판정으로 제한한다. 이는 P2 합성 bias 가설의 긍정/부정과 독립인 선행 자산 감사다.

**소스:** 원 `research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json`과 `p0_verify_inputs.py`를 변경하지 않는다. 실행 전 `p3_pre_audit.py`에서 두 파일의 Git blob/sha, manifest의 필수 물리 계약·관측 정의·기존 도구의 AST·workflow audit 선행 여부를 검사한다. P3 실행은 사전 감사 GO 후에만 GitHub-hosted에서 가능하다. 독립 DR-only/RF Range 실험을 자동으로 이식하지 않는다.

**필수:** 원 데이터 checksum/shape/pose_id 누락·불일치, 참값을 추정기로 공급하는 누수, 각도 단위/부호 변경 → 해당 RF 입력 실험 HARD BLOCK. 원 FFD/LoS channel mapping과 R0 가우시안 독립성은 추후 P4 모델 검증 항목으로 별도 표시한다.

**합격 범위:** `P3_INPUT_ELIGIBLE`일 뿐, P4 새 4-state RF 필터, P5 G3 확률적 적분, P6 재귀 실험이나 독립 환경 일반화 성능의 검증이 아니다.
