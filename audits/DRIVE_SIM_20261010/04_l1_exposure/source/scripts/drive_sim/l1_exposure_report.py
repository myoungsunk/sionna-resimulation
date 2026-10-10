"""Read saved exposure records, verify preservation, and write the Korean report."""
import json, pathlib, hashlib, subprocess, math, re
import numpy as np
ROOT=pathlib.Path(__file__).resolve().parents[2]
P=ROOT/'results/DRIVE_SIM_L1_EXPOSURE_20261008'
def rd(p): return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
def sh(p):
    h=hashlib.sha256()
    with pathlib.Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''): h.update(b)
    return h.hexdigest()
def wr(n,d): (P/n).write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
plan=rd(P/'PLAN.json'); match=rd(P/'REPLAY_MATCH.json'); result=rd(P/'OFFLINE_RESULT.json')
records=sum([rd(P/f'EXPOSURE_{s}.json') for s in plan['seeds']],[])
summ=rd(P/'SEED_SUMMARY.json'); intervals=rd(P/'CONTIGUOUS_SEGMENTS.json'); jac=rd(P/'HEADING_JACOBIAN.json'); verts=rd(P/'VERTEX_INDEX.json')
assert len(records)==23472 and len({(r['seed'],r['k']) for r in records})==23472
assert sum(r['evaluation'] for r in records)==9408
range_deltas=[]; max_geometry=0.; max_innovation_identity=0.
for seed in plan['seeds']:
    event=rd(P/f'EVENTS_{seed}.json'); replay=np.load(P/f'REPLAY_{seed}.npz')
    old=np.load(pathlib.Path(plan['source_checkout'])/'results/DRIVE_SIM_20261007/VALIDATION_REPAIR_20261008/METRICS_INDEPENDENT_CHECK_20261008'/f'distance_{seed}.npz')
    gate=np.array([[r['k'],0,r['nis'],float(r['accepted'])] for r in event['range']]); ref=old['gate_events'];ref=ref[ref[:,1]==0]
    assert np.array_equal(gate[:,[0,1,3]],ref[:,[0,1,3]])
    range_deltas.append(float(np.max(abs(gate[:,2]-ref[:,2])))); assert range_deltas[-1]<1e-10
    assert event['failure'] is None
    for e in event['s']:
        assert len(e['queries'])==1
        assert np.isfinite(np.array(e['state_before'])).all() and np.isfinite(np.array(e['covariance_before'])).all()
    for r in [r for r in records if r['seed']==seed]:
        x,y,heading=r['state_before'][:3];u=x-4.;v=y;rho=math.sqrt(max(u*u+v*v,1e-12))
        angles=[math.degrees(math.atan2(rho,2.2)),math.degrees(math.atan2(-v,u)),(math.degrees(math.atan2(-v,-u))-math.degrees(heading)+180)%360-180]
        max_geometry=max(max_geometry,max(abs(a-b) for a,b in zip(angles,r['angles'])))
        max_innovation_identity=max(max_innovation_identity,abs(r['innovation_direct_offline']-r['innovation']-r['delta_s']))
        assert all(np.isfinite(r[k]) for k in ['delta_s','direct_s','lut_s','R','S','innovation','nis','selection_component','fixed_tap_interpolation_component'])
        assert r['R']>0 and r['S']>0
assert max_geometry<1e-10 and max_innovation_identity<1e-12
preservation={k:sh(k)==v for k,v in {**plan['input_hashes'],**plan['source_preservation'],**plan['original_execution_source_hashes']}.items()}
assert all(preservation.values())
stage2=pathlib.Path(plan['l1_checkout']).parent/'SENSOR_V2_STAGE2_20261008/FINAL_REPORT_KO.md'; assert stage2.is_file()
repo={}
for name,root in [('original',pathlib.Path(plan['source_checkout'])),('isolated',ROOT)]:
    repo[name]={k:subprocess.check_output(cmd,cwd=root,text=True).strip() for k,cmd in dict(head=['git','rev-parse','HEAD'],branch=['git','branch','--show-current'],status=['git','status','--short'],remote=['git','remote','-v']).items()}
wr('VERIFICATION.json',dict(records=len(records),unique=True,finite=True,all_replay_matched=match['all_matched'],range_gate_nis_max=max(range_deltas),geometry_max_abs_deg=max_geometry,innovation_identity_max=max_innovation_identity,vertex_lut_max_abs=max(abs(v['s']-v['lut_vertex']) for v in verts),original_files_unchanged=all(preservation.values()),n_protected_files=len(preservation),stage2_report_sha256=sh(stage2),repositories=repo))
def stats(rr):
    return dict(n=len(rr),accepted=sum(r['accepted'] for r in rr),innovation_rms=float(np.sqrt(np.mean([r['innovation']**2 for r in rr]))),mean_nis=float(np.mean([r['nis'] for r in rr])),position_rmse=float(np.sqrt(np.mean([r['pre_s_position_error_m']**2 for r in rr]))),heading_rmse_deg=float(np.sqrt(np.mean([r['pre_s_heading_error_deg']**2 for r in rr]))),max_delta=max(abs(r['delta_s']) for r in rr)) if rr else dict(n=0)
groups={}
for label,rr in [('all',records),('mixed',[r for r in records if r['mixed_tap']]),('violation',[r for r in records if r['violation']]),('same_index_candidate',[r for r in records if not r['mixed_tap']]),('evaluation',[r for r in records if r['evaluation']])]:
    groups[label]={kind:stats(a) for kind,a in [('pre_gate',rr),('accepted',[r for r in rr if r['accepted']]),('rejected',[r for r in rr if not r['accepted']])]}
wr('ASSOCIATION_SUMMARY.json',groups)
viol=[r for r in records if r['violation']]; mixed=[r for r in records if r['mixed_tap']]
seedn=[sum(r['mixed_tap'] for r in records if r['seed']==s) for s in plan['seeds']]
seedv=[sum(r['violation'] for r in records if r['seed']==s) for s in plan['seeds']]
worst=max(records,key=lambda r:abs(r['delta_s']));longest=max(intervals,key=lambda r:r['n']);worstj=max(jac,key=lambda r:abs(r['difference']))
lines=[]
def add(t): lines.append(t)
add('# L1 결함의 기존 localization 노출·연관 분석 — 최종 보고서')
add('이번 실행은 R2-A-m0/P0 거리 조건부 모델의 기존 24 seed만 추적했다. 실제 LUT 조회 23,472회에서 극점 첫 셀 노출은 0회, tap 혼합 후보는 429회(1.828%), 직접 LoS와의 차이 |Δs|>0.01은 18회(0.0767%)였다. 위반 18회 중 15회가 수용됐다. 평가 mask의 9,408회에서는 혼합 후보와 기준 위반이 모두 0회였지만, 앞선 갱신의 누적 영향은 이번 관찰로 제거하거나 측정하지 않았다. **L1 FAIL, F01/F02 OPEN, scientific_PASS=false를 유지한다.**')
add('## 1. 질문 → 원래 기대값 → 실행 기준')
add(f"질문은 기존 필터가 두 결함을 실제로 조회했는가, 그때 예측·innovation·gating·추정 오차가 어떠했는가이다. 기대값은 사전 고정한 실제 조회 위치에서 기존 L1의 |Δs|≤0.01을 검사하는 것이다. 새 PASS 기준은 만들지 않았다. 원 500개 시험의 median 기준을 궤적 표본에 적용해 원 gate를 재판정하지도 않았다. 이번 표본은 독립 무작위 L1 시험이 아니라 필터 궤적이다.\n\n기준 HEAD는 `{plan['revision']}`, 별도 branch는 `{plan['branch']}`이다. 원 실행 checkout은 `{plan['source_checkout']}`, 이번 checkout은 `{ROOT}`이다. 이 HEAD의 **미커밋 filters.py·uncertainty.py·validation_repair.py**를 hash로 고정하고 그대로 복사했다. NEES≈321을 만든 구현은 sensor-v2가 아니라 legacy EKF/direct-s이다. sensor-v2 작업 checkout은 읽기 전용 증거로만 취급했다. 별도 checkout의 origin은 원 validation checkout의 로컬 경로이며 GitHub로 push하지 않았다. 원/별도 HEAD·branch·dirty·remote는 VERIFICATION.json, 시작 dirty는 GIT_STATUS_BEFORE.txt에 있다.")
add('실행 전에 PLAN.json으로 48개 입력 hash, 실행 source hash, 원 source 136개 보호 hash, seed 5000–5023, 979시점/seed, dt=0.2s, 최대 23,472조회·20,000신규 vertex·576미분점과 진단 선택 규칙을 고정했다. 실제 held-out mask는 기존 STEP5의 evaluation_indices 392개/seed, 시간 117.4–195.6s다. 원 calibration 241시점과 제외 조건을 다시 만들지 않고 저장 mask를 그대로 썼다. full RF 관측은 저장 H에서 기존 처리로 재사용했고 새 RF 채널은 생성하지 않았다.')
add('설정은 anchor=(4,0,2.65)m, robot z=0.45m, mount=0°, EKF, range·direct-s·odom-heading 활성, gate=6.6349, 기존 Q·R·prior 유지다. 거리 σ 테이블은 기존 [0.0196442374, 0.0666634661, missing], support=[2.72993610,11.37082345]m, fallback σ=0.0803431339를 **재보정 없이** 읽었다. thermal variance=0, s inflation=1. range σ=0.05, extra σ=0.05, offset=-0.5315983906m, quantization variance=0.001857863713m²다. 초기 prior std는 [0.1m,0.1m,5°,0.002094395rad,0.0104,0.0064], wheelbase=0.287m다. 전체 config와 seed별 실제 입력·초기 상태는 PLAN.json과 REPLAY_seed.npz에 남겼다. 초기화는 원 프로토콜의 truth 근처 오차 분포를 그대로 재현했으며, 갱신 중 truth나 직접 LoS 값을 필터에 공급하지 않았다.')
add('## 2. 질문 → 기대값 → 방법 → 실제 결과: 동일 실행인가')
add(f"저장 결과에는 post-update 상태·전체 공분산·gate가 있지만 pre-s 상태, 실제 조회·R·innovation이 없어 계측 replay가 필요했다. 원 필터를 상속한 별도 진단 harness가 반환값과 갱신을 바꾸지 않고 조회를 기록했다. 상태·공분산 비교 허용오차는 atol=rtol=1e-10, metric은 atol=1e-8/rtol=1e-10, gate decision은 동일성이다.\n\n24/24 seed의 상태와 공분산 최대 차이는 모두 **0**이다. s gate decision과 NIS가 일치하며, 별도 검산한 range gate decision도 일치하고 NIS 최대 차이는 {max(range_deltas):.3g}이다. 위치 RMSE 평균 {match['summary']['pos_rmse_m']:.9f}m, heading {match['summary']['heading_rmse_deg']:.9f}°, pose NEES(df=3) {match['summary']['nees_mean']:.9f}, 95% pose coverage=0이다. 이 숫자는 재생 동일성 확인이며 새 일관성 승인 기준이 아니다. covariance guard 중단은 0이다. REPLAY_MATCH.json에 seed별 원 metric 차이가 있다.")
add('초기 replay는 진단 코드의 NumPy 2 batched solve RHS 차원 오류로 첫 seed 저장 후 종료(exit 1)했다. 원 필터 결함으로 해석하지 않았다. 진단 RHS만 명시적 singleton 차원으로 고쳤고 HARNESS_BEFORE_NUMPY_FIX.py·HARNESS_AMENDMENT.json·ATTEMPT1_*를 보존했다. 다음 hash 검사에서 Windows CRLF와 문자열 hash 차이로 실행 전 중단(exit 1)했고, 실제 파일 bytes hash로 receipt를 정정했다. 두 실패 로그를 보존했다. 최종 replay/offline는 각각 exit 0이다. 기존 수치에 맞추는 tuning은 하지 않았다.')
add('## 3. 현재 계산 구조와 실제 조회')
add('코드 hs_lut.py:20의 los_h는 실제 LP±45 bank로 복소 LoS 채널을 만들고, LUT는 격자마다 CIR→first-path tap→두 RX port power→s=(P1−P2)/(P1+P2)를 먼저 계산해 저장한다. hs_lut.py:102의 trilinear는 이 처리된 s를 보간한다. hs_lut.py:138의 s_model은 추정 x,y,heading→θ,φ_TX,φ_RX와 chain-rule Jacobian을 계산한다. filters.py:285 update_s는 그 상태에서 R와 innovation을 구한 뒤 NIS gate, 수용시 Joseph 갱신을 한다. 따라서 각 vertex에서 선택된 tap이 다른 셀에서는 “각 tap의 s를 보간”과 “조회 위치에서 tap을 선택해 s 계산”이 다르다. 극점 첫 행은 θ=0에서 수평 방향이 사라져 물리적 yaw 대응이 달라지는 별개 문제다. 이 설명의 극점 원인 증거는 이전 Stage3 저장 결과이며 이번에 재실행하지 않았다.')
add('매 step predict→odom-heading→range→s 순서다. EVENTS_seed.json은 range 전 상태와 s 전 상태·전체 P, 실제 angles/angle gradient, 예측값, state Jacobian 6성분, z, port power, R,S, gate 전 innovation/NIS·accepted, 갱신 후 상태/P를 연결한다. EKF는 실제 LUT 조회가 s update당 1회이며 총 23,472회다. IEKF 반복·UKF sigma point·GSF component·필터 수치 Jacobian 추가 조회는 이 조건에 없다. 계측 후 J 검산용 추가 s_model 호출은 callback을 끈 **offline 진단**이며 실제 estimator 조회 횟수에 넣지 않았다. 갱신 후 상태의 polar_geometry는 offline 기하 검사이며 추가 실제 조회로 세지 않았다.')
add('조회 위치 직접 LoS는 기존 L1과 같은 10m·TX column 0·LP+45/LP−45 RX 순서·257주파수와 기존 Hann/padding/delay/threshold 기본 처리로 계산했다. 실제 route 거리의 LoS나 Sionna LoS가 아니다. 각 조회의 8개 vertex tap과 조회 tap을 기록했고, 독립 가중합 보간은 실제 LUT값과 <1e−12로 일치했다. 6,678 vertex의 직접 s와 기존 LUT vertex 최대 차이는 2.3731e−15로 입력·port 처리 동일성을 확인했다. vertex 5개는 이전 Stage3 CIR를 재사용, 6,673개만 새 analytic LoS로 계산했다. 직접 power ratio와 고정 tap ratio는 CIR 복소 성분에서 별도로 계산했다. Python math로 추정 상태→각도를 독립 검산한 최대 차이는 VERIFICATION.json에 있다. 하드웨어 패턴 정확성이나 L2를 입증하지 않는다.')
add('## 4. 실제 결과: 극점과 tap을 분리')
add(f"극점 첫 셀 0≤θ<2°는 실제 조회 0/23,472, 갱신 후 상태의 기하 노출도 {sum(r['post_state_polar_geometry'] for r in records)}회다. 최소 실제 θ={result['aggregate']['all']['min_theta']:.9f}°다. 따라서 이번 조건에서 θ=0.001°의 큰 yaw 대응 오류를 실제 조회 오류로 확인한 사례는 없다. 동일 물리적 yaw 극점 비교는 새 실제 대상이 없어 이번에 수행하지 않았고, 이전 저장 진단과 입력 hash만 확인했다. 다른 route·anchor·mount, 잘못된 초기 heading/position 등에서의 극점 노출은 UNKNOWN이다. 극점 결함 자체는 미수정·미해결이다.")
add(f"tap 혼합 후보는 429/23,472회, 모든 24 seed에 노출됐다. seed별 횟수는 {min(seedn)}–{max(seedn)}회, median {np.median(seedn):g}회다. 시간 범위는 81.4–104.8s, 가장 긴 연속 노출은 {longest['n']}시점/{longest['span_s']:.1f}s(92.4–96.2s)다. 429회 중 395회 수용, 34회 거절됐다. **혼합 후보 411회는 0.01 위반이 아니므로 위험 후보를 오류와 동일시하지 않는다.** 위반은 {sum(v>0 for v in seedv)}/24 seed에서 18회이며 97.0,104.6,104.8s에 발생했다. 연속 위반은 최대 2시점/0.2s다. 조회 시점/셀/8 vertex/선택 tap/분해값은 EXPOSURE_seed.json, 구간은 CONTIGUOUS_SEGMENTS.json에 있다.")
add(f"최대 위반은 seed {worst['seed']}, k={worst['k']}, t={worst['time_s']:.1f}s에서 Δs={worst['delta_s']:.9f}다. 고정한 조회 tap으로 vertex s를 다시 계산한 분해는 Δs=(s_LUT−interp(s_vertex_fixedtap))+(interp(s_vertex_fixedtap)−s_direct)이다. 이 사례의 선택 성분 {worst['selection_component']:.9f}, 같은 tap 보간 성분 {worst['fixed_tap_interpolation_component']:.9f}다. 18개 위반 전체에서 고정 tap 보간 성분 최대 절댓값은 {max(abs(r['fixed_tap_interpolation_component']) for r in viol):.9f}<0.01이며 선택 성분이 지배적이다. 원 관측 정의·판정은 실제 first-path 선택값으로 유지했다. 이 분해는 tap 선택 효과를 구분하는 진단이며 새 모델의 검증이 아니다.")
add('평가 mask는 117.4s부터 시작하므로 위 사건은 모두 평가 전이다. 평가 시점에는 혼합·극점·0.01 위반이 각각 0/9,408, 최대 |Δs|=0.001756712였다. 모든 같은-index 후보의 최대 |Δs|=0.003829379로 원 0.01보다 작았다. 이 관측 범위 밖을 자동 정상으로 판정하지 않는다. 조회 θ,φ_TX,φ_RX·heading에만 한정된 진단이고 시간적으로 상관된 궤적이므로 23,472회를 독립 반복으로 간주하지 않는다.')
add('## 5. innovation·gating·추정 오차의 연관')
add('gate 전 통계와 수용된 측정 통계는 아래처럼 분리했다. pooled RMS는 표본 기술통계이며 통계적 독립성이나 인과 검정의 표본 수가 아니다. SEED_SUMMARY.json에는 seed·mask·위험 분류별 pre_gate/accepted_only/rejected_only와 위치·heading 오차가 모두 있다. 위치 오차는 **s 갱신 직전**이므로 저장 최종 pose RMSE와 수치가 다르다.')
add('| 범위 | gate 전 n / 수용 n | gate 전 innovation RMS / 수용 RMS | gate 전 평균 NIS / 수용 평균 | s 전 위치 RMSE(m) |\n|---|---:|---:|---:|---:|')
for key,label in [('all','전체'),('mixed','tap 혼합'),('violation','0.01 위반'),('same_index_candidate','같은 index 후보'),('evaluation','평가 mask')]:
    a=groups[key]['pre_gate']; b=groups[key]['accepted'];add(f"| {label} | {a['n']} / {b['n']} | {a['innovation_rms']:.6f} / {b['innovation_rms']:.6f} | {a['mean_nis']:.6f} / {b['mean_nis']:.6f} | {a['position_rmse']:.6f} |")
add('위반에서 15회가 gate를 통과했다는 것은 L1 오차가 실제 수용 예측에 들어갔음을 뜻한다. 그러나 full RF innovation은 다른 RF mismatch, 현재 추정 오차, R, J와 P에도 의존한다. offline innovation_direct=innovation_LUT+Δs 관계는 독립 검산했지만 직접값을 실제 필터에 넣지 않았다. tap 혼합 시점의 위치 오차가 커도 같은 구간의 환경·운동·센서·과거 갱신 효과가 섞여 있다. 평가 구간의 큰 NEES와 rejection은 동시 L1 위반 없이 나타난다. 따라서 L1을 F02의 주원인으로 확정하거나 기여율을 계산할 수 없으며, 앞선 15회 수용의 누적 효과도 UNKNOWN이다.')
add('### Seed 단위 추적')
add('| seed | 혼합 n(비율%) | 위반 n(수용) | 최장 혼합 시점/span(s) | 최대 |Δs| | 전체 innovation RMS | 전체 NIS | s 전 위치 RMSE(m) | 평가 NEES |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|')
for s in plan['seeds']:
    a=next(z for z in summ if z['seed']==s and z['mask']=='all');g=a['groups'];bs=[z for z in intervals if z['seed']==s and z['mask']=='all' and z['type']=='mixed_tap'];b=max(bs,key=lambda z:z['n']);met=next(z['metrics'] for z in match['runs'] if z['seed']==s)
    add(f"| {s} | {g['mixed_tap']['pre_gate']['n']} ({100*g['mixed_tap']['pre_gate']['n']/978:.3f}) | {g['violation']['pre_gate']['n']} ({g['violation']['accepted_only']['n']}) | {b['n']}/{b['span_s']:.1f} | {g['all']['pre_gate']['max_abs_delta']:.6f} | {g['all']['pre_gate']['innovation_rms']:.6f} | {g['all']['pre_gate']['mean_nis']:.3f} | {g['all']['pre_gate']['pos_rmse']:.6f} | {met['nees_mean']:.3f} |")
add('## 6. heading Jacobian: 局所 계산과 한계')
add('사전 규칙대로 각 seed에서 top 2 혼합·위반·극점·같은 index 후보와 시간 quartile을 선택해 중복 제거했다. 총 192조회/384직접 평가다. 위치를 고정하고 body heading ±0.01°를 바꾸므로 φ_RX는 ∓0.01°로 변한다. 직접 central secant와 LUT chain-rule J_heading을 모두 s/radian으로 비교했다. θ/φ 단위 degree와 state heading radian을 섞지 않았다. 192개 모두 ±점과 중심의 직접 tap이 같았으나 이는 전체 셀의 매끄러움을 보장하지 않는다. tap 전환 경계를 가로지르는 일반적인 미분으로 해석하지 않았다.')
add(f"혼합 셀 48개에서 |J_direct−J_LUT| median=0.474425, max=1.367960/rad, 같은 index 후보 144개에서는 median=0.031137, max=0.099949/rad다. 위반 18개 median=1.037435/rad다. 최대 차이는 seed {worstj['seed']}, k={worstj['k']}: direct={worstj['direct_secant_per_rad']:.9f}, LUT={worstj['lut_jacobian_per_rad']:.9f}/rad, 직접 tap {worstj['taps']}다. 조회 주변 직접 tap이 유지돼도 **다른 tap vertex가 섞인 보간 곡면의 heading 기울기**는 크게 다를 수 있다는 증거다. 표본은 의도적으로 큰 오차를 포함하는 진단 선택이며 무작위 모집단 추정이 아니다. x,y Jacobian의 직접 finite difference와 epsilon 수렴, 모든 조회의 heading 미분은 미수행이다. 값 오차가 작아도 heading 정보량·P 갱신이 타당하다는 뜻은 아니다. 필터의 실제 J,R,P와 gate는 보존했으며 수정하지 않았다.")
add('## 7. 수정 우선순위와 다음 검증에 주는 의미')
add('**현재 R2-A-m0/P0 실패의 후속 비교 우선순위는 tap 보간 수정안 검증이 먼저다.** 실제 24 seed에 혼합 셀 노출이 있고 15개 위반이 수용됐으며, 같은 tap 국소 직접 secant와 LUT heading J도 다르기 때문이다. 다만 수정안은 별도 단계에서 관측 정의, vertex first-path 처리와 보간 순서, 원 L1 조건을 고정해 검증해야 한다. 이번 자료만으로 더 작은 grid 또는 고정 tap을 채택하지 않는다. 수정 전후 동일 입력·seed로 정확도와 일관성, 초기 노출 뒤 영향까지 비교해야 인과 영향에 접근할 수 있다. 이번에는 그 비교를 실행하지 않았다.')
add('**극점 처리는 near-vertical 적용 전에 반드시 해결할 높은 심각도의 좌표 계약 결함이다.** 기존 약 1.952 오류는 tap 오차보다 훨씬 크지만 이번 실제 조회에는 노출되지 않았다. 따라서 이 R2 결과의 직접 노출 설명을 위해 먼저 고칠 이유는 확인되지 않았다. 동일 physical yaw를 유지하는 θ→0 극한·azimuth wrapping 계약부터 정하고 원 pole 자료를 보존한 별도 수정 검증이 필요하다. 실제 노출 우선순위와 일반화 전 심각도 우선순위를 구분한다. 다른 route/anchor/mount 입력은 이번 선택에 없으므로 UNKNOWN이며 노출 0을 일반화하지 않는다.')
add('F01에는 원 L1 FAIL 외 L2와 관측모델 검증이 남아 있고, F02에는 covariance consistency 실패가 그대로 남는다. 이번 노출·연관 분석은 둘의 해결 선언이나 RF/production/하드웨어 PASS가 아니다. 기존 전체 결과도 자동 무효화하지 않는다. 극점 수정, tap 모델 수정, L2·Sionna, 새 RF/H-store, 후속 필터 비교, Q/R·prior·gate 변경, commit/push/merge는 모두 수행하지 않았다.')
add('## 8. 실행·파일·해시와 재현 방법')
add(f"작업 디렉터리 `{ROOT}`에서 다음 명령을 실행했다. prepare exit 0(약 4.92s), 최종 replay exit 0({match['elapsed_s']:.3f}s), offline exit 0({result['elapsed_s']:.3f}s). 시간은 해당 Python 단계의 wall-clock 기록이며 전체 대화·입력 탐색 시간을 제외한다. offline analytic LoS 신규 계산 {result['n_direct_los']:,}개(조회 23,472 + 신규 vertex 6,673 + 미분 384), 저장 vertex 5개 재사용. RF solver 실행은 0회다. 제한 CPU 재생 24회 외 localization Monte Carlo를 추가하지 않았다.")
add('```text\npy -3.10 -X utf8 scripts/drive_sim/l1_exposure.py prepare\npy -3.10 -X utf8 scripts/drive_sim/l1_exposure.py replay\npy -3.10 -X utf8 scripts/drive_sim/l1_exposure.py offline\npy -3.10 -X utf8 scripts/drive_sim/l1_exposure_report.py\n```')
add('prepare는 새 출력만 생성하도록 되어 있고, 재생에는 HARNESS_AMENDMENT.json의 실제 수정 진단 script hash가 적용된다. 원 PLAN.json은 덮어쓰지 않았다. Python 3.10 / NumPy 2.2.4 사용. PREPARE_L1_EXPOSURE.log, REPLAY_ATTEMPT1.log/2.log, REPLAY.log, OFFLINE.log, REPORT.log와 COMMANDS.json이 명령·exit 기록을 보존한다. 진단 script 본문 수정은 NumPy RHS correction만이며 실제 실행 source 변경은 0이다. 별도 checkout의 복사된 legacy 파일은 원 미커밋 source를 그대로 보존한다.')
add('주요 입력 SHA-256:')
for name in ['LP_plus45_bank.npz','LP_minus45_bank.npz','hs_lut_2deg.npy','H_R2_aA_m0.npy','freqs_hz.npy']:
    entry=next((k,h) for k,h in plan['input_hashes'].items() if pathlib.Path(k).name==name);add(f"- `{entry[0]}`: `{entry[1]}`")
add('실행 source 전체와 metadata·timeline·원 결과·24 NPZ·Stage3 진단 입력 hash는 PLAN.json이다. 원 source/입력 보존을 종료 시 다시 검산했으며 모든 보호 파일이 동일했다. Stage2 보고서의 존재와 hash는 VERIFICATION.json에 기록했다. 원 사전등록·bank·LUT·gate·결과를 수정하지 않았다.')
add('신규 파일 안내: l1_exposure.py 계측/직접 계산, l1_exposure_report.py 저장 자료 검산/보고서, REPLAY_seed.npz 실제 입력·상태·P·mask, EVENTS_seed.json pre/post 업데이트·실제 조회·R/J/innovation/NIS/gate, EXPOSURE_seed.json 직접 LoS·cell·tap·분해·오차, VERTEX_INDEX.json/CIR.npz vertex 원자료, HEADING_JACOBIAN.json/DERIVATIVE_CIR.npz 선택 미분과 복소 CIR, SEED_SUMMARY.json·CONTIGUOUS_SEGMENTS.json·ASSOCIATION_SUMMARY.json seed 기술통계, VERIFICATION.json 동일성/유효성/보존, OUTPUT_MANIFEST.json 신규 출력의 bytes·SHA-256. 각 중심 조회의 각도·직접 tap·두 power·s를 저장했고 복소 center CIR 전체는 중복 저장하지 않았다. 동결 bank·주파수·관측 옵션과 신규 script로 재계산 가능하다. 원 Stage3 5,925채널 계산과 500시험은 다시 실행하지 않았다.')
add('이 보고서의 판정은 저장 입력과 정확히 대응한 24 legacy seed에 한정된다. 미검증 범위는 다른 route/anchor/mount, 변경 모델의 인과 비교, 전체 위치 Jacobian, L2/full RF 물리 원인, production/hardware 일반화다. 필요한 다음 증거는 해당 조건의 실제 실행 입력·query trace와 별도 승인된 모델 수정 전후 비교이며, 이번 단계는 여기서 종료한다.')
# Avoid a pipe inside a table heading and non-Korean accidental label.
text='\n\n'.join(lines).replace('최대 |Δs| |','최대 abs(Δs) |').replace('局所 계산','국소 계산')+'\n'
text=re.sub(r'(?<=\|)\n\n(?=\|)', '\n', text)
(P/'FINAL_REPORT_KO.md').write_text(text,encoding='utf-8')
print('REPORT WRITTEN; protected files unchanged',len(preservation),'records',len(records),'range NIS max',max(range_deltas))
