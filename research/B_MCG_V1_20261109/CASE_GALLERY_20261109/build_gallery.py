#!/usr/bin/env python3
"""Build self-contained, offline, searchable 506-case B-MCG investigation gallery.

Uses only source-verified archived own-state traces and evaluator-only truth
from analyze_cases.py. Does not run new RF/filter or select deployment policy.
"""
from __future__ import annotations
from pathlib import Path
import json,html
import pandas as pd
from plotly.offline import get_plotlyjs

ROOT=Path(__file__).resolve().parent
catalog=pd.read_csv(ROOT/'CASE_CATALOG.csv',encoding='utf-8-sig')
allrows=pd.read_csv(ROOT/'FULL_ENRICHED_6272.csv',encoding='utf-8-sig')
assert len(allrows)==6272 and len(catalog)>=500
categories={
 'ACTIVE_ALL':'실제 가드 개입 · 전수 23건',
 'ACTIVE_BENEFIT_BOTH':'가드 적용으로 양축 개선',
 'ACTIVE_HARM_BOTH':'가드 적용으로 양축 악화',
 'ACTIVE_TRADEOFF':'가드 적용 후 Heading/XY 손익 상충',
 'COMPATIBLE_HARM_HEADING':'COMPATIBLE이지만 Heading 갱신 손해',
 'COMPATIBLE_HARM_XY':'COMPATIBLE이지만 XY 갱신 손해',
 'COMPATIBLE_CORRUPTED_S':'COMPATIBLE + 큰 실제 s 왜곡',
 'UNKNOWN_HARM_HEADING':'판단 불가 + Heading 갱신 손해',
 'UNKNOWN_HARM_XY':'판단 불가 + XY 갱신 손해',
 'BENEFICIAL_FULL_HEADING':'B full 갱신이 Heading 개선',
 'BENEFICIAL_FULL_XY':'B full 갱신이 XY 개선',
 'CLEAN_TAP_S_DISTORTED':'Full/LoS B tap 동일하지만 s 왜곡',
 'TAP_CHANGED_S_STABLE':'tap은 바뀌었지만 s 변화는 작음',
 'LOW_NIS_HIGH_NEES':'작은 혁신·큰 실제 상태오차',
 'GYRO_BIAS_EXTREME':'필터 gyro bias 오염 상위',
 'HIGH_S_MP':'다중경로 편파왜곡 최상위',
 'HIGH_R_MP':'다중경로 range 차이 최상위',
 'RF_SMALL_AFTER_LARGE':'큰 s 왜곡 직후 작은 왜곡',
 'ROUTE_REFERENCE':'루트 구간 대표 표본'
}

def j(x):return json.dumps(x,ensure_ascii=False,separators=(',',':'))
rows_by={}
for (route,st),df in allrows.groupby(['route','stratum'],sort=False):
    df=df.sort_values('k')
    assert (df.k.to_numpy()==range(len(df))).all()
    # Compact numeric precision to 9 decimal places for visual use; original full CSV unrounded.
    vals=df.where(pd.notna(df),None).to_dict('records')
    for rec in vals:
        for k,v in list(rec.items()):
            if isinstance(v,float):
                if v != v or v==float('inf') or v==float('-inf'):rec[k]=None
                else:rec[k]=round(v,9)
    rows_by[f'{route}|{st}']=vals
cat_records=catalog.where(pd.notna(catalog),None).to_dict('records')
for c in cat_records:
  for k,v in c.items():
   if isinstance(v,float) and v!=v:c[k]=None

htmlpage=r'''<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"/>
<title>B-MCG v1 — 506 Casebook · 궤적/IMU/편파/필터</title>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<style>
:root{--ink:#202b37;--dim:#617284;--bg:#f2f5f9;--paper:#fff;--line:#dce3ea;--blue:#2363aa;--orange:#b45a2a;--green:#137153;--red:#b5324c;--dark:#182534}
*{box-sizing:border-box}body{margin:0;background:var(--bg);font-family:'Pretendard','Noto Sans CJK KR','Malgun Gothic',system-ui,sans-serif;color:var(--ink)}a{color:var(--blue)}button,select,input{font:inherit}
header{background:var(--dark);color:#f1f6fc;padding:19px 29px 18px}header h1{font-weight:710;font-size:23px;letter-spacing:-.6px;margin:0 0 6px}header p{color:#cad7e1;margin:0;font-size:13px;line-height:1.6;max-width:1300px}
.summary{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin:15px 19px 12px}.summary .stat{background:#fff;border:1px solid var(--line);border-radius:10px;padding:12px 15px}.summary b{font-size:23px;display:block;font-variant-numeric:tabular-nums}.summary small{font-size:11px;color:var(--dim)}
.workspace{display:grid;grid-template-columns:325px minmax(0,1fr);gap:12px;margin:0 19px 22px}.sidebar{background:#fff;border:1px solid var(--line);border-radius:12px;height:calc(100vh - 188px);min-height:590px;display:flex;flex-direction:column;overflow:hidden}.side-controls{padding:13px;border-bottom:1px solid var(--line);display:grid;gap:8px}.side-controls .row{display:flex;gap:8px}.side-controls select,.side-controls input{min-width:0;width:100%;border:1px solid #ccd6e1;background:#f9fafc;padding:7px 9px;border-radius:7px;font-size:12px}.side-controls label{font-size:10px;color:var(--dim);display:block;padding-bottom:3px}.list-info{padding:9px 13px;border-bottom:1px solid var(--line);font-size:12px;color:var(--dim)}.case-list{overflow:auto;flex:1;padding:4px}.case-item{text-align:left;width:100%;border:1px solid transparent;border-radius:8px;background:transparent;padding:10px;cursor:pointer;margin:3px 0}.case-item:hover{background:#f0f6fe}.case-item.active{background:#e9f2fe;border-color:#a7c8ea}.case-item .heading{font-size:12px;font-weight:700;display:flex;justify-content:space-between;gap:4px}.case-item .hint{font-size:11px;margin-top:3px;color:#526679}.case-item small{font-size:10px;color:#748395}
.legend-chip{display:inline-block;border-radius:12px;font-size:10px;font-weight:700;padding:2px 7px;background:#e9eef4;color:#4c6777}.legend-chip.damped{background:#e1efe9;color:#087551}.legend-chip.harm{background:#fce7e9;color:#a03b49}
.content{min-width:0;display:grid;gap:12px;align-content:start}.card{border:1px solid var(--line);background:#fff;border-radius:12px;padding:15px;overflow:hidden}.page-title{display:flex;justify-content:space-between;gap:12px;align-items:start}.page-title h2{margin:0;font-size:20px}.page-title p{margin:6px 0 0;color:var(--dim);font-size:12px}.page-title .nav{display:flex;gap:7px}button{border:1px solid #cbd9e5;color:#263c56;background:#fff;padding:7px 11px;border-radius:8px;cursor:pointer;font-size:12px}button:hover{background:#e9f2fe}button:focus,select:focus,input:focus{outline:2px solid #80b4e8}.tools{display:flex;gap:15px;flex-wrap:wrap;align-items:center;padding:11px 0}.tools input{max-width:90px}.tools input[type=range]{max-width:150px}.tools label{font-size:12px;color:var(--dim)}
.fact-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:9px;margin-top:13px}.fact{padding:9px;background:#f7f9fc;border:1px solid #e7edf4;border-radius:9px;min-width:0}.fact strong{display:block;font-size:15px;margin:4px 0;font-variant-numeric:tabular-nums}.fact small{color:#56677a;font-size:10px}.case-brief{font-size:13px;line-height:1.75;padding:11px 13px;background:#f5f8fc;border-left:3px solid #779bc5;border-radius:5px;margin-top:12px}.grids{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.plot-card{height:350px;padding:8px 5px 3px}.plot-card.tall{height:385px}.plot{width:100%;height:100%}.note{font-size:12px;line-height:1.75;color:#465868}.note strong{color:#253c58}.bottom-text{font-size:12px;padding:14px 18px 30px;color:var(--dim)}
@media(max-width:1050px){.workspace{grid-template-columns:260px minmax(0,1fr)}.summary{grid-template-columns:repeat(3,1fr)}.fact-grid{grid-template-columns:repeat(3,1fr)}}@media(max-width:760px){.workspace{display:block;margin:0 10px}.sidebar{height:350px;min-height:350px;margin-bottom:12px}.summary{grid-template-columns:repeat(2,1fr);margin:10px}.grids{grid-template-columns:1fr}.fact-grid{grid-template-columns:repeat(2,1fr)}header{padding:15px}.page-title{flex-wrap:wrap}}
</style>
<script>/*PLOTLY_JS_PLACEHOLDER*/</script>
</head><body>
<header><h1>B-MCG v1 · RF × 운동 × 필터 케이스북</h1>
<p>동일 RF를 받은 가드 OFF/ON 필터, 실제 궤적, 예측식에서 복원한 IMU gyro·odometry, Full/LoS의 range·편파 s 및 CIR 요약특징을 시간 동기화해 보여줍니다. 사후 참값·LoS 자료는 <b>평가 전용</b>입니다. 모델 정합 관측을 주입한 스트레스 실험은 실제 RF 측정 사례와 분리합니다.</p></header>
<div class="summary"><div class="stat"><b id="statCases">506</b><small>엄선된 시간별 상세 사례</small></div><div class="stat"><b>3,136</b><small>실제 궤적 샘플 (전체 직접 조회)</small></div><div class="stat"><b>23</b><small>가드 실제 감쇠 기록 (모델별 합계)</small></div><div class="stat"><b>0</b><small>s 채널 단독 감쇠</small></div><div class="stat"><b>4</b><small>회귀 비교 스트림/경로: 2×OFF/ON</small></div></div>
<div class="workspace"><aside class="sidebar"><div class="side-controls">
<div class="row"><div style="flex:1"><label>경로</label><select id="route"><option value="ALL">전체 경로</option><option>R2</option><option>R4</option><option>R5</option></select></div><div style="flex:1"><label>기준 보정</label><select id="stratum"><option value="ALL">모두</option><option value="B_FROZEN">B 원본</option><option value="B_BIAS_COV">B 평균·공분산 보정</option></select></div></div>
<div><label>분류</label><select id="category"><option value="ALL">전체 분류</option></select></div>
<div><label>검색: k, 시간, 구분, 경로</label><input id="search" placeholder="R5, 87, CONFLICT_R, k0435 …"/></div>
<div class="row"><button id="allCases">전수 사례 보기</button><button id="onlyActive">실제 감쇠 23건</button></div></div>
<div class="list-info" id="listInfo"></div><div class="case-list" id="caseList"></div></aside>
<main class="content"><section class="card">
<div class="page-title"><div><h2 id="caseTitle">케이스 선택</h2><p id="caseSubtitle"></p></div><div class="nav"><button id="prev">← 이전</button><button id="next">다음 →</button></div></div>
<div class="tools"><label>중심 k <input id="kInput" type="number" min="0" step="1" value="435"/></label><button id="goK">해당 시점 바로 보기</button><label>전후 <input type="range" id="span" min="2" max="30" step="1" value="8"/><b id="spanTxt">8초</b></label><button id="copyLink">현재 케이스 링크 복사</button></div>
<div id="caseFacts" class="fact-grid"></div><div id="caseBrief" class="case-brief"></div>
</section><div class="grids">
<section class="card plot-card tall"><div class="plot" id="plotXY"></div></section>
<section class="card plot-card tall"><div class="plot" id="plotYaw"></div></section>
<section class="card plot-card"><div class="plot" id="plotImu"></div></section>
<section class="card plot-card"><div class="plot" id="plotS"></div></section>
<section class="card plot-card"><div class="plot" id="plotRange"></div></section>
<section class="card plot-card"><div class="plot" id="plotErrors"></div></section>
<section class="card plot-card"><div class="plot" id="plotGate"></div></section>
<section class="card plot-card"><div class="plot" id="plotCIR"></div></section>
</div>
<section class="card note"><strong>해석 및 계산 정의</strong><p>현재 중심점은 검은 세로선/동그라미로 표시됩니다. <b>실제 참값·LoS-only</b>는 사후 evaluator 자료이며 가드가 운영 중 알 수 없습니다. <b>IMU Gyro</b>는 원본 gy 값을 다운로드한 것이 아니라, 저장된 예측식과 각 OFF/ON 상태에서 역산한 원시 gyro 회전증분입니다. 4개의 독립 저장 스트림 사이의 차이는 10⁻¹⁵ 단위로 검산했습니다. <b>GT-aligned IMU/DR</b>는 창 시작점의 참위치·참방향으로만 초기 정렬한 사후 비교선이며 온라인 정답 기준이 아닙니다. <b>DR(OFF-aligned)</b>는 창 시작점의 OFF 추정상태를 초기값으로 사용합니다.</p>
<p><b>가드 감쇠의 same-prior 손익</b>은 현재 가드의 prior, 동일 관측과 동일 기존 shadow mask에서 무가중 갱신과 가중 갱신을 비교한 값입니다. 전체 OFF와 ON의 차이는 과거 상태가 달라진 <b>폐루프 비교</b>로 별도 그래프에 표시합니다. <b>B 갱신 손익</b>은 가드 자신의 prior 대비 가중치 없는 B 갱신 결과이며, RF만의 인과 기여도는 아닙니다. <b>COMPATIBLE</b>은 현재 운동 기준과 불일치가 검출되지 않았다는 뜻이지 RF가 정확하다는 뜻이 아닙니다. <b>UNKNOWN</b>도 정상 라벨이 아닙니다.</p>
<p><b>RF/CIR</b> 그래프의 복소 왜곡 지표는 이전 원본 CFR 전수 분석에서 계산한 FP 주변 요약값이며, 원본 complex tap 배열을 이 HTML에 포함한 것은 아닙니다. 링크의 CSV와 원본 SHA를 통해 추적할 수 있습니다. 모델 정합 관측 회복의 적대적 반례 R4 k212와 R5 k707은 이 궤적 casebook의 실제 B 관측과 동일시하지 않습니다.</p></section>
</main></div>
<footer class="bottom-text">Sources: GitHub Actions #42600632209, published 41-file artifact SHA, PRIMARY_3136.csv (Full/LoS CFR-derived features). Full numeric rows and Python audit provided alongside this HTML. Neither production policy adoption nor unseen-environment generalization is claimed.</footer>
<script>/*CASE_DATA_PLACEHOLDER*/</script>
<script>
const CATALOG=window.BMCG_CASES, SERIES=window.BMCG_SERIES,CATS=window.BMCG_CATS;
const rSel=document.getElementById('route'),stSel=document.getElementById('stratum'),catSel=document.getElementById('category'),search=document.getElementById('search');
for(const [k,v] of Object.entries(CATS)){const x=document.createElement('option');x.value=k;x.textContent=v;catSel.append(x)}
document.getElementById('statCases').textContent=CATALOG.length.toLocaleString('ko-KR');
let filtered=CATALOG.slice(),current=null;
function fmt(x,d=3){return x==null||!Number.isFinite(x)?'N/A':Number(x).toFixed(d)}
function catdesc(c){return CATS[c]||c}
function key(route,stratum){return route+'|'+stratum}
function dataOf(route,stratum){return SERIES[key(route,stratum)]||[]}
function filterCases(){const r=rSel.value,st=stSel.value,cat=catSel.value,s=search.value.trim().toLowerCase();
 filtered=CATALOG.filter(c=>(r==='ALL'||c.route===r)&&(st==='ALL'||c.stratum===st)&&(cat==='ALL'||c.categories.split('|').includes(cat))&&(!s||(c.id+' '+c.t_s+' '+c.guard_status+' '+c.categories+' '+c.guard_reason).toLowerCase().includes(s)));
 document.getElementById('listInfo').textContent=`${filtered.length.toLocaleString()}개 선택 사례 · 전체 3,136시점은 k 직접 조회 가능`;
 let list=document.getElementById('caseList');list.innerHTML='';const frag=document.createDocumentFragment();
 for(const c of filtered){const b=document.createElement('button');b.className='case-item'+(current&&current.id===c.id?' active':'');const act=c.categories.includes('ACTIVE_ALL');
 b.innerHTML=`<span class="heading"><span>${c.route} · ${c.stratum==='B_FROZEN'?'B 원본':'B 보정'} · k${c.k}</span><span class="legend-chip ${act?'damped':''}">${act?'감쇠':c.guard_status}</span></span><div class="hint">${catdesc(c.primary_category)}</div><small>t=${fmt(c.t_s,1)}s · Δs=${fmt(c.e_s_mp,3)} · H ${fmt(c.heading_error_OFF_deg,2)}°→${fmt(c.heading_error_ON_deg,2)}°</small>`;
 b.onclick=()=>renderCase(c);frag.append(b)}list.append(frag)}
function panel(name,traces,layout){let e=document.getElementById(name);const L={paper_bgcolor:'#fff',plot_bgcolor:'#fff',font:{family:'Arial, sans-serif',size:11,color:'#445367'},margin:{l:53,r:56,t:40,b:42},legend:{orientation:'h',y:-.2,x:0,font:{size:10}},hovermode:'x unified',...layout};Plotly.react(e,traces,L,{responsive:true,displaylogo:false,scrollZoom:false})}
function tr(x,y,name,color,extra={}){return {x,y,name,mode:'lines',line:{color,width:2},...extra}}
function vw(t){return {type:'line',x0:t,x1:t,yref:'paper',y0:0,y1:1,line:{color:'#354c64',width:1,dash:'dot'}}}
function around(yaw,start){let out=[yaw[0]],add=0;for(let i=1;i<yaw.length;i++){let d=yaw[i]-yaw[i-1];d=((d+180)%360+360)%360-180;out.push(out[i-1]+d)}return out}
function rawGyroReference(w,source,startYaw,startX,startY,estimatedBias=false){
 let head=[startYaw],X=[startX],Y=[startY];for(let i=1;i<w.length;i++){
  const row=w[i],prev=w[i-1];const dt=row.t_s-prev.t_s;const bg=estimatedBias?prev.bias_off_deg_s*Math.PI/180:0;
  const gyro=row.gyro_increment_rad-bg*dt;const phi=head[i-1]*Math.PI/180+gyro/2;
  const sinc=Math.abs(gyro)<1e-9?1:Math.sin(gyro/2)/(gyro/2);const ds=row.odom_distance_increment_m;
  X.push(X[i-1]+ds*sinc*Math.cos(phi));Y.push(Y[i-1]+ds*sinc*Math.sin(phi));head.push(head[i-1]+gyro*180/Math.PI)
 }return {yaw:head,x:X,y:Y}
}
function values(rows,name){return rows.map(a=>a[name])}
function renderCase(c){
 if(!c)return;current=c;const series=dataOf(c.route,c.stratum),v=series[c.k];if(!v){alert('case not found');return}
 const span=Number(document.getElementById('span').value),start=Math.max(0,Math.floor(c.k-span/.2)),end=Math.min(series.length-1,Math.ceil(c.k+span/.2));
 const w=series.slice(start,end+1),tt=values(w,'t_s'),t=v.t_s;
 const gtYaw=around(w.map(q=>q.yaw_true_rad*180/Math.PI));
 const offYaw=around(w.map(q=>q.yaw_off_deg));const onYaw=around(w.map(q=>q.yaw_on_deg));
 // Align each circular series to the true yaw chart branch without changing actual relative errors.
 const align=(a,ref)=>{const dif=((a[0]-ref+180)%360+360)%360-180;const shift=ref+dif-a[0];return a.map(v=>v+shift)};
 const offA=align(offYaw,gtYaw[0]),onA=align(onYaw,gtYaw[0]);
 const rGT=rawGyroReference(w,'gt',gtYaw[0],w[0].x_true,w[0].y_true,false);
 const rBiasGT=rawGyroReference(w,'gt',gtYaw[0],w[0].x_true,w[0].y_true,true);
 const rDR=rawGyroReference(w,'off',offA[0],w[0].x_off_m,w[0].y_off_m,true);
 const ix=c.k-start, marker=()=>({mode:'markers',marker:{size:10,symbol:'circle-open',color:'#161f2e',line:{width:2}},showlegend:false});
 const high=(q,unit)=>`<div class="fact"><small>${q}</small><strong>${unit}</strong></div>`;
 const deltaE=v.guard_harm_heading_deg2,deltaX=v.guard_harm_xy_cm2;
 const scoreAct=v.beta_r<.999999||v.beta_s<.999999;
 document.getElementById('caseTitle').textContent=`${c.route} · ${c.stratum==='B_FROZEN'?'B 원본':'B 평균·분산 보정'} · k=${c.k}`;
 document.getElementById('caseSubtitle').textContent=`t=${fmt(t,1)}s  •  ${c.categories.split('|').map(catdesc).join(' · ')}  •  ${v.monitor_state}  •  기존 수용=${v.legacy_accepted?'YES':'NO'}`;
 document.getElementById('kInput').value=c.k;
 document.getElementById('caseFacts').innerHTML=[
 high('참값 위치',`${fmt(v.x_true,2)}, ${fmt(v.y_true,2)}m`),high('참값 헤딩',`${fmt(v.yaw_true_rad*180/Math.PI,1)}°`),
 high('Heading 오차 OFF → ON',`${fmt(v.heading_error_off_deg,2)}° → ${fmt(v.heading_error_on_deg,2)}°`),
 high('XY 오차 OFF → ON',`${fmt(v.xy_error_off_cm,1)} → ${fmt(v.xy_error_on_cm,1)}cm`),
 high('가드 가중치 βr / βs',`${fmt(v.beta_r,3)} / ${fmt(v.beta_s,3)}`),
 high('Full−LoS Δs',fmt(v.e_s_mp,4)),
 high('Full−LoS Δr',`${fmt(v.e_r_mp_m*100,1)}cm`),high('Full/LoS B tap',`${v.B_F} / ${v.B_L}`),
 high('현재 gyro 증분',`${fmt(v.gyro_increment_rad*180/Math.PI,3)}°`),
 high('OFF 추정 gyro bias',`${fmt(v.bias_off_deg_s,4)}°/s`),
 high('main NIS / 상태 NEES3',`${fmt(v.nis_off,2)} / ${fmt(v.nees_off,1)}`),
 high('한 시점 가드 손익 (Heading / XY)',`${fmt(deltaE,4)} deg² / ${fmt(deltaX,2)} cm²`)
 ].join('');
 let brief=`<b>${scoreAct?'감쇠 발생':'감쇠 없음'}.</b> `;
 if(scoreAct)brief+=`같은 prior의 무가중 갱신과 비교한 가드 효과: Heading ${deltaE<0?'개선':'악화'} (${fmt(deltaE,4)} deg²), XY ${deltaX<0?'개선':'악화'} (${fmt(deltaX,3)} cm²). `;
 else brief+=`원래 B 관측을 적용한 직후의 Heading 손익은 ${v.B_update_harm_heading_deg2>0?'악화':'개선'} (${fmt(v.B_update_harm_heading_deg2,4)} deg²); 이것만으로 RF 단독 원인은 확정되지 않습니다. `;
 if(v.monitor_state==='COMPATIBLE')brief+=`운동모델에 대한 호환 판정은 실제 정확도 검증이 아닙니다. `;
 if(v.monitor_state==='UNKNOWN')brief+=`가드는 이 시점을 정상으로 판단한 것이 아니라 판단을 유보했습니다. `;
 brief+=`CIR FP 주변 복소 왜곡 지표 ${fmt(v.local_complex_distortion,3)}; |Δs|=${fmt(Math.abs(v.e_s_mp),4)}. `;
 brief+=`이 그래프는 k=${c.k} 전후 ±${span}s를 표시하며, IMU/DR의 참값 시작 정렬은 사후 비교용입니다.`;
 document.getElementById('caseBrief').innerHTML=brief;
 // XY compare: true, independent source filter outputs, two DR reconstructions.
 const xy=[
 tr(values(w,'x_true'),values(w,'y_true'),'GT (evaluator)','#1a2636',{line:{width:3,color:'#1a2636'}}),
 tr(values(w,'x_off_m'),values(w,'y_off_m'),'B guard OFF','#2363aa'),
 tr(values(w,'x_on_m'),values(w,'y_on_m'),'B guard ON','#ba6434'),
 tr(rGT.x,rGT.y,'IMU+odom, GT-anchored','#16836a',{line:{color:'#16836a',width:1.8,dash:'dash'}}),
 tr(rDR.x,rDR.y,'DR, OFF-anchored','#7d609a',{line:{color:'#7d609a',width:1.7,dash:'dot'}}),
 {x:[v.x_true],y:[v.y_true],name:'current GT',...marker()}
 ];
 panel('plotXY',xy,{title:{text:'XY 궤적: GT / OFF / ON / IMU+odometry',font:{size:14}},xaxis:{title:'x [m]',scaleanchor:'y',scaleratio:1},yaxis:{title:'y [m]'},hovermode:'closest'});
 panel('plotYaw',[
 tr(tt,gtYaw,'GT yaw','#1a2636',{line:{color:'#1a2636',width:3}}),
 tr(tt,offA,'B OFF yaw','#2363aa'),tr(tt,onA,'B-MCG ON yaw','#ba6434'),
 tr(tt,rGT.yaw,'Raw gyro (GT start align)','#16836a',{line:{color:'#16836a',dash:'dash',width:1.5}}),
 tr(tt,rBiasGT.yaw,'Gyro − B bias (GT start align)','#8b63aa',{line:{color:'#8b63aa',dash:'dot',width:1.5}}),
 ],{title:{text:'Heading: 실제 / 필터 / IMU 누적',font:{size:14}},xaxis:{title:'시간 [s]'},yaxis:{title:'unwrapped heading [deg]'},shapes:[vw(t)]});
 let gyroRate=w.map((q,i)=>i===0?null:q.gyro_increment_rad*180/Math.PI/(q.t_s-w[i-1].t_s));
 let trueRate=w.map((q,i)=>i===0?null:((q.true_yaw_increment_rad)*180/Math.PI/(q.t_s-w[i-1].t_s)));
 panel('plotImu',[
 tr(tt,gyroRate,'IMU gyro rate','#16836a'),
 tr(tt,trueRate,'GT yaw rate (eval)','#1a2636',{line:{color:'#1a2636',dash:'dash',width:1.6}}),
 tr(tt,values(w,'bias_off_deg_s'),'B OFF estimated gyro bias','#ba6434',{yaxis:'y2',line:{color:'#ba6434',width:1.8}})
 ],{title:{text:'원시 gyro 회전속도 · 실제 회전 · 추정 bias',font:{size:14}},xaxis:{title:'시간 [s]'},yaxis:{title:'rate [deg/s]'},yaxis2:{title:'bias [deg/s]',overlaying:'y',side:'right',showgrid:false},shapes:[vw(t)]});
 panel('plotS',[
 tr(tt,values(w,'s_F'),'Full B s','#ba6434'),
 tr(tt,values(w,'s_L'),'LoS-only B s (eval)','#1a2636',{line:{color:'#1a2636',dash:'dash'}}),
 tr(tt,values(w,'s_pred_off'),'Model predicted s, OFF','#2363aa',{line:{color:'#2363aa',dash:'dot'}}),
 tr(tt,values(w,'e_s_mp'),'Full−LoS Δs','#ad7396',{line:{color:'#ad7396',dash:'dashdot'}})
 ],{title:{text:'편파 s: 관측·LoS 대조·모델 예측·다중경로 차이',font:{size:14}},xaxis:{title:'시간 [s]'},yaxis:{title:'s (dimensionless)'},shapes:[vw(t)]});
 panel('plotRange',[
 tr(tt,values(w,'r_observed_m'),'Full B range','#ba6434'),
 tr(tt,w.map(q=>q.B_L*(__BSTEP__)),'LoS-only B range (eval)','#1a2636',{line:{color:'#1a2636',dash:'dash'}}),
 tr(tt,values(w,'r_pred_off_m'),'Model predicted range, OFF','#2363aa',{line:{color:'#2363aa',dash:'dot'}})
 ],{title:{text:'거리: B Full/LoS 기준 tap 및 모델',font:{size:14}},xaxis:{title:'시간 [s]'},yaxis:{title:'observed range [m]'},shapes:[vw(t)]});
 panel('plotErrors',[
 tr(tt,values(w,'heading_error_off_deg'),'Heading err OFF','#2363aa'),
 tr(tt,values(w,'heading_error_on_deg'),'Heading err ON','#ba6434'),
 tr(tt,values(w,'xy_error_off_cm'),'XY error OFF [cm]','#386dba',{yaxis:'y2',line:{color:'#386dba',dash:'dot'}}),
 tr(tt,values(w,'xy_error_on_cm'),'XY error ON [cm]','#c58b55',{yaxis:'y2',line:{color:'#c58b55',dash:'dashdot'}})
 ],{title:{text:'상태 실제 오차: Heading (signed) / XY (magnitude)',font:{size:14}},xaxis:{title:'시간 [s]'},yaxis:{title:'yaw error [deg]'},yaxis2:{title:'XY error [cm]',side:'right',overlaying:'y',showgrid:false},shapes:[vw(t)]});
 panel('plotGate',[
 tr(tt,values(w,'beta_r'),'β range','#c05d44'),
 tr(tt,values(w,'beta_s'),'β s','#16836a'),
 tr(tt,values(w,'score_r'),'range compatibility score','#2363aa',{yaxis:'y2',line:{color:'#2363aa',dash:'dot'}}),
 tr(tt,values(w,'score_s'),'s compatibility score','#a575b0',{yaxis:'y2',line:{color:'#a575b0',dash:'dash'}})
 ],{title:{text:'가드 판단: βr/βs · 정합성 점수',font:{size:14}},xaxis:{title:'시간 [s]'},yaxis:{title:'β [0,1]',range:[-.05,1.06]},yaxis2:{title:'pre-inflation score',side:'right',overlaying:'y',showgrid:false},shapes:[vw(t)]});
 panel('plotCIR',[
 tr(tt,values(w,'local_complex_distortion'),'FP local complex distortion','#2363aa'),
 tr(tt,w.map(q=>q.B_F-q.B_L),'B tap Δ(Full−LoS)','#ba6434',{yaxis:'y2'}),
 tr(tt,values(w,'e_s_mp'),'Δs (Full−LoS)','#16836a',{yaxis:'y2',line:{color:'#16836a',dash:'dot'}}),
 ],{title:{text:'CIR 요약: 국소 복소 왜곡 · B tap 이동 · Δs',font:{size:14}},xaxis:{title:'시간 [s]'},yaxis:{title:'local distortion [a.u.]'},yaxis2:{title:'tap shift / Δs',side:'right',overlaying:'y',showgrid:false},shapes:[vw(t)]});
 filterCases();history.replaceState(null,'',`#${c.route}|${c.stratum}|${c.k}`);
}
for(const id of ['route','stratum','category','search'])document.getElementById(id).addEventListener(id==='search'?'input':'change',filterCases);
document.getElementById('allCases').onclick=()=>{rSel.value='ALL';stSel.value='ALL';catSel.value='ALL';search.value='';filterCases()};
document.getElementById('onlyActive').onclick=()=>{rSel.value='ALL';stSel.value='ALL';catSel.value='ACTIVE_ALL';search.value='';filterCases()};
document.getElementById('prev').onclick=()=>{let i=filtered.findIndex(q=>current&&q.id===current.id);if(i<0)i=0;renderCase(filtered[(i-1+filtered.length)%filtered.length])};
document.getElementById('next').onclick=()=>{let i=filtered.findIndex(q=>current&&q.id===current.id);if(i<0)i=-1;renderCase(filtered[(i+1)%filtered.length])};
document.getElementById('span').oninput=(e)=>{document.getElementById('spanTxt').textContent=e.target.value+'초';renderCase(current)};
document.getElementById('goK').onclick=()=>{let r=rSel.value!=='ALL'?rSel.value:(current?.route||'R5'),s=stSel.value!=='ALL'?stSel.value:(current?.stratum||'B_FROZEN');let k=Number(document.getElementById('kInput').value);const ds=dataOf(r,s);if(!Number.isInteger(k)||k<0||k>=ds.length){alert('유효한 k를 입력하세요: 0 ~ '+(ds.length-1));return}const c=CATALOG.find(z=>z.route===r&&z.stratum===s&&z.k===k)||{id:`${r}_${s}_k${k}`,route:r,stratum:s,k,categories:'DIRECT_K',t_s:ds[k].t_s,primary_category:'ROUTE_REFERENCE'};renderCase(c)};
document.getElementById('copyLink').onclick=()=>{const url=location.href;if(navigator.clipboard?.writeText)navigator.clipboard.writeText(url);else prompt('복사:',url)};
let hash=decodeURIComponent(location.hash.slice(1));let a=hash.split('|');let c=(a.length===3&&Number.isInteger(Number(a[2])))?CATALOG.find(x=>x.route===a[0]&&x.stratum===a[1]&&x.k===Number(a[2])):null;
filterCases();renderCase(c||CATALOG.find(x=>x.route==='R5'&&x.stratum==='B_FROZEN'&&x.k===435)||CATALOG[0]);
</script></body></html>'''
htmlpage=htmlpage.replace('/*PLOTLY_JS_PLACEHOLDER*/',get_plotlyjs())
htmlpage=htmlpage.replace('/*CASE_DATA_PLACEHOLDER*/',f'window.BMCG_CASES={j(cat_records)};window.BMCG_SERIES={j(rows_by)};window.BMCG_CATS={j(categories)};')
htmlpage=htmlpage.replace('__BSTEP__',str(299792458/(1028*1950000)))
path=Path('/mnt/data/B_MCG_506_CASES_INTERACTIVE_20261109.html')
path.write_text(htmlpage,encoding='utf-8')
print('HTML',path,path.stat().st_size,'bytes, cases',len(catalog),'rows',len(allrows),'Plotly inline','present')
