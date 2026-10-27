"""Read-only source analysis: contiguous prior-estimated-distance episodes."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
PRIMARY = {'R2_aA_m45', 'R4_aA_m0', 'R4_aB_m0'}

def main():
    lock = json.loads((ROOT / 'INPUT_LOCK.json').read_text(encoding='utf-8'))
    for item in lock['files']:
        assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest() == item['sha256']
    df = pd.read_csv(ROOT.parent / 'pol_azimuth_alloc/C3_PACKETS.csv.gz')
    rows, coverage = [], []
    for (case, bias, arm), g in df.groupby(['case', 'bias', 'arm']):
        g = g.sort_values('k').reset_index(drop=True)
        assert g.k.is_unique and g.t_s.is_monotonic_increasing
        near = (g.d_est_m < 1.5).to_numpy()
        starts = np.flatnonzero(near & ~np.r_[False, near[:-1]])
        ends = np.flatnonzero(near & ~np.r_[near[1:], False])
        assert len(starts) == len(ends)
        coverage.append(dict(case=case, bias=bias, arm=arm, primary=case in PRIMARY,
                             episodes=len(starts), has_pass=bool(len(starts))))
        for pid, (i, j) in enumerate(zip(starts, ends), 1):
            segment = g.iloc[i:j+1]
            start, end = float(g.t_s.iloc[i]), float(g.t_s.iloc[j])
            mn = segment.loc[segment.d_est_m.idxmin()]
            row = dict(case=case, bias=bias, arm=arm, primary=case in PRIMARY,
                       pass_id=pid, start_s=start, end_s=end, n=j-i+1,
                       min_d_est_m=float(mn.d_est_m), min_d_time_s=float(mn.t_s),
                       window_start_s=start-10, window_end_s=end+10,
                       record_start_s=float(g.t_s.min()), record_end_s=float(g.t_s.max()))
            # Audit both possible P3 boundaries without choosing an inference convention.
            for label, lo, hi in [('episode', start, end), ('window', start-10, end+10)]:
                row[label+'_pre30_complete'] = bool(lo-30 >= g.t_s.min())
                row[label+'_post30_complete'] = bool(hi+30 <= g.t_s.max())
                row[label+'_pre30_n'] = int(((g.t_s >= lo-30) & (g.t_s < lo)).sum())
                row[label+'_post30_n'] = int(((g.t_s > hi) & (g.t_s <= hi+30)).sum())
            rows.append(row)
        assert sum(r['n'] for r in rows if (r['case'], r['bias'], r['arm']) == (case, bias, arm)) == int(near.sum())
    pd.DataFrame(rows).to_csv(ROOT/'P2_PASSES.csv', index=False)
    pd.DataFrame(coverage).to_csv(ROOT/'P2_COVERAGE.csv', index=False)
    for item in lock['files']:
        assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest() == item['sha256']
    result = dict(status='P2_PASS', source_hashes_unchanged=True, no_replay=True,
                  episode_membership_count_exact=True, conditions=28,
                  primary_has_pass=all(r['has_pass'] for r in coverage if r['primary']),
                  overall_stage0='PENDING_DEFINITIONS_P1_P3_P4')
    assert result['primary_has_pass']
    (ROOT/'CHECKS.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(pd.DataFrame(rows).query("primary and bias == 'B0' and arm == 'BB'").to_string(index=False))

if __name__ == '__main__':
    main()
