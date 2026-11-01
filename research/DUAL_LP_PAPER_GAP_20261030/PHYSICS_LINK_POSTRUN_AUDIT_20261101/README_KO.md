# Dual-LP Physics Link — 제안 목적·구현·결과 사후 감사

**최종 판정: 제출물 REVISION_REQUIRED / 재구현 핵심 수치 ACCEPT_WITH_BOUNDARIES / 과학적 결과 MIXED.**

## 읽는 순서

1. [감사 보고서](AUDIT_REPORT_KO.md): 무엇을 실제 재계산했고 무엇이 미확인인지, V0–V5의 유효범위와 R1–R6 지적.
2. [구현자 수정 인계서](IMPLEMENTER_REPAIR_HANDOFF_KO.md): 구체적 코드 위치, 최소 수정, 실패 주입시험, 완료조건.
3. [기계 판독 판정·검증 범위](AUDIT_VERDICT.json): 입력 ZIP SHA, 독립 재계산 수, 최대 수치 차이, FFD 회수 및 역할 제한.

## 확인된 사항

144 논리 비교의 1,296 지표를 132개 실제 trace에서 별도로 재산출했다. 원 CSV 864개 표시값과 B0/L2 original CONTROL 12개 상태/P/mask를 대조했다. 50,176 동일-prior 갱신 후보, 다른 두 route로 정한 상수 추가분산, 6,272행 보존 prediction 계보도 확인했다. 모든 trace의 운동·업데이트 대수는 전수 검사했다.

GitHub에서 원 ±45° FFD bank를 추가 회수해 SHA를 대조한 뒤, source model의 9,408 차분 중 안정 9,356/전환 52를 분리했고, 모든 132개 trace에서 추출한 4,224개 prior의 h/J를 재계산했다. 원본 SourceFFD는 공유하지만 제출 validation helper는 사용하지 않았다. 모든 필터를 132회 새로 재실행한 것은 아니며 외부 기관 인증도 아니다.

R4의 상수 우세·XY 악화는 유효한 결과다. 이를 실패로 바꾸거나 다른 모델로 교체하도록 요구하지 않는다. 현재 요구사항은 출처 정리, 실제 mean-null 시험, 필수 검사 fail-closed 집계, 첫 분기 값 원장 보완이다. 강한 누적 인과 설명에는 별도 근거가 필요하나 V4가 선택 항목이라는 사실은 유지한다.

## 원격 게시 상태와 감사 대상의 구분

원본으로 언급된 `1550335002367c656939bab4876675c612f0915c`는 현재 원격에서 찾지 못했다. 첨부 ZIP은 이를 회수하지 못하고 새로 계산한 `NEW_RETROSPECTIVE_RECONSTRUCTION`이라고 명시한다.

기존 validation branch HEAD `20f4545ca5b462c1f8be4464607108f5fdc681fe`는 일부 문서 두 개만 게시했다. rebuild branch HEAD `632568ae79de36ad4d75d4e40e3e5628c1181e7d`에는 입력회수 workflow 세 개가 있을 뿐 검증 코드·전체 trace가 모두 커밋된 것은 아니다. 이 감사 브랜치는 **감사 문서와 판정만 게시**한다. 원본·재구현 전체 ZIP을 게시했다고 주장하지 않는다.

감사 대상 ZIP: 219,499,008 bytes, SHA256 `fda9f1c34e8f14471ea00238b3c24a269ed17acc59d5f9a0c7f6041df314aca3`.
별도 재계산 스크립트·원장 CSV·로그는 대화의 `DualLP_Physics_Link_Proposer_Audit_20261101.zip`으로 전달한다. 대용량 검증 입력·FFD bank는 그 감사 ZIP에 중복 포함하지 않으며 재현 안내에 출처와 해시를 명시한다.

## 변경 범위

이 audit 폴더의 신규 파일만 추가했다. 원 구현·모델·입력·결과·원고·기존 계약·Actions는 수정하지 않았다. 정식 사전 독립 승인 없이 실행된 역사적 결과를 소급 FROZEN 또는 preregistered로 승격하지 않는다. 사용자 요청에 따른 사후 기술 감사로 기록한다.
