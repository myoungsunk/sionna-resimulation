#!/usr/bin/env python3
"""Two new frozen-RF experiments, NOT original Stage 1-6.

7: 2x2 Range low-frequency error x Polarization GT-oracle plus controls.
8: First-pass exit state/covariance donor x post-pass polarization oracle.
No network / no training / no edits to user source. New output root only.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import traceback
import numpy as np
import pandas as pd

from dsreassess.io import Config,Context,StageWriter,read_json,sha256,write_json
from dsreassess.causal_evidence import PRIMARY,CONTRACT_VERSION,stage7,stage8

BASE_SHA='4d2414a7238176b6e116cae2d10546e724b66b8d'
ALL_CASES=('R2_aA_m45','R4_aA_m0','R4_aB_m0',
           'R2_aA_m0','R2_aB_m0','R5_aA_m0','R5_aB_m0')
FOLDERS={'7':'07_rf_pol_factorial','8':'08_post60_handoff'}


def verify_code_lock():
    root=Path(__file__).resolve().parent
    manifest=read_json(root/'CAUSAL_CODE_LOCK.json')
    if manifest.get('base_commit')!=BASE_SHA or manifest.get('version')!=CONTRACT_VERSION:
        raise RuntimeError('CODE_LOCK_VERSION_OR_BASE_MISMATCH')
    for fn,hash_expected in manifest['files'].items():
        p=root/fn
        if not p.is_file() or sha256(p)!=hash_expected:
            raise RuntimeError(f'CAUSAL_CODE_SHA_MISMATCH: {p}')
    return sha256(root/'CAUSAL_CODE_LOCK.json')


def verify_checkout(root):
    q=subprocess.run(['git','-C',str(root),'rev-parse','HEAD'],capture_output=True,text=True,check=True)
    sha=q.stdout.strip()
    if sha!=BASE_SHA:raise RuntimeError(f'CHECKOUT_HEAD_MUST_BE_{BASE_SHA}_ACTUAL_{sha}')
    return sha


def verify_stage_dir(root,stage):
    loc=root/FOLDERS[stage]
    if not loc.is_dir():raise RuntimeError(f'MISSING_STAGE_{stage}')
    status=read_json(loc/'RUN_STATUS.json')
    if status.get('status')!='CODE_EXECUTION_PASS_NOT_SCIENTIFIC_VALIDATION':
        raise RuntimeError(f'NONPASS_STAGE_{stage}')
    manifest=read_json(loc/'OUTPUT_SHA256.json')
    for fn,expected in manifest.items():
        p=loc/fn
        if not p.is_file() or sha256(p)!=expected:
            raise RuntimeError(f'STAGE_{stage}_OUTPUT_HASH_MISMATCH {p}')
    checks=read_json(loc/'CHECKS.json')
    if not checks or any(x.get('status')!='PASS' for x in checks):
        raise RuntimeError(f'STAGE_{stage}_CHECKS_NOT_ALL_PASS')
    return {'stage':stage,'checks':len(checks),'hashed_outputs':len(manifest),
            'output_manifest_sha256':sha256(loc/'OUTPUT_SHA256.json')}


def ensure_contract(previous,contract):
    if read_json(previous)!=contract:
        raise RuntimeError(f'EXECUTION_CONTRACT_CHANGED {previous}')


def plan_contract(cfg,code_sha):
    return {'version':CONTRACT_VERSION,'base_commit':BASE_SHA,
            'code_manifest_sha256':code_sha,
            'cases':list(cfg.cases),'biases':list(cfg.biases),
            'repo_root':str(cfg.repo_root),'source_root':str(cfg.source_root),
            'artifacts_root':str(cfg.artifacts_root),'output_root':str(cfg.output_root),
            'fixed_mask':'A_B','Q_R_training':'FROZEN_NO_TUNING',
            'range_smoother':'centered original GT residual,2s,first GT pass +/-10s',
            'pol_smoother':'centered original GT residual,5s,whole route',
            'post60':'from end_s crossing, clipped before second pass/record end',
            'scientific':'GT-oracle interventions only; tests do not establish deployable model'}


def main(argv=None):
    p=argparse.ArgumentParser(description='Frozen RF decisive diagnostics, standalone additive overlay on 4d2414a')
    for arg in ('repo-root','source-root','artifacts-root','output-root'):
        p.add_argument('--'+arg,required=True,type=Path)
    p.add_argument('--step',choices=['preflight','7','8','all','verify'],required=True)
    p.add_argument('--cases',default='all',help='all (7) or primary (3) or explicit comma list')
    p.add_argument('--biases',default='B0,L2',help='B0,L2 (recommended paired)')
    args=p.parse_args(argv)
    cases=ALL_CASES if args.cases=='all' else PRIMARY if args.cases=='primary' else tuple(v.strip() for v in args.cases.split(',') if v.strip())
    biases=tuple(v.strip() for v in args.biases.split(',') if v.strip())
    if not cases or len(set(cases))!=len(cases) or not set(cases)<=set(ALL_CASES):
        p.error('unknown/duplicate/empty case selection')
    if not biases or len(set(biases))!=len(biases) or not set(biases)<={'B0','L2'}:
        p.error('unknown/duplicate/empty bias selection')
    code_sha=verify_code_lock();repo_root=args.repo_root.resolve()
    sha=verify_checkout(repo_root)
    cfg=Config(args.repo_root,args.source_root,args.artifacts_root,args.output_root,
               cases=cases,biases=biases,strict_source=True)
    contract=plan_contract(cfg,code_sha)
    output=cfg.output_root
    output.mkdir(parents=True,exist_ok=True)
    # Only status/receipts in fresh output root; never writes under repo/source.
    contract_path=output/'CAUSAL_CONTRACT.json'
    if contract_path.exists():ensure_contract(contract_path,contract)
    else:
        if args.step in ('8','verify'):
            raise RuntimeError('MISSING_STAGE7_CONTRACT: run --step 7 or all first')
        if any(output.iterdir()):
            raise RuntimeError('OUTPUT_ROOT_NOT_FRESH_OR_MISSING_CONTRACT')
        with contract_path.open('x',encoding='utf-8') as f:
            json.dump(contract,f,indent=2,ensure_ascii=False,allow_nan=False)
    if args.step=='verify':
        s7=verify_stage_dir(output,'7');s8=verify_stage_dir(output,'8')
        result=read_json(output/'CAUSAL_FINAL_QA.json')
        if result['contract_sha256']!=sha256(contract_path) or result['stages']!=[s7,s8]:
            raise RuntimeError('FINAL_RECEIPT_HASH_MISMATCH')
        print(json.dumps(result,indent=2,ensure_ascii=False));return 0
    ctx=Context(cfg)
    if args.step=='preflight':
        _=ctx.model
        for d in ctx.cases():
            p=ctx.first_pass(d.case['id'],d.bias)
            print('[READY]',d.key,'n=',len(d.t),'accepted=',int(d.mask.sum()),
                  'first GT pass=',p['start_s'],p['end_s'],flush=True)
        dest=output/'CAUSAL_PREFLIGHT.json'
        if dest.exists():raise RuntimeError('PREFLIGHT_RECEIPT_ALREADY_EXISTS')
        write_json(dest,{'status':'SOURCE_AND_E1_READABLE_NO_SCIENTIFIC_EXECUTION',
                         'contract_sha256':sha256(contract_path),
                         'input_metadata':ctx.evidence_metadata()})
        return 0
    steps=['7','8'] if args.step=='all' else [args.step]
    for step in steps:
        if step=='8':
            s7=verify_stage_dir(output,'7')
            if not (output/'CAUSAL_STAGE7.json').exists():
                raise RuntimeError('MISSING_STAGE7_RECEIPT')
            receipt=read_json(output/'CAUSAL_STAGE7.json')
            if receipt['stage']!=s7 or receipt['contract_sha256']!=sha256(contract_path):
                raise RuntimeError('STAGE7_RECEIPT_CONTRACT_MISMATCH')
        name=FOLDERS[step];writer=StageWriter(ctx,name)
        try:
            print('[START]',step,name,flush=True)
            (stage7 if step=='7' else stage8)(ctx,writer)
            result=verify_stage_dir(output,step)
            dest=output/f'CAUSAL_STAGE{step}.json'
            with dest.open('x',encoding='utf-8') as f:
                json.dump({'stage':result,'contract_sha256':sha256(contract_path)},
                          f,indent=2,allow_nan=False)
            print('[SUCCESS]',step,json.dumps(result),flush=True)
        except BaseException as ex:
            writer.json('RUN_FAILURE.json',{'error':str(ex),
                         'error_type':type(ex).__name__,'traceback':traceback.format_exc()})
            print('[ABORT]',step,str(ex),file=sys.stderr,flush=True)
            raise
    if (output/'CAUSAL_STAGE7.json').exists() and (output/'CAUSAL_STAGE8.json').exists():
        s7=verify_stage_dir(output,'7');s8=verify_stage_dir(output,'8')
        final={'status':'TECHNICAL_QA_PASS_NOT_SCIENTIFIC_CAUSAL_PROOF',
               'contract_sha256':sha256(contract_path),
               'stages':[s7,s8],
               'experiment':'GT offline 2x2 factor + first-pass donor x/P/post-s counterfactual',
               'scope':'7 routes x B0/L2 paired, pre-registered fixed 2/5s windows',
               'source_evidence_commit':sha,
               'claim_boundary':'Observed differences are model-based interventions, not independently identified physical mediators or deployable algorithm'}
        dest=output/'CAUSAL_FINAL_QA.json'
        if dest.exists():
            if read_json(dest)!=final:raise RuntimeError('FINAL_ALREADY_EXISTS_DIFFERENT_CONTRACT')
        else:
            with dest.open('x',encoding='utf-8') as f:
                json.dump(final,f,indent=2,ensure_ascii=False,allow_nan=False)
        print('[ALL DONE]',final['status'],flush=True)
    else:print('[PARTIAL] only selected stage complete; no final causal receipt',flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
