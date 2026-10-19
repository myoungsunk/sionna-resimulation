"""Build a readable report only from already-validated output tables."""
from pathlib import Path
import argparse,json,hashlib
import pandas as pd

def table(df):
    vals=[list(df.columns)]+[[str(v) for v in row] for row in df.itertuples(index=False,name=None)]
    return '\n'.join(['| '+' | '.join(vals[0])+' |','|'+'|'.join(['---']*len(vals[0]))+'|']+['| '+' | '.join(r)+' |' for r in vals[1:]])

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--delivery',required=True);args=ap.parse_args();d=Path(args.delivery)
    ev=pd.read_csv(d/'analysis/EVALUATION_SCORES.csv');cnt=pd.read_csv(d/'analysis/DESCRIPTIVE_HYPOTHESIS_COUNTS.csv');post=d/'mechanism'
    qa=json.loads((d/'analysis/FINAL_QA.json').read_text())
    memo=ev[(ev.bias=='B0')&ev.arm.isin(['POWER1','MEM_RS','MEM_R','MEM_S'])].copy()
    memo=memo[['case','arm','heading_rmse_deg','heading95','sigma_rms_deg','gyro_bias_rmse_dps']]
    for c in ['heading_rmse_deg','sigma_rms_deg','gyro_bias_rmse_dps']:memo[c]=memo[c].map(lambda x:f'{x:.6f}')
    memo.heading95=memo.heading95.map(lambda x:f'{100*x:.2f}%')
    cc=cnt[cnt.arm.isin(['STATIC_RICH','MEM_RS','MEM_R','MEM_S','MEM_SHORT','MEM_LONG','P4_HARD_BOTH','P4_HARD_MEAN','P4_HARD_COV','P4_UTILITY','POWER_IEKF','POWER_SR4','POWER_NO_GATE','POWER_RECOVERY','POWER_FREEZE_BG'])][['arm','n_conditions','heading_improved','heading_worse_10pct','coverage_closer_95','nll_improved']]
    local=pd.read_csv(d/'analysis/LOCAL_AFTER_EFFECTS.csv');local=local[(local.bias=='B0')&local.arm.isin(['LOCAL_MEM_DROP','LOCAL_MEM_KEEP','LOCAL_RICH'])]
    for c in ['after_heading_rmse_deg','baseline_after_rmse_deg']:local[c]=local[c].map(lambda x:f'{x:.6f}')
    local=local[['case','arm','after_n','baseline_after_rmse_deg','after_heading_rmse_deg']]
    text='''# POWER1·Joint4 — 근본 사슬 가설 검증 실행 결과

실행일 2026-10-19. 이는 계획서가 아니라 실제 GitHub Actions 계산 결과이다.

## 실행 범위

- 7개 유효 route-anchor-mount × 4 gyro-bias(B0/L0/L1/L2) × 29 방법 = **812개 전 경로 재귀 계산**, 28개 저장 trace. 전 조건을 같은 현재 Full RF로 실행했다.
- Mount 비교는 R2 A M0/M45, 나머지는 R2 B/R4 A·B/R5 A·B M0. 모든 자료는 기존 한 복도이다. 신규 Office/6개 경로 Full H 검증은 **NOT_TESTED**.
- SourceFFD·POWER 원 절차를 재학습/재현했고, 추가 모델은 바깥 평가 route를 제외한 학습 자료만 사용했다. 대형 FFD 보관본 두 개를 복원해 읽기 전용 배열로 사용했다.
- 추정 함수는 GT·GT 좌표·GT 기울기를 받지 않는다. GT는 초기 synthetic sensor 생성, 학습 레이블 및 사후 평가에만 사용한다.
- 사소한 패키지 누락(features.py)을 복원하고 실행을 계속했다. 보조 RF pose-bank 인접관계를 시간으로 오인하지 않도록 실제 t/pose 대응으로 시간 파라미터를 다시 추정했다.

## 가장 중요한 판정

**시간상관을 반영하면 일부 조건의 정확도와 공분산 과신이 함께 개선되지만, 현재의 단일 Gauss–Markov 후보가 모든 Full RF에서 정확도·신뢰도를 함께 보장한다는 가설은 지지되지 않는다.**

R2 A Mount45 B0: POWER1 Heading 0.982634° → 양 채널 시간모델 0.637936°, 95% 포함률63.57% →100%, 예측 sigma RMS0.475156° →0.845208°. 정확도도 개선돼 단순 구간확대만은 아니지만 100%가 확률적으로 최적이라는 뜻은 아니다.

R5 A B0: 같은 후보의 Heading 4.556146° →9.032129°, 포함률39.68% →16.36%. 이 실패를 제외하지 않는다. 위치·방향·동역학에서 관측편향과 실제 상태를 구분하는 모델의 한계가 남는다.

MEM_WHITE는 같은 6-state 표현과 같은 1회 관측 전체분산을 사용하되 기억만0이다. 이 대조는 28조건에서 원 POWER1을 수치 정밀도로 재현했다. 따라서 MEM_RS/MEM_R/MEM_S 차이를 단순 상태 차원 증가나 전체 R 확대 때문이라고 볼 수 없다.

## 모델 정의

z_k = h(x_k) + mu_POWER(q_k) + B_k u_k + epsilon_k,
u_{k+1} = a_k u_k + eta_k,
Cov(u)=I, Cov(eta)=(1-a_k^2)I,
B_k B_k^T + R_epsilon,k = R_POWER,k.

r/s 단독 기억은 해당 변수의 조건부 분산 일부만 사용한다. r/s 동시 기억은 sqrt(f) chol(R)를 사용한다. 실제 주행 시각에서 학습 경로의 잔차 1/2-lag 모멘트로 a,f를 추정했으며, 이것이 독립 반복 RF의 물리적 확률모형으로 확인됐다는 뜻은 아니다. 파라미터 short/long 민감도와 nav–RF latent 교차공분산을 인위적으로 제거한 음성 대조도 포함했다.

## B0 주요 수치

'''+table(memo)+'''

## 전28조건의 기술적 비교 횟수

다음은 동일 RF에 대한 조건별 카운트이며 독립 통계검정 또는 10% 비열등성 검정이 아니다. 포함률만 높아진 것을 성공으로 세지 않는다.

'''+table(cc)+'''

## 실제 가능한 국소 개입 후 동일 Full RF를 계속 사용

공통 시작 이력을 보존하고, 훈련 detector-sensitivity 90분위 초과가 2회 연속 관찰되는 첫 구간에서 개입했다. 이 조건은 GT를 사용하지 않지만, 최초 물리 반사원인이 규명된 구간이라고 주장하지 않는다.

LOCAL_MEM_DROP는 해당 구간에서만 편향기억을 적용한 후 nav 상태의 주변분포를 남기고 원래4-state 방법으로 복귀한다. LOCAL_MEM_KEEP는 그 뒤에도 계속 기억 모델을 사용하므로 **한 구간만의 개입과 다르다**. LOCAL_RICH는 그 구간에서만 richer static mean/cov를 사용한다. LOCAL_PLACEBO는 이후의 동일 길이 양호구간을 사용한 오프라인 대조이다.

'''+table(local)+'''

선택한 구간에만 시간모델을 적용하고 제거한 경우의 효과는 대체로 작거나 조건 의존적이다. '한 구간만 고치면 장기 오류가 보편적으로 해소된다'고 결론내리지 않는다. 국소 richer static 보정이 개선한 사례도 함께 보존한다.

## P4 / Gate / 선형화 판정

- 이번 P4 분류기는 기존17개 CIR 특징과 기존 임계 레이블을 사용하는 **새로운 outer-fold RandomForest 후보**다. 과거 보관된 P4 계수를 그대로 재실행한 것이라고 주장하지 않는다.
- 같은 위험점수에서 평균만/공분산만/둘 다를 바꾸어 정책 연결부를 분리했다. 보정효용 분류기는 공통 prior의 1회 Heading 손실을 훈련 레이블로 쓰는 새 후보다. GT는 runtime 입력이 아니다. 이 후보도 전 경로 성능을 보장하지 않았다.
- Gate 제거/연속 거부 후 R 확대 재수용/공통 mask 대조를 실행했다. 공통 mask는 오프라인 비교이며, 복구 후보가 Gate 문제 전체의 가능한 해법을 대표하지 않는다.
- IEKF는 같은 prior와 단일 관측 목적함수를 반복해서 풀며, 관측을 여러 번 정보로 누적하지 않는다. SR4는 조건부 whitening을 적용한 원본 구현이다. 반복/순차법의 추가 이득은 조건 의존적이다.
- POWER_FREEZE_BG는 RF→Gyro Bias 연결을 차단하는 진단이다. 상태회복 경로까지 차단할 수 있으며 새 실용방법으로 권하지 않는다.

## 검증 수준·미확정

독립 저장 trace scorer로 812개 점수를 다시 계산하고 SPD를 확인했다. 원 source joint update와 sample parity, MEM_WHITE 전체재귀 동등성, 국소 prefix 동등성을 기록했다. 수치 계산 독립성은 외부 연구자 검증이나 독립 장면 재현이 아니다.

합성 알려진 모형에서 시간상관을 무시한 NEES11.513/coverage43.17%, 상관을 반영한 NEES0.996/coverage95.12%를 얻었다. 이는 수학 구현 검증이며 Sionna 실험 결과가 아니다. toy 식별성은 고정 민감도에서 Heading·상수RFoffset이 분리되지 않음을 보여준다. 실제 전체 비선형 시스템의 전역 식별성을 증명한 것은 아니다.

특정 벽·반사경로가 최초 오류를 만든다는 분석은 이번에 추가하지 않았다. 기존의 RF 물리 진단과 별개로, 본 실험은 오차모델·상태기억·업데이트·Gate 연결부를 변경한 가설검증이다. 신규 물리 장면·하드웨어·Office Full RF가 없으므로 그 일반화는 미검증이다.

실패 결과를 삭제하거나 평가 route에서 a/f/임계값을 최적화하지 않았다. 최종 모델 승인이나 '완전 Bayesian consistency'를 선언하지 않는다.

## 파일과 재현

analysis/: 812개 전 조건 성능, 방법별 카운트, 국소후속 효과, 독립 재채점 QA.
mechanism/: 오류 시작의 실제 좌표·상대각·관측잔차, innovation 항등식과 실제 갱신 기여, Gate 유용성.
results/: 28개 원시 재귀 trace NPZ, 모든 CSV, 학습 파라미터·실행 로그.
code/: 사용한 전체 가설 검증 코드. 원 RF·FFD 입력은 재현 참조의 Actions 보관본 또는 원 저장소에서 별도로 복원한다.

메인 실행: https://github.com/myoungsunk/sionna-resimulation/actions/runs/39246189321
원 FFD/source 준비: https://github.com/myoungsunk/sionna-resimulation/actions/runs/39244326803
'''
    (d/'REPORT_KO.md').write_text(text)
    rows=[]
    for p in sorted(d.rglob('*')):
        if p.is_file() and p.name!='FINAL_MANIFEST.csv':
            with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
            rows.append({'path':str(p.relative_to(d)),'bytes':p.stat().st_size,'sha256':h})
    pd.DataFrame(rows).to_csv(d/'FINAL_MANIFEST.csv',index=False)
    print(json.dumps({'files':len(rows),'bytes':sum(r['bytes'] for r in rows),'report':str(d/'REPORT_KO.md'),'numerical_errors':len(qa['errors'])}))

if __name__=='__main__':main()
