from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parent;figs=R/'figures';figs.mkdir(exist_ok=True)
primary=['R2_aA_m45','R4_aA_m0','R4_aB_m0']
def table(df):
 def val(v):
  if isinstance(v,(float,np.floating)):return '—' if pd.isna(v) else f'{v:.6f}'
  return str(v)
 return '| '+' | '.join(df.columns)+' |\n| '+' | '.join(['---']*len(df.columns))+' |\n'+'\n'.join('| '+' | '.join(val(v) for v in row)+' |' for row in df.itertuples(index=False,name=None))
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':160})
lines=['# 물리량 단위 위치–Heading 진단','', '> 기존 E1 trace의 기술 분해와 GT 위치를 이용한 편파 기하 차단을 구분한다. B0/L2는 같은 RF의 쌍이며 독립 반복이 아니다.','', '## 실행 및 검산','']
if (R/'C_GAP_REDUCTIONS.csv').exists():
 lines[4:4]=['## 핵심 결과','', '**A0″·A·C 완료. B는 상수 성분의 B0/L2 동일성 검산에서 중단했으며 sweep은 실행하지 않았다.**' if (R/'B_FAILURE.json').exists() else 'A0″·A·C 검산 완료. B 상태는 아래에 기록한다.','', '| 주 분석 경로 | CUT_ALL gap 크기 감소 B0 / L2 | CUT_AZ 감소 B0 / L2 | 해석 |','| --- | --- | --- | --- |','| R2_aA_m45 | 71.81% / 72.62% | 59.28% / 58.39% | 전체 위치→편파 경로 필요성 지지. 단일 기하 성분의 70% 기준은 충족하지 않음 |','| R4_aA_m0 | 94.16% / 93.85% | 86.80% / 87.45% | 방위각 경로가 주 경로라는 oracle 근거 |','| R4_aB_m0 | 97.79% / 98.26% | 83.54% / 84.33% | 방위각 경로가 주 경로라는 oracle 근거 |','', '주 분석 6조건에서 CUT_ALL의 gap 부호 반전은 없다. 이 결과는 차단 이후 공분산과 gain 변화까지 포함하는 oracle 개입이며, 유일 원인이나 배포 해법의 확정은 아니다.','', 'R2_aA_m45의 위치 등가 성분은 실제 Heading bias 변화와 반대 부호였지만 CUT_ALL의 gap은 줄었다. 기술적 오차 구성과 재귀 경로 개입은 서로 다른 양이므로 모순으로 보지 않는다.','']
for stage in ['A0','A','C','B']:
 f=R/f'{stage}_GATE.json';fail=R/f'{stage}_FAILURE.json'
 if f.exists():lines.append(f'- {stage}: {json.loads(f.read_text())["status"]}')
 elif fail.exists():lines.append(f'- {stage}: STOP — `{json.loads(fail.read_text())["error"]}`')
 else:lines.append(f'- {stage}: 미완료')
lines+=['','[실행 전 정의](PROTOCOL.md) · [A 수치 구현 보충](A_NUMERICS_ADDENDUM.md) · [입력 hash](INPUT_LOCK.json)','', '## A. 위치 등가 Heading 오차와 기술 분해','', '위치 등가 오차는 추정 위치에서 편파 예측을 GT 값으로 맞추는 Heading 변화다. 재귀 필터의 실제 인과 기여량이나 추정기의 bias 보정값으로 동일시하지 않는다. 근은 유한 격자로 탐색하므로 격자 사이의 매우 가까운 복수 근을 완전히 배제한 수학적 인증은 아니다.','']
if (R/'A0_GATE.json').exists():
 gate=json.loads((R/'A0_GATE.json').read_text());count=sum(c[k]['n'] for c in gate['conditions'] for k in ['x','prior']);err=max(c[k]['G_explicit_max'] for c in gate['conditions'] for k in ['x','prior'])
 lines += [f'A0″: {count:,}개 prior/posterior 상태에서 재구현 G 최대 차이 {err:.6g}. UNCUT 해석 Jacobian도 원본과 비교했으며, 차단 Jacobian은 m0/m45의 안정한 셀·tap 표본에서 수치미분으로 별도 확인했다.','']
if (R/'A_METRICS.csv').exists():
 a=pd.read_csv(R/'A_METRICS.csv');rat=pd.read_csv(R/'A_EQ_RATIOS.csv');cont=pd.read_csv(R/'A_INPUT_CONTRIBUTIONS.csv')
 lines+=[table(rat), '', '분자: alpha0/1의 공통 유효 표본에서 위치 등가 오차 bias 차이. 두 분모는 각각 같은 공통 표본 및 E1 전체 평가 표본이다. 공통 결측 10% 초과 또는 분모 0.05° 미만이면 비율을 해석하지 않는다.','',f'70개 Arm 조건 중 undefined>10%: {int((a.undefined_fraction>.1).sum())}. wrap 항등식 위반 표본 합: {int(a.wrap_count.sum())}.','', '[A 전체 지표](A_METRICS.csv) · [입력별 편파비 변화](A_INPUT_CONTRIBUTIONS.csv)','']
 fig,axes=plt.subplots(2,3,figsize=(13,7),layout='constrained')
 for col,case in enumerate(primary):
  for bias,color in [('B0','#27689b'),('L2','#b65e28')]:
   g=a[(a.case==case)&(a.bias==bias)].sort_values('alpha')
   axes[0,col].plot(g.alpha,g.psi_bias,'o-',color=color,label=f'{bias}: heading')
   axes[0,col].plot(g.alpha,g.eq_bias,'x--',color=color,label=f'{bias}: equivalent')
   axes[1,col].plot(g.alpha,g.undefined_fraction*100,'o-',color=color,label=bias)
  axes[0,col].set_title(case);axes[0,col].set_ylabel('Signed bias (deg)');axes[1,col].set_ylabel('Undefined (%)');axes[1,col].set_xlabel('alpha');axes[1,col].axhline(10,color='gray',ls=':')
  for ax in axes[:,col]:ax.legend(fontsize=8);ax.grid(alpha=.2)
 fig.suptitle('A: descriptive equivalent error; valid-root samples only for dashed curves');fig.savefig(figs/'A_equivalent.png');plt.close(fig)
 lines+=['![기술 분해와 결측 비율](figures/A_equivalent.png)','', '### 거리 입력 음성 대조','',f'모든 조건/alpha의 |delta_s_r| 최대값: {cont.ds_r_max_abs.max():.6g}. 편파비의 공통 진폭은 상쇄되지만, 거리별 주파수 위상과 이산 첫 경로 검출은 남을 수 있다. 따라서 비영 값만으로 구현 오류라 판정하지 않는다.','']
 fig,axes=plt.subplots(2,3,figsize=(13,7),layout='constrained')
 for col,case in enumerate(primary):
  for row,bias in enumerate(['B0','L2']):
   g=cont[(cont.case==case)&(cont.bias==bias)&(cont.alpha==1)].iloc[0];ax=axes[row,col]
   ax.bar(range(5),[g[k+'_bias'] for k in ['ds_beta','ds_epsilon','ds_r','ds_interaction','ds_pos']],color=['#27689b','#4c9c82','#c58436','#8f6ca9','#555555'])
   ax.set_xticks(range(5),['AZ','EL','R','interaction','total'],rotation=20);ax.set_ylabel('Mean polarization-ratio change');ax.set_title(case+' / '+bias);ax.axhline(0,color='black',lw=.5)
 fig.suptitle('A3: one physical input replaced at a time, true heading, alpha=1');fig.savefig(figs/'A_input_contributions.png');plt.close(fig)
 lines+=['### 물리량별 편파비 변화','',f'전체 70개 Arm 조건 중 성분별 몫 해석 제외: {int((~cont.shares_interpretable).sum())}. 작은 분모 또는 상호작용 30% 초과 기준을 적용했다.','', '![물리량별 편파비 변화](figures/A_input_contributions.png)','']
 if (R/'A_DISTANCE_AUDIT.csv').exists():
  da=pd.read_csv(R/'A_DISTANCE_AUDIT.csv')
  lines += ['조건별 최대 거리 효과 표본에서 공통 진폭만 적용했을 때 원래 편파비가 유지되고, 주파수별 위상만 적용했을 때 거리 교체 결과가 재현되는지 검산했다. 이 검산은 선택된 설명용 표본에 대한 결과다.','',table(da[['case','bias','s_true','s_range','s_amplitude_only','s_phase_only','tap_true','tap_range']]),'','[거리 효과 검산](A_DISTANCE_AUDIT.csv)','']
if (R/'C_GAP_REDUCTIONS.csv').exists():
 c=pd.read_csv(R/'C_GAP_REDUCTIONS.csv');inter=pd.read_csv(R/'C_INTERACTIONS.csv')
 lines+=['## C. 물리량 경로 차단','', 'G는 alpha1−alpha0 Heading signed bias 차이다. f_magnitude는 gap 크기 감소이며 f_signed와 부호 반전을 별도 보고한다. GT 차단으로 이후 P/K도 변하므로 직접 효과만의 추정값은 아니다.','',table(c[c.case.isin(primary)]),'','[C 전체 지표](C_SCORES.csv) · [조건별 gap](C_GAP_REDUCTIONS.csv) · [차단 상호작용](C_INTERACTIONS.csv)','']
 fig,axes=plt.subplots(1,3,figsize=(14,5),layout='constrained')
 for ax,case in zip(axes,primary):
  for bias,color in [('B0','#27689b'),('L2','#b65e28')]:
   g=c[(c.case==case)&(c.bias==bias)].set_index('mode').loc[['CUT_ALL','CUT_AZ','CUT_EL','CUT_R']]
   ax.plot(range(4),g.f_magnitude,'o-',color=color,label=bias)
  ax.set_title(case);ax.set_xticks(range(4),['ALL','AZ','EL','R']);ax.set_ylabel('Gap magnitude reduction');ax.axhline(.7,color='gray',ls='--');ax.axhline(.3,color='gray',ls=':');ax.legend();ax.grid(alpha=.2)
 fig.suptitle('C: oracle interventions; paired B0/L2');fig.savefig(figs/'C_gap_reduction.png');plt.close(fig)
 lines+=['![경로별 gap 감소](figures/C_gap_reduction.png)','', '### 조건별 해석','']
 for (case,bias),g in c.groupby(['case','bias']):
  g=g.set_index('mode');row=g.loc['CUT_ALL'];fm=row.f_magnitude
  conclusion='분모가 작아 판정 불가' if pd.isna(fm) else '위치→편파 예측 경로의 필요성을 지지하는 oracle 근거' if fm>=.7 else '부분 감소' if fm>=.3 else '이 경로만으로 gap을 설명하지 못함'
  lines.append(f'- {case}/{bias}: {conclusion}; CUT_ALL f_magnitude={fm:.4f}.')
 lines+=['','개별 차단의 우세는 CUT_ALL 결과와 함께 읽는다. CUT_R의 작은 결과는 해당 조건에서의 음성대조 관찰이며 일반적인 거리 의존성 부재를 증명하지 않는다.','']
if (R/'B_INTERACTIONS.csv').exists():
 b=pd.read_csv(R/'B_INTERACTIONS.csv');lines+=['## B. 상수/변동 성분','',table(b[b.alpha==1]),'','[성분 정의](B_COMPONENTS.csv) · [B 지표](B_SCORES.csv) · [가산성](B_INTERACTIONS.csv)','', '성분별 몫은 기술적 구성 비중이다. 정규화 상호작용>0.3 또는 작은 분모에서는 해석하지 않는다.']
elif (R/'B_FAILURE.json').exists():
 lines+=['## B. 중단','',json.loads((R/'B_FAILURE.json').read_text())['error'],'','중단 기준을 통과시키기 위해 평균이나 표본을 바꾸지 않았다. CONST/VAR/FULL의 B replay는 시작하지 않았다.']
 if (R/'B_MASK_AUDIT.csv').exists():
  bm=pd.read_csv(R/'B_MASK_AUDIT.csv');lines+=['',table(bm),'', '모든 쌍의 packet별 delta_mu 차이는 0이다. 그러나 R2_aA_m0는 BASE 수용 집합이 8개 packet, R5_aA_m0는 1개 packet에서 다르다. 따라서 각자 A_B에서 평균을 내면 c가 달라진다. 같은 RF라는 사실이 재귀 gate mask의 동일성을 보장하지 않는다.','', '**재개 제안:** 원래 수식대로 각 B0/L2의 A_B에서 c를 계산하고, B0/L2 c 동일성 요구만 제거한다. mean(v|A_B)=0 및 나머지 검산은 유지한다. 이 변경은 아직 적용하지 않았다.','', '[평균/변동 검산](B_COMPONENTS.csv) · [mask 차이 확인](B_MASK_AUDIT.csv)']
lines+=['','## 해석 한계','', '- GT는 오프라인 oracle 진단에만 사용했다. 배포 가능한 보정기로 제안하지 않는다.','- 기존 X1/X2/E1–E4 결과는 수정하지 않았다. 새 결과의 수치 PASS와 가설 지지를 구분한다.','- 통계적 유의성·동등성·일반화를 주장하지 않는다.','']
(R/'RESULTS_KO.md').write_text('\n'.join(lines),encoding='utf-8')
print('Report generated')
