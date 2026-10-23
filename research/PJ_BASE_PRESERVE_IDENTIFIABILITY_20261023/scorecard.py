"""S7 complete paired evidence, missing-run accounting, and per-case noninferiority."""
from __future__ import annotations
import itertools
import numpy as np
import pandas as pd
from .common import CASES,BIASES,SEEDS,require
from .numerics import paired_bootstrap,time_block_sensitivity


def compare(scores, arms, *, cases=CASES,biases=BIASES,seeds=SEEDS,margin=0.,channel='full',reference_arm='BASE'):
    df=pd.DataFrame(scores)
    require(not df.duplicated(['case','bias','channel','seed_idx','arm','window']).any(),'Duplicate score keys')
    rows=[];completeness=[]
    for case,bias in itertools.product(cases,biases):
        pop=df[(df.case==case)&(df.bias==bias)&(df.channel==channel)&(df.window=='stable_30_plus')]
        for arm in arms:
            if arm==reference_arm:continue
            B=pop[pop.arm==reference_arm].set_index('seed_idx');C=pop[pop.arm==arm].set_index('seed_idx')
            expected=set(seeds);missing_B=expected-set(B.index);missing_C=expected-set(C.index)
            complete=not missing_B and not missing_C and set(B.index)==expected and set(C.index)==expected
            finite_status=complete and (B.status=='PASS').all() and (C.status=='PASS').all()
            completeness.append(dict(case=case,bias=bias,arm=arm,reference_arm=reference_arm,channel=channel,complete=bool(complete),successful=bool(finite_status),
                missing_base=','.join(map(str,sorted(missing_B))),missing_candidate=','.join(map(str,sorted(missing_C)))))
            if not finite_status:
                rows.append(dict(case=case,bias=bias,arm=arm,reference_arm=reference_arm,channel=channel,conclusion='BLOCKED',reason='missing/failed runs are not dropped'));continue
            B=B.loc[list(seeds)];C=C.loc[list(seeds)]
            metrics=['heading_deg_mse','xy_cm_mse','radial_cm_mse','tangential_cm_mse','bias_dps_mse',
                     'heading_deg_q95','heading_deg_q99','xy_cm_q95','xy_cm_q99','heading_deg_peak','xy_cm_peak',
                     'heading_nees_log_deviation','xy_nees_log_deviation','pose_nees_log_deviation','all4_nees_log_deviation',
                     'heading_cov95_deviation','xy_cov95_deviation','pose_cov95_deviation','all4_cov95_deviation']
            for comp,thresholds in [('heading_deg',[1,2,5,10,20]),('xy_cm',[5,10,20,50,100])]:
                for threshold in thresholds:
                    metrics += [f'{comp}_above_{threshold:g}_duration_s',f'{comp}_above_{threshold:g}_longest_s']
            for metric in metrics:
                if metric not in B or metric not in C or not np.isfinite(B[metric]).all() or not np.isfinite(C[metric]).all():
                    rows.append(dict(case=case,bias=bias,arm=arm,reference_arm=reference_arm,channel=channel,metric=metric,conclusion='BLOCKED',reason='undefined metric'));continue
                if len(seeds)<2:
                    rows.append(dict(case=case,bias=bias,arm=arm,reference_arm=reference_arm,channel=channel,metric=metric,conclusion='INCONCLUSIVE',reason='one paired seed; uncertainty not estimable',n_pairs=len(seeds)))
                    continue
                report=paired_bootstrap(B[metric].to_numpy(),C[metric].to_numpy(),margin=margin)
                rows.append(dict(case=case,bias=bias,arm=arm,reference_arm=reference_arm,channel=channel,metric=metric,**report))
    return rows,completeness


def ledger(comparisons, *, candidates, population='7 cases x B0/L2 x 12 paired motion/initialization seeds', complete_protocol=True):
    df=pd.DataFrame(comparisons);out=[]
    for arm in candidates:
        d=df[df.arm==arm]
        required=d[d.metric.isin(['heading_deg_mse','xy_cm_mse'])] if 'metric' in d else d.iloc[:0]
        if len(required)==0 or (d.conclusion=='BLOCKED').any():status='BLOCKED'
        elif (required.conclusion=='CONTRARY').any():status='CONTRARY'
        elif (required.conclusion=='SUPPORT').all():status='SUPPORT'
        else:status='INCONCLUSIVE'
        # Accuracy support is NEVER promoted to overall success when tails/calibration are harmed or unresolved.
        other=d[~d.metric.isin(['heading_deg_mse','xy_cm_mse'])] if 'metric' in d else d.iloc[:0]
        overall=status if len(other) and (other.conclusion=='SUPPORT').all() else ('CONTRARY' if (other.conclusion=='CONTRARY').any() else 'INCONCLUSIVE')
        if status=='BLOCKED':overall='BLOCKED'
        out.append(dict(claim='BASE-preserving heading AND position improvement',arm=arm,accuracy_outcome=status,overall_outcome=overall,candidate_adoption='NOT_AUTOMATIC_MECHANISM_REVIEW_REQUIRED',
            population=population, complete_protocol=complete_protocol,
            controlled_factor='incremental polarization correction; original BASE range/gate/update contract unless separately named',
            limitation='fixed RF, previously inspected development routes; no unseen-scene claim; ORACLE excluded from candidate decisions',
            next_action='inspect the complete per-case table, not the best route median'))
    return out
