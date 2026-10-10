# A23 이후 기존 실행 증거 게시

이 패키지는 요청 revision `ccc1ba5`에서 별도 결과 브랜치로 게시한다. 새 실험, 측정모델 수정, Q/R·gate·prior 변경은 수행하지 않았다. 원 실행 revision은 `f81b42d541fdf9a37b6868d4901c2a3bb9d8090e`이며 게시 commit과 구분한다.

- [Q2·joint·L2 한국어 보고서](Q2_JOINT_L2/FINAL_REPORT_KO.md)
- [Q1 보고서](Q1/FINAL_REPORT_KO.md)
- [요청 충족·누락 목록](REQUEST_FULFILLMENT.json)
- [필터 원자료](Q2_JOINT_L2/retrieved/OUTPUT/)
- [L2 원자료](Q2_JOINT_L2/retrieved/L2_ATTEMPT3/)
- [전체 파일 해시·크기·CSV 열·NPZ shape](PACKAGE_MANIFEST.json)

Q2 1,200행·joint 450행, 통합 3,300행은 누락·중복·실패 0으로 검산됐다. trace는 기존 seed 0–1만 있다. 요청한 seed 2–4 및 J3 블록 시작 인덱스는 저장되지 않았으며 이번 게시에서 새로 만들지 않았다. `VERIFICATION.json`의 공분산 검사는 저장 trace 범위에만 해당한다.

L2의 2,056회 호출은 **8 pose × 257 주파수**이다. `s`는 257 주파수로 만든 CIR 전체에 대해 pose당 한 번 계산한다. 따라서 최대 직접 LoS–Sionna 차이 8.569e−7은 8개 광대역 관측값에서의 최대이며, 2,056개의 독립 `s` 표본에서 얻은 값이 아니다. `CHANNELS.npz`의 H는 (8,257,2,2)이며 주파수별 경로 계수·지연도 보존한다. 원 L2 최대 0.0104489, 4/8 위반으로 FAIL이다.

요청 B의 저장되지 않은 sub-tap/branch 선택/격자점 tap·가중치 중간값, C의 전체 timeline LoS H·반사 경로 자료, D의 G3 pose 집합 일치는 미검증 또는 미수행이다. C는 신규 RF 계산이 필요하다. 이번 게시를 잔차 분해 완료나 F01/F02 해결로 해석하면 안 된다. `scientific_PASS=false`, F01/F02 OPEN을 유지한다.

원 로컬·Snowball 자료는 변경하지 않았다. 복사한 보고서의 파일 링크만 브랜치 상대 경로로 바꿨다. 원본 해시와 게시 해시는 manifest에서 구분한다. NPZ/NPY는 이 디렉터리의 속성으로 LFS를 해제해 전체 바이트를 게시한다. 40 MiB 초과 파일은 없다.
