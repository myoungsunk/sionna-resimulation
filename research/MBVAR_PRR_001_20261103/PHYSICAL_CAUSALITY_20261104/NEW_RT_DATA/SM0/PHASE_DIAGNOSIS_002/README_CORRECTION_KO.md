# 수치 진단 002: 001의 비교 연산 정밀도 정정

이 진단의 권위 있는 소스는 `diagnosis_phase_002.py`와 SM0 최상위 `diagnosis_phase.py`이다. 두 파일의 SHA256은 **bf65e40e51a7cd89bb812c2d77e79e7d81c66aa5c66b4d8c3197304677d15608**이다. 진단 결과는 이 폴더의 `NUMERICAL_DIAGNOSIS.json`을 인용한다.

001에서 002로 바뀐 것은 `compare()` 첫 부분의 두 줄뿐이다. 비교 대상과 참조를 먼저 complex128로 승격한 뒤 크기와 교차 위상을 계산한다. 001은 complex64 입력끼리 `actual * conj(reference)`를 계산할 때 단정도 반올림 때문에, 비트 단위로 같은 CFR 배열에도 최대 약2.51e-8rad의 가짜 교차 위상을 보고했다. 002에서는 동일 배열의 상대 오차와 위상 차이가 모두 정확히0이다. complex64 크기 연산의 작은 반올림도 함께 제거된다.

새 RF 계산, 원시 데이터 수정, 위상 보정/정렬, 정규화, FFT 또는 기여도 계산은 없다. 원래 canary의 STOP_MISMATCH, 생산자 소스/계약, raw/실패 receipt 및 판정 기준도 바꾸지 않았다. Full/LoS의 주요 복소 상대 L2 오차와 결론은 동일하다. 두 버전의 `PHASE_CONTROLS.npz`는 같은 SHA256 **bdcd6f9b0ceaa7248cfbafa9099c0ee00eb5fe107b8a770eaf71b37bb793fc13**이다.

001은 보존한다. 당시 소스는 `../PHASE_DIAGNOSIS_001/diagnosis_phase_001.py`, SHA256 **3ea9f5f99cd638e68ad1fd200436a474ce219205ceb5b9a02dbe76b68b4edab0**이다. 알려진 두 줄 차이를 되돌린 bytes가 당시 결과 JSON에 기록된 소스 SHA와 정확히 일치함을 확인한 뒤 이 사본을 추가했다. 이미 게시된001 결과에는 이002 정정 문서를 연결해야 한다.

해석 범위는 보존된 raw에 대한 수치 위상 관례 진단이다. original32를 새로운 수용 기준으로 선택하거나 원래 canary 실패를 PASS로 바꾸는 근거 문서가 아니다.
