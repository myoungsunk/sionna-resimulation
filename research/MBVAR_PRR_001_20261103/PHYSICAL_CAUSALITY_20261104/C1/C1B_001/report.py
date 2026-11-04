"""Summarize all completed C1b cells without changing any scientific output."""
from pathlib import Path
import csv
import hashlib
import json
import statistics

root = Path('D:/codex/MBVAR_PRR_001_20261103/research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/C1/C1B_001')
paths = [root/'DEV_001/CELL_SUMMARY.json',root/'REMAINING_001/CELL_SUMMARY.json']
rows = [r for p in paths for r in json.loads(p.read_bytes())]
expected = {(r,b,s,a) for r in ('R2','R4','R5') for b in ('B0','L2') for s in range(10,30) for a in ('FF','LF','FL','LL')}
keys = [(r['route'],r['bias'],r['seed'],r['arm']) for r in rows]
assert len(keys) == len(set(keys)) == 480 and set(keys) == expected
report = root/'RESULTS_KO.md'
table = root/'AGGREGATE_SUMMARY.csv'
if report.exists() or table.exists():raise RuntimeError('preserve report')
fields = ('route','bias','arm','seeds','mean_xy_m','mean_heading_deg','mean_delta_xy_vs_FF','mean_delta_heading_vs_FF','mean_delta_xy_vs_C1a','mean_delta_heading_vs_C1a','newly_accepted_all','newly_rejected_all','newly_accepted_primary','newly_rejected_primary')
summary = []
for route in ('R2','R4','R5'):
    for bias in ('B0','L2'):
        for arm in ('FF','LF','FL','LL'):
            group = [r for r in rows if (r['route'],r['bias'],r['arm']) == (route,bias,arm)]
            assert len(group) == 20 and len({r['n'] for r in group}) == 1
            item = dict(route=route,bias=bias,arm=arm,seeds=20)
            for key in fields[4:]:
                item[key] = sum(r[key] for r in group) if key.startswith('newly_') else statistics.mean(r[key] for r in group)
            summary.append(item)
with table.open('x',encoding='utf8',newline='') as f:
    writer = csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(summary)
text = '''# C1b — 같은 Full prior에서 원래 BASE gate를 재판정한 결과

계산 완료, 독립 전체 결과·보고서 감사 전 기록이다. 최종 수용 여부는 audit의 독립 판정과 STAGE_COMPLETION.json을 따른다. R2/R4/R5·B0/L2·공개 seed10–29의120조건,125440 prior,4arm501760행이다. DEV6조건과 잔여114조건을 합쳤으며 seed10을 재실행하지 않았다.

FF=Full/Full, LF=Native-LoS range만, FL=Native-LoS polarization만, LL=둘 모두다. 아래 값은 t>=30의 pose별 절대오차 평균을 seed별로 구한 뒤20seed를 평균한 값이다. RMSE·미래 오차 적분·재귀효과가 아니다. Δ는 arm−FF이며 음수는 이 한 번의 갱신에서 오차 감소다. 현재 BASE gate가 달라도 다음 시점은 원래 Full 이력으로 돌아가므로, 독립된 hybrid 자연 재귀 궤적이 아니다.

| 경로 | bias | arm | XY[m] | Heading[deg] | ΔXY vs FF[m] | ΔHeading vs FF[deg] | ΔHeading vs C1a[deg] | 신규수용/신규거절(전체시점) |
|---|---|---|---:|---:|---:|---:|---:|---:|
'''
for r in summary:
    text += f"|{r['route']}|{r['bias']}|{r['arm']}|{r['mean_xy_m']:.9f}|{r['mean_heading_deg']:.9f}|{r['mean_delta_xy_vs_FF']:+.9f}|{r['mean_delta_heading_vs_FF']:+.9f}|{r['mean_delta_heading_vs_C1a']:+.9f}|{r['newly_accepted_all']}/{r['newly_rejected_all']}|\n"
text += '''
신규 수용/거절은 같은 Full BASE prior에서 FF gate와 해당 arm gate가 달랐던 시점을20seed에 걸쳐 합한 기술적 건수다. 동일 RF와 반복 seed를 독립 사건으로 해석하지 않는다. primary(t>=30)의 별도 건수와 모든 개별 seed 값은 AGGREGATE_SUMMARY.csv 및 각 실행 CELL_SUMMARY.json에 보존한다.

Full mean/R와 MB_VAR prior/H를 고정하고 실제 BASE shadow의 현재 NIS만 재평가했다. 기존 FF에서 거절됐어도 hybrid가 수용되면 unmasked gain으로 갱신한다. C1a와의 차이는 이 동일 prior의 현재 gate 선택 효과다. arm간 P 차이를 공분산 교정·일관성 개선이라고 부르지 않는다. LoS oracle를 이용한 사후 기전 분석이며, 새 온라인 gate/복구 정책·다른 RF 환경 성능·알고리즘 채택을 검증한 결과가 아니다. 기존 NO-GO/HOLD는 유지한다.

추후 C2에서는 창 한정 관측 개입 이후의 state/P/H/K/R와 BASE shadow를 실제 재귀로 진행해 미래 오차·NEES를 분리한다. C2의 상세 계약·코드·실행 GO는 별도다.
'''
report.write_bytes(text.encode('utf8'))
print(json.dumps(dict(cells=120,priors=125440,posterior_rows=501760,summary_rows=480,aggregate_rows=24,report_sha256=hashlib.sha256(report.read_bytes()).hexdigest(),table_sha256=hashlib.sha256(table.read_bytes()).hexdigest())))
