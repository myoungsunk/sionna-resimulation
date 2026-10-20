"""Add concrete S2 result tables and an additive S0/S1-preserving root summary."""
from pathlib import Path
import json
import pandas as pd
ROOT=Path(__file__).resolve().parents[4];HERE=ROOT/'research/POWERJOINT_AUDIT_FOLLOWUP_20261020/S2_N2_GEOMETRY'
def main():
 d=json.loads((HERE/'DECISION.json').read_text());checks=pd.read_csv(HERE/'CHECKS.csv');los=pd.read_csv(HERE/'LOS_SAFETY.csv');seeds=pd.read_csv(HERE/'SEED_SUMMARY.csv');gain=pd.read_csv(HERE/'GAIN_COMPARISON.csv')
 s='\n## 고정 기준 위반 셀\n\n| 기준 | case | bias | GEOM ° | 기준 arm ° |\n|---|---|---|---:|---:|\n'
 for r in d['violations']:
  baseline=r['Q_POWER1'] if r['denominator']=='NEW_SEED0_36' else r['DIST_ONLY']
  s+=f"| {r['denominator']} | {r['case']} | {r['bias']} | {r['GEOM']:.9f} | {baseline:.9f} |\n"
 if not d['violations']:s+='| 없음 | — | — | — | — |\n'
 s+='\n## Native LoS 안전성 수치\n\n아래는 네 LoS 셀 각각을 R0와 비교한 절대·상대 변화의 범위다. 양수는 악화다. 전체 16행은 LOS_SAFETY.csv에 보존했다.\n\n| arm | 최소 변화 ° | 최대 변화 ° | 최소 상대 변화 | 최대 상대 변화 |\n|---|---:|---:|---:|---:|\n'
 for arm,g in los.groupby('arm',sort=False):s+=f"| {arm} | {g.absolute_change_deg.min():.9f} | {g.absolute_change_deg.max():.9f} | {100*g.relative_change.min():.3f}% | {100*g.relative_change.max():.3f}% |\n"
 s+='\n## 같은 RF의 motion noise 반복\n\n각 arm에서 5개 seed의 셀 내 Heading 범위(max−min)가 가장 큰 셀이다. 모든 case×bias별 min/median/max·최악 seed·위반 seed 수는 SEED_SUMMARY.csv에 있다. 조건/seed를 독립 표본으로 세지 않는다.\n\n| arm | case / bias | min ° | median ° | max ° | 최악 seed |\n|---|---|---:|---:|---:|---:|\n'
 for arm,g in seeds.groupby('arm',sort=False):
  g=g.copy();g['span']=g.heading_max_deg-g.heading_min_deg;r=g.loc[g.span.idxmax()]
  s+=f"| {arm} | {r['case']} / {r['bias']} | {r.heading_min_deg:.9f} | {r.heading_median_deg:.9f} | {r.heading_max_deg:.9f} | {int(r.worst_seed)} |\n"
 hist=checks[(checks.check=='Q_BASELINE_REPRODUCTION')&(checks.reference_kind=='HISTORICAL_TRACE')];regen=checks[(checks.check=='Q_BASELINE_REPRODUCTION')&checks.reference_kind.fillna('').str.startswith('REGENERATED')]
 s+=f"\n역사적 trace 재현 {len(hist)}셀의 최대 Heading 차이 {hist.heading_difference_deg.max():.17g}°, gate 불일치 합 {int(hist.gate_mismatches.sum())}. 재생성 T2 reference {len(regen)}셀은 역사적 gate 확인과 구분한다. 기존 DIST_ONLY–T9 최대 절대 차이는 {checks.loc[checks.check=='DIST_ONLY_T9_ROWWISE','heading_difference_deg'].abs().max():.17g}°다.\n"
 s+='\n## 실행·증거 보존\n\nlock `2f1b21b9f984ba0d5d3768f9a84a8f5b7d263683`, 모델/adapter `481c249e04164ffc5deccaaefbcc84c16a5779f3`. 학습 run39374401047, 기존/LoS run39374960558, 신규 성공 run39375649673. 입력 준비 중단 18개 route-job와 보존 단계의 GitHub 연결 중단을 원래 로그·artifact·SHA와 함께 보존했다. 판정·모델·엔진을 바꾸지 않았으며 성공 계산만을 재귀 재실행하지 않았다. MANIFEST.json에 모든 원본 artifact의 digest/bytes, release asset ID/URL, 전체 재다운로드 SHA, run/head를 기록했다.\n'
 manifest=json.loads((HERE/'MANIFEST.json').read_text());s+='\n미해결 입력: '+('없음(현재 S2 계약 범위). ' if d['technical']=='TECHNICAL_PASS' else 'ERRORS.json의 현재 오류 참조. ')+ '원래77개 명단 및 구현2·3 원본 소스 미확보는 S0/S1의 제한으로 그대로 남는다.\n'
 (HERE/'RESULTS_KO.md').write_text((HERE/'RESULTS_KO.md').read_text(encoding='utf-8')+s,encoding='utf-8')
 root=HERE.parent/'00_SUMMARY_KO.md';text=root.read_text(encoding='utf-8');assert '\n## S2 N2 기하 특징 검증 최종\n' not in text,'NO_DUPLICATE_S2_SUMMARY'
 text+=f'''\n\n## S2 N2 기하 특징 검증 최종

S1 감사 ACCEPT는 실행 증거와 NOT_ESTABLISHED를 인수하며 N1 지지를 뜻하지 않는다. S0/S1 본문·수치·실패 기록은 위에 그대로 보존한다.

| 과제 | TECHNICAL | 과학 판정 | 핵심 수치 | commit / run / artifact |
|---|---|---|---|---|
| S2 N2 GEOM | {d['technical']} | {d['scientific']} | 신규 seed0 {d['new_seed0']['pass_cells']}/36, 기존 M0 {d['legacy_M0']['pass_cells']}/12; GEOM_Q 개선 {d['geom_q_additional']['improved_cells']}/36 | lock2f1b21b; code481c249; runs39374401047/39374960558/39375649673; artifact·release는 S2 MANIFEST |

공통 11지표 792행과 별도 LoS R0 4행을 보존했다. 주 평가는 t≥30 전체 motion clock·seed0이며 seed1–4는 같은 RF motion noise 반복이다. GEOM/GEOM_Q 잔차 평균·공분산은 사용자 승인 d 삼분위, 평균만 10/11차원이다. Native LoS 안전성과 seed 범위, 위반 셀은 S2_N2_GEOMETRY/RESULTS_KO.md 및 CSV에 보고했다. R2 A M45는 OUT_OF_TRAINING_RANGE_MOUNT다. 독립 장면 일반화·정규화 Bayesian posterior·하드웨어 실증·q 인과 기전은 주장하지 않는다. **S2에서 종료하며 S3는 시작하지 않았다.**
'''
 root.write_text(text,encoding='utf-8');print('S2_REPORT_AND_ADDITIVE_SUMMARY_WRITTEN',flush=True)
if __name__=='__main__':main()
