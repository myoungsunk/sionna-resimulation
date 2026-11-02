"""Read-only pole probe and evidence report; no estimator replay."""
from pathlib import Path
import sys,json,hashlib
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import NullFormatter
from PIL import Image
OUT=Path(__file__).resolve().parent;RUN=OUT.parent
sys.path.insert(0,str(RUN));import replay_observer_swap as A
assert json.loads((OUT/'CHECKS.json').read_text())['inputs_unchanged']
d=pd.read_csv(OUT/'PACKET_DIAGNOSTICS.csv.gz');s=pd.read_csv(OUT/'SUMMARY_24.csv');c=pd.read_csv(OUT/'CROSS_ERROR_COV_AND_GATE.csv')
mb=d[d.stage=='PROPOSED_MB_VAR'];sm=s[s.stage=='PROPOSED_MB_VAR'];cm=c[c.stage=='PROPOSED_MB_VAR']
z=dict(np.load(RUN/'R5_aB_m0_L1_PROPOSED_MB_VAR_LUT.npz'));spec=A.DG.C.CASES['R5_aB_m0'];model=A.DG.C.base_model();lut=A.LutBatch()
rows=[]
# Hypothetical directions at fixed heading. Offline limiting-behavior probe only.
for rho in [.1,.05,.02,.01,.001,.00001]:
    ph=np.linspace(0,2*np.pi,72,endpoint=False);xx=np.tile(z['xp'][706],(len(ph),1));xx[:,0]=10+rho*np.cos(ph);xx[:,1]=rho*np.sin(ph)
    hs,js=model.batch(xx,spec);hl,jl=lut.batch(xx,spec)
    rows.append(dict(rho_m=rho,theta_deg=np.degrees(np.arctan2(rho,2.2)),s_Source_range=np.ptp(hs[:,1]),s_LUT_range=np.ptp(hl[:,1]),s_Source_min=hs[:,1].min(),s_Source_max=hs[:,1].max(),s_LUT_min=hl[:,1].min(),s_LUT_max=hl[:,1].max(),max_J_Source=np.linalg.norm(js[:,1,:2],axis=1).max(),max_J_LUT=np.linalg.norm(jl[:,1,:2],axis=1).max()))
pd.DataFrame(rows).to_csv(OUT/'POLE_LIMIT_PROBE.csv',index=False)

plt.rcParams.update({'font.family':'Times New Roman','font.size':9,'axes.labelsize':9,'axes.titlesize':9,'xtick.labelsize':8,'ytick.labelsize':8,'legend.fontsize':9,'axes.linewidth':.6,'pdf.fonttype':42,'ps.fonttype':42})
fig,axs=plt.subplots(3,4,figsize=(7.16,5.8),sharex=True)
fig.subplots_adjust(left=.105,right=.985,bottom=.09,top=.90,wspace=.25,hspace=.18)
metrics=[('J_sxy_norm',r'$\|\partial s/\partial(x,y)\|$ (1/m)',(.001,100),[.001,.01,.1,1,10,100]),('sigma_y_cm',r'$\sigma_y$ (cm)',(.08,12),[.1,1,10]),('nees_pose','Pose NEES (3D)',(.5,1200),[1,10,100,1000])]
for col,b in enumerate(A.BIASES):
    for row,(metric,ylabel,ylim,ticks) in enumerate(metrics):
        ax=axs[row,col]
        for j,ob in enumerate(['SourceFFD','LUT']):
            q=mb[(mb.bias==b)&(mb.observer==ob)&(mb.t_s>=135)&(mb.t_s<=165)]
            ax.plot(q.t_s,q[metric],color=['#2C648C','#B96616'][j],ls=['-','--'][j],lw=1,label=ob)
        ax.axvline(141.2,color='.5',ls=':',lw=.7)
        if row==2:ax.axhline(3,color='.5',ls=':',lw=.6)
        ax.set_yscale('log');ax.set_ylim(*ylim);ax.set_yticks(ticks,[f'{v:g}' for v in ticks]);ax.yaxis.set_minor_formatter(NullFormatter())
        allvals=mb[mb.t_s.between(135,165)][metric]
        assert allvals.min()>=ylim[0] and allvals.max()<=ylim[1],(metric,'data clipped')
        ax.set_xlim(135,165);ax.set_xticks([135,145,155,165]);ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',color='.88',lw=.4)
        ax.text(.04,.95,f'({chr(97+row*4+col)})',transform=ax.transAxes,va='top',fontsize=8)
        if row==0:ax.set_title(b)
        if col==0:ax.set_ylabel(ylabel)
        else:ax.tick_params(labelleft=False)
        if row==2:ax.set_xlabel('Time (s)')
fig.legend(*axs[0,0].get_legend_handles_labels(),loc='upper center',bbox_to_anchor=(.54,.995),ncol=2,frameon=False)
fig.canvas.draw();renderer=fig.canvas.get_renderer()
for ax in axs.flat:
    for tx in [ax.xaxis.label,ax.yaxis.label,ax.title,*ax.get_xticklabels(),*ax.get_yticklabels()]:
        if tx.get_visible() and tx.get_text():
            box=tx.get_window_extent(renderer);assert box.x0>=0 and box.y0>=0 and box.x1<=fig.bbox.x1+1 and box.y1<=fig.bbox.y1+1
fig.savefig(OUT/'F01_R5_POLE_COV_NEES_IEEE.pdf');fig.savefig(OUT/'F01_R5_POLE_COV_NEES_IEEE.png',dpi=600);plt.close(fig)
im=Image.open(OUT/'F01_R5_POLE_COV_NEES_IEEE.png');im.thumbnail((1400,1400));im.save(OUT/'QA_preview.png')

def pair(b,key,fmt='.3f'):
    q=sm[sm.bias==b].set_index('observer');return f'{q.loc["SourceFFD",key]:{fmt}} → {q.loc["LUT",key]:{fmt}}'
text='''# 사행 경로에서 LUT 교체 후 pose NEES가 커진 원인

질문 ID: `DLP-R5-LUT-NEES-CAUSE-20261102`. 원 실행: `DLP-ANCHORB-LUT-OBSERVER-SWAP-20261102`. 역할: AUDITOR 자기 검사. 기존 입력·결과를 읽고 관측함수를 같은 prior에서 평가했으며, 필터 재실행·모델 수정·보정값 재학습·원고 수정은 하지 않았다. 기존 sparse recovered runtime의 파일 해시를 실행 식별자로 사용한다. 지침과 소스의 해시는 이 폴더 `CONTRACT.json` 및 부모 계약에 기록했다.

## 결론

**직접적인 원인은 앵커 바로 아래를 지나는 구간의 LUT 위치 Jacobian 급증과, 그 Jacobian을 사용한 EKF의 위치 공분산 과도 축소다.** 이때 실제 위치 오차가 함께 줄지 않았고, 이후 위치–heading 상관 구조까지 오차와 맞지 않게 되어 3차원 pose NEES가 크게 증가했다. 전체 heading RMSE는 별도의 주변 오차 지표이므로 동시에 감소할 수 있다.

네 bias 모두 MB_VAR의 수용 mask가 SourceFFD와 완전히 같았다. gate 변경이나 관측 거부 증가는 이 차이의 원인이 아니다. 원 LUT의 극점 근처 동작이 원인이라는 근거는 저장된 시간 기록, 같은 prior에서의 h/H 대조, 같은 prior·R에서 H만 바꾼 단일 공분산 갱신 검산, 극점 접근 관측함수 평가가 일치한다는 데 있다. 단일 갱신 검산은 재귀 필터 반사실 실험이 아니며, 수정 후 전체 성능은 검증하지 않았다.

## 네 bias의 실제 오차와 NEES

각 칸은 SourceFFD → LUT. R5의 t≥30 s 모든 1,265시점이며 관측 거부 시점도 포함한다. heading은 래핑한 각도 RMSE, XY는 2차원 위치 RMSE다.

| bias | heading RMSE (°) | XY RMSE (cm) | heading NEES | XY NEES | pose NEES |
|---|---:|---:|---:|---:|---:|
'''
for b in A.BIASES:text+='| '+b+' | '+' | '.join(pair(b,k) for k in ['heading_rmse_deg','xy_rmse_cm','nees_heading','nees_xy','nees_pose'])+' |\n'
text+='''
heading NEES는 방향각 오차와 Pψψ만 사용한다. XY NEES는 x·y 오차와 2×2 위치 공분산, pose NEES는 x·y·ψ 오차와 교차 공분산까지 포함한 3×3 공분산을 사용한다. 자이로 bias는 이 NEES에 포함하지 않는다. 전체 heading NEES 증가만으로 pose NEES 증가를 설명할 수 없다.

## 약 141초에서 실제로 생긴 일 — L1

141.0 s에서 LUT의 y 표준편차는 직전 3.308 cm에서 0.437 cm로 줄었고, 141.2 s에는 0.128 cm가 되었다. 141.2 s 실제 y 오차는 3.603 cm였다. 예측한 표준편차의 약 28배 오차가 남은 상태다. SourceFFD는 같은 시점 y 오차 −0.727 cm, y 표준편차 5.052 cm였다. 부호는 truth−estimate다.

| 141.2 s, L1 MB_VAR | SourceFFD의 실제 경로 | LUT의 실제 경로 |
|---|---:|---:|
| prior 수평 앵커 거리 (cm) | 4.719 | 1.605 |
| prior 수직축 각도 (°) | 1.229 | 0.418 |
| 위치 Jacobian 크기 (1/m) | 0.03394 | 36.30865 |
| heading Jacobian (1/rad) | 0.21953 | 0.64740 |
| posterior σy (cm) | 5.052 | 0.128 |
| y 오차 (cm) | −0.727 | 3.603 |
| heading 오차 (°) | 0.118 | −0.369 |
| XY NEES | 6.935 | 804.509 |
| pose NEES | 6.960 | 816.779 |
| NIS | 0.01442 | 0.07685 |
| gate 수용 | 수용 | 수용 |

이 표의 Jacobian은 각 필터의 실제 prior에서 계산한 값이므로 궤적 차이도 포함한다. 이를 분리하기 위해 같은 prior에서 양쪽 함수를 계산했다. **LUT prior를 고정하면 위치 Jacobian 크기는 SourceFFD 약 0.02761/m 대 LUT 36.30865/m**로 약 1,315배 차이가 난다. SourceFFD prior를 고정해도 SourceFFD 약 0.03394/m 대 LUT 약 24.78/m다. 따라서 이 차이는 추정 위치 차이만으로 생긴 것이 아니다.

같은 L1 LUT prior·prior 공분산·R에서 H만 바꾼 단일 갱신 계산 결과, 141.0 s의 Py 축소 비율은 LUT H 0.01732 대 SourceFFD H 0.99992였다. 141.2 s에는 각각 0.08414 대 0.999999였다. 즉 LUT H로 인해 해당 갱신에서 y 분산이 각각 약 98.3%, 91.6% 줄었다. 저장된 posterior는 원 Joseph 갱신식과 일치한다. 이 검산은 관측값 h나 평균 보정의 재학습 없이 공분산 계산 경로를 분리한다.

141.2 s 이후 정상 크기 Jacobian으로 돌아와도 공분산은 이미 축소된 상태여서 NEES가 바로 회복되지 않는다. L1에서는 141.4≤t<151.2 s의 49시점이 전체 pose NEES 합의 약 57.8%를 차지한다. 이는 표본 1개만의 집계 이상이 아니다.

## LUT의 극점 접근 동작

원 LUT는 θ=0°와 2° 사이에서도 방위각 φtx·φrx에 따라 s를 보간한다. θ는 수직축에서의 각도이고, φtx·φrx는 송신·수신 로컬 방위각이다. 수평 앵커 거리를 ρ라 하면 adapter에서 방위각의 위치 미분은 1/ρ 크기로 증가한다. 극점에서는 방위각이 유일하지 않으므로, 수평 위치가 수직축으로 접근할 때 s의 극한이 접근 방위각에 따라 달라지면 위치 Jacobian이 크게 증가할 수 있다.

실제 L1의 141.2 s prior heading을 고정하고, 같은 높이에서 앵커 둘레 72방향을 평가했다. 이것은 저장된 관측함수의 오프라인 극한 동작 검사이며 새로운 주행/RT 시뮬레이션이 아니다.

| 수평 거리 ρ | 같은 heading에서 SourceFFD s의 방향별 범위 | LUT s의 방향별 범위 | 최대 위치 Jacobian SourceFFD / LUT (1/m) |
|---|---:|---:|---:|
'''
for r in rows:
    text+=f'| {r["rho_m"]:.5f} m | {r["s_Source_range"]:.6g} | {r["s_LUT_range"]:.6g} | {r["max_J_Source"]:.4g} / {r["max_J_LUT"]:.6g} |\n'
text+='''
거리를 0에 가깝게 해도 LUT s의 방향별 범위는 사라지지 않고 약 1.95까지 남는다. 반면 SourceFFD의 범위는 0으로 감소한다. 원 LUT와 현재 adapter를 함께 사용한 관측함수에 수직축 근처의 접근 방향 의존성이 있음을 직접 확인한 것이다. 이 기록만으로 원 테이블 생성 단계의 어느 연산이 그 불일치를 만들었는지까지 확정하지는 않는다.

SourceFFD는 0.1–0.5°에서 복소 전계의 Cartesian cap을 적용한다. LUT의 큰 차이는 SourceFFD prior θ≈1.23°에서도 확인되어 cap 사용 여부만으로 설명되지 않는다. LUT와 SourceFFD의 거리 처리·복소 전계/스칼라 보간 차이는 배경 차이로 남지만, 이번 급격한 NEES 상승의 직접 경로는 극점 근처 H와 공분산 갱신으로 특정된다. 큰 LUT Jacobian은 중앙 차분과 최대 절대차 약 6.17×10⁻⁸로 일치했다. 현재 adapter의 미분 계산 부호나 단위 오류로 큰 H가 발생한 증거는 없다.

## Gate와 분산표

네 bias 모두 SourceFFD·LUT MB_VAR는 총 1,415개 중 1,409개, 평가 구간 1,265개 중 1,259개를 수용했다. 수용 mask 불일치도 0개다. 141.0/141.2 s의 L1 LUT NIS는 0.02421/0.07685로 gate 9.21034보다 작았다. gate는 관측 혁신 ν와 혁신 공분산 S로 NIS=νᵀS⁻¹ν를 평가하며 상태 참오차는 보지 않는다. 큰 H는 S=HP⁻Hᵀ+R도 키울 수 있으므로 작은 NIS가 posterior 공분산의 정확성을 보증하지 않는다.

분산 규칙은 기존과 같은 이전 posterior 수평 거리 조회였다. Rss의 SourceFFD/LUT 최대 절대차는 bias별 약 4.1×10⁻⁵–5.3×10⁻⁵이고 평균은 약 0.03894로 비슷하다. L1 141.2 s의 Rss는 SourceFFD 0.00313327 대 LUT 0.00312950 수준이다. 같은 prior와 R를 고정하고 H만 바꾼 검산에서 급격한 분산 축소가 재현되어, R 변화가 이 급증을 설명하는 데 필요하지 않다.

## 오차와 공분산을 분리한 진단

동일 시점의 LUT 오차 eL에 SourceFFD 공분산 PS를 대입한 NEES를 계산했다. 이는 서로 다른 추정기의 오차·공분산을 조합한 오프라인 대수 진단이며 유효한 새 필터 결과가 아니다.

| bias | 실제 SourceFFD: eS, PS | LUT 오차·SourceFFD 공분산: eL, PS | SourceFFD 오차·LUT 공분산: eS, PL | 실제 LUT: eL, PL |
|---|---:|---:|---:|---:|
'''
for _,r in cm.iterrows():text+='| '+r['bias']+' | '+' | '.join(f'{r[k]:.3f}' for k in ['NEES_eS_PS','NEES_eL_PS','NEES_eS_PL','NEES_eL_PL'])+' |\n'
text+='''
L1의 LUT 오차를 그대로 두어도 SourceFFD 공분산을 사용하면 평균 pose NEES는 44.466에서 3.284로 작아진다. 오차 크기만의 변화로는 원래 증가량이 설명되지 않으며 공분산의 크기·방향·교차상관 불일치가 중요함을 보여준다. 두 변화에는 상호작용이 있으므로 이 대입표로 유일한 기여율을 주장하지 않는다.

pose NEES는 XY NEES와 단순 heading NEES의 합이 아니다. 정확히는 XY NEES에 위치를 조건으로 한 heading 잔차의 정규화 제곱을 더한 값이다. L1은 SourceFFD 2.037+0.360=2.397 대 LUT 6.928+37.538=44.466이다. 위치를 조건으로 한다는 것은 참값으로 필터를 보정했다는 뜻이 아니라 joint Gaussian의 Schur 보완 분해다. 조건부 잔차와 분산은 교차 공분산까지 포함한다. 전체 heading 오차의 제곱평균이 작아져도 이 항은 커질 수 있다.

## 그림과 확인 범위

![[03_Research/EKF/2026-11-01 논문 초안/figures/lut_observer_swap_20261102/diagnosis_R5_NEES/F01_R5_POLE_COV_NEES_IEEE.png|1000]]

그림. 사행 경로 MB_VAR의 네 bias 조건. 위부터 위치 Jacobian 크기, y 표준편차, 3차원 pose NEES다. y축은 로그 척도이며 열마다 같은 범위를 쓴다. 세로선은 141.2 s, NEES의 수평선은 차원 기준값 3이며 독립 실험 기반 검정 경계가 아니다. Times New Roman, 폭 7.16 inch, PDF 및 600 dpi PNG로 저장했다.

원 h·저장 J·HPH·S·NIS gate와 Joseph posterior를 대조했고 모두 일치했다. NEES를 XY+조건부 heading 항으로 분해한 값이 직접 선형계 풀이와 일치했다. 진단 전후 입력 SHA256이 일치했다. 네 bias와 세 구성 모두를 검사했으며 여기서는 사용자가 질문한 MB_VAR의 큰 증가를 중심으로 설명했다. 전체 24행 요약은 `SUMMARY_24.csv`, 시점별 오차·공분산·Jacobian·gate는 `PACKET_DIAGNOSTICS.csv.gz`, 같은 prior 함수 대조는 각 `JACOBIAN_SAME_PRIOR.npz`에 있다.

판정: **질문한 현상의 원인 설명은 이 frozen 실행 범위에서 근거가 충분하다. 관측모델 결함 수정·수정 후 재검증·채택은 미완료다.** 같은 작성자의 자체 검사이며 독립 감사가 아니다. 기존 수치와 원 LUT를 보존한다. 다음 수정 후보는 극점에서 접근 방향에 독립적인 LUT 또는 Cartesian 모델을 구성하고 해당 H와 공분산을 재검증하는 것이다. 이번 요청에서는 수정하거나 재실행하지 않았다. 수정이 다른 구간 성능까지 개선할지는 아직 확인하지 않았다.
'''
text+='\n기호: s는 두 포트 전력의 정규화 차, ψ는 heading, H는 관측함수의 상태 Jacobian, P⁻는 갱신 전 상태 공분산, P는 갱신 후 공분산, R은 관측잡음 공분산, Rss는 R의 s 성분 분산, ν는 관측 혁신, S는 혁신 공분산이다. σy는 y 위치의 추정 표준편차이고, Py는 해당 분산 Pyy를 뜻한다. eS/eL은 SourceFFD/LUT의 truth−estimate pose 오차, PS/PL은 각 방법의 pose 공분산이다. 각도 오차·미분의 내부 단위는 rad이며 표시는 °로 변환했다.\n'
(OUT/'00 원인 진단.md').write_text(text,encoding='utf-8')
locked=json.loads((OUT/'CONTRACT.json').read_text())['input_hashes']
assert all(A.sha(p)==h for p,h in locked.items())
(OUT/'FIGURE_QA.json').write_text(json.dumps(dict(width_inches=7.16,height_inches=5.8,png_dpi=600,pdf_fonttype=42,font='Times New Roman',all_text_within_canvas=True,source='PACKET_DIAGNOSTICS.csv.gz; stage PROPOSED_MB_VAR, 135<=t<=165'),indent=2),encoding='utf-8')
hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file() and p.name!='OUTPUT_HASHES.json'}
(OUT/'OUTPUT_HASHES.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2),encoding='utf-8')
print('REPORT_AND_IEEE_FIGURE_DONE')
