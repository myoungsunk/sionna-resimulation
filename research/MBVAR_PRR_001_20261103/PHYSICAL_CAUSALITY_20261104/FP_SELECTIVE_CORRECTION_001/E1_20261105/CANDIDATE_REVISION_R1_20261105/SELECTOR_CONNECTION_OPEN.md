# OPEN — 후보 생성과 후속 선택기의 지원 의미 연결

상태: 미해결 / 이번 E1 후보 개정 재검증 범위 밖. E2_GO=false.

확인한 후속 소스 커밋은 486f0b6c008e7a953ada75a03a941ffa46994985다. 그 버전의 selection.from_pool은 max_lobe[min(1,prominence/G) * exp(-abs(tap-edge))]를 support로 만들고, select는 supported=true 및 support>=0.15를 요구한다. 모든 지원 edge에서 거리가 2 이상이면 support<=exp(-2)=0.1353352832이므로 추가 후보가 선택 가능 집합에서 다시 빠질 수 있다. B가 허용한 낮은 양측 prominence도 기존 점수에 재사용된다. 다른 포트/봉우리의 지지가 있을 수 있으므로 모든 추가 후보의 무조건 탈락으로 일반화하지 않는다.

이번 R1 생성기는 별도 모듈이며 OriginalAdapter/Policy/selection.py를 수정하지 않았다. E1 가용성 결과를 후속 선택 성공으로 연결하거나, 그림 스크립트가 운영 adapter에 설치되었다고 해석하면 안 된다.

후속 작업은 candidate_revision, candidate_config_sha256, support_semantics_version, mapping_recipe_sha256의 명시적 결속, supported/selection_eligible/rf_score 의미 분리, 같은 lobe와 다른 group 사이 margin 구분, 강한 e+2/낮은 bilateral·높은 left-rise/noise-only/한 RX null 회귀가 필요하다. 정확한 점수식·가중치·선택 안전성 관문은 별도 계약 및 검증 대상으로 남긴다. 기존 전역 임계값만 낮춰 해결한 것으로 처리하지 않는다.

이 기록은 선택기 변경·실행 또는 E2 시작을 승인하지 않는다.
