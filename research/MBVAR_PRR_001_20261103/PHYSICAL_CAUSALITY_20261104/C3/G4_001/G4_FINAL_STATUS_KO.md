# C3 G4 최종 상태

사용자 요청: 확보한24조건으로 기존 계약의 코드·의존성 관문을 먼저 통과하고, 물리 분석·독립 결과감사 후 GitHub 게시. 질문 C3-SM2-YAW-001.

| 구분 | 상태 | 근거 |
|---|---|---|
| 독립 SPEC·CODE 및 SHA 실행 GO | PASS | audit/C3_G4_SPEC_RESULT.json, C3_G4_CODE_RESULT.json, GO_G4_001.json |
| 실행 전 검사·의존성 | 10검사 PASS | logs/preflight_004.*, PREFLIGHT_RECORD_KO.md |
| 실제 저장 RF 분석 | 정상 종료0 | logs/analysis_001.json 및 managed_finish; RUN_001/MANIFEST.json |
| 독립 수치·결과·주장 감사 | ACCEPT | audit/INDEPENDENT_G4_RESULT_001.json, C3_G4_RESULT_AUDIT_RESULT.json, RESULT_FINDINGS_G4_KO.md |
| GitHub 결과 게시 독립감사 | ACCEPT | audit/C3_G4_PUBLICATION_AUDIT_RESULT.json |
| 이전 G3 원래 실행 결함 | 미해결·원본 보존 | FORCED_AFTER20, original_clean_execution_acceptance=false |
| 알고리즘 전체 채택 / 실시간 적용 | NO-GO / HOLD 유지 | 물리 관측 분해를 필터 성능·지연 개선으로 해석하지 않음 |

## 결과와 범위

6좌표×4yaw=24조건, 6좌표×6대조=36쌍, 6,168 주파수 bin, 경로 제거2,976행과 표면 제거288행을 보존했다. 생산 모델 초기화1회와 별도 독립 검산 모델 초기화1회이며 새 RT·학습·EKF는 모두0회다. 원래 모델·전이 의존성·bank·Windows C1B 환경·BLAS1을 고정했다. 두 실행 모두 자연 종료0 후 실제 프로세스·supervisor·job 부재 및 참조0을 확인했다.

원래 모델의 Hψ는 20조건에서 두 step의 smooth 차분 검증을 통과했다. P10Yp/P10Yn의 yaw0°/180° 네 조건은 branch 변화로 미정의를 표시하고 endpoint를 보존했다. 새 RT의 물리 미분·Fisher 정보로 해석하지 않는다.

R5_982 yaw0°의 eMP=+0.541626은 fixed=+0.081130과 selector=+0.460496으로 나뉘며 +35.7°에서는 selector=0이다. P10 두 좌표의 8조건은 tap 변화가 없지만 fixed 차이가 남는다. 직접파 응답 변화와 복소 간섭·검출 tap 선택을 분리해야 한다는 이 좌표·yaw 범위의 근거다. 전체 표·반례·저장 경로 개입 및 해석 한계는 [G4 물리 분석](G4_PHYSICAL_FINDINGS_KO.md), [독립 결과감사](audit/RESULT_FINDINGS_G4_KO.md)에 있다.

## 게시 이력

- 코드·독립 GO: `1c1decaa8ae43dcd5119596943b499f9b495d338` (33파일, LFS0).
- 결과·독립 결과감사: `3c520c977a106c5eccd8b6bab36078757bf027f8` (127변경파일, LFS24).
- 별도 게시감사 수신증·운송 기록·이 최종 상태 문서는 후속 메타데이터 커밋으로 게시한다. 자체 최종 커밋 SHA를 문서에 소급 삽입하거나 재귀적 자기 해시를 주장하지 않는다.

독립 게시감사는 결과 커밋의 Git 원문과 LFS pointer OID/size, 로컬 실제 payload SHA 및 업로드 성공을 확인한다. 원격 LFS payload를 다시 내려받는 감사는 수행하지 않았다. 최종 메타데이터 게시 후 Mother가 원격 branch SHA와 실제 Git/LFS 바이트 연결을 다시 확인하며 이것은 독립 과학 감사와 구분한다.

기존 C0–C2·G2·G3 산출물과 계약·임계값은 변경하지 않았다. G3의 저장 데이터 ACCEPT만 이용했고 원래 강제 종료를 정상 종료로 소급 변경하지 않았다. 현재 G4 수용과 기존 전체 알고리즘 채택·실시간 판정은 별개다.
