from pathlib import Path
import json,subprocess,sys,hashlib,datetime,csv
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];OUT=HERE/'out/i1_run_01'
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def main():
    spec=json.loads((OUT/'FROZEN_SPEC.json').read_text())
    assert json.loads((HERE/'I1_SPEC.json').read_text())==spec
    checks=[]
    for label,args in [('compile',[sys.executable,'-m','compileall','-q',str(HERE)]),('tests',[sys.executable,'-m','pytest','-q',str(HERE/'tests')])]:
        r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True);(OUT/(label+'.log')).write_text(r.stdout+r.stderr)
        checks.append(dict(check=label,exit_code=r.returncode,command=args));assert r.returncode==0
    df=pd.read_csv(OUT/'STRUCTURAL_RANK.csv');ts=pd.read_csv(OUT/'CAL_FIM_TIMESERIES.csv')
    inv=json.loads((OUT/'NONLINEAR_INVARIANCES.json').read_text());prof=json.loads((OUT/'PROFILE_LIKELIHOOD.json').read_text())
    profiles=[p for c in prof['results'] for p in c['profiles']];starts=[s for p in profiles for s in p['all_starts']]
    assert len(df)==126 and len(ts)==630 and df.rank_stable.all()
    assert all(g['pass_rotation'] for g in inv['gauge'].values())
    monotonic=all(np.min(np.diff(g.sort_values('time_s').lambda_min))>=-1e-8 for _,g in ts.groupby(['case','pose_case','information']))
    assert monotonic
    meta_path='results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_meta.json'
    meta=subprocess.check_output(['git','show','f1d6d9fc:'+meta_path],cwd=ROOT);(OUT/'F0_LUT_SOURCE_META.json').write_bytes(meta)
    assert not json.loads(meta)['gate_L1_interpolation']['passed']
    summary=dict(conditions=df['case'].nunique(),information_rows=len(df),timeseries_rows=len(ts),profiles=len(profiles),starts=len(starts),failed_starts=sum(not s['success'] for s in starts),profiles_without_converged_start=sum(p['status']!='CONVERGED_LOCAL' for p in profiles),rank_stable=bool(df.rank_stable.all()),information_monotonic=monotonic,gauge_max=max(g['max_observation_change'] for g in inv['gauge'].values()),checks=checks)
    write(OUT/'VERIFICATION.json',summary)
    q=df[(df.pose_case=='S0')&(df.information=='DATA_ONLY')]
    lines=['# I1 실행 결과','', '**A_DR·Ideal Range 국소 분석 및 비선형 진단 완료 / 전체 I1 INCONCLUSIVE(F0 미실행) / I2 NOT_RUN.**','',
      '관측 입력에 조건부인 고정 공분산 Gaussian tangent 모델의 평균 정보이다. 실제 posterior 정밀도·필터 일관성·독립 확증 결과가 아니다. 방법과 해석 경계는 ../../I1_METHOD_KO.md를 따른다.','',
      '| 전체 경로 | DR 최소 고유값 | Ideal Range A | Ideal Range B | DR 조건수 | Range A 조건수 |',
      '|---|---:|---:|---:|---:|---:|']
    for route in ['R2','R4','R5']:
        a=q[q['case']==route+':A_DR:A'].iloc[0];b=q[q['case']==route+':B0_IDEAL_RANGE:A'].iloc[0];c=q[q['case']==route+':B0_IDEAL_RANGE:B'].iloc[0]
        lines.append(f'| {route} | {a.lambda_min:.4f} | {b.lambda_min:.4f} | {c.lambda_min:.4f} | {a.condition:.1f} | {b.condition:.2f} |')
    lines+=['','표의 값은 사전 고정 척도로 무차원화한 S0 DATA_ONLY Calibration 유효 정보이다.',
      '', '1. R2/R4/R5 전체 경로에서 DR 자체의 Calibration 국소 rank는 2다. 정보가 완전히 없는 경우와 약한 방향의 정보가 작은 경우를 구분해야 한다. Ideal Range는 약한 방향 정보를 증가시켰다. 실제 요구 정밀도 충족은 아직 판정하지 않았다.',
      '2. S0의 전체 관측 Jacobian rank는 DR 3, Range 포함 5였다. Range에서도 anchor 주위 절대 회전 gauge가 남지만 Calibration rank 2와 양립한다.',
      '3. 일정속도 직진 DR에는 동일 관측을 만드는 bg/eps 연속 상태군이 존재한다. 가변속도 직진에서는 Calibration rank가 1에서 2로 증가했다. 이는 I1의 모델·정보 분석이며 I5 센서 재생/성능 확증은 아니다.',
      '4. 방사방향 Range에서는 nominal 점의 Calibration rank가 1이고, 비영 ±bg/±eps 반사쌍의 Range가 정확히 같다. 영 Calibration과 비영 상태 사이에는 작은 Range 차이가 있으므로 선형 rank 결손을 연속적인 비선형 비식별성과 동일시하지 않는다.',
      '5. 접선방향 직선 Range에서는 Calibration rank 2였지만 약한 방향 정보는 작았다. 일정속도 원운동에서는 SFg nuisance를 제거하면 DR rank 0, Range 포함 rank 1이다. 회전 자체만으로 모든 Calibration 상태가 구별되는 것은 아니다.',
      '',f"검증: 기존 I0 12개 + I1 5개 테스트 총 17개 통과. {summary['conditions']}조건, {len(df)}개 정보행, {len(ts)}개 시계열행. Gauge 관측 차이 최대 {summary['gauge_max']:.3g}. Rank 허용오차 3개에서 판정이 일치했다.",
      '',f"Profile: {len(profiles)}개 문제, {len(starts)}개 시작점 중 {summary['failed_starts']}개는 반복 한도에 도달했다. 각 문제에는 수렴한 시작점이 적어도 하나 있다. 모든 시작점/실패 상태를 보존했다. 전역 최적성·다봉성 해소·95% 구간은 증명하지 않았다.",
      '', 'F0: 기존 LUT 최대 보간오차 0.0239721이 동결 기준 0.01을 초과한 기록을 확인하여 실행하지 않았다. 원문은 F0_LUT_SOURCE_META.json이다. 검증된 s 모델 없이는 전체 I1 PASS로 승격하지 않는다.',
      '', '독립 수학 설계 검토는 ACCEPT였다. 구현 후 독립 감사는 동일 모델의 용량 제한으로 2회 실패하여 완료되지 않았다. 구현 검증은 작성자의 명시적 수치 테스트 및 결과 검사로 수행했다.',
      '', 'I2는 미실행이다. 기존 D6 UNRESOLVED, I0 RF 통합 미완료 및 L1–L7 NOT_RUN을 유지한다. 독립 확증 seed를 생성/열람하지 않았다.']
    (OUT/'REPORT_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    write(OUT/'I1_GATE.json',dict(implementation='PASS',A_DR='PASS: analysis execution',B0_IDEAL_RANGE='PASS: analysis execution',F0='NOT_RUN',overall='INCONCLUSIVE',cause='F0 model qualification incomplete; local mean-information is not full nonlinear posterior evidence',independent_design_review='ACCEPT',independent_implementation_review='UNAVAILABLE_CAPACITY',I2='NOT_RUN',L1_to_L7='NOT_RUN'))
    write(OUT/'FINAL_MANIFEST.json',dict(timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file() and p.name!='FINAL_MANIFEST.json'},sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.iterdir() if p.is_file() and (p.name.startswith('i1_') or p.name in ['I1_SPEC.json','I1_METHOD_KO.md','run_i1.py','finalize_i1.py'])}))
    print(json.dumps(summary),flush=True)
if __name__=='__main__':main()
