from pathlib import Path
import sys,json,hashlib,subprocess,datetime
OUT=Path(__file__).resolve().parent;FIG=OUT.parent;PREV=FIG/'distance_lut_mbvar_20261102_v3'
SHA='a9214294a0d1811c2a90a4137a0e4957393e01d8'
REPO=Path('C:/Users/Myoungsun Kim/dlp1102/publish_checkpoint_20261102')
REC=Path('C:/Users/Myoungsun Kim/dlp1102/DualLP_Physics_Link_Validation_20261101')
def digest(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    target=OUT/'CONTRACT_BB_MB_DISTANCE_LUT.json';assert not target.exists(),'APPEND_ONLY'
    previous=json.loads((PREV/'CONTRACT.json').read_text(encoding='utf-8'));lock=dict(previous['input_hashes'])
    assert all(digest(p)==h for p,h in lock.items()),'PARENT_INPUT_DRIFT'
    files=[PREV/'CONTRACT.json',PREV/'DISTANCE_CORRECTION_NODES.npz',PREV/'distance_lut.py',FIG/'lut_pole_fix_20261102_v3/pole_regularized_lut.py',REC/'results/tables/RECURSIVE_144_LOGICAL_SCORES.csv',REC/'results/FIXED_SELF_TRACE_INDEX.json',Path(__file__),OUT/'run_matched.py']
    cases=['R2_aB_m0','R4_aB_m0','R5_aB_m0'];biases=['B0','L0','L1','L2']
    for case in cases:
        files += [REC/f'recovered/inputs/traces/{case}_B0_CONTROL.npz',REC/f'recovered/inputs/rf/SAMPLES_{case}.json']
        for bias in biases:
            files.append(PREV/f'{case}_{bias}_MB_VAR_DISTANCE_LUT.npz')
            for arm in ['BB_ORIG','MB_VAR']:files.append(REC/f'results/traces/{case}__{bias}__{arm}__self.npz')
    gov=Path('C:/Users/Myoungsun Kim/.codex/research-governance')
    files += [gov/n for n in ['COMMON_CONTRACT.md','ROLE_PROPOSER.md','ROLE_IMPLEMENTER.md','ROLE_AUDITOR.md']]
    for p in files:lock[str(p)]=digest(p)
    pin='research/DUAL_LP_PAPER_GAP_20261030/OBSIDIAN_CHECKPOINT_20261102/paper/figures/'
    pinned={}
    for relative,local in [('distance_lut_mbvar_20261102_v3/distance_lut.py',PREV/'distance_lut.py'),('distance_lut_mbvar_20261102_v3/DISTANCE_CORRECTION_NODES.npz',PREV/'DISTANCE_CORRECTION_NODES.npz'),('lut_pole_fix_20261102_v3/pole_regularized_lut.py',FIG/'lut_pole_fix_20261102_v3/pole_regularized_lut.py'),('lut_observer_swap_20261102/replay_observer_swap.py',FIG/'lut_observer_swap_20261102/replay_observer_swap.py')]:
        raw=subprocess.check_output(['git','show',SHA+':'+pin+relative],cwd=REPO)
        h=hashlib.sha256(raw).hexdigest();assert h==digest(local);pinned[relative]=h
    c=dict(contract_id='DLP-LUT-BB-MB-MATCHED-001',status='FROZEN_EXECUTION_AUTHORIZED',role='PROPOSER then IMPLEMENTER; independent audit delegated to distinct agent by user',base_git_sha=SHA,base_repo='myoungsunk/sionna-resimulation',implementation_source_identity='Pinned observer/loader bytes and recovered runner; new harness identified by SHA256, not falsely attributed to old commit',
      authorization=['User confirmed contract freeze and paired24 replay','User explicitly authorized subagent independent audit'],governance=dict(policy='RESEARCH-GOVERNANCE-v1',source='local COMMON_CONTRACT and role files, SHA256 locked in inputs',repository_policy_checked_at=SHA,applicability='Repository docs/research-governance/COMMON_CONTRACT explicitly only covers MBVAR-INFO-* under MBVAR_CONTROLLED_INFO_20261029. This DLP-LUT contract is outside that scope. Local general policy governs; no automatic override of the old campaign.'),
      pinned_observer_sha256=pinned,cases=cases,biases=biases,bias_deg_s=[0,.01,.05,.20],scene='C0 Corridor',anchor=[10,0,2.65],tag_z=.45,mount_deg=0,sensor_seed=0,expected_score_counts={'R2':829,'R4':592,'R5':1265},score_count_each_arm=10744,
      arms={'BB_ORIG':dict(bg='BB',mode='orig',gate='self',mean='original2D BB donor',R='original control R[:,jb], no sigma addition'),'MB_VAR':dict(bg='MB',mode='var',gate='self',mean='original2D MB donor; same s mean as BB',R='same base R, add HAND sigma(rho_previous_posterior)^2 only to s diagonal')},
      controls='Same full z, 4state x/y/psi/bias, ds/gy/dt, x0/P0, Q, observer h/J, selfNIS threshold and original donor arrays; no refit or fixed-mask substitution; zero-mean R0 MULTIPATH_EKF is not BB_ORIG',
      observer='Original a921 DistanceLut: height2.2m, mount0, theta<88deg, fixed2deg grid, unchanged1/2deg Cartesian pole regularization, synthetic direct(actual)-direct10 nodes. Reuse exact archived cache; missing nodes generated from same banks/rule only; no result-based node tuning.',
      run_budget=dict(source_reference_validation_recursions=24,distance_lut_MB=12,distance_lut_BB=12,total_recursions=48,primary_paired_recursions=24,explanation='V1 MB12 parity runs are themselves the MB half of the paired24; do not run an additional duplicate MB12. Source24 are baseline verification only.'),
      gates=['V0 verify locks, keys/time/pose, donors, historicalSource24 replay parity','V1 disableddistance h/J parity, inherited math checks, MB12 fulltrace parity','V2 BB12 plus V1 MB12 paired24; full packet update/Joseph/R/gate checks and negative fixtures','V3 complete ledger, improvement/worsening counts, separate technical and scientific verdict, independent audit'],
      thresholds=dict(state_parity_abs=1e-10,P_parity_abs=1e-10,R_parity_abs=1e-12,gate_mismatch=0,hJ_parity_abs=1e-10,history_score_atol=1e-9,history_score_rtol=1e-10,update_abs=1e-10,fd_abs=2e-5,improvement_delta_deg_or_cm=1e-10),
      evaluation='All t>=30-1e-9, including rejected points; heading wrap in radians then degrees, XY metres to cm; NEES heading1/XY2/pose3 excludes bias; coverage1/2/3 chi-square95 cutoffs3.841458820694124/5.991464547107979/7.814727903251179; rates100*(1-RMSE_MB/RMSE_BB). Improvement if BB-MB>1e-10 metric units; worsening if < -1e-10; otherwise tie.',
      first_divergence='k indexed same pose/time; first componentwise abs(X_BB-X_MB)>1e-10 and first used-mask difference separately; record previous posterior and current prior/posterior x/P/R/nu/J/K/S/NIS for both. Candidate K reconstructed from logged prior/J/S, appliedK=0 when rejected.',
      negative_fixtures='Configuration/packet copies only, no extra full recursive arms: wrong zero mean, wrong R0, donor swap, omittedMBvariance, flipped selfgate/fixedgate, alteredmean. Validators must reject mutations; retain tests/results.',
      prohibited=['new RT','new training','third tap','5state','fixedmask replacement','MB_ORIG/BB_VAR ablation','LoS/FullR0 extra24','manuscript adoption','new GitHub push without request'],
      scientific_claims='One corridor, one RF realization, same sensor seed; 12 paired repeated conditions not12independent scenes. Synthetic source-bank LUT, not measured LUT. New counts reported even if mixed or worse; historical Source12/12 and8/12 only references verified anew. TechnicalPASS distinct from scientificSUPPORTED/MIXED/NOT_SUPPORTED; independentaudit separate.',
      input_hashes=lock,frozen_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    target.write_text(json.dumps(c,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'CONTRACT_SHA256.txt').write_text(digest(target)+'  '+target.name+'\n',encoding='utf-8')
    print('CONTRACT_FROZEN',digest(target),'locked_files',len(lock))
if __name__=='__main__':main()
