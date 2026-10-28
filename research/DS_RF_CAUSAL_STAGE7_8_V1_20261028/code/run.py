#!/usr/bin/env python3
"""Entry point. By design nothing executes at import time."""
from __future__ import annotations
import argparse,sys,traceback
from pathlib import Path
from dsreassess.io import Config,Context,StageWriter,PRIMARY,write_json
from dsreassess.stage12 import stage1,stage2
from dsreassess.stage34 import stage3,stage4
from dsreassess.stage56 import stage5,stage6

STAGES={'1':('01_range',stage1),'2':('02_residuals',stage2),
        '3':('03_RF_R_H',stage3),'4':('04_CUT_RT_factorial',stage4),
        '5':('05_full_observability',stage5),'6':('06_layout_bias_Q',stage6)}


def main(argv=None):
    p=argparse.ArgumentParser(description='Independent 2026-10-27 DS causal reassessment, code only until invoked')
    p.add_argument('--repo-root',required=True,type=Path,help='Git checkout with frozen E1 LFS data; HEAD contains 2ee7313')
    p.add_argument('--source-root',required=True,type=Path,help='Original frozen p2 snapshot (source of v_replay / banks)')
    p.add_argument('--artifacts-root',required=True,type=Path,help='Original frozen p2_artifacts snapshot')
    p.add_argument('--output-root',required=True,type=Path,help='New workspace outside repo/source; never overwrites stage directory')
    p.add_argument('--step',choices=['preflight','1','2','3','4','5','6','all'],required=True)
    p.add_argument('--cases',default='all',help='all, primary, or comma-separated exact IDs')
    p.add_argument('--biases',default='B0,L2',help='comma-separated B0,L2')
    p.add_argument('--fd-stride',default=20,type=int)
    p.add_argument('--block-seconds',default=8.0,type=float)
    p.add_argument('--cov-shrink',default=0.5,type=float)
    p.add_argument('--min-train-n',default=30,type=int)
    p.add_argument('--skip-source-hash',action='store_true',help='NOT RECOMMENDED, marks source identity UNVERIFIED')
    p.add_argument('--br-prior-std-m',default=0.08,type=float)
    p.add_argument('--br-q-std-m-sqrt-s',default=0.0,type=float)
    p.add_argument('--tangent-q-std-m-sqrt-s',default=0.01,type=float)
    p.add_argument('--post-exit-seconds',default=30.0,type=float)
    args=p.parse_args(argv)
    all_cases=('R2_aA_m45','R4_aA_m0','R4_aB_m0','R2_aA_m0','R2_aB_m0','R5_aA_m0','R5_aB_m0')
    cases=(all_cases if args.cases=='all' else PRIMARY if args.cases=='primary' else tuple(x.strip() for x in args.cases.split(',') if x.strip()))
    biases=tuple(x.strip() for x in args.biases.split(',') if x.strip())
    if not cases or not biases or not set(biases)<= {'B0','L2'}:
        p.error('cases and biases must be nonempty; B0/L2 only')
    cfg=Config(args.repo_root,args.source_root,args.artifacts_root,args.output_root,
               cases=cases,biases=biases,fd_stride=args.fd_stride,
               block_seconds=args.block_seconds,cov_shrink=args.cov_shrink,
               min_train_n=args.min_train_n,strict_source=not args.skip_source_hash,
               augmented_br_prior_std_m=args.br_prior_std_m,
               augmented_br_q_std_m_per_sqrt_s=args.br_q_std_m_sqrt_s,
               tangent_q_std_m_per_sqrt_s=args.tangent_q_std_m_sqrt_s,
               post_exit_seconds=args.post_exit_seconds)
    print('[PRECHECK] frozen paths/source/E1 manifest...',flush=True)
    ctx=Context(cfg)
    if args.step=='preflight':
        _=ctx.model  # Real SourceFFD bank checks; only writes in output scratch.
        for d in ctx.cases():
            print('READY',d.key,'n',len(d.t),'A_B',int(d.mask.sum()),flush=True)
        write_json(cfg.output_root/'PREFLIGHT.json',{'status':'INPUT_SOURCE_READABLE_NO_EXPERIMENT_EXECUTED',
                                                    'context':ctx.evidence_metadata()})
        return 0
    planned=tuple(STAGES) if args.step=='all' else (args.step,)
    for stage in planned:
        name,fn=STAGES[stage]
        # Previous-stage QA must have completed for the same case/bias selection.
        for prerequisite in (('1',) if int(stage)>=3 else ()) + (('2',) if stage=='3' else ()) + (('5',) if stage=='6' else ()):
            prev=cfg.output_root/STAGES[prerequisite][0]/'RUN_STATUS.json'
            if not prev.is_file():
                raise RuntimeError(f'Stage {stage} requires complete stage {prerequisite}: {prev}')
            import json
            rr=json.loads(prev.read_text(encoding='utf-8'))
            if rr.get('status')!='CODE_EXECUTION_PASS_NOT_SCIENTIFIC_VALIDATION':
                raise RuntimeError(f'Stage {prerequisite} not successfully completed')
            old=rr['inputs']['config']
            if not set(cases).issubset(set(old['cases'])) or not set(biases).issubset(set(old['biases'])):
                raise RuntimeError(f'Stage {prerequisite} did not cover the requested case/bias selection')
        wr=StageWriter(ctx,name)
        try:
            print(f'[START {stage}/6] {name}',flush=True)
            fn(ctx,wr)
            print(f'[DONE {stage}/6] {name}',flush=True)
        except BaseException as err:
            wr.json('RUN_FAILURE.json',{'stage':stage,'error':str(err),
                                        'traceback':traceback.format_exc()})
            print(f'[STOP {stage}/6] {err}',file=sys.stderr,flush=True)
            raise
    return 0


if __name__=='__main__':raise SystemExit(main())
