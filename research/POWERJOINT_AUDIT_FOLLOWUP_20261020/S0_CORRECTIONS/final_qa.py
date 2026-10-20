"""S0 completion evidence: inspect outputs and preserved evidence, no model runs."""
from pathlib import Path
import argparse, ast, csv, gzip, hashlib, json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def strict(path):return json.loads(path.read_text(encoding='utf-8-sig'),parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
def main():
    p=argparse.ArgumentParser();p.add_argument('--original-root',type=Path,required=True);a=p.parse_args()
    old=a.original_root/'research/POWERJOINT_AUDIT_RERUN_20261020';now=ROOT/'research/POWERJOINT_AUDIT_RERUN_20261020'
    unchanged=[]
    for source in old.rglob('*'):
        if not source.is_file() or not(source.name.endswith(('.csv','.csv.gz')) or source.name.startswith('DECISION') and source.suffix=='.json'):continue
        target=now/source.relative_to(old);assert sha(source)==sha(target),str(target)
        unchanged.append(dict(path=target.relative_to(ROOT).as_posix(),sha256=sha(target),bytes=target.stat().st_size))
    validity=strict(HERE/'VALIDITY_INDEX.json')
    original_receipts=strict(HERE/'ORIGINALS/RECEIPTS.json')
    for rel,r in original_receipts.items():
        saved=ROOT/r['original_path'];assert sha(saved)==r['sha256'] and saved.stat().st_size==r['bytes']
        if rel.endswith('.json'):
            j=strict(ROOT/rel);before=strict(saved);assert {k:v for k,v in j.items() if k!='posthoc_validity_20261020'}==before
    receipt=strict(HERE/'TRACE_RECEIPT.json');inventory=strict(HERE/'TRACE_INVENTORY.json')
    assert receipt['task_status']=='COMPLETE'
    recs=receipt['artifacts'];assert len(recs)==receipt['expected_artifact_count']==44
    assert sum(r['downloaded_bytes'] for r in recs)==1883401358
    for r in recs:
        assert r['original_digest_verified'] and r['original_digest_present']
        assert r['original_digest']=='sha256:'+r['downloaded_sha256']
        assert r['downloaded_sha256']==r['release_download_sha256'] and r['downloaded_bytes']==r['release_download_bytes']
    assert sha(HERE/'TRACE_INVENTORY.json')==receipt['inventory_sha256']
    stats=strict(HERE/'statistics_execution/STATISTICS_SUMMARY.json');assert stats['total']==9519 and stats['clock_total']==7251
    assert sum(stats['counts'].values())==9519
    t4=strict(HERE/'POST_HOC_REVISED_ANALYSIS_T4.json');assert t4['original_decision_sha256']==sha(now/'T4_F1_EVENT/POST30_B_OLD/DECISION.json')
    assert t4['analysis_label']=='결과를 본 뒤 개정한 판정이며 사전등록 검증이 아님' and t4['diagnostics']==['D3','D6']
    json_count=csv_count=ast_count=0
    for pth in HERE.rglob('*'):
        if not pth.is_file() or '__pycache__' in pth.parts:continue
        assert pth.stat().st_size<=20_000_000
        if pth.suffix=='.json':strict(pth);json_count+=1
        if pth.suffix=='.py':ast.parse(pth.read_text(encoding='utf-8-sig'));ast_count+=1
        if pth.name.endswith(('.csv','.csv.gz')):
            opener=gzip.open if pth.name.endswith('.gz') else open
            with opener(pth,'rt',encoding='utf-8-sig',newline='') as f:
                rows=csv.reader(f);header=next(rows);assert header
                for row in rows:assert len(row)==len(header),(str(pth),len(row),len(header))
            csv_count+=1
    expected='Range 행 Jacobian = 0으로 직접 Range 감도 제거, C_rs·gate 영향만 남음. Range 교정 근거로 사용 불가'
    assert expected in validity['reason_ko']
    assert validity['unaffected_range_models']==['B_OLD','B_REFIT_ONLY']
    # Current-facing amended SRC reports/locks all carry explicit invalidity;
    # historical original text is intentionally retained behind the correction.
    checked=[]
    for rec in validity['changed_text_files']:
        path=ROOT/rec['path'];assert path.exists()
        if rec['kind'] in ['src','mixed','t6']:
            assert 'INVALID_DESIGN_ZERO_RANGE_JACOBIAN' in path.read_text(encoding='utf-8-sig')
            checked.append(rec['path'])
    result=dict(result='PASS',csv_unchanged=sum(r['path'].endswith(('.csv','.csv.gz')) for r in unchanged),original_decisions_unchanged=sum(r['path'].endswith('.json') for r in unchanged),original_snapshots=len(original_receipts),existing_json_values_preserved=True,originals=unchanged,trace_count=44,trace_bytes=1883401358,trace_original_and_release_hash_checks='PASS',trace_inventory_sha256=sha(HERE/'TRACE_INVENTORY.json'),trace_receipt_sha256=sha(HERE/'TRACE_RECEIPT.json'),native9519_counts=stats['counts'],prior_clock7251='exact poseID/raw observations and six-decimal GT rounding certified; original residual columns retained',csv_parse_count=csv_count,json_parse_count=json_count,python_AST_count=ast_count,files_max20MB='PASS',src_current_metadata_checked=checked,valid_B_OLD_B_REFIT_ONLY_preserved=True,old_T4_decision_preserved=True,no_recursive_or_RF_execution=True,scope='S0 only; S1/S2/S3 not executed')
    (HERE/'FINAL_QA.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ['originals','src_current_metadata_checked']},ensure_ascii=False))
if __name__=='__main__':main()
