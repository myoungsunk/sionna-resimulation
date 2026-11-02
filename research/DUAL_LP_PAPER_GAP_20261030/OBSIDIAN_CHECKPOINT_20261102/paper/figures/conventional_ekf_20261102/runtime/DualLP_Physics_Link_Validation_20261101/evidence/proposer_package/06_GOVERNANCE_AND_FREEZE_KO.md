# 06. 기존 GitHub 역할 문서 적용 및 동결 준비

## 적용 문서와 성격
읽은 문서는 현재 원고 branch의 AGENTS.md, 고정 governance ref의 COMMON_CONTRACT/ROLE_PROPOSER, 기존 DLP-EKF-GAPS-001 초안·GOVERNANCE_APPLICABILITY_KO.md, v4 원고, source diag_mbvar 코드와 이전 검토 패키지다. 원래 MBVAR-INFO 규약은 scoped 규정이므로 새 DLP-PHYS-LINK-001에 자동 강제권이 생긴다고 주장하지 않는다. 기존 DLP 적용 문서와 같이 역할분리·원본보호·해시·진짜 독립감사·실행 전 동결을 **자율 채택**한다. 원문 governance나 이전 계약은 수정하지 않는다.

| 기존 규정 | 이번 적용 |
|---|---|
| role/base/governance/hash lock | APPLY; 계약·config·원본 evidence를 구분해 기록 |
| DRAFT/FROZEN와 pre-run independent auditor | APPLY; 문서 업로드로 과학 실행 권한이 생기지 않음 |
| MBVAR S0/S1/TrackR 정해진 scenario·GP·RT budget | NOT_APPLICABLE; 그 연구 계약과 결과는 보호 |
| original model parity | ADAPT; 이번 원고의 BB/MB×ORIG/VAR×fixed/self 및12조건 |
| independent scene split | APPLY as claim boundary; 동일 C0는 retrospective explanatory analysis |
| new multi-anchor·mount45·SUB3·5state 제약 | NOT_SELECTED; 별도 기존 연구를 이번 목적에 섞지 않음 |
| artifact source hashes와 실패 보존 | APPLY; invalid sample·음성 결과도 분모 포함 |
| controlled physical RT | NOT_APPLICABLE; 이번 범위 RT0, 새 RT는 별도 제안 필요 |

## 책임과 서명 상태
PROPOSER는 본 설계·실험의도·예산·주장규칙을 준비했다. IMPLEMENTER와 AUDITOR는 이번 세션에서 수행하지 않았으며 미할당이다. 공유 role 문서를 읽었다고 다른 역할을 수행/승인한 것은 아니다. 저자는 새 source·범위·동결 여부를 승인하고, 독립 감사자는 구현자의 서술이 아닌 별도 계산으로 source→observer→gain→score를 검증한다.

| 동결 전 item | 현재 | 해소 주체 |
|---|---|---|
| 원고 scope:3 B routes×4gyro | 제안 범위 명시, 변경 없음 | User/Proposer |
| base·governance·evidence SHA | 문서에 고정 | Proposer |
| full H/LoS/CONTROL/FFD/train weights 바이트 lock | SOURCE_REGISTER locator만 존재; 미완성 | Implementer preflight |
| original baseline full x/P reference | trace 실제 파일 확인 필요 | Implementer + auditor |
| finite/accepted/stable universe | 후보 분모 고정, 실파일 검증 필요 | Implementer |
| numeric FD/identity tolerances | 제안 config, 테스트 전 감사 필요 | Proposer + auditor |
| lookup 시간·constant 기준 | 제안서 수식으로 고정 | Proposer |
| output schemas·max run count | 문서 명시 | Proposer/Implementer |
| prior mean의 learned lineage | archive replay와 fresh inference 분리 미확정 | Implementer |
| 별도 pre-run auditor | NOT_ASSIGNED | User |
| science FROZEN signatures | NONE | Proposer + auditor + user approval |

## 승인 가능한 단계와 금지
현재는 **문서·패키지 전달만 완료**다. 별도 사용자 지시로 배정된 구현자는 V0 출처/수학 preflight 후보를 준비하고 설계 충돌을 반환한다. 그 후보와 audit를 바탕으로 versioned FROZEN contract를 만드는 과정은 향후 일이다. 아직 결과–label 관계를 새로 계산하거나 학습/필터/RT를 시작하지 않는다.

Future freeze record는 contract SHA, config SHA, input lock SHA, independent audit URI/identity/session, authorization scope, UTC, prior results observed 여부를 포함한다. 원고와 현재 source는 이미 관찰된 개발자료이므로 retrospective라는 사실은 동결 후에도 사라지지 않는다.

설정 변경이 필요하면 원래 규칙·변경 규칙·왜 필요한지·결과 관찰 여부·영향받는 run과 claim을 AMENDMENT-XXX로 남긴다. 독립 감사 부재를 스스로 채우거나 실패 결과를 덮어써 승인하지 않는다.
