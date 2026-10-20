"""Publish the preregistered scope correction without rerunning the filter."""
import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    old = json.loads((HERE/'final_B_OLD/DECISION.json').read_text())
    post = json.loads((HERE/'POST30_B_OLD/DECISION.json').read_text())
    src = json.loads((HERE/'POST30_SRC_TAP/DECISION.json').read_text())
    refs = dict(zip([x['event'] for x in old['events']],
                    [7.751,5.393,1.798,4.340,1.775,-1.025,-3.079,-15.347,-4.330,-2.439]))
    rows=[]
    for a,b,c in zip(old['events'],post['events'],src['events']):
        assert a['event']==b['event']==c['event']
        rows.append(dict(event=a['event'],role=a['role'],historical_post30_skip_gain_deg=refs[a['event']],
                         canonical_global_t30_skip_gain_deg=a['skip_gain_deg'],
                         canonical_post30_skip_gain_deg=b['skip_gain_deg'],src_post30_skip_gain_deg=c['skip_gain_deg'],
                         src_sign_changed=c['sign_changed']))
    with (HERE/'EVENT_SCOPE_COMPARISON.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
    for version,sub,lock in [('B_OLD','POST30_B_OLD','PROTOCOL_LOCK_POST30.json'),
                             ('SRC_TAP','POST30_SRC_TAP','PROTOCOL_LOCK_SRC_POST30.json')]:
        d=HERE/sub
        m=json.loads((d/'MANIFEST.json').read_text())
        m.update(technical='COMPLETE_WITH_PRESERVED_D4_NONSPD',decision_scope='POST30',
                 scope_correction_preregistration_commit='52b121207b634f21fc6f86e60e75805fc5f3d18d',
                 protocol_sha256=sha(HERE/lock),filter_rerun=False,
                 outputs={p.name:sha(p) for p in d.iterdir() if p.is_file() and p.name!='MANIFEST.json'})
        (d/'MANIFEST.json').write_text(json.dumps(m,indent=2),encoding='utf-8')
    m=json.loads((HERE/'MANIFEST.json').read_text())
    m.update(primary_decision_scope='POST30',original_global_decision='final_B_OLD/DECISION.json',
             primary_decision='POST30_B_OLD/DECISION.json',src_primary_decision='POST30_SRC_TAP/DECISION.json',
             scope_correction_preregistration_commit='52b121207b634f21fc6f86e60e75805fc5f3d18d',
             protocol_post30_sha256=sha(HERE/'PROTOCOL_LOCK_POST30.json'),
             protocol_src_post30_sha256=sha(HERE/'PROTOCOL_LOCK_SRC_POST30.json'),
             scope_note='Original source contrasts are post-event30s, not global t>=30s. Both estimands preserved. No filter/parameter changes.')
    (HERE/'DECISION_GLOBAL_T30.json').write_bytes((HERE/'final_B_OLD/DECISION.json').read_bytes())
    (HERE/'DECISION.json').write_bytes((HERE/'POST30_B_OLD/DECISION.json').read_bytes())
    lines=['# T4 F1 이벤트 검증', '',
           'TECHNICAL: COMPLETE_WITH_PRESERVED_D4_NONSPD. 과학 판정: NOT_ESTABLISHED (B_OLD 및 SRC_TAP).', '',
           '고정 10개 이벤트의 POWER1/SKIP/D1/D2/D3/D5/D6 실행과 독립 채점을 완료했다. B_OLD와 SRC_TAP 각각 D4 5건은 교차공분산 제거 후 NONSPD로 실패했다. 공분산을 수리하거나 실패를 제외해 통과시키지 않았다.', '',
           '주 판정 구간은 원문과 같은 POST30(마지막 이벤트 RF 시점부터 30초 후까지)이다. 최초 lock의 GLOBAL_T30는 원문 효과량과 평가 범위가 달랐다. 결과를 지우지 않고 52b1212에서 범위 수정 lock을 먼저 커밋한 뒤 기존 POST30 행만 다시 집계했다. GLOBAL_T30 결과는 final_B_OLD/ 및 SRC_TAP/에 그대로 있다. 필터·RF·arm·임계값을 변경하지 않았다. 원문의 상세 끝점 구현은 확보되지 않아 완전한 수치 일치를 주장하지 않는다.', '',
           'D3/D4/D6 중 유해 이벤트에서 50% 이상 회수하면서 모든 고정 유익 이벤트의 안전성을 만족한 진단은 없다. F1 지지 이벤트는 0/5이며, 채널 제거만으로 설명된다는 기각 기준도 충족하지 않았다.', '',
           '| 이벤트 | 고정 역할 | B_OLD POST30 skip 개선 ° | SRC_TAP POST30 skip 개선 ° | SRC 부호 변경 |',
           '|---|---|---:|---:|---|']
    for r in rows:
        lines.append(f"| {r['event']} | {r['role']} | {r['canonical_post30_skip_gain_deg']:.6f} | {r['src_post30_skip_gain_deg']:.6f} | {r['src_sign_changed']} |")
    lines += ['', 'SRC_TAP에서는 tap 안의 range Jacobian이 0이므로 D2(s 제거)는 range-only update의 정보가 없어져 skip과 같아진다. 이를 관측 원인의 일반적 증거로 해석하지 않는다.', '',
              '## 주장하지 않는 것', '',
              '개입은 모두 ORACLE_DIAGNOSTIC이다. GT prior reset을 온라인 정책으로 제시하지 않는다. 독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다.']
    (HERE/'RESULTS_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    m['outputs']={name:sha(HERE/name) for name in ['DECISION.json','DECISION_GLOBAL_T30.json','EVENT_SCOPE_COMPARISON.csv','RESULTS_KO.md']}
    (HERE/'MANIFEST.json').write_text(json.dumps(m,indent=2),encoding='utf-8')
    print(json.dumps(dict(primary_scope='POST30',B_OLD=post['scientific'],SRC_TAP=src['scientific'],events=len(rows))))

if __name__=='__main__':
    main()
