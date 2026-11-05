"""Explicit user-authorized R1-only Snowball orchestration; no E2 dispatch."""
import pathlib,sys,subprocess,json,time,hashlib,datetime
R=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from qclean_uwb.fp_sc.contracts import environment,write_json,sha256,git_head
E=pathlib.Path('research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_SELECTIVE_CORRECTION_001/E1_20261105')
ROOT=R/E/'CANDIDATE_REVISION_R1_20261105';OUT=ROOT/'RUN_001'
def command(args,name):
    start=time.monotonic()
    with (OUT/(name+'.log')).open('x') as f:p=subprocess.run(args,cwd=R,stdout=f,stderr=subprocess.STDOUT)
    write_json(OUT/(name+'_RECEIPT.json'),{'command':args,'exit_code':p.returncode,'elapsed_s':time.monotonic()-start,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()})
    print(name,'exit',p.returncode,flush=True)
    if p.returncode:raise RuntimeError('STOP:'+name)
def main():
    OUT.mkdir(parents=True,exist_ok=False)
    command([sys.executable,'-m','unittest','discover','-s','tests','-p','test_fp_sc_*.py','-q'],'TESTS')
    original=json.loads((R/E/'CODE_LOCK.json').read_text())['files']
    for p,h in original.items():assert sha256(R/p)==h,'OLD_CODE_DRIFT:'+p
    paths=list(original)+['src/qclean_uwb/fp_sc/candidate_revision.py','src/qclean_uwb/fp_sc/revision_corpus.py',
        'scripts/fp_sc_candidate_revision.py','scripts/check_fp_sc_candidate_revision.py','scripts/finalize_fp_sc_candidate_revision.py',
        'scripts/execute_fp_sc_candidate_revision.py','tests/test_fp_sc_candidate_revision.py',str(E/'CANDIDATE_REVISION_R1_20261105/CONTRACT_KO.md'),
        str(E/'INPUT_LOCK.json'),str(E/'METRIC_SPEC.json'),str(E/'SPLIT_MANIFEST.json'),str(E/'RUN_SNOWBALL_20261105_0643/RUN_001/ARTIFACT_HASHES.json')]
    hashes={p:sha256(R/p) for p in paths}
    baseline=R/E/'RUN_SNOWBALL_20261105_0643/RUN_001'
    for name,h in json.loads((baseline/'ARTIFACT_HASHES.json').read_text()).items():
        assert sha256(baseline/name)==h,'BASELINE_DRIFT:'+name
    lock={'schema':'FP_SC_E1_CANDIDATE_R1_EXECUTION_LOCK','authorized_by':'USER_CURRENT_REQUEST',
          'authorization_verbatim':'E1 후보 개정 재검증을 구현하고 스노우볼에서 V0·VA·VB·VAB 전체 50,560행 실행·검산까지 진행해. VAB 주안과 기존 실패 기록은 유지하고, 결과는 깃허브에 올려. 후속 선택기 연결 문제는 별도로 남기고 E2는 시작하지 마.',
          'implementation_commit':git_head(R),'primary':'VAB','scope':{'waveforms':6320,'modes':2,'arms':['V0','VA','VB','VAB'],'rows':50560,'selector_runs':0,'E2_GO':False},
          'files':hashes,'environment':environment(),'external_independent_accept':False,
          'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    oldenv=json.loads((R/E/'RUN_SNOWBALL_20261105_0643/ENV_LOCK.json').read_text())
    for key in ('python','packages','threads','system'):assert lock['environment'][key]==oldenv[key],key
    for p in paths:
        if p.startswith(('src/','scripts/','tests/')):
            data=subprocess.check_output(['git','show',git_head(R)+':'+p],cwd=R)
            assert hashlib.sha256(data).hexdigest()==hashes[p],p
    write_json(OUT/'EXECUTION_LOCK.json',lock)
    for arm in lock['scope']['arms']:
        command([sys.executable,'-u','scripts/fp_sc_candidate_revision.py','--arm',arm,'--lock',str(OUT/'EXECUTION_LOCK.json'),'--output',str(OUT/arm)],arm)
        command([sys.executable,'-u','scripts/check_fp_sc_candidate_revision.py','--arm',arm,'--lock',str(OUT/'EXECUTION_LOCK.json'),'--run',str(OUT/arm),'--output',str(OUT/(arm+'_CHECK'))],arm+'_CHECK')
    command([sys.executable,'scripts/finalize_fp_sc_candidate_revision.py',str(OUT)],'FINALIZE')
    print('R1_COMPLETE_STOP_BEFORE_E2',flush=True)
if __name__=='__main__':main()
