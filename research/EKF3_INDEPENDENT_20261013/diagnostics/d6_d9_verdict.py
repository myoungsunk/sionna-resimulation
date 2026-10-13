"""Exploratory D6-D9 hypothesis verdict with evidence checks (USER-RUN).

Not a scientific/independent-scene PASS oracle. Results are conditional on
single frozen RF scene and must not be used to select held-out test models.
All submitted stage results must have valid completion manifests and hashes.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from d6_d9_common import atomic_json, file_sha, finish, make_out, read_csv

ALLOWED = ('SUPPORTED','PARTIALLY_SUPPORTED','NOT_SUPPORTED','INCONCLUSIVE')


def verified(root: Path | None, stage: str, filename: str):
    if root is None:
        return None
    man=root/(stage+'_MANIFEST.json')
    if not man.is_file():
        raise FileNotFoundError('Stage not complete: '+str(man))
    data=json.loads(man.read_text(encoding='utf-8'))
    if data.get('stage')!=stage or data.get('scientific_PASS') is not False:
        raise RuntimeError('Incorrect stage manifest: '+stage)
    p=root/filename
    if not p.is_file() or file_sha(p)!=data['sha256'].get(filename):
        raise RuntimeError('Missing or drifted stage evidence: '+str(p))
    return read_csv(p)


def metrics(rows, *, condition=None, arm=None, method=None):
    return [r for r in rows if
        (condition is None or r.get('condition')==condition) and
        (arm is None or r.get('arm')==arm) and
        (method is None or r.get('method')==method)]


def summary(d6_mc, d6_bias, d6_d5, d7, d8, d9):
    findings=[]
    if d6_mc:
        straight=[r for r in d6_mc if r['path']=='straight' and
                  float(r['sigma_heading_deg'])>=17.]
        if straight:
            ratios=np.asarray([float(r['mc_over_ekf_forward_var']) for r in straight])
            second=np.asarray([abs(float(r['mc_forward_variance_m2'])-
                                 float(r['second_order_forward_variance_m2'])) for r in straight])
            ekf=np.asarray([abs(float(r['mc_forward_variance_m2'])-
                              float(r['ekf_forward_variance_m2'])) for r in straight])
            evidence={'straight_grid_points':len(straight),
                      'mean_mc_over_ekf_forward_variance':float(np.mean(ratios)),
                      'fraction_second_order_closer_than_ekf':float(np.mean(second<ekf))}
            support=float(np.mean(ratios))>1.25 and np.mean(second<ekf)>.75
            findings.append({'hypothesis':'H1_EKF_LINEARIZATION',
                'status':'PARTIALLY_SUPPORTED' if support else 'NOT_SUPPORTED',
                'evidence':evidence,
                'boundary':'Only exact noise-free pure-SE2 initial-heading synthetic grid; no RF'})
    if d6_bias:
        all_rows=[r for r in d6_bias if r['scenario']=='M2_BIAS_D0']
        base={(r['case'],r['seed'],r['level']):r for r in d6_bias
              if r['scenario']=='M0_NO_BIAS_D0' and r['variant']=='EKF3'}
        biased=[r for r in all_rows if r['variant']=='EKF3']
        pairs=[(r,base.get((r['case'],r['seed'],r['level']))) for r in biased]
        pairs=[(a,b) for a,b in pairs if b is not None]
        if pairs:
            ratio=[float(a['heading_rmse_deg'])/max(1e-12,float(b['heading_rmse_deg']))
                   for a,b in pairs]
            findings.append({'hypothesis':'H1_UNMODELLED_GYRO_BIAS',
                'status':'PARTIALLY_SUPPORTED' if np.mean(ratio)>1.1 else 'INCONCLUSIVE',
                'evidence':{'paired_case_seed_cells':len(pairs),
                            'biased_to_unbiased_heading_rmse_ratio':float(np.mean(ratio))},
                'boundary':'Same archived sensor simulation and frozen scene; bias not estimated in EKF3'})
    if d6_d5:
        findings.append({'hypothesis':'D6_D5_PRIOR_POSTERIOR_AUDIT',
            'status':'PARTIALLY_SUPPORTED',
            'evidence':{'audited_rows':len(d6_d5)},
            'boundary':'Recomputed source traces, not an independent RF scene'})
    else:
        findings.append({'hypothesis':'D6_D5_PRIOR_POSTERIOR_AUDIT',
            'status':'INCONCLUSIVE','evidence':{'status':'NOT_RUN'},
            'boundary':'Local original D5 NPZ not supplied; cannot claim audit completion'})
    if d7:
        full=[r for r in d7 if r['channel']=='full' and int(r['eval_after_30s'])]
        if full:
            total=np.asarray([float(r['full_minus_los_s']) for r in full]);
            selection=np.asarray([float(r['tap_selection_effect_s']) for r in full]);
            same=np.asarray([float(r['same_tap_channel_effect_s']) for r in full]);
            maxdiff=float(np.max(abs(total-selection-same)))
            if maxdiff>1e-9:
                raise RuntimeError('D7 MP attribution identity broken')
            findings.append({'hypothesis':'H2_MP_TAP_AND_SAME_TAP_INTERFERENCE',
                'status':'PARTIALLY_SUPPORTED' if np.std(total)>1e-6 else 'INCONCLUSIVE',
                'evidence':{'n_full_samples':len(full),
                    'rms_tap_effect_s':float(np.sqrt(np.mean(selection**2))),
                    'rms_same_tap_interference_s':float(np.sqrt(np.mean(same**2))),
                    'identity_max_error':maxdiff},
                'boundary':'D7 uses offline Full+LoS counterfactual only for attribution'})
    if d8:
        grp={}
        for r in d8:
            if r['variant'] not in ('Q0_FIXED','Q3_CIR_POL'):continue
            key=(r['heldout_route'],r['channel'],r['range_model'],r['target'])
            grp.setdefault(key,{})[r['variant']]=r
        paired=[(key,rec['Q0_FIXED'],rec['Q3_CIR_POL'])
                for key,rec in grp.items() if set(rec)=={'Q0_FIXED','Q3_CIR_POL'}]
        if paired:
            gains=[float(a['zero_mean_gaussian_nll_proxy'])-
                   float(b['zero_mean_gaussian_nll_proxy']) for _,a,b in paired]
            gain_rate=float(np.mean(np.asarray(gains)>0))
            findings.append({'hypothesis':'H3_CIR_QUALITY_PREDICTION',
                'status':'PARTIALLY_SUPPORTED' if gain_rate>=.75 else 'NOT_SUPPORTED',
                'evidence':{'paired_heldout_route_channel_targets':len(paired),
                            'fraction_Q3_lower_NLL_than_Q0':gain_rate,
                            'mean_Q0_minus_Q3_NLL':float(np.mean(gains))},
                'boundary':'LORO on one scene, not calibrated R or unseen-scene proof'})
    if d9:
        cells=[r for r in d9 if r['method'] in ('F0_ORIGINAL','F3_CIR_R') and r['arm']=='C']
        bycell={}
        for r in cells:
            k=(r['case'],r['channel'],r['condition'],r['level'],r['seed'],r['range_model'])
            if r['method'] in bycell.setdefault(k,{}):
                raise RuntimeError('Duplicate D9 method/arm/cell')
            bycell[k][r['method']]=r
        paired=[r for r in bycell.values() if len(r)==2]
        if paired:
            wins=sum(float(r['F3_CIR_R']['heading_rmse_deg'])<
                     float(r['F0_ORIGINAL']['heading_rmse_deg']) for r in paired)
            findings.append({'hypothesis':'H3_RECURSIVE_RF_FUSION_UTILITY',
                'status':'INCONCLUSIVE',
                'evidence':{'paired_F0_F3_joint_cells':len(paired),
                            'F3_heading_RMSE_win_fraction':wins/len(paired)},
                'boundary':'Ablation only; no independent confirmation-scene or calibrated consistency test'})
    names={x['hypothesis'] for x in findings}
    for code in ('H1_EKF_LINEARIZATION','H1_UNMODELLED_GYRO_BIAS',
                 'H2_MP_TAP_AND_SAME_TAP_INTERFERENCE','H3_CIR_QUALITY_PREDICTION',
                 'H3_RECURSIVE_RF_FUSION_UTILITY'):
        if code not in names:
            findings.append({'hypothesis':code,'status':'INCONCLUSIVE',
                 'evidence':{'status':'NOT_RUN'},
                 'boundary':'Required user-run stage output missing'})
    if any(f['status'] not in ALLOWED for f in findings):
        raise RuntimeError('Hypothesis verdict schema changed')
    return {'schema':'D6_D9_EXPLORATORY_HYPOTHESIS_VERDICT_V1',
            'scientific_PASS':False,'independent_rf_scene':False,
            'new_confirmatory_seed_validation':False,
            'hypotheses':findings,
            'interpretation':'Descriptive, no causal attribution from model performance alone'}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--d6-mc',type=Path,default=None)
    ap.add_argument('--d6-bias',type=Path,default=None)
    ap.add_argument('--d6-d5-trace',type=Path,default=None)
    ap.add_argument('--d7',type=Path,default=None)
    ap.add_argument('--d8',type=Path,default=None)
    ap.add_argument('--d9',type=Path,default=None)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    evidence=(verified(args.d6_mc,'D6_MC','D6_MC_MOMENT_COMPARISON.csv'),
              verified(args.d6_bias,'D6_BIAS','D6_BIAS_ROUTE_ABLATION.csv'),
              verified(args.d6_d5_trace,'D6_D5_TRACE_AUDIT','D6_D5_TRACE_COVARIANCE_AUDIT.csv'),
              verified(args.d7,'D7','D7_ORACLE_EVALUATION_LABELS.csv'),
              verified(args.d8,'D8','D8_CIR_QUALITY_VALIDATION.csv'),
              verified(args.d9,'D9','D9_RECURSIVE_FUSION_METRICS.csv'))
    verdict=summary(*evidence)
    out=make_out(args.out)
    file=out/'HYPOTHESIS_VERDICT.json'
    atomic_json(file,verdict)
    finish(out,'D6_D9_VERDICT',vars(args),[file],caveats=[
        'H1-H3 are exploratory scene-internal descriptive verdicts',
        'Absent D6 original local trace is explicitly NOT_RUN and INCONCLUSIVE',
        'No independent-scene or confirmation-seed scientific_PASS'])
    print('D6_D9_EXPLORATORY_VERDICT_DONE',str(out))

if __name__=='__main__':
    main()
