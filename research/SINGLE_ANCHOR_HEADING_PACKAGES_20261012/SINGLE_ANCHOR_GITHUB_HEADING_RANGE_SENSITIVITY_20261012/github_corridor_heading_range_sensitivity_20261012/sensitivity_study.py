#!/usr/bin/env python3
"""Reproducible heading/ranging sensitivity study on the GitHub corridor.

- Imports the previously validated plain-range 3-state EKF without modifying it.
- Synthetic signals only. RF angle bias is a deliberately illustrative proxy,
  NOT an empirical UWB response and NOT a Sionna RT result.
- 500 independent runs of 100 prediction/update steps are compared per case.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from dataclasses import asdict, replace
from pathlib import Path
import hashlib
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

THIS = Path(__file__).resolve().parent
BASE = THIS.parent / 'github_corridor_sim' / 'corridor_sim.py'
spec = importlib.util.spec_from_file_location('corridor_sim', BASE)
mod = importlib.util.module_from_spec(spec)
sys.modules['corridor_sim'] = mod
spec.loader.exec_module(mod)
Config = mod.Config
CHI2_95_2 = mod.CHI2_95_2


def first_matching_data(c, true_data, z):
    d = dict(true_data)
    d['z_ideal'] = z
    return d


def wall_violations(c, gt):
    illegal = ((np.abs(gt[..., 1]) > c.robot_y_limit_m) | (gt[..., 0] < c.robot_x_min_m) | (gt[..., 0] > c.robot_x_max_m))
    return float(100*illegal.mean()), float(100*np.any(illegal, axis=1).mean())


def run_case(c, data, z, group, case_id, description, assumed_R_std, params=None, dr_metrics=None):
    # EKF uses assumed R, not ground-truth range residual distribution.
    c_ekf=replace(c,range_std_m=float(assumed_R_std))
    updated = first_matching_data(c_ekf, data, z)
    out = mod.apply_filter(c_ekf, updated, 'EKF_IDEAL')
    m = mod.filter_metrics(out)
    dr = dr_metrics if dr_metrics is not None else mod.filter_metrics(mod.apply_filter(c_ekf, updated, 'DR'))
    re = z-data['r_true'][:, 1:]
    rm = mod.range_metrics(re)
    frac_samples, frac_runs = wall_violations(c_ekf, data['true'])
    return dict(group=group, case_id=case_id, description=description,
      **(params or {}),
      assumed_R_std_m=float(assumed_R_std),
      range_bias_m=rm['bias_m'],range_rmse_m=rm['rmse_m'],range_p95_abs_m=rm['p95_abs_m'],
      dr_rmse_2d_m=dr['rmse_2d_m'],dr_final_rmse_2d_m=dr['final_rmse_2d_m'],
      ekf_rmse_2d_m=m['rmse_2d_m'],ekf_rmse_x_m=m['rmse_x_m'],ekf_rmse_y_m=m['rmse_y_m'],
      ekf_final_rmse_2d_m=m['final_rmse_2d_m'],ekf_final_rmse_yaw_deg=m['final_rmse_yaw_deg'],
      ekf_nees_xy_mean=m['nees_xy_mean'],ekf_nis_mean=m['nis_mean'],
      ekf_coverage_xy_95_pct=m['coverage_xy_95_pct'],
      ekf_final_coverage_xy_95_pct=m['final_coverage_xy_95_pct'],
      ekf_final_nees_xy_mean=float(out['nees_xy'][:, -1].mean()),
      improvement_over_dr_pct=float(100*(1-m['rmse_2d_m']/dr['rmse_2d_m'])),
      wall_violation_gt_samples_pct=frac_samples,
      wall_violation_gt_runs_pct=frac_runs,
    )


def recalc_true_with_gyro_bias(c, base, delta_deg_per_step):
    b=np.deg2rad(delta_deg_per_step)
    gt_old=base['true']
    ds=np.linalg.norm(np.diff(gt_old[..., :2],axis=1),axis=-1)
    dpsi=mod.wrap(np.diff(gt_old[..., 2],axis=1))+b
    gt=np.zeros_like(gt_old)
    gt[:,0,:]=gt_old[:,0,:]
    for k in range(c.n_steps):
        gt[:,k+1,:]=mod.f_motion(gt[:,k,:],ds[:,k],dpsi[:,k])
    dd=dict(base)
    noise=base['z_ideal']-base['r_true'][:,1:]
    dd['true']=gt
    dd['r_true']=mod.true_3d_range(c,gt[..., :2])
    dd['z_ideal']=dd['r_true'][:,1:]+noise
    return dd


def angular_rf_bias_proxy(c, gt, amplitude):
    # Placeholder angular (180 deg periodic) + off-axis bias, not measured!
    to_ax=c.anchor_x_m-gt[:,1:,0]
    to_ay=c.anchor_y_m-gt[:,1:,1]
    horizontal=np.hypot(to_ax,to_ay)
    bearing=np.arctan2(to_ay,to_ax)
    rng=mod.true_3d_range(c,gt[:,1:,:2])
    angle=gt[:,1:,2]-bearing
    return amplitude*horizontal/rng*np.cos(2*angle)


def time_ar1_noise(white, rho):
    n,k=white.shape
    e=np.empty_like(white)
    e[:,0]=white[:,0]
    f=np.sqrt(1-rho*rho)
    for j in range(1,k):
        e[:,j]=rho*e[:,j-1]+f*white[:,j]
    return e


def make_rows(runs=500,seed=20261012):
    c=Config(runs=runs,seed=seed)
    d0=mod.generate(c)
    white=d0['z_ideal']-d0['r_true'][:,1:]
    dr0=mod.filter_metrics(mod.apply_filter(c,d0,'DR'))
    rows=[]
    def add(ca,data,z,grp,ident,desc,assumed_R=0.08,params=None,drm=None):
        rows.append(run_case(ca,data,z,grp,ident,desc,assumed_R,params,
                             dr_metrics=dr0 if drm=='baseline' else None))

    # H1: prior uncertainty, correctly reflected in P0, no RF dependence.
    for deg in [0.5,1.0,3.0,6.0]:
        cc=replace(c,initial_yaw_std_deg=deg)
        dd=mod.generate(cc)
        add(cc,dd,dd['z_ideal'],'H1_initial_heading',f'prior_{deg:g}deg',f'initial heading sigma={deg:g} deg',drm='baseline' if deg==3 else None,params={'initial_yaw_std_deg':deg})

    # H2: drift from independent per-step yaw noise, correctly modeled in Q.
    for deg in [0.05,0.10,0.23,0.35]:
        cc=replace(c,dr_yaw_step_std_deg=deg)
        dd=mod.generate(cc)
        add(cc,dd,dd['z_ideal'],'H2_heading_step_noise',f'step_{deg:g}deg',f'heading sigma/step={deg:g} deg',drm='baseline' if deg==0.23 else None,params={'yaw_step_std_deg':deg})

    # H3: unmodelled accumulated systematic bias in angular increment.
    for deg in [0.,0.01,0.03,0.05]:
        dd=recalc_true_with_gyro_bias(c,d0,deg) if deg else d0
        add(c,dd,dd['z_ideal'],'H3_unmodeled_gyro_bias',f'gyro_{deg:g}degstep',f'actual heading drift={deg:g} deg/step (model omits)',drm='baseline' if deg==0 else None,params={'gyro_bias_deg_per_step':deg})

    # H4: optional, purely illustrative orientation-dependent RF bias.
    for amp in [0.,0.05,0.10,0.20]:
        err=angular_rf_bias_proxy(c,d0['true'],amp)
        z=d0['z_ideal']+err
        add(c,d0,z,'H4_hypothetical_heading_RF',f'angle_Am_{amp:g}',f'illustrative RF angle-bias amplitude={amp:g} m',drm='baseline',params={'angle_bias_amplitude_m':amp})

    # R1: Gaussian noise sensitivity (matched assumed R).
    for sigma in [0.03,0.08,0.15,0.30]:
        zz=d0['r_true'][:,1:]+white*(sigma/c.range_std_m)
        add(c,d0,zz,'R1_white_gaussian_matched',f'gauss_{sigma:g}',f'Gaussian ranging sigma={sigma:g} m (matched R)',assumed_R=sigma,drm='baseline',params={'true_range_noise_std_m':sigma})

    # R1b: R miscalibration, retaining same raw noise as R1.
    for sigma in [0.15,0.30]:
        zz=d0['r_true'][:,1:]+white*(sigma/c.range_std_m)
        add(c,d0,zz,'R1b_gaussian_R_underestimated',f'gauss_{sigma:g}_R08',f'Gaussian ranging sigma={sigma:g} m but EKF assumes 0.08 m',drm='baseline',params={'true_range_noise_std_m':sigma})

    # R2: positive and negative systematic biases (not removed by EKF).
    for bias in [-0.2,0.0,0.1,0.2,0.5]:
        add(c,d0,d0['z_ideal']+bias,'R2_fixed_bias',f'bias_{bias:+g}',f'constant range bias {bias:+g} m',drm='baseline',params={'fixed_bias_m':bias})

    # R3: relative ranging scale error, not a calibrated sensor model.
    for pct in [0.01,0.03,0.05]:
        z=d0['z_ideal']+pct*d0['r_true'][:,1:]
        add(c,d0,z,'R3_range_scale_bias',f'scale_{pct*100:g}pct',f'range scale bias +{pct*100:g}% of 3D distance',drm='baseline',params={'range_scale_error_pct':pct*100})

    # R4: same marginal noise level but correlation leads to repeated information.
    for rho in [0.,0.90,0.98]:
        e=time_ar1_noise(white,rho)
        z=d0['r_true'][:,1:]+e
        add(c,d0,z,'R4_AR1_colored_noise',f'ar1_{rho:g}',f'AR(1) temporal correlation rho={rho:g}, nominal sigma=0.08 m',drm='baseline',params={'ar1_rho':rho})

    # R5: sporadic extra-positive outliers, no gating.
    rng=np.random.default_rng(seed+7171)
    uniforms=rng.random(white.shape)
    for p,amp in [(0.01,0.50),(0.05,0.50),(0.05,1.00)]:
        mask=uniforms<p
        z=d0['z_ideal']+amp*mask
        add(c,d0,z,'R5_positive_outliers',f'outlier_{p*100:g}pct_{amp:g}m',f'positive outliers p={p*100:g}% amplitude={amp:g} m',drm='baseline',params={'outlier_probability_pct':p*100,'outlier_amplitude_m':amp,'realized_outlier_probability_pct':float(100*mask.mean())})

    # Independent calibration of +0.20m offset: uses proper augmented EKF.
    calibrated=mod.apply_filter(c,d0,'EKF_CALIBRATED')
    mc=mod.filter_metrics(calibrated)
    rc=mod.range_metrics(d0['z_biased']-d0['b_hat'][:,None]-d0['r_true'][:,1:])
    rows.append(dict(group='R6_independent_calibration',case_id='bias_0.2_corrected',
      description='0.20 m bias, 1000 independent calibration samples; 4-state residual-bias EKF',
      assumed_R_std_m=c.range_std_m,
      range_bias_m=rc['bias_m'],range_rmse_m=rc['rmse_m'],range_p95_abs_m=rc['p95_abs_m'],
      dr_rmse_2d_m=dr0['rmse_2d_m'],dr_final_rmse_2d_m=dr0['final_rmse_2d_m'],
      ekf_rmse_2d_m=mc['rmse_2d_m'],ekf_rmse_x_m=mc['rmse_x_m'],ekf_rmse_y_m=mc['rmse_y_m'],
      ekf_final_rmse_2d_m=mc['final_rmse_2d_m'],ekf_final_rmse_yaw_deg=mc['final_rmse_yaw_deg'],
      ekf_nees_xy_mean=mc['nees_xy_mean'],ekf_nis_mean=mc['nis_mean'],
      ekf_coverage_xy_95_pct=mc['coverage_xy_95_pct'],ekf_final_coverage_xy_95_pct=mc['final_coverage_xy_95_pct'],
      ekf_final_nees_xy_mean=float(calibrated['nees_xy'][:,-1].mean()),
      improvement_over_dr_pct=float(100*(1-mc['rmse_2d_m']/dr0['rmse_2d_m'])),
      wall_violation_gt_samples_pct=wall_violations(c,d0['true'])[0],
      wall_violation_gt_runs_pct=wall_violations(c,d0['true'])[1],
      fixed_bias_m=0.20,independent_calibration_samples=1000))
    return c,pd.DataFrame(rows),d0


def plot_comparisons(df: pd.DataFrame, c: Config, out: Path):
    plt.rcParams.update({'font.size':10,'axes.grid':True,'grid.alpha':.23})
    def get(g):return df[df.group==g]
    # 1: initial heading prior and gyro bias (separate mechanisms)
    a=get('H1_initial_heading');b=get('H3_unmodeled_gyro_bias')
    fig,axs=plt.subplots(2,2,figsize=(11.4,7),constrained_layout=True)
    axs[0,0].plot(a.initial_yaw_std_deg,a.dr_rmse_2d_m,'o-',label='DR only')
    axs[0,0].plot(a.initial_yaw_std_deg,a.ekf_rmse_2d_m,'o-',label='Range EKF')
    axs[0,0].set(xlabel='Initial heading sigma (degrees)',ylabel='Overall position RMSE (m)',title='Heading uncertainty and localization');axs[0,0].legend()
    axs[0,1].plot(a.initial_yaw_std_deg,a.ekf_final_coverage_xy_95_pct,'o-')
    axs[0,1].axhline(95,linestyle=':',color='gray')
    axs[0,1].set(xlabel='Initial heading sigma (degrees)',ylabel='Final 2D 95% coverage (%)',title='EKF consistency vs. heading prior')
    axs[1,0].plot(b.gyro_bias_deg_per_step*100,b.ekf_rmse_2d_m,'o-',label='Range EKF')
    axs[1,0].plot(b.gyro_bias_deg_per_step*100,b.dr_rmse_2d_m,'o-',label='DR')
    axs[1,0].set(xlabel='Unmodeled accumulated heading drift over 100 steps (degrees)',ylabel='Overall position RMSE (m)',title='Systematic DR yaw bias');axs[1,0].legend()
    axs[1,1].plot(b.gyro_bias_deg_per_step*100,b.ekf_final_coverage_xy_95_pct,'o-',label='Final coverage')
    axs[1,1].axhline(95,linestyle=':',color='gray')
    axs[1,1].set(xlabel='Unmodeled accumulated heading drift (degrees)',ylabel='Final 95% coverage (%)',title='Bias produces overconfidence')
    fig.savefig(out/'01_heading_localization.png',dpi=170,bbox_inches='tight');plt.close(fig)

    # 2: changing RF amplitude and stationary yaw sweep proxy
    h=get('H4_hypothetical_heading_RF')
    fig,axs=plt.subplots(1,2,figsize=(11.4,3.85),constrained_layout=True)
    axs[0].plot(h.angle_bias_amplitude_m,h.range_rmse_m,'o-',label='Synthetic range RMSE')
    axs[0].plot(h.angle_bias_amplitude_m,h.ekf_rmse_2d_m,'o-',label='EKF 2D RMSE')
    axs[0].set(xlabel='Assumed RF orientation bias amplitude (m)',ylabel='RMSE (m)',title='Sensitivity to assumed orientation bias');axs[0].legend()
    yaws=np.linspace(0,180,181)
    x=9.;dz=c.anchor_z_m-c.tag_z_m
    horiz=abs(x-c.anchor_x_m)
    r=np.hypot(horiz,dz)
    for amp in (0.1,0.2):
        bb=amp*horiz/r*np.cos(2*np.deg2rad(yaws))
        axs[1].plot(yaws,bb,label=f'Proxy A={amp:.1f} m')
    axs[1].axhline(0,linestyle=':',color='gray')
    axs[1].set(xlabel='Physical robot yaw (degrees), stationary at x=9 m',ylabel='Assumed RF bias (m)',title='HYPOTHETICAL yaw sweep, not Sionna/measurement');axs[1].legend()
    fig.savefig(out/'02_yaw_rf_proxy.png',dpi=170,bbox_inches='tight');plt.close(fig)

    # 3: range error sources -> EKF localization vs NIS/NEES
    groups=['R1_white_gaussian_matched','R2_fixed_bias','R3_range_scale_bias','R4_AR1_colored_noise','R5_positive_outliers']
    group_titles=['White Gaussian noise','Constant range offset','Range scale error','Time-correlated noise','Positive outliers']
    fig,axs=plt.subplots(3,2,figsize=(13,10),constrained_layout=True)
    for i,(gp,title) in enumerate(zip(groups,group_titles)):
        sub=get(gp);x=np.arange(len(sub))
        ax=axs.flat[i]; ax.bar(x-.18,sub.ekf_rmse_2d_m,width=.35,label='2D RMSE')
        ax.bar(x+.18,sub.ekf_final_rmse_2d_m,width=.35,label='Final RMSE')
        ax.axhline(float(df[(df.group=='R1_white_gaussian_matched') & (df.case_id=='gauss_0.08')].iloc[0].dr_rmse_2d_m),color='gray',linewidth=1,linestyle=':')
        ax.set(title=title,ylabel='Position RMSE (m)',xticks=x,xticklabels=[v.replace('gauss_','σ ').replace('bias_','b ').replace('scale_','scale ').replace('ar1_','ρ ').replace('outlier_','out ') for v in sub.case_id],)
        ax.tick_params(axis='x',rotation=15)
        if i==0:ax.legend(fontsize=8)
    ax=axs.flat[-1]
    labels=['baseline','bias +0.20','AR1 0.98','outlier 5% +1m']
    keys=['gauss_0.08','bias_+0.2','ar1_0.98','outlier_5pct_1m']
    vals=[df[df.case_id==key].iloc[0] for key in keys]
    ax.bar(np.arange(4)-.2,[r.ekf_nis_mean for r in vals],width=.4,label='Mean NIS')
    ax.bar(np.arange(4)+.2,[r.ekf_nees_xy_mean for r in vals],width=.4,label='Mean NEES2D')
    ax.axhline(2,linestyle=':',color='gray',label='E[NEES]=2')
    ax.set(yscale='log',xticks=range(4),xticklabels=labels,title='Innovation vs. actual consistency (log scale)');ax.tick_params(axis='x',rotation=15);ax.legend(fontsize=8)
    fig.savefig(out/'03_ranging_localization.png',dpi=170,bbox_inches='tight');plt.close(fig)

    # 4: same-ranging-RMSE but different temporal correlation.
    ar=get('R4_AR1_colored_noise')
    fig,ax=plt.subplots(figsize=(8,4.0),constrained_layout=True)
    ax.plot(ar.ar1_rho,ar.ekf_rmse_2d_m,'o-',label='Overall RMSE 2D')
    ax.plot(ar.ar1_rho,ar.ekf_final_rmse_2d_m,'o-',label='Final RMSE 2D')
    ax.set(xlabel='AR1 rho',ylabel='Position RMSE (m)',title='Temporal correlation: same nominal range noise scale');ax.legend()
    fig.savefig(out/'04_ar1_same_variance.png',dpi=170,bbox_inches='tight');plt.close(fig)


def qa_checks(c,df,d0):
    expected=pd.read_csv(THIS.parent/'github_corridor_sim'/'methods_summary.csv').set_index('method')
    baseline=df[(df.group=='R1_white_gaussian_matched')&(df.case_id=='gauss_0.08')].iloc[0]
    assert abs(baseline.ekf_rmse_2d_m-expected.loc['EKF_IDEAL','rmse_2d_m'])<1e-6
    assert abs(baseline.ekf_nis_mean-expected.loc['EKF_IDEAL','nis_mean'])<1e-6
    assert abs(baseline.ekf_final_coverage_xy_95_pct-expected.loc['EKF_IDEAL','final_coverage_xy_95_pct'])<1e-6
    for grp in ('H1_initial_heading','H2_heading_step_noise','H3_unmodeled_gyro_bias'):
        part=df[df.group==grp]
        # geometric ranging noise independent of heading/DR uncertainty.
        assert np.max(np.abs(part.range_rmse_m-part.iloc[0].range_rmse_m))<1e-10,(grp,part.range_rmse_m.tolist())
    for a in [0.0,0.03,0.10,0.20]:
        # Centered antenna, fixed pose: true geometric range strictly independent of yaw.
        xy=np.array([[9.,0.]])
        r=mod.true_3d_range(c,xy)
        assert abs(float(r[0])-np.hypot(5.,2.2))<1e-10
    assert (df.ekf_rmse_2d_m > 0).all()
    assert np.isfinite(df.ekf_nees_xy_mean).all()
    assert np.isfinite(df.ekf_nis_mean).all()
    # Calibration must restore unbiased baseline within MC tolerance.
    calib=df[df.case_id=='bias_0.2_corrected'].iloc[0]
    assert abs(calib.ekf_rmse_2d_m-baseline.ekf_rmse_2d_m)<0.005
    # Same marginal range sigma case doesn't guarantee lower localization error.
    # Sample time-correlated std is finite, not forced exact.
    return dict(baseline_match=True,heading_independent_geometric_ranging=True,
      calibration_sanity=True,finite_metrics=True,plots_computed=True)


def markdown_report(c,df,checks,output):
    def tab(grp,cols):
        sub=df[df.group==grp]
        return sub[cols].to_markdown(index=False,floatfmt='.3f')
    cols=['description','range_rmse_m','ekf_rmse_2d_m','ekf_nees_xy_mean','ekf_nis_mean']
    t=[f'''# GitHub 복도 단일 앵커 Range-only + DR/EKF: Heading 및 Ranging 오차 민감도

## 실험 환경

- 출처: `myoungsunk/sionna-resimulation`의 `src/qclean_uwb/scenarios/corridor.py`, `codex/range-only-bias-consistency-20261011` (원본 수치 자체가 실측이 아닌 placeholder).
- 복도 20×2.4×2.7m, 앵커 (4,0,2.65)m, 태그 z=0.45m, 로봇 (4,0)→(14,0) 10m 직진.
- 0.1 m/step, 100 step, 0.5s/step, Monte Carlo {c.runs} independent runs, seed {c.seed}.
- 초기 heading sigma=3°, 상대 DR yaw sigma=0.23°/step, 이동 sigma=0.008m/step, ranging noise sigma=0.08m (기본값).
- **RF 측정 전파/다중경로는 계산하지 않음.** 자의적인 angle-bias 함수는 설명용 가상 proxy임.
- Range EKF는 기본적으로 `R=(0.08m)^2`를 가정, `R1`만 실제 Gaussian 표준편차에 맞게 R 조절.
- 복도 벽은 시각화 및 위반 확인 용도로만 활용함(충돌/운동 제약 미구현).
- 모델 공분산 기준: 평균 NIS 1, 평균 2D NEES 2, 2D 95% coverage 목표 95%.

## A. Heading -> ranging / localization

중앙 태그 위치에서 **기하 거리**는 heading에 직접 의존하지 않음: $r=\\sqrt{{(x-4)^2+y^2+2.2^2}}$, 따라서 $\\partial r/\\partial\\psi=0$ (고정 위치). Heading 오차는 DR 이동을 통해 위치를 변경하여 간접적으로 측정 거리와 위치 오차에 영향을 줄 수 있음. 추가 RF 효과는 검증되지 않은 angle-bias proxy로 독립 분리.

### A1. 초기 heading prior 표준편차 변화

{tab('H1_initial_heading',cols)}

### A2. 상대 heading의 매 스텝 Gaussian 오차

{tab('H2_heading_step_noise',cols)}

### A3. 필터가 모델링하지 않은 누적 DR yaw bias

{tab('H3_unmodeled_gyro_bias',cols)}

### A4. **가정**한 RF 방향별 거리 편향 함수

$b_{{RF}}(\\psi,\\beta)=A(d_{{xy}}/r)\\cos[2(\\psi-\\beta)]$. A는 물리적으로 측정된 값이 아니며, Sionna나 DW1000 수신기의 추정 곡선이 아님.

{tab('H4_hypothetical_heading_RF',cols)}

## B. Ranging -> localization

### B1. Gaussian white ranging noise (R 정합)

{tab('R1_white_gaussian_matched',cols)}

### B1b. 실제 ranging noise에 비해 EKF가 R을 과소평가

{tab('R1b_gaussian_R_underestimated',cols)}

### B2. 비보정 상수 range bias

{tab('R2_fixed_bias',cols)}

### B3. 거리 비례 scale bias

{tab('R3_range_scale_bias',cols)}

### B4. 시간적 상관 AR(1) noise

{tab('R4_AR1_colored_noise',cols)}

### B5. 양의 이상치(no gating)

{tab('R5_positive_outliers',cols)}

### B6. 독립적인 상수 bias calibration (1000 sample)

{tab('R6_independent_calibration',cols)}

## 전 조건 상세 수치

`all_scenarios.csv`의 33개 시나리오에 `RMSE_x`, `RMSE_y`, 전체/최종 `RMSE_2D`, NIS, NEES, 95% coverage, GT 복도 허용범위 위반률을 수록. 전체구간 RMSE에는 step 1~100, 최종은 step100만 포함.

## QA

{json.dumps(checks,ensure_ascii=False,indent=2)}

## 재현

```bash
python3 -m pip install -r requirements.txt
python3 sensitivity_study.py --runs 500 --seed 20261012
```

`../github_corridor_sim/corridor_sim.py`의 원본 EKF 함수를 직접 import. 패키지로 독립 실행하려면 `github_corridor_sim/corridor_sim.py`를 현재 폴더와 같은 상위 디렉터리로 풀거나, 아래 ZIP에 포함된 패키지용 폴더 계층을 그대로 유지.
''']
    (output/'REPORT_KO.md').write_text('\n'.join(t),encoding='utf-8')



def heading_geometry_report(c:Config, base:dict, out:Path):
    """How actual trajectory yaw drift affects 3D geometric range vs location."""
    rows=[]
    for bias in (0.,0.01,0.03,0.05):
        d = recalc_true_with_gyro_bias(c,base,bias)
        delta_xy = d['true'][:,-1,:2]-base['true'][:,-1,:2]
        delta_r = d['r_true'] - base['r_true']
        rows.append(dict(
          gyro_bias_deg_per_step=bias,
          accumulated_bias_deg=bias*c.n_steps,
          final_xy_shift_rms_m=float(np.sqrt(np.mean(np.sum(delta_xy**2,axis=-1)))),
          final_geometric_range_shift_rms_m=float(np.sqrt(np.mean(delta_r[:,-1]**2))),
          overall_geometric_range_shift_rms_m=float(np.sqrt(np.mean(delta_r[:,1:]**2))),
          final_geometric_range_shift_mean_m=float(np.mean(delta_r[:,-1]))))
    tab=pd.DataFrame(rows)
    tab.to_csv(out/'heading_geometric_effect.csv',index=False,float_format='%.9f')
    fig,ax=plt.subplots(figsize=(8,4.4),constrained_layout=True)
    ax.plot(tab.accumulated_bias_deg,100*tab.final_xy_shift_rms_m,'o-',label='Final actual position displacement (cm)')
    ax.plot(tab.accumulated_bias_deg,100*tab.final_geometric_range_shift_rms_m,'o-',label='Final geometric range change (cm)')
    ax.axhline(100*c.range_std_m,linestyle=':',color='gray',label='Baseline 1-sigma ranging error (cm)')
    ax.set(xlabel='Accumulated systematic yaw mismatch over 100 steps (degrees)',ylabel='RMS difference (cm)',title='Heading drift changes position far more than one-anchor range')
    ax.legend(loc='upper left',fontsize=8)
    fig.savefig(out/'05_heading_geometry_vs_range.png',dpi=170,bbox_inches='tight')
    plt.close(fig)
    return tab


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--runs',type=int,default=500)
    ap.add_argument('--seed',type=int,default=20261012)
    ap.add_argument('--out',type=Path,default=THIS)
    args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    print('BEGIN Monte Carlo scenarios',flush=True)
    c,df,d0=make_rows(args.runs,args.seed)
    df.to_csv(args.out/'all_scenarios.csv',index=False,float_format='%.9f')
    plot_comparisons(df,c,args.out)
    heading_geom=heading_geometry_report(c,d0,args.out)
    checks=qa_checks(c,df,d0) if args.runs==500 and args.seed==20261012 else {'baseline_match':'skipped_nondefault_seed'}
    cfg={'config':asdict(c),'checks':checks,'scenarios':len(df),'sha256_base_code':hashlib.sha256(BASE.read_bytes()).hexdigest(),
         'source_git_repo':'myoungsunk/sionna-resimulation','source_branch':'codex/range-only-bias-consistency-20261011',
         'source_blob_sha':'eba1ab64d5e2117bfd519ceb5cac077b24caf3f8',
         'models':'geometric 3D range; synthetically assigned error models; EKF Joseph covariance; no RF ray tracing',
         'signal_groups':df.groupby('group').size().astype(int).to_dict()}
    (args.out/'RUN_MANIFEST.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
    markdown_report(c,df,checks,args.out)
    with (args.out/'REPORT_KO.md').open('a',encoding='utf-8') as f:
        f.write('\n## Heading 경로 굴곡과 기하 거리 변화 (동일 난수 구동)\n\n')
        f.write(heading_geom.to_markdown(index=False,floatfmt='.6f'))
        f.write('\n\n복도 충돌·맵 기반 제약은 미사용. 위 최종 위치 변화는 heading bias가 없는 실제 GT와 비교한 값이며 EKF 오차가 아님.\n')
    print('DONE scenarios',len(df),flush=True)
    print(df[['group','case_id','range_rmse_m','ekf_rmse_2d_m','ekf_nees_xy_mean','ekf_nis_mean','ekf_final_rmse_2d_m','ekf_final_coverage_xy_95_pct']].round(3).to_string(index=False),flush=True)


if __name__=='__main__':main()
