"""Descriptive reporting of every frozen C2 window; no selection or adoption gate."""
import csv
import hashlib
import json
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent


def main():
    rows = []
    manifests = {}
    for phase in ('DEV_001', 'REMAINING_001'):
        folder = HERE / phase
        manifest = json.loads((folder / 'MANIFEST.json').read_bytes())
        if manifest['status'] != 'NUMERICAL_PASS_PENDING_INDEPENDENT_RESULT_AUDIT':
            raise ValueError('complete numerical phase required')
        manifests[phase] = dict(manifest_sha256=hashlib.sha256((folder / 'MANIFEST.json').read_bytes()).hexdigest(),
                                artifact_hashes_sha256=hashlib.sha256((folder / 'ARTIFACT_HASHES.json').read_bytes()).hexdigest())
        rows.extend(json.loads((folder / 'TRAJECTORY_SUMMARY.json').read_bytes()))
    keys = [(r['route'],r['bias'],r['seed'],r['window'],r['mode'],r['arm']) for r in rows]
    if len(keys) != 2640 or len(set(keys)) != 2640:
        raise ValueError('all 2640 trajectories required')
    groups = {}
    for row in rows:
        key = tuple(row[k] for k in ('route','bias','window','mode','arm'))
        groups.setdefault(key, []).append(row)
    fields = [k for k,v in rows[0].items() if isinstance(v,(int,float)) and not isinstance(v,bool)
              and k not in ('seed','first_index','suffix_rows','primary_rows','start_s','end_s')
              and not k.startswith('first_')]
    # Include keys whose first row is explicitly NA (e.g. a late-window horizon).
    fields = sorted(set(fields) | {k for k in rows[0] if k.startswith(('primary_','delta_primary_','own_minus_fixed_','I_','FF_I_','delta_I_'))
                                  and not k.endswith(('_available','_actual_packets','_unavailable_reason'))
                                  and k != 'primary_rows'})
    aggregate = []
    for key, group in sorted(groups.items()):
        if sorted(r['seed'] for r in group) != list(range(10,30)):
            raise ValueError('20 paired published seeds per group')
        row = dict(zip(('route','bias','window','mode','arm'),key), seeds=20)
        for field in fields:
            values = [r[field] for r in group if r.get(field) is not None]
            if any(not isinstance(v,(int,float)) for v in values):
                raise ValueError('numeric reporting field '+field)
            row[field+'_n'] = len(values)
            for statistic,fn in (('median',statistics.median),('min',min),('max',max)):
                row[field+'_'+statistic] = fn(values) if values else None
        aggregate.append(row)
    with (HERE/'AGGREGATE_SUMMARY.csv').open('w',encoding='utf8',newline='') as output:
        writer=csv.DictWriter(output,fieldnames=list(aggregate[0]));writer.writeheader();writer.writerows(aggregate)
    lines = ['# C2 창 한정 관측 개입의 재귀 전파 결과', '',
        '실행 수치검사 완료. 이 보고서의 독립 결과감사 및 게시 검증 판정은 별도 감사 보고서를 따른다.', '',
        '기존 Full 결과를 공통 시작 상태로 사용하고, 등록된 창 안에서만 거리(LF), 편파(FL), 양쪽(LL) 관측을 Native-LoS로 교체했다. 창 밖에서는 Full 관측으로 경로 끝까지 재귀했다. fixed는 기존 Full BASE 게이트, own은 각 분기의 BASE 게이트를 사용했다.', '',
        '총 120개 원본 조건, 440개 창 조건, 2,640개 분기 궤적, 1,528,320개 suffix posterior 행이다. seed 10–29는 이미 공개된 같은 RF 자료의 반복이며 독립 RF 표본이나 새 잠금 평가로 해석하지 않는다.', '',
        '아래 값은 각 seed에서 계산한 전체 t≥30초 Heading RMSE의 Full 대비 차이(deg)를 20개 seed의 중앙값 [최솟값, 최댓값]으로 표시한다. 음수는 오차 감소이다. 창별 후속 적분, XY, 공분산, NEES, coverage와 own−fixed 비교는 AGGREGATE_SUMMARY.csv 및 원본 사건별 요약에 모두 보존했다.', '',
        '|경로|bias|창|게이트|LF ΔRMSE|FL ΔRMSE|LL ΔRMSE|',
        '|---|---|---|---|---:|---:|---:|']
    lookup = {tuple(r[k] for k in ('route','bias','window','mode','arm')):r for r in aggregate}
    for route,bias,window,mode in sorted({k[:4] for k in lookup}):
        values=[]
        for arm in ('LF','FL','LL'):
            row=lookup[(route,bias,window,mode,arm)];prefix='delta_primary_heading_deg_rmse_'
            values.append(f"{row[prefix+'median']:+.9f} [{row[prefix+'min']:+.9f}, {row[prefix+'max']:+.9f}]")
        lines.append('|'+ '|'.join((route,bias,window,mode,*values))+'|')
    lines.extend(['', '구간 적분은 창 시작 후 [0,2], [2,5], [5,10], [10,20]초의 실제 시각 사다리꼴 적분이다. 양 끝점이 없는 구간은 부분 적분으로 대체하지 않고 NA·분모·사유를 기록했다. NEES3는 위치·Heading 주변 공분산, NEES4는 실제 scalar gyro-bias 정답을 포함한 4상태 공분산을 사용한다. Heading 오차는 표에서 degree, NEES 계산에서는 radian이다.', '',
        'RF 오염→관측 innovation→추정 오차와 공분산의 연결을 검사하는 오프라인 개입이다. SourceFFD의 GT 관측값은 기존 연속거리/B_OLD 및 surrogate 모델이며 물리 LoS 정답으로 대체 해석하지 않는다. Hψ는 활성 분기의 s/rad 민감도이고 Fisher 정보량이 아니다. Native-LoS 개입은 온라인에서 이용 가능한 guard가 아니며 기존 전체 채택 NO-GO·실시간 HOLD를 변경하지 않는다.', '',
        'C3, 새로운 RF 시뮬레이션, 학습, S2/S3 복구, 정책 선택은 실행하지 않았다.', ''])
    (HERE/'RESULTS_KO.md').write_bytes(('\n'.join(lines)).encode('utf8'))
    (HERE/'REPORT_INPUTS.json').write_bytes((json.dumps(dict(phases=manifests,trajectories=len(rows),groups=len(aggregate),seeds=list(range(10,30))),indent=2)+'\n').encode('utf8'))
    print(json.dumps(dict(trajectories=len(rows),groups=len(aggregate))))


if __name__ == '__main__':
    main()
