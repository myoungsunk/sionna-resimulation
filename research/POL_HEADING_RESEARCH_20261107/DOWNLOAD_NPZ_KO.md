# LFS 없이 실제 NPZ 받기

이 문서가 포함된 커밋부터 이 연구 패키지의 NPZ 300개는 LFS 포인터가 아닌 일반 Git 바이너리다. 총 172,129,371바이트이며, 각 파일은 기존 `4c0df3972b2f8d5c193e862a446084dc8a06cbcb`의 LFS SHA256 및 크기와 일치한다. 과거 커밋 자체의 포인터는 변경하지 않았다.

- 입력: [original_run/verified_inputs](inputs/original_run/verified_inputs/)
- S4를 포함하는 원본 재귀 결과: [original_run/results/replay](inputs/original_run/results/replay/)
- 원본 입력·실행 ZIP: [AnchorB_8arm_Run_v1.zip](inputs/original_run/AnchorB_8arm_Run_v1.zip)
- 원본 결과 ZIP: [AnchorB_8arm_Results_v1.zip](inputs/original_run/AnchorB_8arm_Results_v1.zip)
- frozen LUT·기존 코드: [FGO frozen](experiments/POL_FGO_CORR_20261106_v1/frozen/)
- NPZ별 SHA256·크기: [NPZ_DIRECT_MANIFEST.json](NPZ_DIRECT_MANIFEST.json)

GitHub 파일 페이지의 **Download raw file**로 실제 NPZ를 받는다. 이 패키지의 폴더 구조를 유지하면 `python -X utf8 portable.py verify`로 원본 보존 해시를 검사할 수 있다. 검증에는 Sionna RT 재계산이 필요하지 않다. NPZ 단독으로 새로운 분석 전체의 실행 가능성이 보장되는 것은 아니며 Python 의존성과 분석용 경로 설정은 별도로 필요하다.

저장소 다른 경로의 대형 antenna bank 등에는 LFS가 남아 있다. 전체 저장소를 받을 경우 해당 객체의 자동 다운로드를 생략하려면 `GIT_LFS_SKIP_SMUDGE=1`로 clone한다. 이 연구 패키지의 NPZ는 그 설정에서도 실파일로 체크아웃된다.

이번 변경은 파일 전달 방식만 바꾼다. 기존 결과·수치·실패 판정은 그대로이며, 이후 로컬 A단계 결과를 이 커밋에 추가한 것은 아니다.
