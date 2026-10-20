"""Post-hoc D3/D6 reaggregation of frozen B_OLD POST30 rows, no filter runs."""
from pathlib import Path
import csv, hashlib, json
HERE=Path(__file__).resolve().parent
OLD=HERE.parents[2]/'research/POWERJOINT_AUDIT_RERUN_20261020/T4_F1_EVENT'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    path=OLD/'INTERVENTIONS.csv';decision=OLD/'POST30_B_OLD/DECISION.json'
    original_hash=sha(decision);old=json.loads(decision.read_text())
    with path.open() as f:rows=list(csv.DictReader(f))
    rows={(r['event'],r['arm']):r for r in rows if r['scope']=='POST30' and r['status']=='TECHNICAL_PASS'}
    def effect(event,arm):
        base=rows.get((event,'POWER1'));r=rows.get((event,arm))
        return None if base is None or r is None else float(base['heading_rmse_deg'])-float(r['heading_rmse_deg'])
    events=old['events'];safe={};safety=[]
    for arm in ['D3','D6']:
        checks=[]
        for e in events:
            if e['role']!='beneficial':continue
            skip=effect(e['event'],'SKIP');d=effect(e['event'],arm)
            ok=skip is not None and d is not None and skip<0 and -d<=-.5*skip
            checks.append(ok);safety.append(dict(event=e['event'],arm=arm,skip_gain_deg=skip,diagnostic_gain_deg=d,passes=ok))
        assert len(checks)==5;safe[arm]=all(checks)
    detail=[];support=[];channel=[]
    for e in events:
        eid=e['event'];skip=effect(eid,'SKIP');ratios={a:None if skip is None or skip<=0 or effect(eid,a) is None else effect(eid,a)/skip for a in ['D1','D2','D3','D6']}
        qualifies=[a for a in ['D3','D6'] if safe[a] and ratios[a] is not None and ratios[a]>=.5]
        if e['role']=='harmful':
            if qualifies:support.append(eid)
            if any(ratios[a] is not None and ratios[a]>=.5 for a in ['D1','D2']) and all(ratios[a] is not None and ratios[a]<.2 for a in ['D3','D6']):channel.append(eid)
        detail.append(dict(event=eid,role=e['role'],skip_gain_deg=skip,recovery_ratios=ratios,qualifying_safe_diagnostics=qualifies))
    verdict='SUPPORTED_BUT_LIMITED' if len(support)>=3 else 'FALSIFIED_FOR_TESTED' if len(channel)>=3 else 'NOT_ESTABLISHED'
    result=dict(analysis_label='결과를 본 뒤 개정한 판정이며 사전등록 검증이 아님',scientific=verdict,original_scientific=old['scientific'],original_decision_sha256=original_hash,input_csv_sha256=sha(path),scope='POST30: last event RF timestamp through +30s inclusive',diagnostics=['D3','D6'],excluded=dict(D4='INVALID_PSD_NOT_GUARANTEED; missing/failed D4 is not zero effect'),conservative_all_beneficial_safety=safe,supported_events=support,channel_only_events=channel,events=detail,safety=safety,D3_claim_boundary='D3 resets event-entry psi mean only, retains P and all other prior errors; cannot reject the entire prior mechanism',no_recursive_execution=True)
    (HERE/'POST_HOC_REVISED_ANALYSIS_T4.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    assert sha(decision)==original_hash
    print(json.dumps(dict(old=old['scientific'],new=verdict,supported=len(support),channel_only=len(channel),original_decision_unchanged=True)))
if __name__=='__main__':main()
