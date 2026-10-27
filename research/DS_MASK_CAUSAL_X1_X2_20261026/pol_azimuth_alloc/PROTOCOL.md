# 요청서: 편파 innovation의 ψ/방위각 배분과 접선 위치 calibration 진단

- 작성일: 2026-10-27 (KST)
- 대상 브랜치: research/ds-x1-x2-results-20261026 (기준 commit d2fe43a)
- 실행 범위: **기존 trace 재계산 + 측정 모델 평가만.** 필터 replay, 재학습, R/Q 변경은 하지 않는다.
- 결과 폴더(신규): research/DS_MASK_CAUSAL_X1_X2_20261026/pol_azimuth_alloc/
- 기존 산출물(X1, X2, E1–E4, geometry_physical, component_azimuth, tangent_ledger, cut_odo)은 수정하지 않는다.

## 0. 배경과 이번에 답할 질문
주 분석 6조건 oracle 진단: 편파 예측 방위각 오차→Heading bias 필요성·충분성; 추정 위치 방위각 이동은 편파 예측 위치 입력 순환 없이도 발생한다.
R2DIAG 배경: d<1.5m 잔차 RMS 0.010–0.015, V는 분산 기준 11–23배; 접선 1cm≈1°는 |∂s/∂β|≈|∂s/∂ψ| 근사에 의존; 4상태 NEES 10–32.
Q1 실제 H_s의 ∂s/∂β와 ∂s/∂ψ는 거리별로 얼마인가?
Q1b 위치 기인 편파 예측 오차가 측정 오차보다 큰가?
Q2 편파 innovation의 ψ/접선/반경 배분은?
Q3 σ_t와 σ_ψ가 실제 오차와 맞는가?
이번은 기술 진단이다. 2단계 개입은 별도 승인 후 수행한다.

## 1. 입력
E1 trace e1_e4/E1/{case}_{bias}.npz: t_s,pose_id,names,prior,x,Pprior,P,h,H,K,nu,acc,R,mu,truth_scoring_only.
E1 점수 e1_e4/SCORES.csv; case 정의 research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json(anchor,robot_z_m,mount_deg).
측정 모델 geometry_physical/geometry_model.py GeometryFFD; R2DIAG research/PJ_D0_CIR_P2_RECURSIVE_20261022/results_r2diag/{R2,R4,R5}_R2DIAG_PACKETS.csv.gz(pose_id,dist,g,V,e_true,r_base).
주 분석 R2_aA_m45,R4_aA_m0,R4_aB_m0×B0/L2. 나머지 8조건 보조 기술값, 판정 제외.
Arm A0=BB,A1=MB. names로 찾고 index 하드코딩 금지.
시간: 적분 t=0부터; 집계 t>=30s. Q3 오차/calibration은 모든 packet posterior; Q2는 수용 packet만.

## 2. 공통 정의
### 2.1 기하
h=a_z-robot_z_m; d=||p-a||; r=sqrt(d²+h²); u_r=(p-a)/d; u_t=(-u_r,y,u_r,x).
β=atan2(a_y-y,a_x-x); ∇β=u_t/d.
오차 축은 GT(_gt), H/gain 축은 prior 추정(_est), 거리 bin은 GT d.
### 2.2 오차
 e=p_hat-p; e_r=u_r(GT)^T e; e_t=u_t(GT)^T e (cm).
β_error=wrap(β(p_hat)-β(p)), ψ_error=wrap(ψ_hat-ψ) (deg). wrap=(-180,180].
### 2.3 H_s(Q1)
H_s=[h_x,h_y,h_ψ,h_b]; h_rad=H_s[:2]·u_r(est); h_tan=H_s[:2]·u_t(est) (1/m).
ds/dβ=h_tan*d_est (1/rad), ds/dψ=h_ψ (1/rad); 둘 다 pi/180 곱하여 1/deg.
κ=|ds/dβ|/|ds/dψ|. h_b=0 검산. 활성 cell 내부 해석적 Jacobian이며 tap/cell 불연속은 반영하지 않는다. fp_margin/cells diagnostics가 있으면 저장.
### 2.4 gain 배분(Q2)
k_s=K[:,1]; rad/tan은 est 축 투영, ψ=k_s[2], b=k_s[3].
a_rad=h_rad*k_s,rad; a_tan=h_tan*k_s,tan; a_ψ=h_ψ*k_s,ψ; a_b=h_b*k_s,b.
합=H_s k_s. share_x=a_x/(H_s k_s), 음수 보존.
수용 packet 실제 편파 증분: dψ=k_s,ψ ν_s(deg); dt=k_s,tan ν_s(cm); dβ=(dt/100)/d_est(deg); dr=k_s,rad ν_s(cm).
range 열 K[:,0]도 ψ/접선/반경 증분 기록. Δβ는 국소 미분 증분이며 유한 회전의 정확한 각도 차이가 아님.
### 2.5 calibration(Q3)
posterior P, prior Pprior도 같은 열에 _prior 접미사.
σ_t=sqrt(u_t(GT)^T P_xy u_t(GT)), σ_r=sqrt(u_r(GT)^T P_xy u_r(GT))(cm).
σ_β=(σ_t/100)/d_gt(deg), σ_ψ=sqrt(P_ψψ)(deg).
ρ_tψ=(u_t^T P_xy,ψ)/(σ_t[m]*σ_ψ[rad]). z_t=e_t/σ_t,z_r=e_r/σ_r,z_ψ=ψ_error/σ_ψ.
구간별 RMS(z),mean(z),coverage(|z|<1.96).
### 2.6 예측/측정 오차(Q1b)
GeometryFFD modes=None. ds_pos=h_s(p_hat_prior,ψ_hat_prior)-h_s(p_GT,ψ_hat_prior).
ds_ψ=h_s(p_GT,ψ_hat_prior)-h_s(p_GT,ψ_GT).
측정 오차 r_base는 case+pose_id join, B0/L2 공통. λ_pos=RMS(ds_pos)/RMS(r_base), λ_ψ 동일.
SourceFFD와 1e-12 이내 검산. batch 평가 허용.
### 2.7 고정 거리 bins
[0,.5),[.5,1),[1,1.5),[1.5,2),[2,3),[3,4),[4,6),[6,8),[8,∞) m.
case×bias×arm×bin n<30이면 지표 NA, 개수만 보존, 판정 제외.

## 3. 계산 단계
C0 필수 trace 필드 하나라도 없으면 중단. E1 Heading RMSE,bias,앵커 3D거리 RMSE 1e-10 재현. C0_TRACE_INVENTORY.json,C0_PARITY.json.
C1 H_s 분해: C1_PACKETS.csv.gz,C1_HS_BY_BIN.csv.
C1b 예측/측정: C1B_PACKETS.csv.gz,C1B_BY_BIN.csv.
C2 gain/증분: C2_PACKETS.csv.gz,C2_ALLOC_BY_BIN.csv.
C3 calibration: C3_PACKETS.csv.gz,C3_CALIB_BY_BIN.csv.
C4 DECISIONS.csv,figures/,RESULTS_KO.md.

## 4. 산출 형식
모든 packet 공통: case,route,bias,arm(BB|MB),k,pose_id,t_s,scoring,accepted,d_gt_m,d_est_m,bin.
C1 추가: h_x,h_y,h_psi,h_b,h_rad_per_m,h_tan_per_m,ds_dbeta_per_deg,ds_dpsi_per_deg,kappa,fp_margin(있을 때).
C1B: s_pred_est,s_pred_posGT,s_pred_allGT,ds_pos,ds_psi,r_base,e_true,V.
C2: nu_s,nu_r,S_ss,R_ss,HsKs,a_rad,a_tan,a_psi,a_b,share_rad,share_tan,share_psi,share_b,dpsi_pol_deg,dt_pol_cm,dbeta_pol_deg,dr_pol_cm,dpsi_rng_deg,dt_rng_cm,dr_rng_cm.
C3: e_r_cm,e_t_cm,beta_err_deg,psi_err_deg,sigma_r_cm,sigma_t_cm,sigma_beta_deg,sigma_psi_deg,rho_t_psi,z_r,z_t,z_psi; prior도 _prior.
구간 공통: case,bias,arm,bin,n.
C1: ds_dbeta_med,ds_dpsi_med,kappa_med,kappa_p10,kappa_p90,h_tan_med,h_rad_med (절댓값), frac_same_sign.
C1B: rms_ds_pos,rms_ds_psi,rms_r_base,lambda_pos,lambda_psi.
C2: share_psi_med,share_tan_med,share_rad_med,sum_dpsi_pol_deg,sum_dbeta_pol_deg,sum_dt_pol_cm,MB-BB delta_*.
C3: rms_e_t,mean_e_t,sigma_t_med,rms_z_t,mean_z_t,cov95_t; r,psi 동일; rho_t_psi_med.
DECISIONS: question,case,bias,arm,bin_group,metric,value,threshold,result(SUPPORT|NOT_SUPPORT|NA),note.
near<1.5,mid1.5–4,far>=4. packet 가중 통합; bin 중앙값 평균 사용 금지.

## 5. 고정 기술적 판정
BB 기준 near: Q1 .5<=medianκ<=2; Q1b λ_pos>3; Q2 median share_ψ>.5 AND >median share_tan; Q3 rms_z_t>2 AND >far rms_z_t.
MB 동일 지표와 차이 기술, 주 판정은 BB.
조건 단위 판정, route별 묶음, B0/L2 비독립. 유의성/동등성/일반화 금지. 사후 기준 변경 금지.
Q1 근사 불일치이면 실제 κ로 e*(d) 재계산표.

## 6. 그림
F1_kappa_by_d.png: 거리(log)별 |ds/dβ|,|ds/dψ|,κ 중앙값+p10–p90; route/case 패널; κ=1,.5,2.
F2_pred_vs_meas.png: 거리(log),편파비(log),RMS(ds_pos),RMS(ds_ψ),RMS(r_base),sqrt(V).
F3_allocation.png: BB/MB shareψ,tan,rad 선/막대, 음수 유지.
F4_calibration.png: 거리(log),RMS(z_t,z_r,z_ψ),BB/MB,1 기준선,.5m이하 강조.
F5_example_pass.png: R4_aB_m0 B0 앵커 통과 한 구간, 공통 t축 d,e_t,σ_t,ψ_error,σ_ψ,shareψ,dβ_pol,dψ_pol; BB/MB.
직접 렌더링하여 축/단위/겹침 검토. 조건 평균으로 상반된 결과를 숨기지 않는다.

## 7. 보고서 순서
1 요약표 Q1–Q3/Q1b route별 SUPPORT 수와 수치
2 실행/검산 C0,K1–K6,입력해시
3 Q1 F1/구간표/필요시 e*표
4 Q1b F2/표
5 Q2 F3/표/MB-BB
6 Q3 F4/표/σ_t 대 실제 e_t
7 사례 F5/2–3줄
8 한계: Jacobian 불연속 미반영,GT 오프라인,B0/L2 쌍,simulation RF
9 2단계 제안(실행하지 않음): Q2,Q3 각각 3그룹 중 >=2 SUPPORT일 때만 (a)near 접선 process noise 증가,(b)a+R_s를 σ_s²(d)로 교체,(c)b+접근1–4m 윈도우 방위각 고정. 각 arm 예측 포함.

## 8. 검산
K1 ∇β 해석 vs 수치 100점 1e-9.
K2 H_s b열=0,range행 ψ열=0 정확히.
K3 sum a=H_s k_s 1e-12.
K4 posterior-prior=K(ν⊙acc),위치/ψ,1e-10 (ψ wrap 고려).
K5 GeometryFFD modes=None vs SourceFFD h_s 1e-12.
K6 bin n 합=packet 표본수 정확히.
P/Pprior 대칭1e-12,최소 고유값>=-1e-12. 실패 즉시 중단/근거 저장.

## 9. 운영
PROTOCOL.md 실행전 저장/INPUT_LOCK.json 해시. 입력 전후 해시, 기존 결과 읽기 전용. OUTPUT_SHA256.json. pycache/pyc 제외. 완료후 commit/push 메시지에 "diagnostic only, no replay". 2단계 별도 승인.

## 실행 전 명세 보완 (기준 변경 아님)
요청의 수식/단계/산출/기준을 위 실행 프로토콜로 기록했다.
- 현재 HEAD 9ff1810, 기준 d2fe43a 대비 E1/geometry 입력 diff 없음. 기존 결과 수정 금지.
- |h_ψ|,|HsKs|<=1e-12는 해당 비율 NA, 유효 n 별도. 거리<=1e-9는 기하 정의 실패로 중단. 분모를 임의 clamp하지 않는다.
- 전체 packet 저장; K6는 all/scoring/scoring&accepted 세 모집단을 별도 대조. 본문 집계는 요청의 시간/수용 조건 준수.
- 그룹 통합은 n>=30 원래 bin들에 속한 eligible packet을 pool; valid 비율 표본도 >=30 필요.
- 3개 route 그룹은 R2_aA_m45,R4_aA_m0,R4_aB_m0. 실제 route ID는 R2/R4 두 개. 두 bias 모두 SUPPORT만 그룹 합의 SUPPORT; 불일치/NA 분리.
- e*의 목표 크기가 요청에 없어 측정 RMS와 동일한 1차 예측 오차를 만드는 접선오차 e*_noise=RMS(r_base)/|h_tan|와 1도 Heading과 등가인 e*_1deg=d*pi/180/κ를 함께 제공. 조건/구간 packet 중앙값. 인과/정확한 비선형 임계값 아님.
- F5는 GT d 최소인 t>=30 packet 중심 ±10s로 사전 정의; 가능하면 전체 20s. 셀 n<30는 구간 그림/판정 NA, raw 시계열은 그대로 표시.
