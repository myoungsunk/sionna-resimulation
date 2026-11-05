# 동적 detector-domain mapping 검증 계획 — 미실행

질문: 측정 전 위치/방향 prior를 SourceFFD native detector tap/range로 변환한
7점 envelope가 실제 동적 불확실성과 raw-only 이력의 offset 보정을 지탱하는가?
기존 E0 static mapping 확인은 동적 검증의 대체 근거가 아니다.

## 고정 대상

R2/R4/R5 B0의 모든 보관 prior/Pprior, 동일 주파수/RX/정규화, 원본 SourceFFD bank,
sigma scale=2, slack=0.15m, VAB/TWO_PORT_UNION 및 검출 전용 이력 R1을 고정한다.
LoS/truth는 평가자에만 제공한다. pose별 native tap, geometric range, offset을 별개로 기록한다.
model의 연속 range surrogate를 native detector range로 대체해 해석하지 않는다.

## 단계별 검사와 기록

1. 입력 동일성/인과성: packet-control-trace-evaluator t/pose exact join, prior 시점,
   source/model SHA, Rx 순서와 주파수 확인. truth·현재 posterior·미래 packet을 온라인 함수에
   전달하지 않는 API/변조 반례. 배열/hash/schema/인과 위반은 0건이어야 한다.
2. 수학 특수 사례: 영 공분산은 동일 중심 7점, 양의 준정부호·yaw wrap 경계,
   대칭 perturbation, 축 교환, 비유한 입력 거부, tap quantization 경계.
   중복점의 일관성과 행 재배열에 대한 envelope 불변성을 검사한다.
3. 동적 sensitivity: 전체 prior 중심과 7점에 대해 native range/tap, envelope 폭,
   분기 전환, 포화/invalid를 기록한다. 경로별·Full/LoS별·정상/큰오류별 누락/제외 분모 공개.
4. envelope 반례: 동일 frozen prior 공분산의 축 조합/회전 방향에 대해 7점 외 probe를
   별도 사전 등록하고, envelope 밖 거리와 tap 차이를 전수 기록한다.
   7점은 confidence region이 아니므로 통계적 95% coverage로 해석하지 않는다.
5. wrong/overconfident prior: 사전 고정 위치/방향 오프셋과 공분산 축소 grid에서
   HOLD_PRIOR/잘못 좁은 support/원래 tap 배제 빈도를 공개한다. grid와 목표 허용치의
   별도 사전 계약이 확정되기 전 이 계산을 시작하지 않는다.
6. 이력: 원래 tap만 갱신, bootstrap 전/후, gap>2s, 중복/역순 packet, 비정상 ds,
   stale offset 및 prior conflict 합성 검사와 실제 시간열 diagnostics를 분리한다.
   미래 packet 변경이 이전 결과에 영향을 주면 실패다.

## 판정과 중단

구조·정체성·인과성·유한성 검사는 위반 0건을 요구한다. 성능/coverage 수용 기준은 아직
동결되지 않았으므로 관찰 결과를 보고 slack·grid·임계값을 맞추고 PASS로 선언하지 않는다.
수용할 probe domain, 허용 envelope miss 및 과도 폭 기준을 실행 전 별도 계약에 명시해야 한다.
반례가 나오면 원본 recipe 결과를 보존하고 새 mapping 버전으로 수정·재검증한다.
단순 `mapping_reviewed=true`는 부족하다. PASS_DYNAMIC_MAPPING_REVIEW receipt에
code/policy/candidate/bridge/selector/history 해시, 실제 근거 파일 목록, 검토자를 기록한다.
현재 receipt는 NOT_RUN이며 E1-02/E2 실행 권한이 없다.

완료 후에도 주장 범위는 노출 개발 데이터의 mapping/검출 준비 적합성에 한정한다.
