#!/usr/bin/env python3
"""Stage2 statistics / Stage3 population / Stage5 Fisher audit, no 1/4/6 replay.

The original 450a21f code+data remains untouched.  Each stage writes a new
folder beneath an external output root. Failure always causes nonzero exit.
"""
from __future__ import annotations
import argparse
import json
import hashlib
import subprocess
import sys
import traceback
from pathlib import Path
import numpy as np
import pandas as pd
from dsreassess.io import Context,Config,StageWriter,write_json,sha256,PRIMARY,read_json
from dsreassess.stage12 import stage2_from_verified_cache
from dsreassess.stage34 import stage3
from dsreassess.stage56 import stage5

BASE_SHA='450a21fd38cf6be510d55352ae3741c8e808bc0a'
RELATIVE='research/DS_REASSESS_1_TO_6_20261027'
EXPECTED_ALL=('R2_aA_m45','R4_aA_m0','R4_aB_m0','R2_aA_m0',
              'R2_aB_m0','R5_aA_m0','R5_aB_m0')


def verify_patch_code_unchanged():
    manifest=Path(__file__).resolve().parent/'PATCHED_PY_SHA256.json'
    if not manifest.is_file():
        raise RuntimeError('PATCH_CODE_MANIFEST_MISSING: use APPLY_PATCH, not raw old ZIP')
    for rel,expected in read_json(manifest)['sha256'].items():
        p=Path(__file__).resolve().parent/rel
        if not p.is_file() or sha256(p)!=expected:
            raise RuntimeError(f'PATCHED_CODE_HASH_MISMATCH: {p}')


def verify_cached_source(old):
    root=old/'02_residuals'
    from dsreassess.io import sha256
    manifest=read_json(root/'OUTPUT_SHA256.json')
    needed=['RESIDUALS.csv.gz','CHECKS.json','MEASURED_FP_SHIFT_STRATA.csv',
            'SOURCE_GT_DIAGNOSTICS.csv']
    if not all((root/name).is_file() and manifest.get(name)==sha256(root/name)
               for name in needed):
        raise RuntimeError('OLD_STAGE2_INPUT_HASH_OR_MISSING: extract Git LFS/cached data')
    status=read_json(root/'RUN_STATUS.json')
    if status.get('status')!='CODE_EXECUTION_PASS_NOT_SCIENTIFIC_VALIDATION':
        raise RuntimeError('OLD_STAGE2_NOT_TECHNICAL_PASS')
    r3=old/'03_RF_R_H'
    if (not (r3/'SCORES.csv').is_file() or
        read_json(r3/'OUTPUT_SHA256.json').get('SCORES.csv')!=sha256(r3/'SCORES.csv')):
        raise RuntimeError('OLD_STAGE3_PARITY_REFERENCE_HASH_OR_MISSING')
    return {k:sha256(root/k) for k in needed}


def validate_selected_output(root,steps):
    results={}
    for step,folder in [('2','02_residuals'),('3','03_RF_R_H'),('5','05_full_observability')]:
        if step not in steps:continue
        path=root/folder
        status=read_json(path/'RUN_STATUS.json')
        if status.get('status')!='CODE_EXECUTION_PASS_NOT_SCIENTIFIC_VALIDATION':
            raise RuntimeError(f'NOT_PASS_{folder}')
        manifest=read_json(path/'OUTPUT_SHA256.json')
        for name,sha in manifest.items():
            if sha256(path/name)!=sha:raise RuntimeError(f'OUTPUT_HASH_MISMATCH {folder}/{name}')
        checks=read_json(path/'CHECKS.json')
        if not checks or any(x.get('status')!='PASS' for x in checks):
            raise RuntimeError(f'NO_REAL_CHECKS_PASS_{folder}')
        results[folder]={'n_checks':len(checks),'n_hashed_outputs':len(manifest)}
    if '3' in steps:
        val=read_json(root/'03_RF_R_H/LEGACY_ALL_PARITY.json')
        if val.get('status')!='PASS' or val.get('max_abs_diff',1)>1e-10:
            raise RuntimeError('Stage3 legacy all arm parity must pass')
        results['legacy_stage3_parity']=val
    if '5' in steps:
        qa=pd.read_csv(root/'05_full_observability/FISHER_INDEPENDENT_AUDIT.csv')
        chains=pd.read_csv(root/'05_full_observability/H_PHI_FD_CHAIN_AUDIT.csv')
        if (qa.empty or not qa.status.eq('PASS').all() or
                not set(chains.status).issubset({'STABLE_PASS','NONSMOOTH_SEPARATE'}) or
                not chains.status.eq('STABLE_PASS').any()):
            raise RuntimeError('Stage5 independent Fisher QA not usable')
        results['stage5_real_fisher_scenarios']=len(qa)
        results['stage5_stable_fd_checks']=int(chains.status.eq('STABLE_PASS').sum())
        results['stage5_nonsmooth_fd_separate']=int(chains.status.eq('NONSMOOTH_SEPARATE').sum())
    if '2' in steps:
        stats=pd.read_csv(root/'02_residuals/RESIDUAL_STATS.csv')
        need=['lag1_n_pairs','lag5_n_pairs','boot_8_status','boot_16_status',
              'boot_32_status','bootstrap_stability','original_origin_s']
        if stats.empty or any(n not in stats.columns for n in need):
            raise RuntimeError('Stage2 packet-aligned statistics absent')
        results['stage2_statistics_rows']=len(stats)
        results['stage2_bootstrap_stability_counts']=stats.bootstrap_stability.value_counts().to_dict()
    return results


STAGE_FOLDERS={'2':'02_residuals','3':'03_RF_R_H','5':'05_full_observability'}


def verify_stage_receipt(root,step,contract):
    receipt=read_json(root/f'PATCH_STAGE_{step}.json')
    if (receipt.get('status')!='STAGE_TECHNICAL_QA_PASS' or
            receipt.get('step')!=step or receipt.get('contract')!=contract):
        raise RuntimeError(f'STAGE_CONTRACT_MISMATCH_{step}')
    folder=root/STAGE_FOLDERS[step]
    for name in ('RUN_STATUS.json','OUTPUT_SHA256.json'):
        if receipt.get('receipt_hashes',{}).get(name)!=sha256(folder/name):
            raise RuntimeError(f'STAGE_RECEIPT_HASH_MISMATCH_{step}/{name}')
    validate_selected_output(root,(step,))
    return receipt


def record_stage_completion(root,step,contract):
    validation=validate_selected_output(root,(step,))
    folder=root/STAGE_FOLDERS[step]
    receipt={'status':'STAGE_TECHNICAL_QA_PASS','step':step,
             'contract':contract,'validation':validation,
             'receipt_hashes':{n:sha256(folder/n) for n in
                               ('RUN_STATUS.json','OUTPUT_SHA256.json')}}
    with (root/f'PATCH_STAGE_{step}.json').open('x',encoding='utf-8') as f:
        json.dump(receipt,f,indent=2,ensure_ascii=False,allow_nan=False)
    return receipt


def finalize_available(root,contract):
    # A per-stage invocation may complete the set, but never claims missing work.
    completed=[]
    for step in STAGE_FOLDERS:
        if (root/f'PATCH_STAGE_{step}.json').is_file():
            verify_stage_receipt(root,step,contract)
            completed.append(step)
    missing=[s for s in STAGE_FOLDERS if s not in completed]
    progress={'status':'PARTIAL_TECHNICAL_QA_PASS' if missing else
              'TECHNICAL_QA_PASS_NOT_SCIENTIFIC_ADOPTION',
              'completed_steps':completed,'missing_steps':missing,
              'contract':contract,'output_root':str(root)}
    if not missing:
        # Recheck all hashes and all stage-specific gates at finalization time.
        progress['validation']=validate_selected_output(root,tuple(STAGE_FOLDERS))
        final=root/'PATCH_V2_FINAL.json'
        if final.exists():
            if read_json(final)!=progress:
                raise RuntimeError('FINAL_RECEIPT_ALREADY_EXISTS_WITH_DIFFERENT_CONTENT')
        else:
            with final.open('x',encoding='utf-8') as f:
                json.dump(progress,f,indent=2,ensure_ascii=False,allow_nan=False)
    elif (root/'PATCH_V2_FINAL.json').exists():
        raise RuntimeError('FINAL_RECEIPT_EXISTS_WITH_INCOMPLETE_STAGE_SET')
    write_json(root/'PATCH_PROGRESS.json',progress)
    return progress


def make_args():
    p=argparse.ArgumentParser(description='Immutable 450a21f Stage2/3/5 audit-only rerun')
    p.add_argument('--repo-root',required=True,type=Path)
    p.add_argument('--source-root',required=True,type=Path)
    p.add_argument('--artifacts-root',required=True,type=Path)
    p.add_argument('--output-root',required=True,type=Path)
    p.add_argument('--step',required=True,choices=('preflight','2','3','5','all'))
    p.add_argument('--fd-stride',type=int,default=20)
    p.add_argument('--cov-shrink',type=float,default=.5)
    p.add_argument('--min-train-n',type=int,default=30)
    return p.parse_args()


def main():
    a=make_args()
    verify_patch_code_unchanged()
    repo=a.repo_root.expanduser().resolve()
    out=a.output_root.expanduser().resolve()
    old=repo/RELATIVE/'results'
    # Git checkout of the exact completed experiment is not rewritten.
    cmd=subprocess.run(['git','-C',str(repo),'rev-parse','HEAD'],
                       capture_output=True,text=True,check=True)
    sha=cmd.stdout.strip()
    if sha!=BASE_SHA:
        raise RuntimeError(f'EXACT_450a21f_CHECKOUT_REQUIRED: {sha}, expected {BASE_SHA}')
    if repo in out.parents or repo==out or out==old or out in old.parents:
        raise RuntimeError('NEW_OUTSIDE_GIT_OUTPUT_DIRECTORY_REQUIRED')
    inputs=verify_cached_source(old)
    cfg=Config(repo,a.source_root,a.artifacts_root,out,
               cases=EXPECTED_ALL,biases=('B0','L2'),
               fd_stride=a.fd_stride,cov_shrink=a.cov_shrink,
               min_train_n=a.min_train_n,strict_source=True,
               block_seconds=8.)
    ctx=Context(cfg)
    cases=list(ctx.cases())
    if len(cases)!=14:raise RuntimeError('EXACT_14_PAIRED_INPUT_CASES_REQUIRED')
    print('[PREFLIGHT] 450a21f exact, 14 E1 cells, prior Stage2/3 inputs SHA PASS',flush=True)
    base_detail={'base_commit':BASE_SHA,'source_reused_sha256':inputs,
                 'source_code_hashes':ctx.evidence_metadata()['package_code_sha256'],
                 'E1_reference_count':len(cases),
                 'unchanged_steps':['1','4','6'],'new_steps':['2','3','5']}
    contract=json.loads(json.dumps({
        'revision':'2.1',**base_detail,
        'config':ctx.evidence_metadata()['config'],
        'initial_input_sha256':ctx.evidence_metadata()['input_sha256'],
        'runner_sha256':sha256(Path(__file__).resolve()),
        'patched_manifest_sha256':sha256(Path(__file__).resolve().parent/'PATCHED_PY_SHA256.json'),
        'old_stage3_scores_sha256':sha256(old/'03_RF_R_H/SCORES.csv')},sort_keys=True))
    # Validate any completed stages before starting more work in this output root.
    for previous in STAGE_FOLDERS:
        if (out/f'PATCH_STAGE_{previous}.json').exists():
            verify_stage_receipt(out,previous,contract)
    if a.step=='preflight':
        _=ctx.model
        write_json(out/'PATCH_PREFLIGHT.json',dict(status='PASS_ONLY_PRECHECK',**base_detail))
        return 0
    planned=('2','3','5') if a.step=='all' else (a.step,)
    mapping={'2':('02_residuals',lambda w:stage2_from_verified_cache(ctx,w,old)),
             '3':('03_RF_R_H',lambda w:stage3(ctx,w)),
             '5':('05_full_observability',lambda w:stage5(ctx,w))}
    completed=[]
    for step in planned:
        if step=='3':
            verify_stage_receipt(out,'2',contract)
        name,fn=mapping[step]
        writer=StageWriter(ctx,name)
        try:
            print(f'[START] STAGE_{step} {name}',flush=True)
            fn(writer)
            record_stage_completion(out,step,contract)
            completed.append(step)
            checks=read_json(writer.dir/'CHECKS.json')
            print(f'[PASS] STAGE_{step}: {len(checks)} real checks',flush=True)
        except BaseException as exc:
            writer.json('RUN_FAILURE.json',{'step':step,'error':str(exc),
                           'traceback':traceback.format_exc()})
            raise
    record=finalize_available(out,contract)
    if record['missing_steps']:
        print('[PARTIAL] Verified stages: '+','.join(record['completed_steps'])+
              '; missing: '+','.join(record['missing_steps'])+'; no final verdict.',flush=True)
    else:
        print('[DONE] Stage 2/3/5 independently validated; Stage 1/4/6 not rerun.',flush=True)
    print(json.dumps(record,indent=2,ensure_ascii=False),flush=True)
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as err:
        print(f'[HARD STOP] {type(err).__name__}: {err}',file=sys.stderr)
        raise
