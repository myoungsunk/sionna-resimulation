#!/usr/bin/env python3
"""Heading-1 accumulated signed fixed-bias vs Heading-2 unbiased Gaussian SD, 5x5.

Reproduces published 2026-10-12 four-route single-anchor synthetic EKF.
IMU/odom DR yaw increment (Heading 1) is the prediction input with unmodelled
constant rate bias; RF absolute yaw (Heading 2) is a synthetic measurement
with zero fixed bias, SD swept. Every scenario has its own correct Gaussian R.

Not Sionna, not dual-LP, no RF heading derivation, no collision response.
"""
from __future__ import annotations
import argparse, dataclasses, hashlib, json, math, os, sys, time, zipfile
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib import colormaps
from dual_heading_sim_extended import Config, ROUTES, D2R, CHI2_2_95, generate, measure, filter_run, wrap

B1=(.5,1.,2.,5.,10.)
S2=(.5,1.,2.,5.,10.)
CHI3_95=7.814727903251179
METRICS={
    'rmse_2d_m':('2D position RMSE','m',3),
    'rmse_heading_deg':('Fused heading RMSE','deg',2),
    'final_coverage_pct':('Final 95% xy coverage','%',1),
}

def pose_coverage(res,d):
    err=res['final_est']-d['gt'][:,-1,:]
    err[:,2]=wrap(err[:,2])
    P=res['final_cov']
    lam=np.linalg.eigvalsh(P)
    if not bool(np.all(lam[:,0]>0)):
        raise AssertionError('Non-positive-definite posterior P')
    z=np.linalg.solve(P,err[:,:,None])[...,0]
    s=np.sum(err*z,axis=1)
    return float(np.mean(s<=CHI3_95)*100),float(np.mean(s)),float(lam.min())

def rf_rmse_deg(obs,d):
    err=wrap(obs['zheading']-d['gt'][:,1:,2])/D2R
    return float(np.sqrt(np.mean(err**2))), float(np.mean(err))

def raw_dr_rmse_final_deg(obs,d):
    e=wrap(d['initial'][:,2]+np.sum(obs['dpsi'],axis=1)-d['gt'][:,-1,2])/D2R
    return float(np.sqrt(np.mean(e**2))),float(np.mean(e))

def metric_row(route,cfg,d,obs,r,b1,s2,category):
    posecov,posenees,lmin=pose_coverage(r,d)
    raw2,mean2=rf_rmse_deg(obs,d)
    raw1,mean1=raw_dr_rmse_final_deg(obs,d)
    return dict(route=route,route_ko=ROUTES[route]['ko'],type=category,
                heading1_accum_bias_deg=float(b1),heading1_step_bias_deg=float(b1/cfg.steps),
                heading1_step_std_deg=float(cfg.dr_yaw_std_deg),
                heading2_fixed_bias_deg=0.,heading2_std_deg=float(s2),
                heading2_R_rad2=float((s2*D2R)**2),
                range_std_m=float(cfg.range_std_m),
                raw_heading1_final_rmse_deg=raw1,raw_heading1_final_mean_bias_deg=mean1,
                raw_heading2_all_rmse_deg=raw2,raw_heading2_mean_bias_deg=mean2,
                rmse_2d_m=float(r['rmse_2d_m']),rmse_x_m=float(r['rmse_x_m']),rmse_y_m=float(r['rmse_y_m']),
                rmse_heading_deg=float(r['rmse_heading_deg']),
                final_rmse_2d_m=float(r['final_rmse_2d_m']),
                mean_nees_xy=float(r['mean_nees_xy']),final_nees_xy=float(r['final_nees_xy']),
                final_coverage_pct=float(r['final_coverage_pct']),
                final_pose_coverage_pct=posecov,final_pose_nees=posenees,
                mean_joint_nis=float(r['mean_nis']),min_p_eigenvalue=lmin)

def piv(df,route,key,include_zero=False):
    q=df[df.route==route]
    order=(0.,)+B1 if include_zero else B1
    m=q.pivot(index='heading1_accum_bias_deg',columns='heading2_std_deg',values=key)
    return m.reindex(index=order,columns=S2)

def heatmap_one(df,route,out):
    fig,ax=plt.subplots(1,3,figsize=(15.1,4.75),layout='constrained')
    for aa,(m,(name,unit,n)) in zip(ax,METRICS.items()):
        z=piv(df,route,m).values
        vmin=0 if m!='final_coverage_pct' else 0
        vmax=100 if m=='final_coverage_pct' else max(np.max(z),1e-9)
        im=aa.imshow(z,cmap='viridis' if m!='final_coverage_pct' else 'cividis',vmin=vmin,vmax=vmax,origin='lower',aspect='equal')
        for y in range(5):
            for x in range(5):
                v=z[y,x]
                aa.text(x,y,('%0.3f'%v if m=='rmse_2d_m' else '%0.2f'%v if m=='rmse_heading_deg' else '%0.1f'%v),
                        ha='center',va='center',fontsize=8.3,
                        color='white' if (v/vmax<.50) else 'black')
        aa.set(title=f'{name} ({unit})',xlabel='Heading 2 RF std (deg)',ylabel='Heading 1 total DR bias (deg)',
               xticks=range(5),yticks=range(5),xticklabels=S2,yticklabels=B1)
        fig.colorbar(im,ax=aa,shrink=.72)
    fig.suptitle(f'{ROUTES[route]["name"]}: DR heading bias × unbiased RF heading sigma | 5×5 sweep',fontsize=12)
    # Title is adjusted by caller only with exactly 1000 runs; general run count in main.
    fig.savefig(out/f'heatmap_{route}_three_metrics.png',dpi=175)
    plt.close(fig)

def heatmap_all(df,out,runs):
    metric_list=list(METRICS)
    fig,ax=plt.subplots(4,3,figsize=(14.5,15.0),layout='constrained')
    for ci,m in enumerate(metric_list):
        vals=df[df['type']=='sweep'][m].values
        lo=0.;hi=100. if m=='final_coverage_pct' else float(vals.max())
        norm=Normalize(vmin=lo,vmax=hi)
        for ri,route in enumerate(ROUTES):
            aa=ax[ri,ci]; z=piv(df[df['type']=='sweep'],route,m).values
            im=aa.imshow(z,origin='lower',aspect='equal',cmap='viridis' if ci<2 else 'cividis',norm=norm)
            for i in range(5):
                for j in range(5):
                    aa.text(j,i,('%0.3f'%z[i,j] if ci==0 else '%0.2f'%z[i,j] if ci==1 else '%0.1f'%z[i,j]),
                            ha='center',va='center',fontsize=8.0,color='white' if z[i,j]/hi<.50 else 'black')
            aa.set(xticks=range(5),yticks=range(5),xticklabels=S2,yticklabels=B1,
                   title=f'{ROUTES[route]["name"]} — {METRICS[m][0]}',
                   ylabel='H1 total bias (deg)' if ci==0 else '',xlabel='H2 std (deg)' if ri==3 else '')
        fig.colorbar(im,ax=ax[:,ci],shrink=.46,pad=.02)
    fig.suptitle(f'4 routes × 25 paired scenarios | MC {runs} / scenario | H2 fixed bias = 0°',fontsize=14)
    fig.savefig(out/'all_routes_5x5_overview.png',dpi=170)
    plt.close(fig)

def line_charts(df,out,runs):
    sweep=df[df.type=='sweep']; baseline=df[df.type=='unbiased_h1_reference']
    fig,axes=plt.subplots(3,4,figsize=(16,10.2),layout='constrained',sharex='col')
    fields=['rmse_2d_m','rmse_heading_deg','final_coverage_pct']
    for ci,route in enumerate(ROUTES):
        q=sweep[sweep.route==route]
        for ri,field in enumerate(fields):
            aa=axes[ri,ci]
            for b in B1:
                sub=q[np.isclose(q.heading1_accum_bias_deg,b)].sort_values('heading2_std_deg')
                aa.plot(sub.heading2_std_deg,sub[field],marker='o',lw=1.5,label=f'H1 bias {b:g}°')
            if field=='final_coverage_pct':aa.axhline(95,ls=':',color='gray',lw=1)
            # White markers unbiased-h1 baseline for reference.
            zb=baseline[baseline.route==route].sort_values('heading2_std_deg')
            aa.plot(zb.heading2_std_deg,zb[field],color='black',marker='x',ls='--',lw=1.3,label='H1 bias 0°')
            if ri==0:aa.set_title(ROUTES[route]['name'])
            if ci==0:aa.set_ylabel(fields[ri].replace('_',' '))
            if ri==2:aa.set_xlabel('RF Heading 2 sigma (deg)')
            aa.grid(alpha=.22);aa.set_xscale('log');aa.set_xticks(S2,labels=[f'{s:g}' for s in S2])
    hh,ll=axes[0,0].get_legend_handles_labels();fig.legend(hh,ll,ncol=6,loc='upper center',bbox_to_anchor=(.5,.985),fontsize=9)
    fig.suptitle('Effect of DR heading bias (unmodeled) vs RF heading accuracy',y=1.018,fontsize=15)
    fig.savefig(out/'precision_vs_dr_bias_all_routes.png',dpi=175,bbox_inches='tight')
    plt.close(fig)

def trajectory_figure(cfg,cached,out):
    route='straight';d=cached[route]
    scenarios=[(.5,.5),(.5,10.),(10.,.5),(10.,10.)]
    fig,axs=plt.subplots(2,2,figsize=(13.2,7.4),layout='constrained')
    for ax,(b,s) in zip(axs.ravel(),scenarios):
        obs=measure(cfg,d,gyro_std_deg=cfg.dr_yaw_std_deg,gyro_accum_bias_deg=b,rf_std_deg=s,rf_bias_deg=0.)
        z=filter_run(cfg,d,obs,method='both',dr_std_deg=cfg.dr_yaw_std_deg,rf_std_deg=s,retain_trace=True)
        est=z['trajectory'];ground=d['gt']
        obs_d=filter_run(cfg,d,obs,method='dr',dr_std_deg=cfg.dr_yaw_std_deg,rf_std_deg=s,retain_trace=True)
        ax.plot(d['ref'][:,0],d['ref'][:,1],color='black',ls=':',lw=1.2,label='Reference')
        ax.plot(ground[0,:,0],ground[0,:,1],color='#237fbb',lw=2.0,label='Ground truth')
        ax.plot(obs_d['trajectory'][0,:,0],obs_d['trajectory'][0,:,1],color='#d9923b',lw=1.3,label='DR only')
        ax.plot(est[0,:,0],est[0,:,1],color='#148766',lw=1.7,label='Fused EKF')
        ax.scatter([4],[0],marker='*',color='#7a4cc3',s=100,label='Anchor')
        ax.set(xlabel='x (m)',ylabel='y (m)',title=f'H1 accumulated bias={b:g}°, H2 sigma={s:g}° | EKF RMSE={z["rmse_2d_m"]:.3f} m')
        ax.grid(alpha=.2);ax.set_xlim(3.7,14.6);ax.set_ylim(-.95,.95)
        for y in (-cfg.robot_center_ymax_m,cfg.robot_center_ymax_m):ax.axhline(y,ls=':',lw=.9,color='#c77777',alpha=.65)
    handles,labels=axs.flat[0].get_legend_handles_labels();fig.legend(handles,labels,ncol=5,loc='upper center',bbox_to_anchor=(.5,1.01))
    fig.suptitle('Straight corridor / example run 0 only / same ground truth and random seeds',fontsize=13,y=1.05)
    fig.savefig(out/'straight_four_corner_trajectory_examples.png',dpi=170,bbox_inches='tight');plt.close(fig)

def format_md_table(pivot,style):
    hdr='| H1 total bias ↓ / H2 σ → | '+ ' | '.join(f'{x:g}°' for x in S2)+' |\n'
    hdr+='|:--|'+ '|'.join('--:' for _ in S2)+'|\n'
    for ix in B1:
        vals=pivot.loc[ix]
        cells=[('{:.3f}'.format(vals[j]) if style=='position' else '{:.2f}'.format(vals[j]) if style=='heading' else '{:.1f}%'.format(vals[j])) for j in S2]
        hdr+=f'| {ix:g}° | '+' | '.join(cells)+' |\n'
    return hdr

def write_report(cfg,df,out,qa):
    sv=df[df.type=='sweep'];br=df[df.type=='unbiased_h1_reference']
    lines=[
        '# Single-anchor Dual-Heading EKF: Heading 1 고정 Bias × Heading 2 표준편차 5×5',
        '',
        '## 실험 정의',
        '',
        '- **행**: Heading 1(IMU/odom 상대 회전증분)의 누적 고정 bias = +0.5°, +1°, +2°, +5°, +10° (100 step 동안 단계별 동일 오차를 추가).',
        '- **열**: Heading 2(가정한 RF 독립 절대 Heading)의 **표준편차** = 0.5°, 1°, 2°, 5°, 10°; Heading 2 고정 bias = 0°.',
        '- Heading 1의 무작위 오차 표준편차는 0.23°/step, UWB ranging = 0.08 m, odometry 거리증분 = 0.008 m/step으로 고정.',
        '- EKF는 IMU/odom으로 예측하고, RF의 거리/절대 heading 두 관측으로 갱신. EKF의 Heading 1 bias는 미모델링, Heading 2는 bias 0으로 생성.',
        '- RF angle std의 제곱을 **rad²로 변환**하여 R[1,1]에 반영, 백색잡음은 세 센서 간 독립, 동일 시점/시간 상관은 모두 0.',
        f'- GitHub 복도: 20×2.4×2.7 m, anchor(4,0,2.65) m, tag z=0.45 m, 10 m/100 step, Δt=0.5 s, {cfg.runs}회 Monte Carlo, seed={cfg.seed}.',
        '- 구형/다중 LP RF 신호처리 없음. **RF가 독립 절대 Heading을 제공한다는 것은 검증되지 않은 가정**입니다.',
        '- 모든 비교에서 실제 ground truth, 초기 상태, 센서 난수 스트림은 같은 것을 재사용하므로 **paired Monte Carlo**입니다.',
        '',
        '## 수학 모델',
        '',
        r'$$\Delta\psi_{1,k}=\Delta\psi_k^{GT}+\frac{b_{1,\mathrm{total}}}{N}+\epsilon_{1,k},\quad \epsilon_{1,k}\sim\mathcal N(0,(0.23\pi/180)^2).$$',
        '',
        r'$$z_{2,k}=\operatorname{wrap}(\psi_k^{GT}+\epsilon_{2,k}),\quad \epsilon_{2,k}\sim\mathcal N\left(0,(\sigma_2\pi/180)^2\right),\quad b_2=0.$$ ',
        '',
        r'$$z_{r,k}=\sqrt{(x_k-4)^2+y_k^2+2.2^2}+\epsilon_{r,k},\quad\epsilon_{r,k}\sim\mathcal N(0,0.08^2).$$',
        '',
        r'$$R_{\mathrm{RF}}=\operatorname{diag}(0.08^2,(\sigma_2\pi/180)^2),\quad P^-=FP^+F^T+GQG^T.$$ ',
        '',
        'Final 95% 위치 포함률: 각 run의 마지막 오차 e_xy와 마지막 P_xy에 대해 ' + r'$e_{xy}^TP_{xy}^{-1}e_{xy}\le\chi^2_{2,0.95}=5.9915$'+'를 만족한 비율.',
        '',
        '## 4개 경로 × 3 지표: 5×5 실행 결과',
        '',
    ]
    for route in ROUTES:
        lines += [f'### {ROUTES[route]["ko"]} ({route})','',
            '**1) 전체 10 m 2D 위치 RMSE (m)**','',format_md_table(piv(sv,route,'rmse_2d_m'),'position'),
            '**2) 전체 주행 융합 Heading RMSE (°)**','',format_md_table(piv(sv,route,'rmse_heading_deg'),'heading'),
            '**3) 최종 95% 위치 신뢰타원 포함률 (%)**','',format_md_table(piv(sv,route,'final_coverage_pct'),'coverage'),
            f'![{route} 결과](heatmap_{route}_three_metrics.png)',''
        ]
    lines += ['## Heading 1 bias=0° 기준선 (각 Heading 2 표준편차별)','',
      '| 경로 | H2 std | 위치 RMSE (m) | 융합 Heading RMSE (°) | 최종 95% |',
      '|:--|--:|--:|--:|--:|']
    for row in br.itertuples():
        lines.append(f'| {row.route_ko} | {row.heading2_std_deg:g}° | {row.rmse_2d_m:.3f} | {row.rmse_heading_deg:.2f} | {row.final_coverage_pct:.1f}% |')
    lines += ['', '## 공분산과 Bias 해석', '',
      'Heading 1 bias는 매 step 실제 회전량과 DR 회전량 간 지속적 offset이므로 **분산 Q를 올바르게 설정해도 공분산이 실제 error의 평균을 설명하지 못할 수 있습니다**.',
      'Heading 2가 0-bias라도 표준편차가 커지면 필터가 Heading 1 예측을 더 신뢰해 Heading 1 bias의 영향이 커질 수 있습니다. 그러나 수치는 경로, 초기 prior, RF 갱신 주기에 의존합니다.',
      '위치 RMSE가 작은 네모 경로는 이동 구간의 cancellation이 작용할 수 있으므로 **종료 위치 95% 외에 전체 자세 95%와 융합 Heading RMSE도 검토**해야 합니다.',
      '', '## 평가 경계', '',
      '- σ2의 10°는 분산 10 deg²가 아니라 **표준편차 10°**를 의미하고, 실제 분산은 (10π/180)² rad²입니다.',
      '- UWB ranging 및 Heading RF 관측 간 상관/시간 상관은 **0으로 고정**했습니다. 본 실험은 bias × variance만 격리합니다.',
      '- 각 경로의 실제 궤적은 주행 중 모터 noise가 있는 독립 시뮬레이션이며, 물리 충돌 및 지형 map constraints는 적용하지 않았습니다.',
      '- RF absolute world heading 획득은 가상 오라클 관측입니다. 단일 앵커 relative bearing만으로 동일 성능을 기대할 수 없습니다.',
      '', '## 재현성 / 검증', '',
      '```bash', 'pip install numpy pandas matplotlib',
      f'python run_grid.py --runs {cfg.runs} --seed {cfg.seed}',
      '```','', f'- QA: {json.dumps(qa,ensure_ascii=False)}','',
    ]
    (out/'REPORT_KO.md').write_text('\n'.join(lines),encoding='utf8')


def run(cfg,out,fast_fig=False):
    out.mkdir(parents=True,exist_ok=True)
    t0=time.monotonic()
    sweep=[];baseline=[];diag=[];cached={};qa={}
    for route in ROUTES:
        d=generate(cfg,route); cached[route]=d
        # Same GT and normalized noise streams across every parameter pair.
        for sigma in S2:
            o=measure(cfg,d,gyro_accum_bias_deg=0,rf_std_deg=sigma,rf_bias_deg=0)
            z=filter_run(cfg,d,o,method='both',dr_std_deg=cfg.dr_yaw_std_deg,rf_std_deg=sigma)
            baseline.append(metric_row(route,cfg,d,o,z,0.,sigma,'unbiased_h1_reference'))
        for bias in B1:
            for sigma in S2:
                obs=measure(cfg,d,gyro_std_deg=cfg.dr_yaw_std_deg,gyro_accum_bias_deg=bias,rf_std_deg=sigma,rf_bias_deg=0)
                res=filter_run(cfg,d,obs,method='both',dr_std_deg=cfg.dr_yaw_std_deg,rf_std_deg=sigma)
                sweep.append(metric_row(route,cfg,d,obs,res,bias,sigma,'sweep'))
        print(f'DONE route={route} cases={len(sweep)} elapsed={time.monotonic()-t0:.1f}s',flush=True)
    df=pd.DataFrame(sweep)
    bd=pd.DataFrame(baseline)
    alld=pd.concat([df,bd],ignore_index=True)
    alld.to_csv(out/'all_scenarios.csv',index=False,float_format='%.13g')
    df.to_csv(out/'bias1_vs_sigma2_all_routes.csv',index=False,float_format='%.13g')
    bd.to_csv(out/'unbiased_heading1_reference.csv',index=False,float_format='%.13g')
    # Audit one fixed case against previous exact 2026-10-12 seeded baseline.
    previous=Path('/mnt/data/SINGLE_ANCHOR_DUAL_HEADING_BIAS_5X5_20261012/unbiased_reference_by_route.csv')
    if previous.exists() and cfg.runs==1000 and cfg.seed==20261012:
        p=pd.read_csv(previous)
        merged=bd[np.isclose(bd.heading2_std_deg,1)][['route','rmse_2d_m','rmse_heading_deg','final_coverage_pct']].merge(
            p[['route','rmse_2d_m','rmse_heading_deg','final_coverage_pct']],on='route',suffixes=('_this','_previous'))
        maxerr=max(abs(merged[f'{c}_this']-merged[f'{c}_previous']).max() for c in ('rmse_2d_m','rmse_heading_deg','final_coverage_pct'))
        qa['previous_unbiased_baseline_exact']=bool(maxerr<1e-10)
        (out/'baseline_audit.csv').write_text(merged.to_csv(index=False),encoding='utf8')
        print('baseline max diff',maxerr,flush=True)
    else:
        qa['previous_unbiased_baseline_exact']='NOT_RUN_MISSING_PREVIOUS_FILE_OR_DIFFERENT_CONFIG'
    qa['expected_100_sweep_rows']=bool(len(df)==100 and all(len(df[df.route==r])==25 for r in ROUTES))
    qa['zero_rf_fixed_bias']=bool(np.all(alld.heading2_fixed_bias_deg==0.))
    qa['positive_definite_covariance']=bool(np.isfinite(alld.min_p_eigenvalue).all() and (alld.min_p_eigenvalue>0).all())
    qa['range_and_heading_gaussian_noise_calibration']=bool(all(abs(r.raw_heading2_all_rmse_deg-r.heading2_std_deg)<0.10*max(1,r.heading2_std_deg) for r in alld.itertuples()))
    qa['positive_std_and_covariance']=bool(np.all(alld.heading2_R_rad2>0))
    qa['no_nan_outputs']=bool(np.isfinite(alld.select_dtypes(include=[np.number]).values).all())
    qa['same_b1_input_for_all_s2']=bool(all(np.ptp(df[(df.route==route)&(df.heading1_accum_bias_deg==b)].raw_heading1_final_rmse_deg)<1e-12 for route in ROUTES for b in B1))
    # Compare all σ2 settings (b1=0) to the earlier separately published RF σ sweep.
    previous_rf=Path('/mnt/data/SINGLE_ANCHOR_DUAL_HEADING_CORRELATED_EKF_20261012/all_cases.csv')
    if previous_rf.exists() and cfg.runs==1000 and cfg.seed==20261012:
        prior=pd.read_csv(previous_rf)
        prior=prior[(prior.study=='rf_2d_sweep') & np.isclose(prior.rf_heading_bias_deg,0.) &
                    prior.rf_heading_sigma_deg.isin(S2)]
        curr=bd[['route','heading2_std_deg','rmse_2d_m','rmse_heading_deg','final_coverage_pct']]
        joined=curr.merge(prior[['route','rf_heading_sigma_deg','rmse_2d_m','rmse_heading_deg','final_coverage_pct']],
                          left_on=['route','heading2_std_deg'],right_on=['route','rf_heading_sigma_deg'],
                          suffixes=('_new','_old'))
        qa['previous_rf_sigma_sweep_exact']=bool(len(joined)==4*len(S2) and all(
            np.max(np.abs(joined[c+'_new']-joined[c+'_old']))<1e-10
            for c in ('rmse_2d_m','rmse_heading_deg','final_coverage_pct')))
        joined.to_csv(out/'rf_sigma_reference_audit.csv',index=False,float_format='%.13g')
    else:
        qa['previous_rf_sigma_sweep_exact']='NOT_RUN_DIFFERENT_SEED_OR_PRIOR_MISSING'
    invalid={}
    for route,d in cached.items():
        invalid[route]=float(100*np.mean((np.abs(d['gt'][:,:,1])>cfg.robot_center_ymax_m).any(axis=1)))
    with (out/'qa_checkpoints.json').open('w',encoding='utf8') as f:
        json.dump(dict(qa=qa,invalid_gt_run_pct=invalid,run_count=cfg.runs,seed=cfg.seed),f,indent=2,ensure_ascii=False)
    if not all(v is True or isinstance(v,str) for v in qa.values()):
        raise AssertionError(f'QA failed {qa}')
    # Plot grid and trajectory examples.
    if not fast_fig:
        for route in ROUTES:
            heatmap_one(df,route,out)
        heatmap_all(df,out,cfg.runs)
        line_charts(alld,out,cfg.runs)
        trajectory_figure(cfg,cached,out)
    write_report(cfg,alld,out,qa)
    (out/'README_KO.md').write_text('\n'.join([
      '# Dual Heading: Heading 1 Bias × Heading 2 표준편차 5×5',
      '',f'경로 {len(ROUTES)}개 × bias 5 × RF sigma 5 = 100개 실험 × Monte Carlo {cfg.runs}회.',
      '', '## 주요 파일', '',
      '- `REPORT_KO.md`: 네 경로의 5×5 × 3개 평가 지표 수치표.',
      '- `bias1_vs_sigma2_all_routes.csv`: 100개 조건의 자세한 수치.',
      '- `unbiased_heading1_reference.csv`: Heading 1 bias=0° 기준선.',
      '- `all_routes_5x5_overview.png`: 4개 경로 × 3개 지표 매트릭스.',
      '- `heatmap_{route}_three_metrics.png`: 경로별 확대 heatmap.',
      '- `precision_vs_dr_bias_all_routes.png`: 표준편차와 bias 효과 곡선.',
      '- `straight_four_corner_trajectory_examples.png`: 네 극단 조건의 예시 궤적.',
      '- `dual_heading_sim_extended.py`: 센서 생성·EKF core, 과거 시뮬레이션에서 동일하게 복사.',
      '- `run_grid.py`: 본 grid 실행 및 결과 생성.',
      '- `CONFIG.json` / `MANIFEST.json` / `qa_checkpoints.json`: 설정·검증·해시 감사.',
      '', '## 실행', '',
      '```bash','python -m pip install numpy pandas matplotlib',
      f'python run_grid.py --runs {cfg.runs} --seed {cfg.seed}', '```','',
      '## 유의 사항','',
      '- Heading 2 bias는 모든 실험에서 0°이고, 표에 표시한 0.5/1/2/5/10은 **표준편차**입니다.',
      '- Heading 1 bias는 100 step 전체에 누적되는 미보정 회전 바이어스입니다.',
      '- RF 절대 Heading 관측은 가상 가정이며 단일 앵커가 이를 제공하는지는 검증 대상입니다.',
      '- Dual-LP 또는 Sionna 채널 생성은 사용하지 않았습니다.',
      '- 복도 형상은 GitHub의 비실측 기본 치수를 사용했습니다.'
    ]),encoding='utf8')
    cfg_json=dict(config=dataclasses.asdict(cfg),bias1_accum_total_deg=list(B1),heading2_sigma_deg=list(S2),
        heading2_fixed_bias_deg=0.,heading1_step_std_deg=cfg.dr_yaw_std_deg,
        heading1_bias_unmodelled=True,rf_abs_heading_idealized=True,
        heading1_bias_is_accumulated_total=True,correlation_mode='independent white noise',
        output_metrics=list(METRICS),run_s=time.monotonic()-t0,
        corridor_git_source='myoungsunk/sionna-resimulation src/qclean_uwb/scenarios/corridor.py, ref codex/range-only-bias-consistency-20261011')
    (out/'CONFIG.json').write_text(json.dumps(cfg_json,indent=2,ensure_ascii=False),encoding='utf8')
    hsh={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(out.iterdir()) if f.is_file() and f.name not in ('MANIFEST.json','execution.log','run.pid')}
    (out/'MANIFEST.json').write_text(json.dumps(dict(files_sha256=hsh,QA=qa),indent=2,ensure_ascii=False),encoding='utf8')
    print('SUMMARY',df[df.route=='straight'][['heading1_accum_bias_deg','heading2_std_deg','rmse_2d_m','rmse_heading_deg','final_coverage_pct']].to_string(index=False))
    print('INVALID',invalid)
    print('QA',qa)
    print('TOTAL_SECONDS',round(time.monotonic()-t0,2),flush=True)
    return df,bd,qa

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--runs',type=int,default=1000)
    p.add_argument('--seed',type=int,default=20261012)
    p.add_argument('--out',type=Path,default=Path(__file__).resolve().parent)
    p.add_argument('--no-figures',action='store_true')
    a=p.parse_args()
    cfg=Config(runs=a.runs,seed=a.seed)
    run(cfg,a.out,fast_fig=a.no_figures)
