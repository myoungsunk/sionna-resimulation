from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent
PRIMARY=['R2_aA_m45','R4_aA_m0','R4_aB_m0']
def wrap(x):return 180-(180-x)%360
def rms(x):return float(np.sqrt(np.mean(np.asarray(x)**2)))
def table(d):
    return '\n'.join(['| '+' | '.join(d.columns)+' |','| '+' | '.join(['---']*len(d.columns))+' |']+['| '+' | '.join(f'{v:.4f}' if isinstance(v,float) else str(v) for v in row)+' |' for row in d.itertuples(index=False,name=None)])

def main():
    assert json.loads((ROOT/'RT_EXECUTION_RESULT.json').read_text())['status']=='TECHNICAL_PASS'
    passes=pd.read_csv(ROOT/'P2_PASSES_GT.csv');passes=passes[passes.primary]
    manifest=json.loads(Path(r'D:/SLAM_bot/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/execution_33e9849/p2/research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())
    cases={x['id']:x for x in manifest['cases']};rows=[];plotdata={};checks=[]
    for stage in ['RS0','RS1_RS2','RT_OFF','RT_CUT']:
        for p in passes.itertuples():
            z=np.load(ROOT/stage/f'{p.case}_{p.bias}.npz');t=np.round(z['t_s'],8);truth=z['truth_scoring_only'];x=z['x'];anc=np.array(cases[p.case]['anchor']);rad=truth[:,:2]-anc[:2];d=np.linalg.norm(rad,axis=1);ur=rad/d[:,None];ut=np.column_stack([-ur[:,1],ur[:,0]])
            pe=x[:,:,:2]-truth[:,None,:2];et=np.einsum('nji,ni->nj',pe,ut)*100;er=np.einsum('nji,ni->nj',pe,ur)*100
            psi=wrap(np.degrees(x[:,:,2]-truth[:,None,2]));beta=wrap(np.degrees(np.arctan2(anc[1]-x[:,:,1],anc[0]-x[:,:,0])-np.arctan2(anc[1]-truth[:,1],anc[0]-truth[:,0])[:,None]))
            S=z['H']@z['Pprior']@z['H'].swapaxes(-1,-2)+z['R'];nis=z['nu'][:,:,1]**2/S[:,:,1,1]
            fullerr=x-truth[:,None,:];fullerr[:,:,2]=np.radians(psi)
            nees=np.einsum('nji,nji->nj',fullerr,np.linalg.solve(z['P'],fullerr[...,None])[...,0]);hn=np.radians(psi)**2/z['P'][:,:,2,2]
            re=(np.sqrt(np.sum((x[:,:,:2]-anc[:2])**2,axis=2)+(anc[2]-cases[p.case]['robot_z_m'])**2)-np.sqrt(d*d+(anc[2]-cases[p.case]['robot_z_m'])**2)[:,None])*100
            masks={'scoring':t>=30,'pass':(t>=p.window_start_s)&(t<=p.window_end_s),'post':(t>p.post_start_s)&(t<=p.post_end_s)}
            assert int(masks['post'].sum())==p.post_n
            for j,arm in enumerate(z['names']):
                plotdata[(p.case,p.bias,str(arm))]=(t,psi[:,j],et[:,j])
                for scope,m in masks.items():
                    acc=m&z['acc'][:,j]
                    rows.append(dict(case=p.case,bias=p.bias,arm=str(arm),scope=scope,n=int(m.sum()),heading_rmse_deg=rms(psi[m,j]),heading_bias_deg=float(psi[m,j].mean()),
                                     et_bias_cm=float(et[m,j].mean()),er_bias_cm=float(er[m,j].mean()),beta_bias_deg=float(beta[m,j].mean()),xy_rmse_cm=rms(np.linalg.norm(pe[m,j],axis=1)*100),range_rmse_cm=rms(re[m,j]),
                                     heading_nees=float(hn[m,j].mean()),state4_nees=float(nees[m,j].mean()),pol_nis_accepted=float(nis[acc,j].mean()) if acc.any() else np.nan,accepted_n=int(acc.sum()),pol_nis_all=float(nis[m,j].mean())))
            # Independent numerical update guard from saved trace, including modified gains.
            dx=np.einsum('njab,njb->nja',z['K'],z['nu'])*z['acc'][:,:,None]
            diff=z['x']-z['prior'];diff[:,:,2]=np.radians(wrap(np.degrees(diff[:,:,2]-dx[:,:,2])))+dx[:,:,2]
            err=float(np.max(abs(diff-dx)));assert err<1e-10
            checks.append(dict(stage=stage,case=p.case,bias=p.bias,update_max_abs=err))
            for col in ['P','Pprior']:
                assert abs(z[col]-z[col].swapaxes(-1,-2)).max()<1e-12
                assert np.linalg.eigvalsh(z[col]).min()>=-1e-12
    metrics=pd.DataFrame(rows);metrics.to_csv(ROOT/'WINDOW_METRICS.csv',index=False)
    decisions=[];rt=[]
    for p in passes.itertuples():
        g=metrics[(metrics.case==p.case)&(metrics.bias==p.bias)].set_index(['arm','scope'])
        for rs in [1,2]:
            base=g.loc[('RS0_BB','scoring')];new=g.loc[(f'RS{rs}_BB','scoring')]
            oldet=abs(g.loc[('RS0_BB','post'),'et_bias_cm']);newet=abs(g.loc[(f'RS{rs}_BB','post'),'et_bias_cm'])
            gap0=g.loc[('RS0_MB','scoring'),'heading_bias_deg']-base.heading_bias_deg
            gap=g.loc[(f'RS{rs}_MB','scoring'),'heading_bias_deg']-new.heading_bias_deg
            etratio=newet/oldet if oldet>1e-12 else np.nan;gr=abs(gap/gap0) if abs(gap0)>1e-12 else np.nan
            improved=new.heading_rmse_deg<base.heading_rmse_deg
            decisions.append(dict(case=p.case,bias=p.bias,arm=f'RS{rs}',rmse_base=base.heading_rmse_deg,rmse_new=new.heading_rmse_deg,rmse_improved=improved,
                                  post_abs_et_base_cm=oldet,post_abs_et_new_cm=newet,post_et_ratio=etratio,heading_gap_base_deg=gap0,heading_gap_new_deg=gap,heading_gap_abs_ratio=gr,
                                  result='REJECT' if not improved else 'CONDITIONAL' if etratio>1.1 or gr>1.1 else 'CANDIDATE' if np.isfinite(etratio) and np.isfinite(gr) else 'NA'))
        for scope in ['post','scoring']:
            for kind in ['PASS','ALL']:
                row=dict(case=p.case,bias=p.bias,arm='CUT_RT_'+kind,scope=scope)
                for metric,col,minimum in [('et','et_bias_cm',.1),('beta','beta_bias_deg',.01),('heading','heading_bias_deg',.01)]:
                    g0=g.loc[('OFF_MB',scope),col]-g.loc[('OFF_BB',scope),col];gc=g.loc[(kind+'_MB',scope),col]-g.loc[(kind+'_BB',scope),col]
                    valid=abs(g0)>=minimum;fm=1-abs(gc/g0) if valid else np.nan
                    row.update({metric+'_base_gap':g0,metric+'_cut_gap':gc,metric+'_f_magnitude':fm,metric+'_f_signed':1-gc/g0 if valid else np.nan,metric+'_sign_flip':bool(g0*gc<0),metric+'_result':'NA' if not valid else 'SUPPORT' if fm>=.7 else 'PARTIAL' if fm>=.3 else 'NOT_SUPPORT'})
                rt.append(row)
    decisions=pd.DataFrame(decisions);rt=pd.DataFrame(rt);decisions.to_csv(ROOT/'RS_DECISIONS.csv',index=False);rt.to_csv(ROOT/'RT_GAP_REDUCTIONS.csv',index=False)
    checksfile=dict(status='PASS',saved_trace_update_and_covariance=checks)
    (ROOT/'REPORT_CHECKS.json').write_text(json.dumps(checksfile,indent=2),encoding='utf-8')
    fig=ROOT/'figures';fig.mkdir(exist_ok=True)
    plt.rcParams.update({'font.size':10,'axes.grid':True,'grid.alpha':.25})
    gaps=pd.read_csv(ROOT/'P3_GAP_SERIES.csv');led=pd.read_csv(ROOT/'2A_LEDGER_PASS.csv')
    for bias in ['B0','L2']:
        f,ax=plt.subplots(4,3,figsize=(15,10),sharey='row',layout='constrained')
        for j,case in enumerate(PRIMARY):
            p=passes[(passes.case==case)&(passes.bias==bias)].iloc[0];g=gaps[(gaps.case==case)&(gaps.bias==bias)];g=g[(g.t_s>=max(0,p.window_start_s-10))&(g.t_s<=p.post_end_s)]
            for i,(col,label) in enumerate([('d_gt_m','GT distance (m)'),('e_t_cm','MB-BB tangent (cm)'),('e_r_cm','MB-BB radial (cm)'),('psi_err_deg','MB-BB heading (deg)')]):
                ax[i,j].plot(g.t_s,g[col],color='#1f77b4');ax[i,j].axvspan(p.start_s,p.end_s,color='orange',alpha=.18);ax[i,j].axvspan(p.post_start_s,p.post_end_s,color='green',alpha=.07);ax[i,j].set_ylabel(label);ax[i,j].axhline(0,color='gray',lw=.6)
            ax[0,j].set_title(case+' / '+bias);ax[-1,j].set_xlabel('Time (s)')
        f.suptitle('First pass: orange = near episode; green = post window');f.savefig(fig/f'F1_formation_{bias}.png',dpi=140);plt.close(f)
    f,ax=plt.subplots(2,3,figsize=(15,7),sharey=True,layout='constrained')
    for i,bias in enumerate(['B0','L2']):
        for j,case in enumerate(PRIMARY):
            p=passes[(passes.case==case)&(passes.bias==bias)].iloc[0]
            for arm,col in [('RS0_BB','#555555'),('RS1_BB','#0072b2'),('RS2_BB','#d55e00')]:
                t,psi,et=plotdata[(case,bias,arm)];m=(t>=p.window_start_s)&(t<=p.post_end_s);ax[i,j].plot(t[m],psi[m],label=arm,color=col,lw=1.2)
            ax[i,j].axvspan(p.start_s,p.end_s,color='orange',alpha=.15);ax[i,j].set(title=case+' / '+bias,xlabel='Time (s)',ylabel='Heading error (deg)');ax[i,j].legend(fontsize=8)
    f.savefig(fig/'F2_RS_heading.png',dpi=140);plt.close(f)
    f,ax=plt.subplots(2,3,figsize=(15,8),sharey=True,layout='constrained');cols=['initial_cm','prop_cm','rng_rad_cm','rng_tan_cm','pol_cm']
    for i,bias in enumerate(['B0','L2']):
        for j,case in enumerate(PRIMARY):
            q=led[(led.case==case)&(led.bias==bias)].iloc[0];ax[i,j].bar(['initial','prop','range radial','range tangent','pol'],q[cols].astype(float),color=['gray','#009e73','#56b4e9','#0072b2','#cc79a7']);ax[i,j].axhline(q.post_gap_cm,color='black',ls='--',label='observed total');ax[i,j].axhline(0,color='black',lw=.6);ax[i,j].tick_params(axis='x',rotation=25);ax[i,j].set(title=case+' / '+bias,ylabel='Post tangent contribution (cm)');ax[i,j].legend(fontsize=8)
    f.savefig(fig/'F3_ledger.png',dpi=140);plt.close(f)
    f,ax=plt.subplots(2,3,figsize=(15,8),sharey=True,layout='constrained')
    for i,bias in enumerate(['B0','L2']):
        for j,case in enumerate(PRIMARY):
            q=rt[(rt.case==case)&(rt.bias==bias)&(rt.scope=='post')].set_index('arm')
            for off,kind,col in [(-.18,'PASS','#0072b2'),(.18,'ALL','#d55e00')]:ax[i,j].bar(np.arange(3)+off,[q.loc['CUT_RT_'+kind,k+'_f_magnitude'] for k in ['et','beta','heading']],.35,label=kind,color=col)
            ax[i,j].set_xticks(range(3),['tangent','azimuth','heading']);ax[i,j].axhline(.7,color='green',ls='--');ax[i,j].axhline(.3,color='gray',ls=':');ax[i,j].axhline(0,color='black',lw=.6);ax[i,j].set(title=case+' / '+bias,ylabel='Post gap reduction');ax[i,j].legend(fontsize=8)
    f.savefig(fig/'F4_CUT_RT.png',dpi=140);plt.close(f)
    ls=pd.read_csv(ROOT/'2A_LEDGER_SERIES.csv.gz');f,ax=plt.subplots(2,3,figsize=(15,8),sharey=True,layout='constrained')
    for i,bias in enumerate(['B0','L2']):
        for j,case in enumerate(PRIMARY):
            p=passes[(passes.case==case)&(passes.bias==bias)].iloc[0];q=ls[(ls.case==case)&(ls.bias==bias)&(ls.t_s<=p.post_end_s)]
            for col in ['initial_cm','prop_cm','rng_rad_cm','rng_tan_cm','pol_cm']:ax[i,j].plot(q.t_s,q[col],label=col.removesuffix('_cm'),lw=1)
            ax[i,j].plot(q.t_s,q.observed_gap_cm,'k--',label='observed',lw=1.4);ax[i,j].axvspan(p.start_s,p.end_s,color='orange',alpha=.12);ax[i,j].set(title=case+' / '+bias,xlabel='Time (s)',ylabel='Cumulative projection (cm)');ax[i,j].legend(fontsize=7,ncol=2)
    f.savefig(fig/'F5_ledger_time.png',dpi=140);plt.close(f)
    cv=pd.read_csv(ROOT/'P1_CV.csv').iloc[:3];formation=pd.read_csv(ROOT/'P3_FORMATION.csv');formation=formation[formation.primary]
    summary=[]
    for rs in ['RS1','RS2']:
        d=decisions[decisions.arm==rs];improved=sum(bool(g.rmse_improved.all()) for _,g in d.groupby('case'));candidate=sum(bool((g.result=='CANDIDATE').all()) for _,g in d.groupby('case'))
        summary.append(dict(arm=rs,improved_cases=improved,candidate_cases=candidate,result='ADOPTION_CANDIDATE' if candidate>=2 else 'NOT_ADOPTED'))
    pd.DataFrame(summary).to_csv(ROOT/'RS_CASE_SUMMARY.csv',index=False)
    text='# 앵커 통과 구간 R_s 및 방위각 이동 진단\n\n'
    text+='## 요약\n\n단계0 P1–P4 모두 Go. RS0/RT_OFF 재현과 수치 검산 통과 후 RS1·RS2, 2a 장부, CUT_RT_PASS/ALL을 순서대로 실행했다. 선택 RS3와 2c 윈도우 구현은 실행하지 않았다.\n\n'+table(pd.DataFrame(summary))+'\n\n'
    text+='**RS1·RS2 모두 채택 기준 미충족.** Heading RMSE가 개선된 R4_aB도 통과 후 접선 bias 크기가 RS1에서1.94–1.95배로 커졌다. R2_aA_m45와 R4_aA는 Heading RMSE도 악화됐다. 작은 NIS가 R_s 감소의 충분한 근거는 아니었다.\n\n**CUT_RT_PASS의 통과 후 접선 gap 감소:** R2_aA_m45 78–94%, R4_aA 53–54%, R4_aB 4–6%. R2에서는 H2 개입 효과가 크고 R4_aA에서는 부분 기여, R4_aB에서는 작은 효과다. Heading gap 감소는 각각59–72%,62–63%,3–4%로 동일하지 않다.\n\nBB 전체 t≥30 Heading RMSE 기준이며 B0/L2 모두 개선해야 case 1개로 센다. 아래 통과 후 지표를 함께 확인한다. case 그룹3개는 독립 route3개가 아니며 실제 route는 R2/R4 두 개다. LORO 학습은 R2/R4/R5의 route 분할이다.\n\n'
    text+='## 검산 및 고정 정의\n\n원문 PROTOCOL.md, 사용자 수정 PROTOCOL_ADDENDUM.md, 실험2 정의를 실행 전에 보존했다. 분석 창은 GT 거리로 공통 정의했고 적용 R_s는 각 arm prior 추정거리로 계산했다. 모든 고정-mask arm은 A_B이며 자연 gate는 RS2만 쓴다. 입력/출력 해시 및 종료 증거는 각 LOCK/CHECKS/FINISH 파일에 기록했다. P/Pprior 대칭·PSD, 거절 상태/P 보존, saved Kν 갱신 일치, 평균 및 range R 보존을 확인했다. RS0와 RT_OFF는 각6조건에서 E1 x/P/prior/Pprior/h/H/K/mu/R/nu/acc를 절대오차1e-10 이하로 재현했다.\n\n'
    text+='## 단계0: 유효성\n\n### P1 LORO 분산\n\n'+table(cv)+'\n\n전체시간의 B0/BB만 사용하며, GT/test route를 분산 표 학습에 넣지 않았다. 잔차 평균은 별도 보존하고 ddof=1 분산만 R_s로 사용했다. 이 표는 시뮬레이션 오프라인 잔차로 보정된 것으로 실측 하드웨어 검증이 아니다.\n\n### P2/P3 첫 통과\n\n'+table(formation[['case','bias','start_s','end_s','pre_length_s','pre_n','post_length_s','post_n','init_overlap','e_t_cm_pre','e_t_cm_post','formation_ratio','result']])+'\n\n초기 짧은 pre는 최소5초 조건을 충족한 부분창이다. R2/R4_aA에는 init_overlap 표시가 있다. 두 번째 이후 통과는 P3_FORMATION.csv의 reexposure 행에 별도 보존했다. 이전 d_est 기반 P2_PASSES.csv는 preliminary이며 최종 공통 창은 P2_PASSES_GT.csv다.\n\n'
    text+='### P4 gate 미리보기\n\n'+table(pd.read_csv(ROOT/'P4_GATE_PREVIEW.csv').query('primary')[['case','bias','arm','new_reject_n','accepted_n','new_reject_fraction_accepted','result']])+'\n\nP4는 기존 prior/innovation 고정 계산이다. RS2의 실제 재귀 상태 변화 뒤 gate 결과를 보장하지 않는다. MB의 원래 자연 gate가 A_B와 같을 필요도 없으며 차이는 P4_BASELINE_GATE_DIFFERENCES.csv에 기록했다.\n\n'
    text+='## 실험1: R_s 재설정\n\n'+table(decisions[['case','bias','arm','rmse_base','rmse_new','post_et_ratio','heading_gap_abs_ratio','result']])+'\n\npost_et_ratio는 |평균 e_t|의 새값/기준값이다. 원값과 전체 지표는 RS_DECISIONS.csv 및 WINDOW_METRICS.csv에 보존했다.\n\n'+table(metrics[(metrics.arm.isin(['RS0_BB','RS1_BB','RS2_BB']))&(metrics.scope.isin(['pass','post']))][['case','bias','arm','scope','heading_rmse_deg','heading_bias_deg','et_bias_cm','pol_nis_accepted']])+'\n\n'
    text+='R4_aA는 초기 통과 영향 때문에 pass/post 지표를 전체점수와 함께 우선 검토한다. 위 채택표는 사전에 명시된 t≥30 주지표를 유지하며, 통과 지표로 기준을 사후 교체하지 않았다. 개선된 조건도 접선오차나 Heading gap이10% 넘게 악화되면 조건부로 표시했다.\n\n![Heading](figures/F2_RS_heading.png)\n\n'
    if (ROOT/'ACTUAL_GATE_CHANGES.csv').exists():
        actual=pd.read_csv(ROOT/'ACTUAL_GATE_CHANGES.csv');actual=actual[actual.arm.str.startswith('RS2')]
        text+='### 실제 재귀 gate 변화\n\n'+table(actual[['case','bias','arm','AB_accepted','new_rejected','new_accepted','new_reject_fraction']])+'\n\nR4_aA의 RS2_BB 신규 거절은 B0 47.2%, L2 24.3%로, 기존 innovation 고정 P4의 약9–10%보다 컸다. 실제 재귀에서는 gate 변화가 크게 동반되므로 RS1과 분리해 해석해야 한다. 이는 사전 Go 기준의 사후 변경이 아니라 별도 운용 결과다.\n\n'
    text+='## 실험2a: 세계 좌표 장부\n\n'+table(led[['case','bias','post_gap_cm','initial_cm','prop_share','rng_rad_share','rng_tan_share','pol_share','CUT_RT_trigger']])+'\n\n장부 합은 각 packet 및 post 평균에서1e-10cm 이내로 관측 gap과 일치한다. 표는 초기차이를 포함한 signed 구성비로, 양·음 성분이 상쇄하므로 합 또는 개별 비율이 직관적 확률이 아니다. 확장 창 내부에서 생긴 증분과 이후 증분은 원본CSV에 분리했다. R2의 prop 몫도 커서 range 접선 성분만의 유일한 원인으로 해석할 수 없다. R4_aB의 range 반경 성분은 H1의 기술적 귀속이며 개입으로 H1을 확정한 것은 아니다.\n\n![장부](figures/F3_ledger.png)\n\n'
    text+='## 실험2b: CUT_RT\n\n'+table(rt[rt.scope=='post'][['case','bias','arm','et_f_magnitude','beta_f_magnitude','heading_f_magnitude','et_sign_flip','beta_sign_flip','heading_sign_flip']])+'\n\n양수는 gap 감소, 음수는 확대다. PASS는 첫 GT 통과 확장 창, ALL은 전체 구간이며 편파 gain 열은 직접 바꾸지 않았다. 이후 상태·공분산·gain 변화는 개입 효과에 포함된다. 개별 조건 감소가 모든 경로의 유일성을 입증하지 않는다.\n\n![CUT_RT](figures/F4_CUT_RT.png)\n\n'
    text+='## 통과 시계열\n\n![B0](figures/F1_formation_B0.png)\n\n![L2](figures/F1_formation_L2.png)\n\n![세계 좌표 누적 후 현재 접선축 투영](figures/F5_ledger_time.png)\n\n'
    text+='## 해석 한계와 다음 단계\n\n- P1 표는 세 route의 유한 표본 분산이며, 평균 편향은 제거하지 않았다. 작은 NIS만으로 R_s 감소의 유효성을 보장할 수 없다.\n- 분석/개입 시간창은 GT를 이용하므로 CUT_RT_PASS 자체는 oracle 진단이다. RS1은 oracle A_B 고정, RS2만 온라인 거리와 자기 gate를 쓰는 형태다.\n- B0/L2는 같은 RF의 쌍이다. 유의성·동등성·일반화 주장은 하지 않는다.\n- 2c는 별도 승인 대상이다. 설계 방향은 첫 통과 창의 range+주행 잔차를 묶어 재선형화하고 후방 위치를 넘기는 것이다. range bias 상태를 추가하면 위치와 bias의 식별 가능성 및 윈도우 prior를 먼저 검토해야 한다. 편파는 방위각 정보원으로 사용하지 않는 계획이나, 이는 편파의 방위각 민감도가 정확히0이라는 뜻은 아니다. 구현하거나 실행하지 않았다.\n'
    (ROOT/'RESULTS_KO.md').write_text(text,encoding='utf-8')
    print(pd.DataFrame(summary).to_string(index=False));print(rt[rt.scope=='post'][['case','bias','arm','et_f_magnitude','beta_f_magnitude','heading_f_magnitude']].to_string(index=False))

if __name__=='__main__':main()
