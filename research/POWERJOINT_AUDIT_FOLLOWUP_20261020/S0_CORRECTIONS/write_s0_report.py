"""Render S0 reports from verified immutable outputs; no scientific recomputation."""
from pathlib import Path
import csv, hashlib, json, shutil
HERE=Path(__file__).resolve().parent
def load(name):return json.loads((HERE/name).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    stat=load('statistics_execution/STATISTICS_SUMMARY.json');t4=load('POST_HOC_REVISED_ANALYSIS_T4.json');receipt=load('TRACE_RECEIPT.json')
    for name in ['NATIVE_LOS_CASE_STATS.csv','NATIVE_LOS_GROUP_STATS.csv','SLIDE2_RANGE_STATS_POPULATIONS.csv','SLIDE2_ROW_MAPPING.csv','COORDINATE_PRECISION_CERTIFICATION.csv']:
        source=HERE/'statistics_execution'/name;target=HERE/name
        if target.exists():assert target.read_bytes()==source.read_bytes()
        else:shutil.copyfile(source,target)
    with (HERE/'NATIVE_LOS_CASE_STATS.csv').open() as f:cases=[r for r in csv.DictReader(f) if r['population']=='RF_ARCHIVE_9519']
    with (HERE/'SLIDE2_RANGE_STATS_POPULATIONS.csv').open() as f:slide=list(csv.DictReader(f))
    text='''# S0 사후 정정·모집단 감사 결과

S0 완료. S1/S2/S3, 새 재귀 필터 계산, RF 시뮬레이션은 실행하지 않았다. S0-5 보존 완료를 먼저 확인한 뒤 나머지 정정과 통계를 수행했다. 아래 작업 상태와 과학 판정은 별개다.

| 세부 과제 | 주장/검사 | TECHNICAL | 작업 상태 | 과학·유효성 판정 | 핵심 결과 | commit / run / artifact |
|---|---|---|---|---|---|---|
| S0-5 | 원래 감사가 참조한 입력·trace 보존 | PASS | COMPLETE | 보존 사실만 확인 | 44개, 1,883,401,358 bytes; 원본 API digest·전체 다운로드·release 전체 재다운로드 일치 | lock a37364c; 실행9354b20; receipt f7a0ef3; run39367272729 /12239593294 |
| S0-1 | SRC_TAP 적용성 정정 | PASS | COMPLETE | INVALID_DESIGN_ZERO_RANGE_JACOBIAN | 기존 CSV·판정 보존; B_OLD/B_REFIT_ONLY 유효 | VALIDITY_INDEX.json; 결과 commit은 PUBLICATION_RECEIPT.json |
| S0-2 | Native LoS 9,519점 B_OLD 잔차 | PASS | OPEN | NOT_ESTABLISHED | R2 A M45 mean −0.010192554m: 고정 |mean|<0.01m 실패 | lock c2bf8b8; run39368572991 /12239939880 |
| S0-3 | 슬라이드2 모집단·관측식 구분 | PASS | COMPLETE | SOURCE_CONFIRMED; 인과 NOT_ESTABLISHED | 구1303행 전체/FrozenLut; 새829행 t≥30/SourceFFD; 새 슬라이드 모집단 하나 선택 | 구run38711275905 head7d8d20c; 통계run39368572991 |
| S0-4 | D4 제외한 D3/D6 사후 T4 재집계 | PASS | COMPLETE | NOT_ESTABLISHED → NOT_ESTABLISHED | 지지0/5, 채널 전용 회수2/5; 모든 유익 이벤트 안전성 D3/D6 모두 false | POST_HOC_REVISED_ANALYSIS_T4.json; 기존run39359599833 등 |
| S0-6 | 엔진·정책 판정 명칭 | PASS | COMPLETE | 범위 정정 | 구현1 검증된 실행 기준; 구현2/3 DEFERRED_SOURCE_UNAVAILABLE; v2 정책 NO-GO | VALIDITY_INDEX.json |

## 입력 보존

기존 root summary, task/nested manifest·receipt 153개를 스캔하고 참조 run23개의 전체 artifact를 확장해 44개를 보존했다. 입력 전용·요약 전용·실패 실행 artifact도 포함했다. release `audit-traces-20261020-r01`의 자산을 덮어쓰지 않았다. 원본 API digest 누락·만료·검증 실패는 0건이다. `TRACE_INVENTORY.json`과 `TRACE_RECEIPT.json`에 전체 원본 artifact ID, release asset ID/URL, SHA256, bytes, source/run을 기록했다. 후속 S0 자신의 receipt·통계 artifact는 순환 참조를 피하기 위해 이 과거44개 모집단에 추가하지 않고 별도 실행 manifest에 기록했다.

'''
    text+=f"Inventory SHA256 `{sha(HERE/'TRACE_INVENTORY.json')}`. Receipt SHA256 `{sha(HERE/'TRACE_RECEIPT.json')}`. 보존 결과 artifact12239593294 전체 ZIP SHA256 `2998da585eabf1d1b4b9510de0586ffdcacdd70dd03bba4dbc18ff14f9edb3e4`. 통계 결과 artifact12239939880 전체 ZIP SHA256 `ef4d7d1c9925780b9593344a498b0afe2d8385c09c621426a30a9771071bf068`.\n\n"
    text+='''## SRC_TAP 무효화와 보존

**INVALID_DESIGN_ZERO_RANGE_JACOBIAN. Range 행 Jacobian = 0으로 직접 Range 감도 제거, C_rs·gate 영향만 남음. Range 교정 근거로 사용 불가**

R5 A B0 Heading 4.556146→17.904643° 및 T3/SRC_TAP, T4/SRC_TAP·POST30_SRC_TAP의 원래 수치는 남겨 두되 Range 교정·F1 검증 근거에서 제외했다. SRC 재학습 파라미터·파생 `_src`/`_delta` 열도 같은 적용성 제외 대상이다. B_OLD와 B_REFIT_ONLY는 유효하다. 원래 lock 조건과 decision은 변경하지 않았으며 추가 metadata가 사전등록 조건을 소급해 바꾸지 않는다. 수정 전37개 텍스트 파일은 ORIGINALS/와 RECEIPTS에 bytes·SHA로 보존했다. 기존 CSV357개와 DECISION27개는 byte-identical이다.

기존 “9,519점 중2,268점 미확보로 T6 BLOCKED_INPUT”은 철회한다. 전체 RF archive9,519점과 재귀 clock7,251점의 모집단 혼동이었다. 당시 실패·판정·오류는 이력으로 남긴다. SRC_TAP의 제외 사유는 입력 미확보가 아닌 설계 무효다.

## Native LoS B_OLD 잔차

원본 PACKETS_SOURCE_LABELS.csv.gz SHA256 `02038c4c967750905a80dde31b0bcd0b667bd5d11df1cb02e05023e06893ee4d`, channel=los만 사용했다. SRC 조정 cache를 사용하지 않았다. GT x/y·anchor/height로 거리를 독립 계산하고 e = range − (d + B_OLD), B_OLD=−0.5315983906250129m를 적용했다. 원본 e_r와의 최대차2.22e−15m, tap grid 최대차2.84e−14다.

'''
    text+=f"Δ = {stat['delta_m']:.15f}m; σq = {stat['sigma_q_m']:.15f}m.\n\n| case | n | mean m | RMSE m | RMSE/σq | |e|>Δ/2 비율 |\n|---|---:|---:|---:|---:|---:|\n"
    for r in cases:text+=f"| {r['case']} | {r['n']} | {float(r['mean_m']):.9f} | {float(r['rmse_m']):.9f} | {float(r['rmse_over_sigma_q']):.6f} | {float(r['fraction_abs_error_gt_delta_over2']):.6f} |\n"
    text+='''
7조건 모두 RMSE/σq는[0.8,1.2] 안에 있지만 R2 A M45 평균의 절댓값이0.01m보다 커서 전체 AND 기준은 실패했다. **OPEN / NOT_ESTABLISHED**로 남긴다. 반올림으로 PASS 처리하지 않았다. q01/q05/q50/q95/q99와 사전 고정 거리·polar theta·tap전환 그룹은 NATIVE_LOS_CASE_STATS.csv와 NATIVE_LOS_GROUP_STATS.csv에 포함했다. 빈 bin도 보존했다.

7,251행은 exact case/pose_id로 원본 RF 행과 대응하며 관측 range 최대차5.33e−15m다. 다만 RF SAMPLES의 x/y와 yaw(deg)가6자리로 반올림되어 있다. clock GT를 똑같이 반올림하면 전 행 일치하며, 원래 clock 잔차·거리도 독립 재계산으로 확인했다. 이 정밀도 차이로 잔차가 최대5.036603e−7m 달랐다. 표에는 RF_ARCHIVE_9519, RECURSIVE_CLOCK_7251(원래 clock 잔차 유지), RF_ARCHIVE_SUBSET_7251 세 모집단을 구분했다. 통계에서 새 offset을 맞추거나 행을 빼지 않았다.

## 슬라이드2: 선택한 단일 모집단

**SLIDE_SOURCEFFD_T30_829: R2 각829행, frozen clock t≥30s의 exact pose_id를 원본 RF SAMPLES 행에 대응한 SourceFFD/B_OLD 통계**를 슬라이드의 모집단으로 지정한다. GT 정밀도는 원본 RF SAMPLES(x/y6자리, yaw degree6자리)이며, 과거 T3가 사용한 unrounded clock GT와의 작은 차이를 CSV에 별도로 기록했다. 원래 관측 r·s와 exact pose ID, 반올림 좌표를 모두 검사했다. 전체1303행 비교는 감사 열이다. 수치를 보고 모집단을 선택하지 않았다.

| case | 모집단 | n | μr m | Vr m² | ρ(er,es) |
|---|---|---:|---:|---:|---:|
'''
    for r in sorted(slide,key=lambda r:(r['case'],r['population'])):text+=f"| {r['case']} | {r['population']} | {r['n']} | {float(r['mu_r_m']):.9f} | {float(r['V_r_m2']):.9f} | {float(r['rho_er_es']):.9f} |\n"
    text+='''
구 보고서의 A0/A45/B0 μr(.05225/.07187/.03069), V(.01708/.01658/.00807)은 전체1303행이다. 구 e_s는 FrozenLut, 새 e_s는 SourceFFD다. 따라서 구 수치와 새829행의 차이를 관측모델 효과 하나로 설명할 수 없다. 동일1303행 SourceFFD 상관은 A0 .520767452, A45 .060916713, B0 .089960699이며 구 LUT .525/.062/.096과 구분한다. 원본 전체1303행에 timestamp가 없어 실제 초 단위 구간은 NOT_ESTABLISHED다. nominal dt로 시간을 만들어 넣지 않았다. 자세한 pinned source·line 근거는 SLIDE2_PROVENANCE_KO.md와 SOURCE_PROVENANCE.json이다.

## 사후 T4 재집계

**결과를 본 뒤 개정한 판정이며 사전등록 검증이 아님.** 원래 B_OLD INTERVENTIONS의 POST30 기술 성공 행만 집계했다. 평가 마스크는 이벤트 마지막 RF timestamp부터+30s까지 inclusive다. 이벤트5+5, 효과 정의, ≥50% 회수·전체 유익 안전성 기준은 유지했다. D4는 공분산 PSD를 보장하지 못해 제외했으며 실패를 효과0으로 대체하지 않았다.

| 유해 이벤트 | skip 개선 ° | D3 회수율 | D6 회수율 | 유효 진단으로 지지 |
|---|---:|---:|---:|---|
'''
    for e in t4['events']:
        if e['role']=='harmful':text+=f"| {e['event']} | {e['skip_gain_deg']:.6f} | {e['recovery_ratios']['D3']:.6f} | {e['recovery_ratios']['D6']:.6f} | 없음 |\n"
    text+='''
D3/D6의 전체 유익 이벤트 안전성은 모두 false이므로 지지0/5다. 채널 제거 회수≥50% 및 D3/D6 모두<20%를 만족한 이벤트는 C01 B x16–21 V1, C02 A x4–10 V1 두 개로, 반증 기준3/5에도 미달한다. 원래 NOT_ESTABLISHED → 사후 NOT_ESTABLISHED다. 원본 DECISION.json은 SHA 동일하다. D3는 진입 시 ψ 평균만 GT로 보정하고 P와 다른 상태 오차를 유지했으므로 prior 경로 전체의 반증으로 읽을 수 없다. 개입은 ORACLE_DIAGNOSTIC이다.

## 사후 정정 목록·이름·오류

1. SRC_TAP의 적용성을 무효로 표시했고 기존 수치·조건·판정은 보존했다.
2. 과거 T6의 입력 누락 해석을 모집단 혼동으로 정정했다.
3. T4의 D4를 제외한 별도 사후 분석을 추가했다.
4. 구현1/canonical_engine.py는 **검증된 실행 기준**이며 유일한 정본 확정이 아니다. 구현2·3의 차이는 **DEFERRED_SOURCE_UNAVAILABLE**로 남는다. 파일명은 원래 식별자로 보존한다.
5. T7B의 결과는 **v2 정책 NO-GO**다. Full52/64 및 Native8/8 한도 위반은 해당 고정 정책의 결과이며 효용 target 접근 전체 기각이 아니다.

최초 lock a37364c, theta schema 보완 eaaf66f, 좌표 정밀도 인증 lock c2bf8b8을 모두 보존했다. 실행39368233370은 행 대응 불변조건에서 exit1로 멈췄다. 통계 분포 계산 전에 실패했으며, 원인은 GT 저장 정밀도였다. ERROR와 실패 artifact12240406030을 보존한 뒤 좌표 반올림의 exact 인증을 추가해 run39368572991에서 성공했다. 과학 임계값·행 선택·실패 case는 바꾸지 않았다. 게시 preflight도 로컬 다운로드 ZIP의 Git 포함을 거절해 exit1로 멈췄으며, 원격 변경 전에 archive 제외 allowlist로 바로잡았다. ZIP은 로컬에 보존하고 전체 SHA·bytes 회수 영수증을 Git에 남겼다. 원래 JSON lock 필드·original decision과 사후 metadata를 구분한다.

## 남은 미확립·제외 범위

- Native LoS 잔차는 OPEN이다. 본 단계에서 Range 모델을 고치거나 재학습·재귀 계산하지 않았다.
- 구현2·3 원본 코드 미확보로 완전 diff는 DEFERRED_SOURCE_UNAVAILABLE다.
- 구 전체1303행의 실제 timestamp 범위는 미확립이다.829 subset의 frozen clock 대응은 별도로 인증했다.
- SRC_TAP 파생 결과와 D4 진단은 검증 증거에서 제외한다.
- 독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증, s 오염 대 필터 경로의 인과 분리, q의 물리 메커니즘, 양자화의 유일 원인·조건부 불편성은 주장하지 않는다. 조건 수를 독립 표본 수로 쓰거나 p-value를 붙이지 않았다.

## 산출물 검증·검토 진입점

FINAL_QA.json: 기존 CSV357·DECISION27 byte identity, 원문37개 SHA/bytes, 기존 JSON 값 보존, JSON/CSV parse, Python 구문, 파일당20MB, 원본·release hash44개,9519/7251행 인증을 검사했다. 새 RF·재귀 실행은 없다. 적용성 범위는 VALIDITY_INDEX.json, 원문은 ORIGINALS/RECEIPTS.json, 통계 provenance는 statistics_execution/STATISTICS_MANIFEST.json, 전체 artifact 회수 SHA/CRC는 statistics_execution/ACTIONS_ARTIFACT.json을 참조한다. 결과 Git commit·원격 bytes 검증은 PUBLICATION_RECEIPT.json에 기록한다. S0에서 종료한다.
'''
    # Literal pipes in prose within table cells must not split Markdown columns.
    text=text.replace('고정 |mean|<0.01m 실패','고정 abs(mean)<0.01m 실패').replace('| |e|>Δ/2 비율 |','| abs(e)>Δ/2 비율 |')
    (HERE/'RESULTS_KO.md').write_text(text,encoding='utf-8')
    (HERE.parent/'00_SUMMARY_KO.md').write_text(text,encoding='utf-8')
    manifest=dict(stage='S0_ONLY_COMPLETE',base_commit='034e57a7209a3bd1bb8857b24fd85c64942e1258',branch='research/powerjoint-audit-followup-20261020',initial_lock_commit='a37364c11587bae951955e1beb020261118310c1',statistics_lock_execution_commit='c2bf8b89173ebd59e6ad9516ecbb7eedc0f58b01',preservation_run_id=39367272729,preservation_artifact_id=12239593294,statistics_run_id=39368572991,statistics_artifact_id=12239939880,failed_statistics_run_id=39368233370,failed_statistics_artifact_id=12240406030,trace_count=44,trace_bytes=1883401358,trace_receipt_sha256=sha(HERE/'TRACE_RECEIPT.json'),work_status=stat['work_status'],scientific=stat['scientific'],T4_revised_scientific=t4['scientific'],posthoc_analyses=['SRC_TAP applicability correction','T4 D3/D6-only reaggregation','prior labeling and population correction'],no_recursive_or_RF_execution=True,next_stage='NOT_EXECUTED_STOP_S0',output_sha256={p.relative_to(HERE).as_posix():sha(p) for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name not in ['MANIFEST.json','FINAL_QA.json','PUBLICATION_RECEIPT.json'] and p.suffix.lower() not in ['.zip','.npz','.npy']})
    (HERE/'MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
