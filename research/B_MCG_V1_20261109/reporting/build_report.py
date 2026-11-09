"""Build a Korean scientific review from immutable B-MCG numerical evidence.

This is reporting code only. It never executes or changes the filter, a policy,
an input asset, or an experiment. Missing final evidence is a hard error.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import html
import json
import math
from pathlib import Path
import re

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether

BLUE='#245b91'; GOLD='#bc8628'; ORANGE='#b85c37'; DARK='#233647'; GRAY='#687887'; LIGHT='#edf3f7'
ROUTES=('R2','R4','R5')
STRATA=('B_FROZEN','B_BIAS_COV')
MODES=('OFF','OBSERVE_ONLY','ACTIVE_R','ACTIVE_S','ACTIVE_RS','DR_ONLY','NAIVE_YAW_CLIP')
CODE_SHA='e3ddc9fa4371d899a08a2a873d2ee5cf32074a01'
GITHUB='https://github.com/myoungsunk/sionna-resimulation'

def read(p): return json.loads(Path(p).read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def f(x,n=4): return '검증 불가' if x is None else f'{x:,.{n}f}'

def setup_fonts(root):
    regular=root/'tmp/report_fonts/NanumGothic-Regular.ttf'
    bold=root/'tmp/report_fonts/NanumGothic-Bold.ttf'
    for p in (regular,bold):
        if not p.is_file(): raise FileNotFoundError(p)
        font_manager.fontManager.addfont(str(p))
    plt.rcParams.update({'font.family':['NanumGothic','DejaVu Sans'],'font.size':10,'axes.unicode_minus':False,
        'axes.spines.top':False,'axes.spines.right':False,'axes.labelcolor':DARK,
        'text.color':DARK,'xtick.color':DARK,'ytick.color':DARK,'axes.edgecolor':'#a4b0bb',
        'grid.color':'#dce3e9','figure.facecolor':'white','savefig.facecolor':'white'})
    pdfmetrics.registerFont(TTFont('Korean',str(regular)))
    pdfmetrics.registerFont(TTFont('Korean-Bold',str(bold)))
    pdfmetrics.registerFont(TTFont('Symbols','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
    pdfmetrics.registerFontFamily('Korean',normal='Korean',bold='Korean-Bold',italic='Korean',boldItalic='Korean-Bold')

def savefig(fig,out,name):
    fig.savefig(out/(name+'.png'),dpi=185,bbox_inches='tight')
    fig.savefig(out/(name+'.svg'),bbox_inches='tight')
    plt.close(fig)

def make_figures(root,final=None):
    r=root/'results'; out=root/'deliverables/figures';out.mkdir(parents=True,exist_ok=True)
    data=read(r/'bias_feedback/RESULTS.json')
    rows=[]
    for route in ROUTES:
        d=next(v for v in data['cases'] if v['route']==route and v['arm']=='B_FROZEN')
        c=next(v for v in data['cases'] if v['route']==route and v['arm']=='B_BIAS_COV')
        key='endpoint_relative_heading_error_deg'
        rows.append([route,d['windows']['5']['variants']['ZERO_BG'][key]['rmse'],
            d['windows']['5']['variants']['ARCHIVED_PRE_RF_BG'][key]['rmse'],
            c['windows']['5']['variants']['ARCHIVED_PRE_RF_BG'][key]['rmse'],
            d['windows']['5']['n_overlapping_windows']])
    fig,ax=plt.subplots(figsize=(9.3,3.7));xs=np.arange(3);width=.23
    for j,(label,color) in enumerate([('원시 gyro, bg=0',DARK),('B_FROZEN 추정 bg',BLUE),('기존 보정 B 추정 bg',GOLD)]):
        vals=[v[j+1] for v in rows];bars=ax.bar(xs+(j-1)*width,vals,width,color=color,label=label)
        ax.bar_label(bars,labels=[f'{v:.4f}' for v in vals],padding=3,fontsize=9)
    ax.set_xticks(xs,[f'{q[0]}\nn={q[4]} 중첩 창' for q in rows]);ax.set_ylabel('5초 상대 Heading 오차 RMSE (도)')
    ax.set_ylim(0,.31);ax.legend(ncol=3,loc='upper center',bbox_to_anchor=(.5,1.16),frameon=False)
    ax.yaxis.grid(True);ax.set_axisbelow(True);savefig(fig,out,'01_motion_reference')
    pooled=read(r/'bias_causal/RESULTS.json')['pooled']
    arms=['RAW_B','IDEAL_OBSERVER','R_RESIDUAL_ONLY','S_RESIDUAL_ONLY'];labels=['원래 B','모델 이상 관측','range 잔차만','s 잔차만']
    fig,axes=plt.subplots(1,3,figsize=(10,3.6))
    for ax,key,title in zip(axes,['heading_rmse_deg','xy_rmse_cm','bg_rmse_deg_s'],['Heading RMSE (도)','위치 RMSE (cm)','추정 bg RMSE (도/초)']):
        vals=[pooled[a][key] for a in arms];bars=ax.bar(np.arange(4),vals,color=[BLUE,DARK,GOLD,ORANGE])
        ax.set_xticks(np.arange(4),labels,rotation=25,ha='right');ax.set_title(title,fontsize=11)
        ax.bar_label(bars,labels=[f'{v:.3f}' for v in vals],padding=3,fontsize=9)
        ax.set_ylim(0,max(vals)*1.2);ax.yaxis.grid(True);ax.set_axisbelow(True)
    fig.tight_layout();savefig(fig,out,'02_residual_causal')
    bal=read(r/'recovery_cause/UPDATE_BALANCE.json');arms={x['arm']:x for x in bal['arms']};order=['FULL','TAU3','TAU2'];labs=['FULL','τ=3','τ=2']
    fig,axes=plt.subplots(1,2,figsize=(10,3.7),gridspec_kw={'width_ratios':[1.35,1]});xs=np.arange(3)
    for j,(key,label,color) in enumerate([('range_heading_correction_deg','range 항',BLUE),('s_heading_correction_deg','s 항',GOLD)]):
        vals=[arms[a][key] for a in order];axes[0].bar(xs+(j-.5)*.26,vals,.26,label=label,color=color)
    axes[0].set_xticks(xs,labs);axes[0].set_ylabel('Heading 보정 (도)');axes[0].set_ylim(-.065,.065)
    axes[0].axhline(0,color=DARK,lw=.8);axes[0].legend(ncol=2,frameon=False,loc='upper center',bbox_to_anchor=(.5,1.18))
    vals=[arms[a]['net_heading_correction_deg'] for a in order];bars=axes[1].bar(xs,vals,color=[DARK,GOLD,ORANGE])
    axes[1].bar_label(bars,labels=[f'{v:+.6f}' for v in vals],padding=3,fontsize=10)
    axes[1].axhline(0,color=DARK,lw=.8);axes[1].set_xticks(xs,labs);axes[1].set_ylabel('range + s 순보정 (도)')
    axes[1].set_ylim(-.0062,.0022);axes[1].set_title('순보정만 별도 확대',fontsize=11)
    fig.tight_layout();savefig(fig,out,'03_recovery_balance')
    hz=read(r/'horizons/RESULTS.json');event=next(e for c in hz['cases'] if c['route']=='R2' for e in c['events'] if e['k']==484)
    rf=event['RF'];z=np.load(r/'horizons/R2_K484_BRANCHES.npz');raw=z['event_raw_CIR'];clean=z['event_clean_CIR'];tap=rf['B_tap']
    lo=max(0,tap-6);hi=min(len(raw),tap+17);ticks=np.arange(lo,hi);pw=max(float(abs(raw[lo:hi]).max()**2),float(abs(clean[lo:hi]).max()**2))
    fig,axes=plt.subplots(1,3,figsize=(10.3,3.7),gridspec_kw={'width_ratios':[1,1,1.03]})
    for port in (0,1):
        ax=axes[port];ax.plot(ticks,abs(raw[lo:hi,port])**2/pw,color=BLUE,marker='o',ms=3,label='raw CIR')
        ax.plot(ticks,abs(clean[lo:hi,port])**2/pw,color=DARK,ls='--',label='clean CIR')
        ax.axvline(tap,color=ORANGE,lw=1,ls=':');ax.set_ylim(0,1.08);ax.set_xlabel('tap');ax.set_title(f'수신 포트 {port+1}')
        ax.set_ylabel('공통 최대 전력으로 정규화');ax.legend(frameon=False,fontsize=9)
    vals=[rf['B_s'],rf['clean_B_s'],rf['ideal_s_htruth_plus_muMB']]
    bars=axes[2].bar([0,1,2],vals,color=[BLUE,DARK,GOLD]);axes[2].bar_label(bars,labels=[f'{v:.4f}' for v in vals],padding=3,fontsize=9)
    axes[2].set_xticks([0,1,2],['B','clean B','모델 h+μ'],rotation=20);axes[2].set_ylim(-.85,0);axes[2].set_ylabel('s (무차원)');axes[2].set_title('동일 B tap = 57')
    fig.tight_layout();savefig(fig,out,'04_cir_same_tap')
    if final:
        groups={(g['stratum'],g['mode']):g for g in final['groups']}
        fig,axes=plt.subplots(2,2,figsize=(10,7.1)); modes=['OFF','ACTIVE_R','ACTIVE_S','ACTIVE_RS','DR_ONLY','NAIVE_YAW_CLIP'];labels=['OFF','R','S','RS','DR','단순 문턱']
        for row,stratum in enumerate(STRATA):
            for col,(key,unit) in enumerate([('heading_rmse_deg','Heading RMSE (도)'),('xy_rmse_cm','위치 RMSE (cm)')]):
                ax=axes[row,col];vals=[groups[stratum,m]['pooled']['metrics'][key] for m in modes]
                bars=ax.bar(np.arange(6),vals,color=[DARK,BLUE,BLUE,BLUE,GOLD,ORANGE]);ax.bar_label(bars,labels=[f'{v:.3f}' for v in vals],padding=3,fontsize=9)
                ax.set_xticks(np.arange(6),labels);ax.set_title(stratum+' / '+unit,fontsize=10);ax.set_ylim(0,max(vals)*1.23);ax.yaxis.grid(True);ax.set_axisbelow(True)
        fig.tight_layout();savefig(fig,out,'05_recursive_comparison')
    return rows

class Report:
    def __init__(self,out):
        self.out=out;self.story=[];self.md=[]
        self.styles={
            'title':ParagraphStyle('title',fontName='Korean-Bold',fontSize=25,leading=35,textColor=colors.HexColor(DARK),spaceAfter=18,wordWrap='CJK'),
            'h1':ParagraphStyle('h1',fontName='Korean-Bold',fontSize=18,leading=25,textColor=colors.HexColor(DARK),spaceAfter=13,keepWithNext=True,wordWrap='CJK'),
            'h2':ParagraphStyle('h2',fontName='Korean-Bold',fontSize=12,leading=18,textColor=colors.HexColor(BLUE),spaceBefore=10,spaceAfter=7,keepWithNext=True,wordWrap='CJK'),
            'body':ParagraphStyle('body',fontName='Korean',fontSize=9.5,leading=15.5,textColor=colors.HexColor(DARK),spaceAfter=9,wordWrap='CJK'),
            'small':ParagraphStyle('small',fontName='Korean',fontSize=7.8,leading=11.6,textColor=colors.HexColor(GRAY),spaceAfter=7,wordWrap='CJK'),
            'cell':ParagraphStyle('cell',fontName='Korean',fontSize=8,leading=12,textColor=colors.HexColor(DARK),wordWrap='CJK'),
            'head':ParagraphStyle('head',fontName='Korean-Bold',fontSize=8,leading=12,textColor=colors.HexColor(DARK),wordWrap='CJK')}
    def rich(self,s):
        supported=pdfmetrics.getFont('Korean').face.charWidths
        raw=''.join(html.escape(c) if ord(c) in supported or c in '\n\r\t' else '<font name="Symbols">'+html.escape(c)+'</font>' for c in str(s))
        s=re.sub(r'\*\*(.*?)\*\*',r'<b>\1</b>',raw)
        return s.replace('\n','<br/>')
    def p(self,s,small=False):self.story.append(Paragraph(self.rich(s),self.styles['small' if small else 'body']));self.md.append(str(s)+'\n')
    def title(self,s):self.story.append(Paragraph(self.rich(s),self.styles['title']));self.md.append('# '+s+'\n')
    def h(self,s,level=1):self.story.append(Paragraph(self.rich(s),self.styles['h1' if level==1 else 'h2']));self.md.append('#'*(level+1)+' '+s+'\n')
    def page(self):self.story.append(PageBreak())
    def table(self,headers,rows,widths=None):
        dat=[[Paragraph(self.rich(v),self.styles['head' if i==0 else 'cell']) for v in row] for i,row in enumerate([headers]+rows)]
        total=A4[0]-88;ws=[v*total for v in widths] if widths else [total/len(headers)]*len(headers)
        tb=Table(dat,colWidths=ws,repeatRows=1,hAlign='LEFT');tb.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,0),colors.HexColor(LIGHT)),('VALIGN',(0,0),(-1,-1),'TOP'),
            ('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),
            ('LINEBELOW',(0,0),(-1,0),.7,colors.HexColor('#9bacbc')),('LINEBELOW',(0,1),(-1,-1),.3,colors.HexColor('#dce3e9'))]))
        self.story.extend([tb,Spacer(1,10)]);self.md+=['| '+' | '.join(map(str,headers))+' |','| '+' | '.join(['---']*len(headers))+' |']
        self.md+=['| '+' | '.join(str(x).replace('\n','<br>') for x in row)+' |' for row in rows];self.md.append('')
    def figure(self,root,name,caption,width=507):
        p=root/'deliverables/figures'/f'{name}.png';from PIL import Image as PILImage
        with PILImage.open(p) as im:w,h=im.size
        self.story.append(Image(str(p),width=width,height=width*h/w));self.p(caption,True)
        self.md.append(f'![{caption}](figures/{name}.svg)\n')
    def finish(self,path,mdpath):
        def page(c,d):
            c.setStrokeColor(colors.HexColor('#ced7df'));c.line(44,40,A4[0]-44,40)
            c.setFont('Korean',7);c.setFillColor(colors.HexColor(GRAY));c.drawString(44,28,'B-MCG v1 | 구현·검증·적대적 평가 | 2026-11-09')
            c.drawRightString(A4[0]-44,28,str(d.page))
        doc=SimpleDocTemplate(str(path),pagesize=A4,rightMargin=44,leftMargin=44,topMargin=43,bottomMargin=56,
            title='B-MCG v1 구현·검증·적대적 평가',author='Research review')
        doc.build(self.story,onFirstPage=page,onLaterPages=page)
        mdpath.write_text('\n'.join(self.md),encoding='utf-8')

def build(root):
    r=root/'results';final=read(r/'delivery_evaluation/RESULTS.json')
    if final['status']!='COMPLETED_NUMERICAL_DELIVERY_EVALUATION' or len(final['evaluated_records'])!=42:
        raise ValueError('Final 42-stream independent evaluation is required')
    ci=read(r/'github_ci/CI_REMOTE_AUDIT.json')
    if ci.get('status')!='PASS_REMOTE_REPLAY_AND_LOCAL_RECONCILIATION':raise ValueError('Final remote CI reconciliation is required')
    uncertainty=read(r/'uncertainty/RESULTS.json')
    assert uncertainty['n_records']==12
    rows=make_figures(root,final);groups={(g['stratum'],g['mode']):g for g in final['groups']}
    out=root/'output/pdf';out.mkdir(parents=True,exist_ok=True);mdout=root/'repo/research/B_MCG_V1_20261109/REPORT_KO.md'
    q=Report(out);q.title('B-MCG v1을 구현했지만\n현재 데이터에서는 채택하지 않습니다')
    q.p('구현 전 검증 · 잘못된 기준의 원인 추적 · 실제 재귀 비교 · 독립 적대적 평가',True)
    q.h('판정 요약',2)
    q.p('**연구용 구현과 재현 검증을 완료했습니다. 기본 정책은 OFF입니다.** B_FROZEN과 기존 보정 B_BIAS_COV에서 각각 R2·R4·R5를 평가했지만 사전 정책 선택은 6개 fold 모두 OFF였습니다. R2·R5는 엄격한 분할 후 필요한 학습 구간이 부족했고, R4는 평가 가능한 분할에서도 적격 후보가 없었습니다. [E07]')
    q.p('“잘못된 기준을 더 강하게 믿는” 실패는 실제 원본 모델을 이용한 구성 실험에서 재현했습니다. 오염된 과거 RF로 형성한 기준이 정상 복귀 관측을 의심하고, 유한 후보 탐색이 허용되는 정렬을 누락하며, range와 s의 반대 방향 Heading 보정이 감쇠 후 뒤집힐 수 있습니다. [E09-E11]')
    q.p('42개 로컬 재귀 실행(7개 모드 × 3개 루트 × 2개 보정 조건)을 독립 검산했습니다. GitHub Actions는 원본 기준선 6개와 OFF/고정 ACTIVE_RS 12개 실행의 수치·해시·게이트 검사를 통과했습니다. 실행 성공은 정책 채택을 뜻하지 않습니다. [E12-E13]')
    bm=groups['B_FROZEN','OFF']['pooled']['metrics'];am=groups['B_FROZEN','ACTIVE_RS']['pooled']['metrics']
    q.p(f"고정 ACTIVE_RS 진단의 주 분석에서는 Heading RMSE가 {bm['heading_rmse_deg']:.5f}→{am['heading_rmse_deg']:.5f}도, 위치 RMSE가 {bm['xy_rmse_cm']:.4f}→{am['xy_rmse_cm']:.4f}cm로 소폭 개선됐습니다. 이 수확을 숨기지 않되, 사전 선택 실패와 회복 반례·계산 비용을 넘어서는 채택 근거로 확대하지 않았습니다. [E12]")
    q.table(['항목','이번 결과','해석'],[
        ['원본 기준선','6개 조건 최대 재현 오차 0','원래 B를 정확히 재현'],
        ['단위검사','runtime 27개 + 정책 선택 5개 통과','경험적 유용성·허용집합 완전성의 증거와 구분'],
        ['사전 정책 선택','6개 fold 모두 OFF','채택 가능한 선택기 검증 실패/자료 부족'],
        ['원인 추적','RF→bg, 잘못된 history, 후보 누락, 보정항 상쇄','서로 다른 오염 경로를 분리'],
        ['운영 상태','기본 OFF, 병합 없음','고정 τ=2 ACTIVE는 연구 비교군']],[.21,.33,.46])
    q.p('자료 기준: R2 979행, R4 742행, R5 1,415행, 합계 3,136개 원 관측. 여러 비교군에서 재사용한 행 수를 독립 표본 수로 세지 않았습니다. 같은 corridor·B0·seed10이며 새 환경 또는 독립 noise seed에 대한 일반화는 검증하지 않았습니다.',True)
    q.p('구현 커밋: '+CODE_SHA+'\nActions: '+GITHUB+'/actions/runs/42600632209',True)

    q.page();q.h('1. 무엇을 고정했고 무엇을 비교했는가')
    q.p('B의 후보 확장·선정 방식과 B tap에서 계산한 range/s를 그대로 사용했습니다. K1/K2, 새 FP 재선택, 주 필터의 Q 변경은 없습니다. B_FROZEN은 기존 μ/R을 유지한 주 분석이고, B_BIAS_COV는 기존 경로별 bias/covariance 보정을 고정한 민감도 분석입니다. 이번에 보정기를 새로 학습하지 않았습니다. [E01,E12]')
    q.table(['층','고정/허용한 정보','역할'],[
        ['원시 입력','ds, gyro 증분 gy, dt, RF B 관측, 초기 x/P','운동 및 관측 입력'],
        ['운영 monitor','과거 관측·불변 anchor·SourceFFD·기존 μ/R','현재 관측은 history fit에서 제외'],
        ['평가 전용','truth, clean CIR, source h(truth)','오차·원인·반례 평가에만 사용'],
        ['legacy shadow','원래 raw B와 기존 보정','MCG가 rejection을 수용으로 바꾸지 못함'],
        ['실제 갱신','동일 prior에서 β별 R_eff를 정하고 한 번 Joseph 갱신','trial/actual 상태 및 공분산 분리']],[.18,.46,.36])
    q.p('Release NPZ 6개와 FFD bank 2개를 size/SHA로 검증했고, 저장된 calibration archive 9개 member와 원본 코드 계보도 대조했습니다. 원래 W0 재귀는 6개 조건에서 x/P/prior/H 등의 최대 오차가 0이었습니다. OFF/OBSERVE_ONLY adapter는 10⁻¹⁰ 이내 재현을 요구했습니다. [E01,E12-E13]')
    q.h('“odom heading”이라는 표현의 제한',2)
    q.p('현재 저장 입력에는 독립적인 좌·우 wheel encoder yaw가 없습니다. ds는 이동 거리, gy는 gyro 적분각입니다. 따라서 이 구현은 독립 wheel heading과 편파 heading의 두 센서를 비교하는 구조로 해석하면 안 됩니다. 기존 RF posterior에서 가져온 pose와 gyro bias도 운동 기준에 들어가므로 운동 기준 자체의 RF 계보를 추적해야 합니다. [E02]')
    q.h('분리한 기준선과 고정 비교군',2)
    q.p('OFF는 원래 B 재현, OBSERVE_ONLY는 monitor 계산만, ACTIVE_R/S/RS는 각각 range/s/양쪽 감쇠, DR_ONLY는 RF 갱신 제거입니다. NAIVE_YAW_CLIP이라는 CLI 이름은 출력 Heading 절단을 뜻하지 않습니다. 실제로는 가상 Heading 보정 크기 문턱(0.2도)을 넘으면 두 관측을 함께 β=0.25로 감쇠하는 단순 대조입니다. [E12]')

    q.page();q.h('2. 감쇠로 얻을 선택 여지가 있는가')
    op=read(r/'precheck_oracle/RESULTS.json')['pooled']['B_FROZEN'];cnt=op['accepted_action_vs_skip_counts']
    q.p('각 관측의 동일 prior/P/H/R에서 βr, βs ∈ {1, 0.25, 0}의 9개 action을 다시 계산했습니다. 원래 수용 관측만 운영 가능한 action으로 세고, 거절 시 가상 갱신은 별도 진단으로 분리했습니다. FULL의 x/P/K 재현 오차는 6개 조건 모두 0이었습니다. [E03]')
    q.table(['B_FROZEN 수용 관측의 FULL vs SKIP','개수'],[
        ['Heading·XY 모두 개선',cnt['full_benefits_both']],['두 축 모두 악화',cnt['full_harms_both']],
        ['Heading 개선·XY 악화',cnt['full_benefits_heading_harms_xy']],['Heading 악화·XY 개선',cnt['full_harms_heading_benefits_xy']],
        ['FULL보다 두 축을 함께 개선하는 action 존재',op['accepted_with_pareto_improving_action']]],[.75,.25])
    q.p('수용 3,125개 중 1,551개에는 두 축을 개선할 감쇠/제외 선택이 존재합니다. 다만 이 판단은 truth를 본 hindsight oracle입니다. 각 축별 최선 action이 다를 수 있고, 평균 MSE 잠재 감소는 Heading 2.630%, XY 1.752%였습니다. 이는 실제 선택기의 성능이나 전체 폐루프의 개선 상한이 아닙니다. [E03]')
    q.p('range를 항상 β=0.25로 낮추면 좋은 Heading 이득의 26.63%, XY 이득의 36.98%를 잃습니다. s를 항상 낮추면 두 축 평균도 악화됩니다. 따라서 “덜 믿으면 좋아진다”가 아니라, 언제 어느 관측을 줄일지 구분할 정보가 필요한 문제입니다. [E03]')
    q.h('CIR·s 오차와 갱신의 유용성은 다른 대상입니다',2)
    q.figure(root,'04_cir_same_tap','그림 1. R2 k484, t=96.8초. 두 포트와 raw/clean에 동일 전력 정규화를 적용. B/clean B/native tap이 모두 57인 사례. 사후 선택한 XY 개선 극값 사례로, 모집단 대표 사례가 아닙니다. [E04]')
    q.p('이 사건에서 raw B s=-0.705083, clean B s=-0.480970, μ를 포함한 모델 이상 관측 s=-0.439592였습니다. tap이 일치해도 s 왜곡이 남습니다. 동시에 해당 FULL 갱신은 동일 prior에서 XY를 개선했습니다. 큰 |s 잔차|만으로 갱신의 해로움을 결정할 수 없다는 사례입니다. clean CIR와 모델 이상 관측을 서로 대체하지 않았습니다. [E04]')

    q.page();q.h('3. 운동 기준도 RF에 의해 오염되었습니다')
    q.p('B0의 실제 gyro bias와 scale factor는 0입니다. 원래 generator의 seed10 잡음을 재생성해 gy를 정확히 재현했고, raw gyro와 truth 차분의 차이가 그 잡음과 일치함을 확인했습니다. 이 데이터에서 추정된 큰 bias를 하드웨어의 실제 bias로 설명할 수 없습니다. [E02]')
    q.figure(root,'01_motion_reference','그림 2. 같은 pre-RF anchor pose와 같은 raw controls에서 bg만 바꾼 5초 상대 Heading endpoint RMSE. 중첩 창의 기술 통계이며 독립 반복의 신뢰구간은 아닙니다. [E05]')
    q.table(['루트','bg=0 원시 적분','B 추정 bg 사용','기존 보정 B bg 사용'],[[v[0],f(v[1],5)+'°',f(v[2],5)+'°',f(v[3],5)+'°'] for v in rows],[.14,.28,.29,.29])
    q.p('전수 기록에서 다음 항등식을 검증했습니다: Δbg = K(bg,r)·νr + K(bg,s)·νs. 예측 단계는 bg를 그대로 유지했습니다. 따라서 RF 혁신이 bg 추정치에 들어간 뒤, 다음 운동 기준의 gyro 보정에 다시 쓰이는 피드백 경로가 존재합니다. 같은 anchor에서 5초 오차 차이는 정확히 -bg_anchor×5초였습니다. [E05]')
    q.p('R4 t=37.2초 anchor의 추정 bg는 약 0.129819도/초였습니다. 이후 5초 Heading에 미친 누적 bg 효과는 range 기여 +0.001044도, s 기여 -0.650136도였습니다. bg=0 상대 오차 -0.019946도가 기존 bg 적용 후 -0.669038도가 됐습니다. 이 사건에서는 s 경로가 지배적이지만 모든 루트에 일반화할 수 없습니다. [E05]')
    q.p('현재 B0에서 bg=0가 좋다는 결과를 실제 장치에서 bias를 항상 0으로 고정하라는 처방으로 바꾸지는 않았습니다. unknown hardware bias를 검증할 별도 데이터가 없기 때문입니다. 또한 ds 쪽 진단에는 truth의 Euler 적분과 필터 SE(2) 적분 차이도 있어, 모든 위치 차이를 wheel 잡음으로 부르지 않았습니다.',True)

    q.page();q.h('4. RF 잔차를 바꾸면 폐루프가 얼마나 달라지는가')
    pc=read(r/'bias_causal/RESULTS.json')['pooled']
    q.p('원래 SourceFFD 재귀를 다시 실행하고 관측 성분만 네 가지로 바꿨습니다. “모델 이상 관측”은 z=h(truth)+기존 μ입니다. 실제 clean CIR를 다시 검출한 값이 아니며, 모델·검출·잡음·보정 불일치를 함께 제거하는 진단입니다. 각 arm은 자기 shadow 및 자연 게이트를 사용하므로 결과에는 상태와 게이트의 상호작용도 포함됩니다. [E06]')
    q.figure(root,'02_residual_causal','그림 3. B_FROZEN 3개 루트 3,136행의 full recursive 관측 성분 개입. 막대는 RMSE이고 축별 단위가 다릅니다. [E06]')
    labels={'RAW_B':'원래 B','IDEAL_OBSERVER':'모델 이상 관측','R_RESIDUAL_ONLY':'range 잔차만 유지','S_RESIDUAL_ONLY':'s 잔차만 유지'}
    q.table(['관측 개입','Heading (도)','XY (cm)','bg (도/초)','수용 수'],[[labels[a],f(pc[a]['heading_rmse_deg'],4),f(pc[a]['xy_rmse_cm'],3),f(pc[a]['bg_rmse_deg_s'],5),pc[a]['accepted']] for a in labels],[.30,.18,.18,.19,.15])
    q.p('모델 이상 관측에서는 bg RMSE가 0.030511→0.004489도/초로 줄었습니다. RF 관측 잔차가 상태와 bg 오염에 관여한다는 강한 소스 수준 증거입니다. 다만 원인이 순수 다중경로 하나라고 분리한 실험은 아닙니다. R4에서는 s 잔차만 유지해도 bg 오염이 크게 남고, R2에서는 range 잔차만 유지한 쪽의 bg 오염이 더 컸습니다. [E06]')
    q.p('수용 관측 수는 원래 B 3,125개, 모델 이상 관측 3,110개입니다. 수용 수가 많거나 innovation이 작다는 이유만으로 위치·Heading이 정확하다고 판단할 수 없습니다. 이 개입은 가능한 구조적 개선 여지를 보여주지만, 그 이상 관측을 온라인에서 만들 방법을 제공하지는 않습니다. [E06]')
    q.h('즉시 좋아 보이는 action도 미래에는 달라졌습니다',2)
    q.p('사후 극값으로 고른 12개 사건에서 한 번의 action 뒤 1/5/10초를 재귀 전개했습니다. 288개 선택 비교 중 즉시 손실과 endpoint 손실의 개선 부호가 다른 경우가 80개였습니다. 사후 선택·중복 비교이므로 실패율로 일반화할 수 없지만, one-step 이득만으로 폐루프 채택을 정하면 안 된다는 반례를 제공합니다. [E04]')

    q.page();q.h('5. 사전 유용성 검증은 정책을 선택하지 못했습니다')
    q.p('5초 history에서 anchor dx/dy, yaw 정렬, 상수 bg의 네 nuisance를 제한된 범위 안에서 적합했습니다. 현재 RF와 미래 RF는 fit에 넣지 않았습니다. train/dev는 시간 순서로 나누고 15초 embargo를 두며, history 5초·future 10초의 support가 near-pose(0.25m·5도)로 겹치는 구간을 제외했습니다. heldout truth pose는 이 geometry splitter에만 미리 사용했으며, 이를 완전히 보지 않은 blind test라고 부르지 않습니다. [E07]')
    q.table(['heldout 루트','남은 train/dev','판정','이유'],[
        ['R2','298 / 267','OFF · 검증 불가','요구한 R4 train partition은 0'],
        ['R4','396 / 413','OFF · 적격 후보 없음','사전 조건을 함께 충족한 후보 0개'],
        ['R5','0 / 311','OFF · 검증 불가','train 전체가 0']],[.16,.20,.25,.39])
    q.p('후보는 ACTIVE_R/S/RS × τ∈{1.5,2,3,4}, β 최소값 0.25입니다. 순이득과 좋은 갱신 손실 5% 이하를 Heading·XY 각각 판단했습니다. B_FROZEN의 R4 fold에서 고정 RS τ=2는 train 396행 중 4개, dev 413행 중 1개만 감쇠했습니다. train의 Heading·XY 순감소율은 -0.0011483%, -0.0030150%였고 dev는 -0.0000367%, +0.0010562%였습니다. 작은 음수도 개선으로 바꾸지 않았습니다. [E07]')
    q.p('대표 RS τ=2의 좋은 이득 손실 예산은 통과했습니다. 감쇠 횟수는 적지만 선언한 “활동 존재” 조건도 충족했고, 실패한 것은 train/dev의 두 축 순이득 조건입니다. 반면 s 단독 후보는 모든 τ에서 train/dev의 실제 accepted update 감쇠가 0이었습니다. 기존 보정 B_BIAS_COV도 두 조건 × 3개 fold 전체 선택 결과에 포함되며 모두 OFF입니다. 다만 기존 보정 학습이 guard heldout과 nested하게 분리되지 않아 보조 민감도 조건입니다. [E07]')
    q.p('공통 정렬 진단에서 5초 support를 가진 3,061개 창은 선언한 분류상 모두 이동·회전 창이었습니다. 거의 무회전인 직선 또는 정지 창에서의 판별력을 현재 자료로 확인하지 못했습니다. 따라서 이 결과를 직선 주행에 대한 원래 아이디어 전체의 반증으로 쓰지 않습니다. [E08]')
    q.h('monitor가 판단을 내릴 수 있는 범위 자체가 작습니다',2)
    prof=[]
    for s in STRATA:
        for route in ROUTES:
            v=read(r/f'profiles_final/{s}/{route}.json');c=v['counts'];prof.append([s,route,c.get('PROFILE_READY',0),c.get('UNKNOWN',0),c.get('WARMUP',0)])
    q.table(['조건','루트','READY','UNKNOWN','준비 구간'],prof,[.34,.14,.17,.19,.16])
    q.p('READY는 “후보들 사이에서 현재 target을 검사할 수 있음”이라는 구현 상태입니다. 참 위치가 정확하거나 전체 허용집합을 충분히 덮었다는 보증이 아닙니다. UNKNOWN은 이번 연구에서 β=1 bypass하므로, UNKNOWN이 많아서 성능이 유지되는 현상을 보호 효과로 세지 않았습니다. [E07,E11]')

    q.page();q.h('6. 구현한 B-MCG v1의 정확한 경계')
    q.table(['개발 블록','구현 내용','통과시켜야 하는 불변식'],[
        ['입력·계보','원본 SHA, runtime whitelist, evaluator 분리','truth/clean/future가 운영 fit에 유입되지 않음'],
        ['운동 기준','창 시작 pre-RF anchor 불변; raw ds/gy를 재적분','창 안의 RF posterior를 중간 재주입하지 않음'],
        ['공통 정렬','dx/dy ±0.5m, yaw ±30도, bg ±0.2도/초','rotation이 Heading과 상대 XY를 함께 바꿈'],
        ['history profile','soft_l1, 다중 시작점, exact nonlinear 확인','현재 관측으로 history 허용집합을 만들지 않음'],
        ['target 점수','허용 후보의 채널별/공동 비정합성','경계·비정상 fit·누락 징후는 reason 있는 UNKNOWN'],
        ['가중치 adapter','R_eff의 PSD 대각 증가, β=0 행 제외','β=1 parity; off-diagonal 보존; Joseph PSD'],
        ['shadow/main','raw legacy shadow와 실제 main 재귀 분리','기존 rejection을 rescue하지 않음; 실제 갱신 한 번'],
        ['기록·평가','trial/actual, H/K/ν, x/P, 점수/β/latency/hash','최종 trace로 수치·성능·계보 독립 재계산']],[.19,.43,.38])
    q.p('주 창은 5초, 최초 최소 support는 anchor→현재 2초입니다. 5Hz 기준 5초 창에는 과거 RF 25개와 현재 controls가 들어가며, 현재 RF는 history fit에서 제외됩니다. 2초 조건은 과거 RF 10개에 해당합니다. 2/10초의 운동 오차 진단은 했지만, 전체 guard 정책의 2/10초 재귀 민감도 비교는 이번 결과에 포함하지 않았습니다. [E02,E12]')
    q.p('β>0일 때 R_eff = R_base + diag((1/βr - 1)·Rrr, (1/βs - 1)·Rss). β=0이면 해당 관측 행을 제거합니다. 이 정의는 기존 교차 공분산을 유지하고 추가분을 양의 준정부호로 만듭니다. β는 편향 존재확률이나 관측이 맞을 확률이 아닙니다. 이 수식만으로 전체 필터 공분산의 calibration이 보장되지 않습니다. [E12]')
    q.p('coherent한 절대 RF bias는 운동 모양과 양립할 수 있습니다. 따라서 COMPATIBLE/READY를 “정상 RF”라는 라벨로 쓰지 않습니다. 기본 OFF가 선택되어 있으며 ACTIVE_R/S/RS τ=2는 미리 정한 진단 역할로만 실행했습니다. 별도의 회복 hysteresis와 운영 승격 정책을 검증 완료한 제품 기능으로 주장하지 않습니다. [E10,E12]')
    q.p('ACTIVE_POLICY.enabled=false는 이번 연구의 기본 선택 기록입니다. 모든 active CLI 호출을 차단하는 production activation validator는 구현되지 않았습니다. 연구 비교를 위해 active CLI를 명시적으로 호출할 수 있으며, 이를 운영 활성화 허가로 해석하면 안 됩니다. [E14]',True)

    q.page();q.h('7. 잘못된 기준을 믿은 실패를 고정 조건에서 분리했습니다')
    q.p('원본 SourceFFD로 만든 R4 recovery episode에서 26개 coherent 왜곡 관측 뒤 50개 모델 이상 관측으로 복귀시켰습니다. 첫 복귀는 original k212, t=42.4초입니다. 이 때 현재 관측, main prior/P/H/ν/R, gate를 고정하고 monitor 이력 또는 anchor 하나만 바꿨습니다. 물리 clean CIR 실험이 아닌 모델 기반 구성 반례입니다. [E09]')
    q.table(['바꾼 조건','range score','s score','τ=2 결과'],[
        ['왜곡 history 유지','2.740753','3.026782','두 관측 감쇠'],
        ['과거 RF만 model-ideal','0.000219','0.009909','감쇠 소멸'],
        ['anchor pose만 truth','2.690228','3.032324','감쇠 유지'],
        ['anchor bg만 0','2.743066','3.063897','감쇠 유지']],[.42,.18,.18,.22])
    q.p('따라서 이 사건을 anchor 위치 또는 bg 하나의 오류로만 설명할 수 없습니다. 과거 RF 이력으로 형성된 profile 기준이 정상 복귀를 충돌로 판단하는 경로를 확인했습니다. 현재 관측을 history fit에 섞어 낮은 점수를 만드는 방식으로 이 문제를 숨기지 않았습니다. [E09]')
    q.figure(root,'03_recovery_balance','그림 4. 같은 prior에서 바뀐 joint Kalman gain의 range·s 기여를 각각 계산. 오른쪽은 순보정만 다른 척도로 확대. prior Heading 오차는 -2.678965도입니다. [E09]')
    q.table(['설정','range 보정 (도)','s 보정 (도)','순보정 (도)'],[
        ['FULL','-0.052355412','+0.053318685','+0.000963273'],
        ['τ=3','-0.052366069','+0.052395169','+0.000029100'],
        ['τ=2','-0.028353268','+0.023557217','-0.004796051']],[.15,.28,.28,.29])
    q.p('FULL의 작은 양의 순보정은 유익했습니다. τ=3은 그 Heading 제곱오차 개선의 96.98%를 잃었고, τ=2는 보정 방향을 뒤집어 skip보다 나빠졌습니다. FULL의 이득 대비 손실은 598.43%이며, 분모가 작은 유익 순보정이므로 100%를 넘을 수 있습니다. 실제 FULL 대비 손실 증가는 0.0308801도²입니다. [E09]')

    q.page();q.h('8. 수렴한 최적점도 허용집합 전체를 대표하지 못했습니다')
    q.p('R4 첫 복귀 사건의 runtime best history cost는 0.01078057999, 추가 bounded nonlinear 최적화는 0.01078047192였습니다. 차이는 약 1.08×10⁻⁷이므로, 이번 실패의 주원인을 best-fit 미수렴으로 돌릴 수 없습니다. [E11]')
    q.p('같은 nuisance bounds와 history slack 2.5 안에서 τ=3을 통과하는 실제 후보를 찾았습니다. history cost 2.51078047192, range/s score 각각 2.80356513, joint score 3.96483983입니다. runtime의 유한 후보 집합은 이 후보를 놓쳐 s score 3.02678153, joint score 4.26418733을 냈습니다. **허용집합 전체를 표현한다는 주장은 이 반례로 미통과입니다.** [E11]')
    q.p('τ=2에서는 이번 두 시작점 탐색이 호환 후보를 찾지 못했습니다. 이는 글로벌 불가능성 증명이 아닙니다. “어떤 허용 정렬로도 현재 관측을 설명할 수 없다”는 주장을 하려면 다른 수준의 탐색 또는 보증이 필요합니다. 작은 gradient와 작은 sampled target spread만으로 그 주장을 할 수 없습니다. [E11]')
    q.h('초기 수치 결함을 고쳤지만 구조적 문제가 남았습니다',2)
    q.p('초기 R5 반례에서는 fit 비용과 후보 누락을 찾아 exact refinement·target probe·validity 검사를 보강했습니다. 그 사건의 τ=3 오감쇠는 없어졌지만, 이후 R4 재귀 복귀에서 다른 허용 후보 누락을 발견했습니다. 정책 τ와 예산은 고정했고, 성공 결과가 나올 때까지 사후 threshold를 조정하지 않았습니다. [E10-E11]')
    q.h('회복 판정은 약속한 기준과 개별 위험을 나눴습니다',2)
    q.table(['회복 검증 항목','R4 / R5 결과','판정의 한계'],[
        ['Heading ≤1도, 연속 5회','9.6초 / 9.2초; OFF와 비율 1.0','선택 episode에서 ≤1.1 기준 통과'],
        ['XY ≤5cm 및 joint','OFF도 관측 종료 9.8초 안에 미회복','비율은 NOT_ESTIMABLE'],
        ['R4 clean 구간 이득 손실 τ2','Heading 0.306%, XY 0.637%','선언한 5% 구간 예산 통과'],
        ['R4 첫 정상 복귀 사건','τ3 유익 이득 96.98% 상실; τ2 방향 역전','평균 예산이 숨긴 개별 반례'],
        ['coherent source 대조 9개','wrong-current 3개·ideal return 3개·clean history 3개 모두 무감쇠','wrong-current 3개만 잘못된 현재 관측 사례']],[.36,.34,.30])
    q.p('그 중 잘못된 현재 RF를 유지한 R2 구성 사례는 guard와 legacy gate를 통과하면서 skip 대비 Heading 손실을 25.09051도², XY 손실을 0.0105941m² 늘렸습니다. 이 세 사례는 운동과 일관된 잘못된 절대 기준의 blind spot을 보이지만 실제 CIR에서의 발생빈도는 아닙니다. [E10]')
    q.p('단일 사건의 실패를 근거로 사후에 전체 회복시간 gate를 FAIL로 바꾸지 않았습니다. 반대로 구간 예산·Heading 회복시간 통과를 모든 정상 복귀 보호의 증명으로 확대하지도 않았습니다. 105개 선택 SourceFFD stress는 대부분 UNKNOWN 또는 무감쇠였고, 그 상태 자체가 유용성을 입증하지 않습니다. [E10-E11]')

    q.page();q.h('9. 실제 폐루프 비교 결과')
    q.p('모든 비교군은 자기 이전 posterior에서 다음 prior를 계산한 실제 재귀입니다. 보정값과 원래 shadow gate는 고정했습니다. 표의 RMSE는 루트별 RMSE의 단순 평균이 아니라 전체 행의 제곱오차를 모아 계산했습니다. ACTIVE 설정은 선택된 정책이 아니라 고정 τ=2 연구 대조입니다. [E12]')
    q.figure(root,'05_recursive_comparison','그림 5. 각 조건 3,136행. OBSERVE_ONLY는 OFF parity를 별도로 검증했고 막대 중복을 피하기 위해 생략했습니다. 단순 문턱=NAIVE_YAW_CLIP 비교군. 각 패널은 단위·범위가 다릅니다. [E12]')
    q.p('주 분석의 R/RS 개선은 R5에서 주로 나타났으며 R4는 소폭 악화됐습니다. 사전 선택 규칙을 사후 전체 평균에 맞추어 바꾸지 않았습니다. 보정 조건이 달라지면 결과도 달라지므로 두 기준선을 분리해 읽어야 합니다. [E12]')
    q.page();q.h('9.1 전체 비교군의 정확한 수치')
    table=[]
    for s in STRATA:
        for m in MODES:
            g=groups[s,m]['pooled'];v=g['metrics'];table.append([s.replace('B_BIAS_COV','보정 B').replace('B_FROZEN','고정 B'),m.replace('OBSERVE_ONLY','OBSERVE').replace('NAIVE_YAW_CLIP','단순 문턱'),f(v['heading_rmse_deg'],5),f(v['xy_rmse_cm'],4),g['actual_guard_damped_legacy_accepted']])
    q.table(['조건','모드','Heading (도)','XY (cm)','감쇠 수'],table,[.14,.28,.21,.21,.16])
    base=groups['B_FROZEN','OFF']['pooled']['metrics'];act=groups['B_FROZEN','ACTIVE_RS']['pooled']['metrics']
    q.p(f"주 분석의 고정 RS 진단에서 Heading RMSE 감소는 {100*(1-act['heading_rmse_deg']/base['heading_rmse_deg']):.3f}%, XY RMSE 감소는 {100*(1-act['xy_rmse_cm']/base['xy_rmse_cm']):.3f}%입니다. ACTIVE_R과 ACTIVE_RS의 결과가 같고 ACTIVE_S는 OFF와 같습니다. 이는 이번 작동이 s 선택기로서 효과를 보였다는 뜻이 아닙니다. range R을 바꾸어도 joint Kalman gain의 s 기여는 달라질 수 있습니다. [E12]")
    q.p('미세한 개선·악화는 이 고정 데이터의 기술 통계입니다. 정책을 heldout 결과에 맞춰 재선택하지 않았고, 독립 noise/scene에 대한 유의한 개선으로 표현하지 않았습니다.',True)
    q.h('단순 문턱 대조군의 평균 개선도 더 컸습니다',2)
    q.p('NAIVE 대조는 고정 B에서 Heading 5.8938%, XY 6.3944%의 RMSE 감소를 보여 복잡한 MCG보다 평균 개선이 컸습니다. 그러나 R5 Heading이 5.5085% 악화되어 루트별 5% 제한을 넘었고, 좋은 갱신 이득 손실도 Heading 24.9706%, XY 21.0419%로 5% 예산을 넘었습니다. 보정 B에서도 평균은 개선됐으나 R2 Heading +10.6144%, XY +5.8397%와 이득 손실 예산 위반이 남았습니다. [E12]')
    q.p('MCG 고정 B의 같은-prior 좋은 이득 손실은 Heading 0.01037%, XY 0.06078%로 훨씬 작았습니다. 이는 보존과 평균 개선 사이의 실제 tradeoff입니다. 다만 복잡한 monitor가 총 오차·계산량에서 단순 대조보다 우월하다는 증거는 아닙니다. NAIVE는 odom-편파 변화 일관성을 검사하지 않고 가상 보정각 크기만 사용하므로 원래 사용자 제안과 동일한 방법도 아닙니다. [E12]')

    q.page();q.h('10. 루트별 보호와 불확실도·비용')
    recs=final['evaluated_records'];rt=[]
    for s in STRATA:
        for route in ROUTES:
            for m in ('OFF','ACTIVE_RS'):
                v=next(v for v in recs if v['stratum']==s and v['route']==route and v['mode']==m)
                mm=v['metrics'];rt.append([s.replace('B_BIAS_COV','보정 B').replace('B_FROZEN','고정 B'),route,m,f(mm['heading_rmse_deg'],4),f(mm['xy_rmse_cm'],3),f(100*mm['pose95_coverage'],2)+'%'])
    q.table(['조건','루트','모드','Heading °','XY cm','pose95 포함률'],rt,[.14,.09,.20,.18,.17,.22])
    q.p('pose95 포함률은 3차원 pose 오차와 보고된 covariance로 계산한 empirical coverage입니다. 명목 95%와 다른 수치를 실제 95% 확률 보장으로 부르지 않았습니다. 기준선 자체가 과신 상태이므로, coverage의 3%p 악화 제한을 통과해도 충분히 보정된 localization이라는 뜻은 아닙니다. [E12]')
    lt=[]
    for s in STRATA:
        for m in ('OFF','OBSERVE_ONLY','ACTIVE_RS'):
            g=groups[s,m]['pooled'];lat=g['latency'];lt.append([s,m,f(lat['guard_ms_p50_p95_p99'][1],1),f(lat['latency_ms_p50_p95_p99'][2],1)])
    q.table(['조건','모드','guard p95 ms','전체 p99 ms'],lt,[.30,.28,.21,.21])
    q.p('사전 비용 기준은 guard p95 목표 50ms, 전체 p99 ≤200ms였습니다. 현재 로컬 active 실행은 두 비용 기준을 충족하지 못했습니다. 로컬 측정에는 동시 실행에 따른 host 경합이 포함되므로 이 수치를 제품 하드웨어 지연으로 일반화할 수 없습니다. 경합이 있다는 사유로 실측 미통과를 PASS 또는 미측정으로 바꾸지 않았습니다. GitHub의 별도 지연도 artifact에 보존했습니다. [E12-E13]')
    q.p('NAIVE 비교군도 진단 기록을 위해 사용하지 않는 profile 계산을 실행했습니다. 따라서 그 stream의 지연은 최소한의 단순 Heading 문턱 알고리즘 자체 비용이 아닙니다. OFF/DR_ONLY는 profile 계산을 우회합니다.',True)

    q.page();q.h('10.1 구간을 넓혀서 포함률을 만든 것인가')
    q.p('저장된 P를 사용해 명목 XY 95% 타원 면적과 Heading 95% 구간의 전체 폭을 독립 계산했습니다. 면적은 π·χ²(2,0.95)·√det(Pxy), Heading 폭은 2·1.959964·√Pψψ를 degree로 변환한 값입니다. Gaussian 근사로 보고한 구간의 크기이며, 실제 95% 보장이라는 뜻은 아닙니다. 기존 coverage와의 재계산 차이는 0이었습니다. [E15]')
    ut=[];et=[]
    for v in uncertainty['pooled']:
        s=v['stratum'].replace('B_BIAS_COV','보정 B').replace('B_FROZEN','고정 B');c=v['coverage'];z=v['size'];ep=v['outside_episodes']
        ut.append([s,v['mode'],f(100*c['xy95_coverage'],2)+'%',f(z['xy95_ellipse_area_m2']['mean'],6),f(100*c['heading95_coverage'],2)+'%',f(z['heading95_full_width_deg']['mean'],4)])
        et.append([s,v['mode'],f(ep['xy']['observed_elapsed_s_max'],1),f(ep['heading']['observed_elapsed_s_max'],1),f(ep['pose']['observed_elapsed_s_max'],1)])
    q.table(['조건','모드','XY 포함률','XY 평균 면적 m²','Heading 포함률','Heading 평균 폭 °'],ut,[.14,.18,.16,.18,.17,.17])
    q.p('고정 B의 평균 XY 타원 면적은 거의 같고 Heading 구간 폭은 약간 줄었는데 포함률은 소폭 높아졌습니다. 따라서 이번 작은 포함률 개선을 큰 공분산 팽창으로 설명할 수는 없습니다. 하지만 XY 포함률은 46.30%, pose 포함률은 47.58%에 그쳐 명목 95%와 거리가 큽니다. [E15]')
    q.p('기존 보정 B에서는 pooled XY 포함률이 50.38→48.09%, pose는 30.33→28.22%로 내려갔습니다. 특히 R5의 XY -5.0883%p, pose -4.6643%p가 루트별 3%p 악화 제한을 넘었습니다. pooled 평균만 보면 이 위반이 희석됩니다. [E12,E15]')
    q.h('연속 이탈은 짧은 독립 사건으로만 나타나지 않았습니다',2)
    q.table(['조건','모드','XY 최장 이탈 s','Heading 최장 이탈 s','pose 최장 이탈 s'],et,[.16,.20,.22,.22,.20])
    q.p('시간은 관측된 이탈 run의 t_last−t_first이며, 한 표본 run은 0초입니다. 별도 CSV에는 표본 수×0.2초의 nominal support도 병기하고 양끝 censoring을 기록했습니다. 루트 사이의 run은 연결하지 않았고, 여러 축·비교군의 episode를 독립 표본으로 세지 않았습니다. [E15]')
    q.p('이 값은 필터 오차와 보고한 covariance의 불일치가 이어진 시간입니다. 순수 RF 왜곡의 지속시간이나 gyro 잡음 상관시간, 10초 주기 재보정을 정당화하는 값으로 해석하지 않았습니다. [E15]')

    q.page();q.h('11. 개발 단위와 통과 기준으로 내린 평가')
    q.table(['개발 단위','통과 기준','판정'],[
        ['입력·원본 재현','8개 asset SHA/size 및 6개 기준선 ≤10⁻¹⁰','통과'],
        ['수치·누설 경계','27개 runtime 불변식 + 5개 선택 검사','통과 · 과학적 채택과 별개'],
        ['실제 재귀·행동 기록','42개 stream, 실제/가상·used row·Joseph·source lineage 검산','통과 [E12]'],
        ['운동 기준 계보','RF→bg 항등식 및 같은 anchor의 bg 개입','원인 확인'],
        ['정책 사전 유용성','두 축 순이득 >0, 이득 손실 ≤5%, 활동 존재','미입증 · 모든 fold OFF'],
        ['독립 분할 support','요구 train/dev 모든 partition에 데이터 존재','R2·R5 검증 불가'],
        ['허용 profile coverage','허용 현재 호환해를 놓치지 않음','미통과 · R4 positive witness'],
        ['복귀 시간 ≤1.1','baseline도 회복한 축에서 비율 측정','Heading 선택 사례 통과; XY/joint 검증 불가'],
        ['구간 이득 보존','clean 구간 좋은 이득 손실 ≤5%','선택 사례 통과; 개별 반례 존재'],
        ['일관된 절대 오염','정합성 통과를 정확성으로 오인하지 않음','blind spot 명시; 검출 해결 안 됨'],
        ['실시간 비용','guard p95 50ms 목표·total p99 ≤200ms','현재 active 실행 미통과; host 경합 포함'],
        ['독립 환경·잡음 전이','새 scene/seed와 분리된 학습·평가','미검증']],[.26,.47,.27])
    q.p('최종 기계 판정과 각 증거 파일은 DEVELOPMENT_UNITS.csv 및 RESULTS.json에 있습니다. 선택적 숫자가 좋아도 다른 필수 gate를 대체하지 않으며, missing/empty/censored를 0 또는 PASS로 바꾸지 않았습니다. [E12]')
    q.h('블루프린트 전체의 검증 완료를 주장하지 않는 항목',2)
    q.p('실제 정지 회전·직선 주행·독립 gyro bias/scale/ramp·센서 시간지연의 폭넓은 원본 주행 검증, 독립 wheel yaw, 새 환경/seed, 전체 guard의 2/10초 창 재귀 비교는 미완료입니다. 합성 fixture에서 검사한 API 성질을 해당 실제 주행 검증의 대체물로 세지 않았습니다. checkpoint는 상세 추적 보존 수단이며 모든 중단점의 완전한 재개 parity를 보증하는 운영 기능으로 승격하지 않았습니다. [E02,E14]')
    q.p('PARTIAL 결과 저장과 hash entry/exit 검사는 구현했습니다. 그러나 main/shadow/history 상태를 복원하는 checkpoint/resume, 재시작 시 SHA mismatch 거부, release threshold와 새 support·지속조건을 가진 회복 hysteresis는 미구현입니다. 따라서 “원래 블루프린트의 모든 기능 구현·검증 완료”가 아닌 “연구 핵심 경로의 구현·평가 완료”로 범위를 명시합니다. [E14]')

    q.page();q.h('12. 이 결과가 요구하는 다음 개발 단위')
    q.p('다음 단계는 τ를 더 찾는 일이 아닙니다. 이번 데이터에서 확인한 실패 경로에 맞추어 monitor의 기준, 허용집합 표현, 두 관측의 공동 행동을 분리해 검증해야 합니다. 아래는 이번에 구현·통과한 기능 목록이 아니라, v1을 다시 채택 검토하기 위한 개발 단위와 제안 통과 기준입니다.')
    q.table(['다음 단위','구체적인 추가 연산','제안하는 통과 증거'],[
        ['N1 기준의 RF 계보 관리','raw-control 상대 운동 기준과 RF 보정 bg의 계보·불확실성을 분리; bias 가설 집합 유지','B0뿐 아니라 실제 nonzero/ramp bias에서 기준 envelope 포함률·유해 개입을 함께 검증'],
        ['N2 history 허용집합의 target 탐색','history로 허용집합을 고정한 뒤 현재 residual의 constrained minimum 탐색; 보증 실패는 UNKNOWN','R4 k212의 τ3 witness를 포함; 경계·다중 mode·heldout 반례 모음에서 false conflict 검사'],
        ['N3 정상 복귀와 history 전환','이력의 변경점·가설 복수 유지·복귀 시 과거 오염의 영향 감소를 명시','복귀시간과 구간 이득 예산 외, 첫 복귀 tail loss·방향 역전을 별도 사전 지정 지표로 평가'],
        ['N4 joint action 평가','range/s 개별 잔차만이 아니라 joint K 변화와 보정항 상쇄를 기록·비교','같은 prior의 두 축 손익, 1/5/10초 자체 재귀, 이득 보존 예산을 모두 통과'],
        ['N5 독립적인 정보·데이터','wheel yaw 등 별도 motion cue 또는 환경 조건; scene/seed/공간 support 확장','nested calibration과 공통 pose purge 후 모든 fold가 평가 가능; 새 seed/scene에서 고정 정책 검증'],
        ['N6 계산 비용','target 탐색의 비용 상한·캐시·bounded iteration과 정확성 tradeoff','동일 hardware 단독 실행에서 p99≤200ms; 근사로 잃는 feasible coverage도 함께 보고']],[.19,.42,.39])
    q.p('특히 N2의 현재 residual 최소화는 현재를 history loss에 넣는 것과 다릅니다. 현재를 보기 전에 허용집합을 고정한 뒤 그 안에서 현재와 양립하는 해가 존재하는지 검사하는 연산입니다. 이 연산의 추가 비용과 탐색 보증이 동시에 해결되어야 합니다. [E11]')
    q.p('운동과 완전히 일관된 절대 RF bias에는 운동 일관성만으로 답이 없습니다. 이 경우는 불확실성을 유지하거나 추가 정보가 필요합니다. 이 한계를 인정하면서 부분적으로 검출 가능한 오염을 구분하는 것이 다음 설계의 출발점입니다.')

    q.page();q.h('13. 재현·원격 실행·근거 파일')
    q.p('GitHub 연구 브랜치: analysis/b-mcg-v1-20261109. 실행한 코드 커밋은 '+CODE_SHA+'입니다. 결과 문서의 후속 커밋은 실행 코드 변경 없이 별도로 기록합니다. 기존 PR을 병합하거나 기본 브랜치의 운영 정책을 활성화하지 않았습니다. [E13]')
    q.p('이번 B-MCG workflow의 3개 route job은 성공했습니다. 같은 push에서 상속된 다른 workflow가 별도로 validation 실패했으나, 해당 파일은 base commit과 Git blob SHA가 같고 job이 시작되지 않았습니다. 이 실패를 B-MCG 재귀 실패로 합치거나, 전체 저장소 CI가 모두 성공했다고 표현하지 않았습니다. [E13-E14]')
    refs=[
        ['E01','원본·입력 재현','baseline/*_PARITY.json; recovery/INPUT_RECEIPT.json'],
        ['E02','제어 입력 계보·운동 오차','precheck_motion/CONTROL_PROVENANCE_AUDIT.json; P2_MOTION.json'],
        ['E03','동일 prior action 비교','precheck_oracle/RESULTS.json; ACTION_METRICS.csv'],
        ['E04','시간 전개 및 CIR/s','horizons/RESULTS.json; *_BRANCHES.npz'],
        ['E05','RF→gyro bias 및 운동 기준','bias_feedback/RESULTS.json; *_WINDOW_5S.csv; *_BIAS_UPDATES.csv'],
        ['E06','4개 관측 개입 재귀','bias_causal/RESULTS.json; R2_RAW_B.npz 등 route/arm별 NPZ'],
        ['E07','사전 정책 lock·분할·점수','policy_calibration_final/*; profiles_final/*'],
        ['E08','공통 정렬·식별 가능성','projection/PROJECTION_SUMMARY.json; EXACT_BOUND_STRATA.json'],
        ['E09','회복·one-factor·보정항 분해','recovery_final/*; recovery_cause/RESULTS.json; UPDATE_BALANCE.json'],
        ['E10','선택 source/synthetic 반례','source_adversarial_final/*; synthetic_adversarial_final/*'],
        ['E11','놓친 허용해의 positive witness','recovery_feasibility/R4_FIRST_CLEAN_FEASIBILITY.json'],
        ['E12','42개 재귀 독립 평가','delivery_evaluation/RESULTS.json; METRICS.csv; DEVELOPMENT_UNITS.csv'],
        ['E13','GitHub 실제 실행 대조','github_ci/CI_REMOTE_AUDIT.json; remote artifact summaries'],
        ['E14','별도 감사·미완료 범위','review/FINAL_POLICY_INDEPENDENT_CHECK.*; FINAL_ADVERSARIAL_VERDICT_KO.md'],
        ['E15','coverage·sharpness·연속 이탈','uncertainty/RESULTS.json; METRICS.csv; COVERAGE_EPISODES.csv']]
    q.table(['근거','질문','증거 묶음 내부 위치'],refs,[.09,.32,.59])
    q.p('위 수치 증거 경로는 ZIP의 results/ 하위이며 recovery/와 review/는 별도 최상위 폴더입니다. 원본 대용량 Release asset은 ZIP에 중복 포함하지 않았습니다. 경로·size·SHA와 복구 코드는 GitHub에 있습니다. GitHub artifact가 만료되면 동일 SHA의 보관 ZIP을 acquire_archive.py --archive로 지정할 수 있습니다. 근거 묶음에는 실제 traces·요약·실패 반례·그림·manifest가 들어 있습니다.',True)
    q.p('실행된 runtime SHA256\nmcg.py: 8f58b7c412e54ca5fa308e61aa16c59c0fec30f05e482c505cb5cdea11099faf\nexperiment.py: e4abd56b3224782efb2f4c861d61e0bd724e0e3687a8e06d8b81f0520229ed28\n최종 두 조건 정책 lock: bf84d6ccf948d20556e2cd81dcbef2c10d3350c8806ea6de4956f6acfe164bcd',True)
    pdf=out/'B_MCG_V1_IMPLEMENTATION_VALIDATION_KO_20261109.pdf';q.finish(pdf,mdout)
    return {'pdf':str(pdf),'report_md':str(mdout),'pdf_sha256':sha(pdf),'evidence_status':final['status'],'ci_status':ci['status']}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--figures-only',action='store_true');a=p.parse_args();setup_fonts(a.root)
    if a.figures_only:make_figures(a.root);print('PRECHECK_FIGURES_WRITTEN')
    else:print(json.dumps(build(a.root),ensure_ascii=False,indent=2))
