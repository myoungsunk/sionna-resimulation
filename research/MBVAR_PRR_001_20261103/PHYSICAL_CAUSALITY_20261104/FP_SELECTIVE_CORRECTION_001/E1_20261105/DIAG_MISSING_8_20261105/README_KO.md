# 참조 후보 누락 8건 분석 및 수정 제안

사용자가 요청한 '참조 후보가 빠진다는게 무슨 말' 이후 분석을 보존한 패키지다. 참조 후보 누락은 LoS 참조 tap이 Full CIR에서 생성한 사용 가능한 후보 집합에 없다는 뜻이다. 원본 CIR이나 물리 경로가 없다는 의미는 아니다.

- [원인 분석 결과](evidence/DIAGNOSIS_KO.md): 4건은 봉우리 돌출도 미달, 4건은 선행 에지 후보 범위 밖. 다른 RX의 보완 실패도 기록했다.
- [실제 CIR 그림](evidence/CIR_8_CASES.png) / [PDF](evidence/CIR_8_CASES.pdf)
- [수정 및 전체 데이터 검증 제안](evidence/CANDIDATE_REVISION_PROPOSAL_KO.md): DRAFT / NOT_RUN. 기존, 상승 구간 확장, 왼쪽 상승 지지, 결합안의 사전 비교 설계.
- [수치 진단](evidence/DIAGNOSIS.json), [직접 역 DFT 자기 검산](evidence/DIRECT_IDFT_CHECK.json), [CIR 수치](evidence/CIR_WINDOWS.csv), [기존 봉우리 로그](evidence/SOURCE_LOBES.json), [기존 후보 로그](evidence/SOURCE_CANDIDATES.json).

원래 E1 실패 판정과 증거를 보존한다. 수정 규칙의 성능 결과는 아직 없다. E2는 시작하지 않았다. 동일 작업자의 검산이며 독립 감사로 주장하지 않는다.

## 실행 출처 및 스크립트 보존

기준 결과 commit: 0a3693f8be99c9c3c08c23dcc094b79bfb3c85cd. 과학 코드 commit: ce4ac73cae7debe3754c7b7b0b0008ca66fdbf5d.

diagnose_missing.py는 Snowball의 기존 fp-sc-e1:20261105 이미지에서 저장소를 /work로 마운트해 실행한 원본이다. 입력/로그 해시 검증과 기존 CIR 재구성만 수행했다. 출력 디렉터리가 이미 있으면 중단하도록 작성되었다. 재현은 새 scratch checkout에서 수행해야 하며 이 보존 폴더 위에 실행하면 안 된다.

evidence/verify_and_plot.py는 원래 로컬 diagnosis8 폴더에서 실행한 원본이다. 원래 배치는 작업 루트 아래 diagnosis8/와 repo/가 나란히 존재하는 구조다. GitHub 보존 위치에서 그대로 실행하는 용도가 아니다. 재현하려면 해당 두 폴더 구조를 별도 scratch 영역에 구성하고 입력 잠금을 충족한 repo를 사용한다. 원본 스크립트의 경로를 유지해 실행 출처를 보존했다.

직접 역 DFT와 기존 복소 CIR의 최대 절대 차이 4.229667081938549e-17. 8건 인접 봉우리/후보 계산 검산 통과. 검산은 새로운 선택기 실험이 아니다. 패키지 파일 무결성은 MANIFEST_SHA256.json으로 확인한다.
