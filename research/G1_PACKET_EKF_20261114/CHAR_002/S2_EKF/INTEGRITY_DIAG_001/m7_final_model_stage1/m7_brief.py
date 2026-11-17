"""Render complete frozen M7 assessment without selecting or changing models."""
import argparse
import csv
from pathlib import Path
import numpy as np

from m7_prepare import check_records, item, read, utc, write
from m7_inputs import checked
from m7_score_run import _contract, _verify_records, expected_groups, _group_directory
from m7_spec import ARMS, MAIN_CONDITIONS, ROUTES


def csv_file(path, rows):
    with path.open('x',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def render(out):
    contract_path=out/'scoring/RUN_CONTRACT.json'
    _,identity,_,_=_contract(contract_path)
    summary_path=out/'assessment/SUMMARY.json'
    receipt=read(out/'assessment/EXECUTION.json')
    if receipt['status']!='PASS_AGGREGATION':
        raise ValueError('Complete numerical assessment required')
    for name,digest in receipt['outputs'].items():
        if item(out/'assessment'/name)['sha256']!=digest:
            raise ValueError('Assessment output drift')
    summary=read(summary_path)
    failure_rows=[]
    window_rows=[]
    mirrors={}
    rows=[]
    for key in expected_groups():
        directory=_group_directory(out/'scoring',key)
        execution=read(directory/'EXECUTION.json')
        if execution['status']!='PASS_SCORING' or execution['contract']!=identity or execution['group']!=key:
            raise ValueError('Unverified score group')
        _verify_records(execution['dependencies'])
        result=read(checked(execution['group_output']))
        for route in ROUTES:
            for arm in ARMS:
                mirrors[(key['condition'],key['mode'],key['seed'],route,arm)]=result['branches'][route][arm]['mirror_fail_count']
        for route,arms in result['diagnostics'].items():
            for arm,windows in arms.items():
                for name,diagnostic in windows.items():
                    if diagnostic['status']=='NO_SAMPLES':
                        raise ValueError('Mandatory diagnostic window has no samples')
                    window_rows.append(dict(**key,route=route,arm=arm,window=name,
                        **diagnostic['window_summary'],
                        heading_rmse_deg=diagnostic['point']['heading_rmse_deg'],
                        xy_rmse_cm=diagnostic['point']['xy_rmse_cm'],
                        b_g_rmse_deg_s=diagnostic['bias']['bias_error_deg_s']['rmse'],
                        b_g_signed_mean_deg_s=diagnostic['bias']['bias_error_deg_s']['signed_mean']))
        for arm in ARMS:
            for group in (*ROUTES,'pooled'):
                assessed=result['seed_assessments'][arm]['groups'][group]
                for category in ('integrity','accuracy'):
                    for reason in assessed[f'{category}_failures']:
                        failure_rows.append(dict(**key,arm=arm,group=group,category=category,reason=reason))
    for campaign in summary['campaigns'].values():
        for arm,data in campaign['arms'].items():
            for subset,cohort in data['cohorts'].items():
                for group,stats in cohort['groups'].items():
                    row=dict(condition=campaign['condition'],mode=campaign['mode'],arm=arm,subset=subset,
                             group=group,seed_denominator=cohort['seed_denominator'])
                    for metric,distribution in stats['metrics'].items():
                        for statistic in ('median','mean','min','max','p05','p95'):
                            row[f'{metric}_{statistic}']=distribution[statistic]
                    for metric,distribution in stats['rmse_cost_vs_H2_percent'].items():
                        row[f'{metric}_cost_vs_H2_median_pct']=distribution['median']
                    for baseline,metrics in stats['rmse_improvement_percent'].items():
                        for metric,distribution in metrics.items():
                            row[f'{metric}_improvement_vs_{baseline}_median_pct']=distribution['median']
                    row.update(mirror_events=stats['mirror']['event_count'],
                               affected_seed_count=stats['mirror']['affected_seed_count'])
                    rows.append(row)
    target=out/'brief'
    target.mkdir(exist_ok=False)
    csv_file(target/'TRAJECTORY_SUMMARY.csv',rows)
    csv_file(target/'FAILURE_REASONS.csv',failure_rows)
    csv_file(target/'R2_R5_WINDOWS.csv',window_rows)
    from m7_pairs import pair_definitions
    mirror_rows=[]
    for seed in range(10,30):
        for definition in pair_definitions(seed):
            for arm in ARMS:
                for route in (*ROUTES,'pooled'):
                    counts=[]
                    for context in (definition['baseline'],definition['target']):
                        counts.append(sum(mirrors[(*context,seed,r,arm)] for r in ROUTES) if route=='pooled'
                                      else mirrors[(*context,seed,route,arm)])
                    mirror_rows.append(dict(seed=seed,comparison=definition['id'],arm=arm,group=route,
                        baseline_mirror_events=counts[0],target_mirror_events=counts[1],delta_mirror_events=counts[1]-counts[0]))
    csv_file(target/'PAIRED_MIRROR_EVENTS.csv',mirror_rows)
    distributions=[]
    keys={tuple(r[k] for k in ('condition','mode','route','arm','window')) for r in window_rows}
    metric_names=[k for k in window_rows[0] if k not in ('condition','mode','route','arm','window','seed')]
    for key in sorted(keys):
        selected=[r for r in window_rows if tuple(r[k] for k in ('condition','mode','route','arm','window'))==key]
        for subset,subset_rows in (('all_seeds',selected),('seed10_14',[r for r in selected if r['seed']<15]),
                                   ('seed15_29',[r for r in selected if r['seed']>=15])):
            if not subset_rows:
                continue
            for metric in metric_names:
                values=np.array([r[metric] for r in subset_rows])
                distributions.append(dict(zip(('condition','mode','route','arm','window'),key),subset=subset,
                    metric=metric,seed_denominator=len(values),mean=float(values.mean()),median=float(np.median(values)),
                    min=float(values.min()),max=float(values.max()),p05=float(np.percentile(values,5)),p95=float(np.percentile(values,95)),
                    interval_interpretation='descriptive seed variation; not confidence interval'))
    csv_file(target/'R2_R5_WINDOW_DISTRIBUTIONS.csv',distributions)
    lines=['# M7 본 검증 요약','',
           'mount 0°, 앵커 B, Full RF, R2/R4/R5, seed 10–29. 20 seed는 같은 RF 실현을 공유한다.',
           '주 조건은 B0와 주입 잡음에 Q를 맞춘 L2이며 stress·고정 mask는 보고 전용이다. 기준을 변경하지 않았다.','',
           '| arm | B0 I/A/J | L2 I/A/J | B0/L2 mirror 건수 | M7 |',
           '|---|---:|---:|---:|---|']
    for arm in ARMS:
        counts=[summary['campaigns'][f'{c}/own']['arms'][arm]['assessment'] for c in MAIN_CONDITIONS]
        labels=[' / '.join(str(d[f'N_{k}']) for k in ('integrity','accuracy','joint')) for d in counts]
        lines.append(f'| {arm} | {labels[0]} | {labels[1]} | {counts[0]["mirror_passage_events"]} / {counts[1]["mirror_passage_events"]} | {"PASS" if summary["overall_by_arm"][arm]["M7_PASS"] else "FAIL"} |')
    lines += ['', 'I/A/J는 세 궤적과 pooled를 모두 만족한 seed 수이며 각 분모는 20이다. M7_PASS는 두 주 조건에서 각각 J≥18/20과 전 실행 mirror 0을 요구한다.',
              '', '다음 표는 seed별 점수의 중앙값이다. 독립 RF 반복의 평균이나 신뢰구간으로 해석하지 않는다.', '',
              '| 조건 | 궤적 | arm | heading RMSE ° | XY RMSE cm | Pose95 % | Heading95 % | XY95 % | NEES3 |',
              '|---|---|---|---:|---:|---:|---:|---:|---:|']
    for row in rows:
        if row['mode']!='own' or row['subset']!='all_seeds' or row['condition'] not in MAIN_CONDITIONS:
            continue
        lines.append('| {condition} | {group} | {arm} | {heading_rmse_deg_median:.3f} | {xy_rmse_cm_median:.2f} | {pose:.1f} | {head:.1f} | {xy:.1f} | {mean_nees3_median:.2f} |'.format(
            **row,pose=100*row['pose95_coverage_median'],head=100*row['heading95_coverage_median'],xy=100*row['xy95_coverage_median']))
    lines += ['', 'H5는 GM 차감 뒤 잔여 q_s를 사용하므로 실패만으로 b_θ 필요성을 주장할 수 없다. H5′는 σ_θ=0의 동일 LORO 규칙으로 다시 적합한 대조다.',
              '', 'DR·거리 단독 대비 정확도 이득, 세 포함률 및 정확도 비용은 별개다. 실행 완료·수치 판정·독립 검토·채택을 구분한다.',
              '', 'seed 15–29와 10–14의 별도 결과는 TRAJECTORY_SUMMARY.csv 및 ../assessment/COUNTS_SUBSETS.csv에 있다.',
              '모든 seed별 점수와 10 s 하한은 ../assessment/BY_TRAJECTORY_SEED.csv, 실패 항목은 FAILURE_REASONS.csv에 있다.']
    with (target/'REPORT_KO.md').open('x',encoding='utf-8',newline='\n') as stream:
        stream.write('\n'.join(lines)+'\n')
    write(target/'EXECUTION.json',dict(status='PASS_PRESENTATION',exit_code=0,contract=identity,
          created_utc=utc(),sources=[item(Path(__file__))],inputs=[item(summary_path),item(out/'assessment/EXECUTION.json')],
          outputs={p.name:item(p)['sha256'] for p in target.iterdir()},rows=len(rows),
          limitation='Presentation of unchanged frozen assessments; no new fit, experiment, or acceptance criterion'))
    print(target,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    render(parser.parse_args().output)
