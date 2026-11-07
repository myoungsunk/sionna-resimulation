# PALO-GAP-002 추가 실험 및 독립 감사

최종 상태: 독립 검산 ACCEPT. 과학적 적용/채택은 별도이며 현재 개발용 단일 임계값 판정기는 채택하지 않는다.

- [독립 감사](audit/INDEPENDENT_AUDIT_KO.md)
- [누락 증거 보완 및 대조 참조 정정](audit/CORRECTION_NOTE_KO.md)
- [기존 실험 보고서](REPORT_KO.md)
- [전체 재수용 사건](audit/REACCEPTANCE_ALL_ARMS.csv)
- 재현: `audit/independent_audit.py`, `audit/independent_supplement_check.py`. 기존 PALO_EXACT_ORACLE 자료 및 동일 Python/NumPy/SciPy 환경 필요. 스크립트 상단 경로는 실행 환경의 원래 경로다.

원래 보고서/README의 감사 대기 표시는 생성 당시 상태로 보존했다. 현재 상태는 본 문서와 audit 보고서를 따른다. 원본 668개 manifest 파일과 636개 궤적은 변경하지 않았으며, 전체 14,239개 재수용 정책-사건 보완표를 추가했다. 이 사건들은 독립 물리 표본이 아니다.

범위: R2 anchor B seed0 및 공개된 자료의 진단 대조. RF 오염 oracle, 현재 시점 Heading 손익 oracle, 오류 주입, 관측 가능 특징, 공분산 전파를 비교했다. 독립 환경 일반화, 전역 최적 상한, 공분산 통계적 보정 및 실용 판정기 성능 입증을 주장하지 않는다.

거버넌스: 기존 실험에 동결된 COMMON_CONTRACT SHA256 a5cca7d8a8d5f20f4a89ea9b6509da0b8d7506626aac4a47fa1d27891ff5ebdb; 감사 역할 SHA256 e1bdc2f231c71cdc27201c688e041b078576a6adf6c0290acc16ce4d8218291a.
