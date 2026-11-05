# C3-EXEC-01: 첫 호출 이전의 native scalar 읽기 결함

CANARY_001은 게시된 GO와 코드/입력/런타임 검증 및 scene 구성 후, scene.frequency의 Mitsuba Float를 Python float로 바로 바꾸려다 TypeError로 종료했다. primary_solver_calls=0, repeat_solver_calls=0, completed_conditions=0이다. logs/G2_CANARY_001_*와 CANARY_001의 MANIFEST/FAILURES/ARTIFACT_HASHES 및 생성된 scene을 그대로 보존한다. 1회의 실행 시도가 있었으며 과학 RF 결과는 생성되지 않았다.

수정은 원본 native scene의 1원소 frequency array를 np.asarray(...).reshape(-1)로 읽고, 길이1/유한성 검사 후 첫 스칼라를 비교하는 것이다. 원래 setter·solver·주파수·정밀도·장면·yaw·조건·threshold는 바꾸지 않는다. 실제 Mitsuba Float의 정상/NaN/여러 원소/빈 배열 회귀검사를 추가한다. 이 테스트는 RT PathSolver나 scene을 만들지 않는다.

새 출력은 CANARY_002이며 기존 GO_CANARY.json을 보존한다. 새 GO_CANARY_002.json 및 별도 SPEC 운영 수정 확인과 CODE 재감사가 있어야만 실행 가능하다. PLAN의 변경은 출력/GO/해당 SPEC receipt 경로와 수정 기록뿐이다. 총 RF 예산은 그대로 본1028+repeat12=1040이며, 이전 시도의 실제 호출0과 새 시도의 호출을 분리 기록한다. 자동 재시도하지 않는다. G3 잔여20, G4 모델 계산은 계속 HOLD이다.
