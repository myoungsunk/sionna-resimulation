# 기존 진단표 사본

이 폴더의 CSV는 이전 대화에서 만든 자료를 변경 없이 복사한 것이다. 이번 계획 작성 중 새 MB_VAR 실행·파라미터 시험을 수행하지 않았다.

- threshold_sweep_same_prior.csv: 저장된 prior에서의 사후 검출 비교. 새로운 임계값을 적용한 전체 재귀 성능이 아니다.
- one_step_Rss_counterfactual.csv: 동일 prior의 1-step 재계산. 일부 원본 로그는 float32이므로 1e-10 precision 인증용이 아니다.
- conditional_residual_descriptive_bins.csv: 조건부 잔차 기술통계. 온라인 오염예측기의 검증 결과가 아니다.
- AnchorB_MBVAR_selected_hotspots_B0.csv: 선택된 사건표. 사후 선정 표본이므로 전체 경로 대표성이나 일반화 근거로 쓰지 않는다.

사본의 SHA256과 원 ZIP hash는 SOURCE_REGISTRY.json에 기록했다. 이 hash 확인은 파일 무결성 확인이며 독립 코드/결과 감사가 아니다.
