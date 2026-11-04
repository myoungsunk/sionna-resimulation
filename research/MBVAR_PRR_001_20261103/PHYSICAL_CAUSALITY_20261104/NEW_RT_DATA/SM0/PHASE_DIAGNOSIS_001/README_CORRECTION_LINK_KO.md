# 001 보존 및 002 정정 안내

001 결과/controls는 원본 그대로 보존한다. 수치 비교의 권위 있는 최신 결과는 `../PHASE_DIAGNOSIS_002/NUMERICAL_DIAGNOSIS.json`이다. 변경 내용과 소스 SHA는 [002 정정 기록](../PHASE_DIAGNOSIS_002/README_CORRECTION_KO.md)을 따른다.

002는 비교 입력을 complex128로 승격해 complex64 자기 교차곱의 가짜 위상 반올림을 제거했다. 새 RF 계산이나 canary 판정 변경은 없으며, raw 기반 controls bytes도 동일하다. 기존001 게시/인용에는 이 정정 링크를 함께 표시한다.
