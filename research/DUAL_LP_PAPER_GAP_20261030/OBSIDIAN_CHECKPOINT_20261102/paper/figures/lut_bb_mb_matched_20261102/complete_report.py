"""V3 reporting only: no filter recursion or observer modification."""
from pathlib import Path
import json,hashlib,datetime
import numpy as np
import pandas as pd
OUT=Path(__file__).resolve().parent
METRICS=['head_rmse','xy_rmse_cm','nees_heading','nees_xy','nees_pose','head_cov95','xy_cov95','pose_cov95','head_bias','n_used','n_used_score','n_score','n_total']
REC=Path('C:/Users/Myoungsun Kim/dlp1102/DualLP_Physics_Link_Validation_20261101')
def contract_coverage(df,source=False):
    exact=[];changes=[]
    for _,r in df.iterrows():
        path=(REC/'results/traces' if source else OUT/'traces')/f'{r.case}__{r.bias}__{r.arm}__self.npz'
        with np.load(path) as z:
            X=z['X'];P=z['PX']
            if source:
                with np.load(REC/f'recovered/inputs/traces/{r.case}_B0_CONTROL.npz') as c:t=c['t_s'];gt=c['truth_scoring_only']
            else:t=z['t'];gt=z['gt']
            mask=t>=30-1e-9;e=gt[:,:3]-X[:,:3];e[:,2]=np.angle(np.exp(1j*e[:,2]))
            head=e[:,2]**2/P[:,2,2]
            xy=np.einsum('ni,ni->n',e[:,:2],np.linalg.solve(P[:,:2,:2],e[:,:2,None])[...,0])
            pose=np.einsum('ni,ni->n',e,np.linalg.solve(P[:,:3,:3],e[...,None])[...,0])
            exact.append(dict(head_cov95_contract_chi2=float(np.mean(head[mask]<3.841458820694124)),xy_cov95_contract_chi2=float(np.mean(xy[mask]<5.991464547107979)),pose_cov95_contract_chi2=float(np.mean(pose[mask]<7.814727903251179))))
            changes.append(dict(model='SourceFFD' if source else 'DistanceLUT',case=r.case,bias=r.bias,arm=r.arm,head_boundary_changed=int(np.count_nonzero(((head<1.96**2)!=(head<3.841458820694124))&mask)),xy_boundary_changed=int(np.count_nonzero(((xy<5.991)!=(xy<5.991464547107979))&mask))))
    return pd.concat([df.reset_index(drop=True),pd.DataFrame(exact)],axis=1),changes
def dump(name,obj):
    (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def pairs(df):
    rows=[]
    for (case,bias),g in df.groupby(['case','bias'],sort=False):
        assert set(g.arm)=={'BB_ORIG','MB_VAR'} and len(g)==2
        bb=g.set_index('arm').loc['BB_ORIG'];mb=g.set_index('arm').loc['MB_VAR']
        assert bb.n_score==mb.n_score
        r=dict(case=case,bias=bias,n_score=int(bb.n_score))
        for m in METRICS:
            r[m+'_BB']=float(bb[m]);r[m+'_MB']=float(mb[m]);r[m+'_delta_MB_minus_BB']=float(mb[m]-bb[m])
        for m in ['head_rmse','xy_rmse_cm']:
            r[m+'_reduction_pct']=float(100*(1-mb[m]/bb[m]))
            r[m+'_outcome']='IMPROVED' if bb[m]-mb[m]>1e-10 else ('WORSENED' if bb[m]-mb[m]<-1e-10 else 'TIE')
        rows.append(r)
    return pd.DataFrame(rows)
def counts(p):
    return {m:{v:int((p[m+'_outcome']==v).sum()) for v in ['IMPROVED','WORSENED','TIE']} for m in ['head_rmse','xy_rmse_cm']}
def main():
    run=json.loads((OUT/'RUN_MANIFEST.json').read_text(encoding='utf-8'));assert run['status']=='COMPLETED_TECHNICAL_SELF_QA'
    full=pd.read_csv(OUT/'FULL_SCORE_24.csv');src=pd.read_csv(OUT/'SOURCE_REFERENCE_SCORE_24.csv')
    assert len(full)==len(src)==24
    full,changes=contract_coverage(full);src,source_changes=contract_coverage(src,source=True)
    full.to_csv(OUT/'FULL_SCORE_CONTRACT_COVERAGE_24.csv',index=False)
    src.to_csv(OUT/'SOURCE_SCORE_CONTRACT_COVERAGE_24.csv',index=False)
    global METRICS
    METRICS=METRICS+['head_cov95_contract_chi2','xy_cov95_contract_chi2','pose_cov95_contract_chi2']
    pd.DataFrame(changes+source_changes).to_csv(OUT/'COVERAGE_THRESHOLD_EFFECT_48.csv',index=False)
    dump('CONTRACT_CLARIFICATION.json',dict(type='REPORTING_DEFINITION_RESOLUTION',identified_by='independent audit actor',frozen_contract_unchanged=True,filter_or_threshold_changes=False,issue='Inherited historical coverage uses |heading_z|<1.96 and XY_NEES<5.991, while this contract states exact chi2 quantiles.',resolution='Historical coverage retained for archive parity. Explicit *_contract_chi2 columns independently recomputed in separate augmented ledgers and paired tables. No filter recursion rerun.',changed_scored_memberships=sum(v['head_boundary_changed']+v['xy_boundary_changed'] for v in changes+source_changes)))
    p=pairs(full);sp=pairs(src)
    order={b:i for i,b in enumerate(['B0','L0','L1','L2'])}
    p=p.sort_values(['case','bias'],key=lambda col:col.map(order) if col.name=='bias' else col).reset_index(drop=True)
    assert len(p)==12 and p.n_score.sum()==10744
    p.to_csv(OUT/'PAIRED_BB_MB_12.csv',index=False)
    sp.to_csv(OUT/'PAIRED_SOURCE_REFERENCE_12.csv',index=False)
    compare=p.merge(sp,on=['case','bias','n_score'],suffixes=('_LUT','_SourceFFD'),validate='one_to_one')
    compare.to_csv(OUT/'OBSERVER_BY_INTERVENTION_2X2_12.csv',index=False)
    combined=pd.concat([full.assign(model='DistanceLUT'),src.assign(model='SourceFFD')],ignore_index=True)
    combined.to_csv(OUT/'MODEL_ARM_SCORE_48.csv',index=False)
    pooled=[]
    for (model,arm),g in combined.groupby(['model','arm']):
        for route in ['ALL','R2','R4','R5']:
            a=g if route=='ALL' else g[g.case.str.startswith(route)];w=a.n_score.to_numpy();r=dict(model=model,arm=arm,route=route,n_score=int(w.sum()),conditions=len(a))
            for m in ['head_rmse','xy_rmse_cm']:r[m]=float(np.sqrt(np.average(a[m]**2,weights=w)))
            for m in ['nees_heading','nees_xy','nees_pose','head_cov95','xy_cov95','pose_cov95']:r[m]=float(np.average(a[m],weights=w))
            pooled.append(r)
    pooled=pd.DataFrame(pooled);pooled.to_csv(OUT/'POOLED_SCORES.csv',index=False)
    c=counts(p);sc=counts(sp);qa=pd.read_csv(OUT/'UPDATE_QA_24.csv')
    verdict='SUPPORTED_WITHIN_FROZEN_SCENARIO' if all(c[m]['IMPROVED']==12 for m in c) else 'MIXED'
    divergence=pd.read_csv(OUT/'FIRST_DIVERGENCE_12.csv')
    text=['# 거리 반영 LUT의 BB_ORIG/self 대 MB_VAR/self','',
      '질문 ID: DLP-LUT-BB-MB-MATCHED-001. 계약을 동결한 뒤 거리 LUT 24개 전체 재귀를 수행했다. 기존 SourceFFD 24개는 참조 재현 검증용이며 신규 LUT 성과와 구분한다. 아래는 원고 반영 전 결과 기록이다.','',
      '## 비교 정의','',
      '두 구성은 Full 수신 관측 z=[r,s], 4상태 [x,y,ψ,b_g], 초기화·동역학·기본 관측공분산·거리 반영 LUT 관측함수와 Jacobian을 공유한다. r은 거리 관측, s는 두 편파 포트의 정규화 전력차, x와 y는 수평 위치, ψ는 heading, b_g는 자이로 바이어스이다. BB_ORIG는 보존된 BB 평균을 빼며 추가 편파 분산을 넣지 않는다. MB_VAR는 보존된 MB 평균을 빼고, 직전 posterior에서 구한 앵커까지의 수평거리 ρ에 따른 σ_b(ρ)²를 편파 관측분산에 더한다. 두 평균의 편파 성분은 같고 거리 성분이 다르다. 각 구성은 자신의 innovation과 공분산으로 self gate를 결정한다. 따라서 BB→MB 차이는 평균·분산과 gate 피드백을 포함한 결합 개입의 결과이다.','',
      'B0/L0/L1/L2는 각각 0/0.01/0.05/0.20°/s 자이로 바이어스이다. 경로는 R2 순환, R4 지그재그, R5 사행이다. 평가 구간은 t≥30−10⁻⁹ s이며 gate에서 거절된 시각도 포함한다. 조건당 R2 829점, R4 592점, R5 1,265점으로 각 구성의 총 평가점은 10,744개다.','',
      '## 12조건 결과','',
      '|경로|바이어스|Heading BB→MB (°)|감소율 (%)|XY BB→MB (cm)|감소율 (%)|NEES pose BB→MB|',
      '|---|---|---:|---:|---:|---:|---:|']
    for _,r in p.iterrows():
        text.append(f'|{r.case[:2]}|{r.bias}|{r.head_rmse_BB:.6f} → {r.head_rmse_MB:.6f}|{r.head_rmse_reduction_pct:.2f}|{r.xy_rmse_cm_BB:.6f} → {r.xy_rmse_cm_MB:.6f}|{r.xy_rmse_cm_reduction_pct:.2f}|{r.nees_pose_BB:.4f} → {r.nees_pose_MB:.4f}|')
    text += ['',f"Heading은 12조건 중 {c['head_rmse']['IMPROVED']}개 개선, {c['head_rmse']['WORSENED']}개 악화, {c['head_rmse']['TIE']}개 동률이다. XY는 {c['xy_rmse_cm']['IMPROVED']}개 개선, {c['xy_rmse_cm']['WORSENED']}개 악화, {c['xy_rmse_cm']['TIE']}개 동률이다. 음수 감소율은 악화를 뜻한다.",'',
      f"같은 평가 규칙으로 재확인한 SourceFFD는 Heading {sc['head_rmse']['IMPROVED']}/12, XY {sc['xy_rmse_cm']['IMPROVED']}/12 개선이다. 관측모델×개입 2×2 수치는 OBSERVER_BY_INTERVENTION_2X2_12.csv에 기록했다. 모델 간 개선율 차이를 특정 물리 원인의 기여율로 해석하지 않는다.",'',
      '## 불확실도와 필터 검사','',
      'NEES는 추정 오차의 공분산 정규화 제곱합이다. Heading/XY/pose는 각각 1/2/3차원이며 pose는 자이로 바이어스를 제외한다. 해당 차원의 기대값은 1/2/3이지만 이 시계열 표본의 독립성을 가정한 신뢰구간이나 통계적 검정을 제시하지 않는다. 작은 NEES만으로 더 좋은 필터라고 단정할 수 없다. FULL_SCORE_24.csv는 기존 집계의 coverage와 수용 수, heading bias를 보존한다. 기존 heading coverage는 |정규화 오차|<1.96, XY는 NEES<5.991이다. 계약의 정확한 χ² 기준은 FULL_SCORE_CONTRACT_COVERAGE_24.csv와 paired 표의 *_contract_chi2 열에 별도로 계산했다. 이 보고 정의 차이와 경계 packet 수는 CONTRACT_CLARIFICATION.json에 기록했으며 필터·계약·기존 점수를 수정하지 않았다.','',
      f"자체 검사에서 모든 posterior와 prior 공분산이 양의 정부호이고 self gate·원 donor·직전 posterior 기반 추가분산·innovation·gain·Joseph 갱신을 재검산했다. 실제 prior의 수치미분과 Jacobian의 최대 절대차는 {qa.actual_prior_fd_max.max():.3g}로 동결 기준 2×10⁻⁵를 통과했다. 최초 상태/공분산/gate 차이는 FIRST_DIVERGENCE_12.csv에 별도로 기록했으며 gate가 달라도 통제 실패로 간주하지 않는다. gate가 다른 packet 수는 12조건 합 {int(divergence.gate_mismatch_all.sum())}개이다.",'',
      '## 주장 범위','',
      f'과학 결과 분류는 {verdict}이다. 기술 검사 통과와 독립 감사 완료, 원고 채택은 별도 단계다. 독립 감사 판정은 audit/INDEPENDENT_AUDIT.json을 따른다. 이 결과만으로 원고가 수정되거나 모델이 채택된 것은 아니다.','',
      '한 corridor, 한 RF realization, 같은 센서 seed를 사용했다. 12조건은 독립 환경 12개가 아니다. LUT는 SourceFFD bank로부터 만든 synthetic grid이며 실측 LUT가 아니다. 관측모델 변화와 BB→MB 결합 개입에 대한 이 동결 시나리오의 결과를 실측 전이·일반 성능 우위로 확장하지 않는다.']
    (OUT/'RESULTS_TO_MANUSCRIPT_KO.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    dump('V3_RESULT_VERDICT.json',dict(technical='PASS_SELF_CHECK',scientific=verdict,LUT_counts=c,Source_reference_counts=sc,primary_runs=24,reference_validation_runs=24,scored_points_per_arm=10744,independent_audit='SEE_SEPARATE_ACTOR_REPORT',adopted=False,updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    selfqa=json.loads((OUT/'FINAL_SELF_QA.json').read_text(encoding='utf-8'));selfqa['V3']='COMPLETE';selfqa['scientific_status']=verdict;selfqa['actual_prior_fd_max']=float(qa.actual_prior_fd_max.max());dump('FINAL_SELF_QA.json',selfqa)
    files={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.rglob('*') if p.is_file() and 'audit' not in p.relative_to(OUT).parts and '__pycache__' not in p.parts and p.name!='OUTPUT_MANIFEST.json'}
    dump('OUTPUT_MANIFEST.json',dict(files=files,excludes='audit subtree maintained by independent actor; this manifest itself',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    print(json.dumps(dict(LUT=c,Source=sc,scientific=verdict),indent=2))
if __name__=='__main__':main()
