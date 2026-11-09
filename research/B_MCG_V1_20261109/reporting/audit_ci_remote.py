"""Independent artifact/provenance/numerical audit; never imports replay runtime.

All twelve CI OFF/ACTIVE_RS streams must have complete canonical local outputs
before the final PASS receipt is created. Latency and raw floating-byte anchor
digests are audited separately from scientific trace equality.
"""
from __future__ import annotations
import argparse
import base64
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import traceback
import zipfile
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT/'results/github_ci'
REPO = ROOT/'repo'
PACKAGE = Path('research/B_MCG_V1_20261109')
ORIGINAL = REPO/'research/FP_SC_RECOVERY_R0_R5_20261107/R45_sources'
ARCHIVES = ROOT/'restored/fp-b-route-heldout-calibration-42483593407/tmp/fp-b-calibration'
GIT_SHA = 'e3ddc9fa4371d899a08a2a873d2ee5cf32074a01'
SOURCE_COMMIT = 'c141839093d1a2e4a76f91eea632cb6467163e28'
N = {'R2': 979, 'R4': 742, 'R5': 1415}
STRATA = ('B_FROZEN', 'B_BIAS_COV')
MODES = ('OFF', 'ACTIVE_RS')
RUNTIME = ('mcg.py', 'experiment.py', 'ci_route.py')
SCALED_TOLERANCE = 1e-10  # Same existing source replay parity threshold.
TIMING = {'latency_ms', 'guard_ms'}
EXACT_FLOAT = {'t', 'anchor_index', 'history_end', 'rank'}
FINITE = ('x','P','prior','Pprior','h','H','mu','Reff','Rbase','K','nu','S',
          'beta','trial_delta','actual_delta','shadow_x','shadow_P','gate_nis','nis')
COVARIANCES = ('P','Pprior','shadow_P','Rbase','Reff','S')
cache = {}


def sha(p):
    p = Path(p)
    stat = p.stat()
    k = (str(p), stat.st_mtime_ns, stat.st_size)
    if k not in cache:
        h = hashlib.sha256()
        with p.open('rb') as f:
            for block in iter(lambda: f.read(1<<20), b''):
                h.update(block)
        cache[k] = h.hexdigest()
    return cache[k]


def blobsha(b):
    return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()


def objectsha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def read(p):
    return json.loads(Path(p).read_text())


def dump(p, obj):
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def require(condition, description):
    if not condition:
        raise AssertionError(description)


def arrays(p):
    with np.load(p, allow_pickle=False) as f:
        return {k: f[k] for k in f.files}


def numeric_difference(a, b):
    a = np.asarray(a)
    b = np.asarray(b)
    require(a.shape == b.shape, ('shape', a.shape, b.shape))
    require(np.array_equal(np.isnan(a), np.isnan(b)), 'NaN layout differs')
    require(np.array_equal(np.isposinf(a), np.isposinf(b)), '+Inf layout differs')
    require(np.array_equal(np.isneginf(a), np.isneginf(b)), '-Inf layout differs')
    finite = np.isfinite(a) & np.isfinite(b)
    d = np.abs(a[finite]-b[finite])
    scaled = d/np.maximum(1., np.abs(b[finite]))
    return {'max_abs': float(d.max(initial=0.)),
            'max_scaled': float(scaled.max(initial=0.)),
            'finite_values_compared': int(finite.sum()),
            'nan_layout_equal': True, 'infinity_layout_equal': True}


def numeric_pass(a, b, name):
    result = numeric_difference(a, b)
    require(result['max_scaled'] <= SCALED_TOLERANCE, (name, result))
    return result


def compare_metrics(remote, local):
    require(set(remote) == set(local), 'Metric key mismatch')
    result = {}
    for key in remote:
        if key.startswith('latency_'):
            continue
        result[key] = numeric_pass(remote[key], local[key], 'metric:'+key)
    return result


def own_anchor_check(a):
    checked = 0
    for k, digest in enumerate(a['anchor_sha256']):
        if not digest:
            continue
        index = int(a['anchor_index'][k])
        require(0 <= index < k, ('Invalid historical anchor', k, index))
        calculated = hashlib.sha256(np.asarray(a['prior'][index], dtype='<f8').tobytes()).hexdigest()
        require(calculated == digest, ('Anchor was not immutable prior', k, index))
        checked += 1
    return checked


def check_numeric_trace(a, route, archive, meta):
    n = N[route]
    for key, value in a.items():
        require(len(value) == n, ('Trace length', route, key, len(value), n))
    for key in FINITE:
        require(np.isfinite(a[key]).all(), ('Nonfinite executed field', key))
    require(np.array_equal(a['mask'], archive['mask']), 'Raw legacy gate changed')
    require(a['mask'].dtype == bool, 'Gate dtype')
    require(not np.any((a['used_r'] | a['used_s']) & ~a['mask']), 'Legacy rejection rescued')
    require(np.max(abs(a['K'][~a['used_r'], :, 0]), initial=0.) < 1e-12, 'Disabled range has nonzero K')
    require(np.max(abs(a['K'][~a['used_s'], :, 1]), initial=0.) < 1e-12, 'Disabled s has nonzero K')
    require(np.all((a['beta'] >= 0.) & (a['beta'] <= 1.)), 'Invalid beta')
    require(np.all(np.diff(a['t']) > 0.) and len(np.unique(a['pose_id'])) == n, 'Time/pose grain')
    cov = {}
    for key in COVARIANCES:
        smallest = float(np.linalg.eigvalsh(a[key]).min())
        asymmetry = float(abs(a[key]-a[key].swapaxes(-1,-2)).max())
        require(smallest >= -1e-12 and asymmetry <= 1e-10, ('PSD/symmetry', key, smallest, asymmetry))
        if key in ('Rbase','Reff','S'):
            require(smallest > 0., ('Observation covariance is not PD', key))
        cov[key] = {'minimum_eigenvalue':smallest,'max_asymmetry':asymmetry}
    latency = {}
    for key, metric in [('latency_ms','latency_total_p50_p95_p99_ms'), ('guard_ms','latency_guard_p50_p95_p99_ms')]:
        require(np.isfinite(a[key]).all() and (a[key] >= 0.).all(), ('Invalid latency', key))
        q = np.quantile(a[key], [.5,.95,.99])
        numeric_pass(q, meta['metrics'][metric], 'Recorded latency quantiles')
        latency[key] = {'p50_p95_p99_ms':q.tolist(),'max_ms':float(a[key].max()),'mean_ms':float(a[key].mean())}
    damped = a['mask'] & np.any(a['beta'] < 1., axis=1)
    require(int(damped.sum()) == meta['metrics']['guard_damped_legacy_accepted'], 'Damped-count receipt')
    sampling_period_ms = float(np.median(np.diff(a['t']))*1000.)
    return {'n':n,'finite_executed_fields':True,'legacy_mask_exact':True,
            'legacy_accepted_n':int(a['mask'].sum()),'damped_accepted_n':int(damped.sum()),
            'covariances':cov,'own_prior_anchor_digests_verified_n':own_anchor_check(a),
            'latency':latency,
            'latency_against_sampling':{'median_sampling_period_ms':sampling_period_ms,
                'total_latency_p99_within_median_sampling_period':bool(latency['latency_ms']['p50_p95_p99_ms'][2]<=sampling_period_ms),
                'fraction_rows_total_latency_over_median_sampling_period':float(np.mean(a['latency_ms']>sampling_period_ms)),
                'interpretation':'Observed synchronous per-update execution budget only. No asynchronous scheduler or optimized production implementation was tested.'}}


def compare_stream(remote, local):
    require(set(remote) == set(local), 'Trace schema differs')
    result = {'exact_fields':{},'floating_fields':{},'anchor_digest_comparison':{}}
    for key in remote:
        a,b = remote[key],local[key]
        require(a.shape == b.shape and a.dtype == b.dtype, ('Shape/dtype differs', key))
        if key in TIMING or key == 'anchor_sha256':
            continue
        if a.dtype.kind in 'bUSiu' or key in EXACT_FLOAT:
            require(np.array_equal(a,b), ('Exact decision/index field differs', key, int(np.sum(a!=b))))
            result['exact_fields'][key] = {'equal':True,'values':int(a.size)}
        else:
            result['floating_fields'][key] = numeric_pass(a,b,key)
    require(np.array_equal(remote['beta'] < 1.,local['beta'] < 1.), 'Damping activation differs')
    require(np.array_equal(remote['beta'] == 0.,local['beta'] == 0.), 'Channel drop differs')
    result['beta_action_classification_exact'] = True
    result['anchor_digest_comparison'] = {
        'remote_verified_n':own_anchor_check(remote),'local_verified_n':own_anchor_check(local),
        'different_raw_byte_digest_n':int(np.sum(remote['anchor_sha256']!=local['anchor_sha256'])),
        'interpretation':'Each digest is independently verified against its own immutable prior. Cross-platform floating-byte hashes need not match; anchor indices match exactly and prior values pass the numerical threshold.'}
    return result


def verify_zip(item, api_item):
    path = CI/item['name']
    digest = sha(path)
    require(path.stat().st_size == item['bytes'] == api_item['size_in_bytes'], 'Artifact size mismatch')
    require(digest == item['sha256'] == api_item['digest'].removeprefix('sha256:'), 'Artifact digest mismatch')
    require(api_item['workflow_run']['head_sha'] == GIT_SHA, 'Artifact commit differs')
    extracted = path.with_suffix('')
    members = 0
    with zipfile.ZipFile(path) as z:
        require(z.testzip() is None, 'ZIP CRC failure')
        for member in z.infolist():
            if member.is_dir():
                continue
            p = extracted/member.filename
            require(p.resolve().is_relative_to(extracted.resolve()), 'Unexpected ZIP path')
            data = z.read(member)
            require(p.read_bytes() == data, ('Extracted bytes differ', member.filename))
            members += 1
    return {'artifact_id':item['artifact_id'],'name':api_item['name'],'bytes':item['bytes'],
            'sha256':digest,'expires_at':api_item['expires_at'],'expired_at_query':api_item['expired'],
            'created_at':api_item['created_at'],'verified_extracted_file_count':members,
            'status':'SHA_API_DIGEST_CRC_AND_EXTRACTED_BYTES_MATCH'}


def run(allow_pending):
    api = read(CI/'API_EVIDENCE.json')
    require(api['run']['head_sha'] == GIT_SHA and api['run']['status'] == 'completed' and api['run']['conclusion'] == 'success', 'Run not successful exact commit')
    require(api['jobs']['total_count'] == 3 and all(j['conclusion']=='success' for j in api['jobs']['jobs']), 'Jobs not all successful')
    require(api['artifacts']['total_count'] == 3, 'Artifact count')
    git_code = {}
    for name in RUNTIME:
        record = api['commit_files'][name]
        data = base64.b64decode(record['content'])
        require(blobsha(data) == record['sha'], ('Git blob content digest', name))
        require(hashlib.sha256(data).hexdigest() == sha(REPO/PACKAGE/name), ('Current runtime differs from committed source', name))
        git_code[name] = {'git_blob_sha':record['sha'],'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
    expected_code = {k:v['sha256'] for k,v in git_code.items()}
    release_git = read(CI/'COMMITTED_RELEASE_LOCK.json')
    release_bytes = base64.b64decode(release_git['content'])
    require(blobsha(release_bytes)==release_git['sha'], 'Committed release lock blob digest')
    release_local = REPO/'research/FP_NATIVE_B_CAUSAL_ABLATION_20261108/RELEASE_INPUT_LOCK.json'
    require(read(release_local)==json.loads(release_bytes), 'Release lock semantic content differs')
    require(release_local.read_bytes() in (release_bytes, release_bytes+b'\n'), 'Unexpected release-lock byte difference')
    release_committed_sha = hashlib.sha256(release_bytes).hexdigest()
    result = {'schema':'B_MCG_CI_REMOTE_AUDIT_V1','status':'VERIFYING',
        'run_id':42600632209,'execution_git_sha':GIT_SHA,'original_source_commit':SOURCE_COMMIT,
        'audit_code_sha256':sha(Path(__file__)),'api_evidence_sha256':sha(CI/'API_EVIDENCE.json'),
        'runtime_code_from_exact_commit':git_code,
        'verification_scope':{'routes':list(N),'strata':list(STRATA),'modes':list(MODES),
            'remote_streams_expected':12,'source_baseline_replays_expected':6,
            'all_42_local_arms_reexecuted_remotely':False,
            'not_verified_remotely':'OBSERVE_ONLY, ACTIVE_R, ACTIVE_S, DR_ONLY, NAIVE_YAW_CLIP; all primary/secondary calibration, projection, recovery and synthetic analyses are outside this 12-stream CI replay.',
            'performance_adoption':False},
        'comparison_rules':{'floating_scaled_tolerance':SCALED_TOLERANCE,
            'scaled_difference':'abs(remote-local)/max(1,abs(local))',
            'decision_and_index_fields':'exact; also beta<1 and beta==0 exact',
            'nan_and_infinity_patterns':'exact',
            'latency':'validated independently and reported; not an equality condition',
            'anchor_digest':'verified within each stream against its own prior; floating-byte cross-platform digests are reported rather than required equal'},
        'artifacts':[],'routes':{},'streams':[],'pending_local_streams':[],
        'provenance_differences':{'ci_policy_lock':'primary-only lock 7b92acf… is the snapshot committed at dispatch',
            'release_lock':{'committed_git_blob_sha':release_git['sha'],
                'remote_sha256':release_committed_sha,'local_sha256':sha(release_local),
                'remote_bytes':len(release_bytes),'local_bytes':release_local.stat().st_size,
                'json_content_identical':True,
                'explanation':'The locally restored lock has one extra terminal newline. Its parsed object and all eight asset hashes/sizes are identical. CI is bound to the exact committed blob, and actual input assets are rehashed independently.'},
            'local_secondary_policy_lock':'final both-strata lock bf84d6… is recorded by later local secondary executions',
            'causal_effect':'The frozen experiment.active reads the lock only to record its SHA. The fixed diagnostic mode, tau and config are passed explicitly. No policy fitting or selected-policy dispatch occurs in these CI executions.',
            'policy_role_labels':'CI calls OFF and ACTIVE_RS predeclared_diagnostic. Local OFF uses parity_baseline; local ACTIVE_RS uses predeclared_tau2_diagnostic.'}}
    downloads = read(CI/'DOWNLOAD_RECEIPT.json')
    by_id = {v['id']:v for v in api['artifacts']['artifacts']}
    require(len(downloads)==3, 'Downloads count')
    for item in downloads:
        result['artifacts'].append(verify_zip(item,by_id[item['artifact_id']]))
    primary_lock = ROOT/'results/policy_primary_precheck/POLICY_LOCK.json'
    final_lock = ROOT/'results/policy_calibration_final/POLICY_LOCK.json'
    result['ci_primary_policy_lock_sha256'] = sha(primary_lock)
    result['local_final_policy_lock_sha256'] = sha(final_lock)
    source_hashes = None
    for route,n in N.items():
        artifact = CI/f'b-mcg-v1-{route}-42600632209'
        remote_repo = artifact/'home/runner/work/sionna-resimulation/sionna-resimulation'
        pkg = remote_repo/PACKAGE
        out = artifact/f'tmp/b-mcg-v1/{route}'
        summary = read(out/'CI_ROUTE_SUMMARY.json')
        require(summary['status']=='PASS_EXECUTION_PARITY_AND_NUMERICAL_CHECKS' and summary['phase']=='COMPLETE', 'CI route status')
        require(summary['route']==route and summary['execution_git_sha']==GIT_SHA, 'CI route identity')
        require((artifact/'tmp/b-mcg-v1/COMMIT_SHA.txt').read_text().strip()==GIT_SHA, 'Commit marker')
        require(summary['runtime_code_sha256_before']==expected_code==summary['runtime_code_sha256_after'], 'CI runtime hashes')
        for name,expected in expected_code.items():
            require(sha(pkg/name)==expected, ('Packaged runtime differs', name))
        manifest_count = 0
        for line in (artifact/'tmp/b-mcg-v1/EXECUTED_SOURCE_SHA256.txt').read_text().splitlines():
            expected,path = line.split(maxsplit=1)
            require(sha(remote_repo/path.strip())==expected, ('Packaged manifest mismatch', path))
            manifest_count += 1
        test_logs = {}
        for name,count in [('UNIT.log',27),('CALIBRATION_TESTS.log',5)]:
            log_path = artifact/'tmp/b-mcg-v1'/name
            log = log_path.read_text()
            require(log.rstrip().endswith('OK') and re.search(r'Ran '+str(count)+r' tests in ',log), ('Remote unit log',name))
            test_logs[name]={'passed_n':count,'sha256':sha(log_path)}
        protocol = summary['protocol']
        require(objectsha(protocol)==summary['protocol_sha256'], 'Protocol digest')
        require(objectsha(protocol['config'])==protocol['config_sha256']==summary['protocol_config_sha256'], 'Config digest')
        require(protocol['route']==route and protocol['expected_n']==n and protocol['strata']==list(STRATA) and protocol['arms']==list(MODES), 'Protocol scope')
        require(protocol['config']['tau_r']==2. and protocol['config']['tau_s']==2. and protocol['config']['span_s']==5., 'Predeclared diagnostic changed')
        require(protocol['new_parameter_training'] is False and protocol['production_activation'] is False, 'Unauthorized activation/training')
        require(sha(pkg/'EXPERIMENT_CONTRACT.json')==summary['experiment_contract_sha256']==sha(REPO/PACKAGE/'EXPERIMENT_CONTRACT.json'), 'Contract differs')
        require(sha(pkg/'POLICY_LOCK.json')==summary['policy_lock_sha256']==sha(primary_lock), 'CI lock differs from primary snapshot')
        archive_lock = read(pkg/'ARCHIVE_LOCK.json')
        require(sha(pkg/'ARCHIVE_LOCK.json')==summary['archive_receipt']['archive_lock_sha256']==sha(REPO/PACKAGE/'ARCHIVE_LOCK.json'), 'Archive lock')
        for member,expected in summary['archive_receipt']['members_sha256'].items():
            require(sha(ARCHIVES/member)==expected==archive_lock['files_sha256'][member], ('Archive member differs', member))
        acquisition = read(artifact/'tmp/fp-release-assets/ACQUISITION_RECEIPT.json')
        require(acquisition['status']=='PASS' and len(acquisition['files'])==8, 'Input acquisition receipt')
        require(acquisition['lock_sha256']==release_committed_sha, 'Committed release lock digest')
        for f in acquisition['files']:
            p = ROOT/'assets'/f['asset_name']
            require(sha(p)==f['sha256'] and p.stat().st_size==f['size'], ('Raw source input', f['asset_name']))
        staging = read(artifact/'tmp/b-mcg-v1/STAGE/INPUT_RECEIPT.json')
        require(staging['status']=='PASS_STAGED_HASHED_INPUTS' and staging['source_commit']==SOURCE_COMMIT and len(staging['files'])==11, 'Staging receipt')
        for f in staging['files']:
            if f['name'].endswith('_bank.npz'):
                p = ORIGINAL/f['name']
            else:
                staged_name = hashlib.sha256(f['name'].encode()).hexdigest()[:20]+'_'+Path(f['name']).name
                p = ORIGINAL.parent/'inputs'/staged_name
            require(sha(p)==f['sha256'] and p.stat().st_size==f['bytes'], ('Staged input', f['name']))
        baseline = summary['baseline_parity']
        require(baseline['status']=='PASS' and len(baseline['strata'])==2, 'Source baseline parity')
        if source_hashes is None:
            source_hashes = baseline['source_hashes']
        require(baseline['source_hashes']==source_hashes, 'Original source receipts differ across routes')
        for path,expected in source_hashes.items():
            require(sha(ORIGINAL/path)==expected, ('Original SourceFFD source differs', path))
        baseline_checks = {}
        for stratum in STRATA:
            old = arrays(ARCHIVES/route/f'{route}_{stratum}.npz')
            replay = arrays(out/'baseline'/f'{route}_{stratum}.npz')
            checked = {}
            for key in ('x','P','prior','Pprior','h','H','mu','Reff','K','nu','S'):
                checked[key] = numeric_pass(replay[key],old[key], 'Original baseline:'+key)
            require(np.array_equal(replay['mask'],old['mask']), 'Original baseline gate')
            baseline_checks[stratum] = checked
        job = next(j for j in api['jobs']['jobs'] if j['name'].endswith(route))
        seconds = lambda a,b: (dt.datetime.fromisoformat(b.replace('Z','+00:00'))-dt.datetime.fromisoformat(a.replace('Z','+00:00'))).total_seconds()
        step = next(s for s in job['steps'] if s['name']=='Replay source baselines and declared diagnostic guard')
        result['routes'][route] = {'summary_sha256':sha(out/'CI_ROUTE_SUMMARY.json'),
            'execution_git_sha':GIT_SHA,'protocol_sha256':summary['protocol_sha256'],
            'config_sha256':summary['protocol_config_sha256'],
            'runtime_manifest_files_verified':manifest_count,'raw_input_hashes_verified_n':8,'staged_input_hashes_verified_n':11,
            'unit_test_logs':test_logs,
            'original_source_files_verified_n':len(source_hashes),
            'archive_members':summary['archive_receipt']['members_sha256'],
            'source_baseline_comparison':baseline_checks,
            'job_id':job['id'],'job_elapsed_s':seconds(job['started_at'],job['completed_at']),
            'replay_step_elapsed_s':seconds(step['started_at'],step['completed_at']),
            'ci_route_elapsed_s':summary['elapsed_s']}
        require(len(summary['runs'])==4, 'Final CI stream count')
        require({(x['stratum'],x['mode']) for x in summary['runs']}=={(s,m) for s in STRATA for m in MODES}, 'CI arm membership')
        for member in summary['runs']:
            stratum,mode=member['stratum'],member['mode']
            mp,tp = out/member['metadata_relative_path'],out/member['trace_relative_path']
            meta = read(mp)
            require(sha(mp)==member['metadata_sha256'], 'CI metadata SHA')
            require(sha(tp)==member['trace_sha256']==meta['trace_sha256'], 'CI final trace SHA')
            require(meta['status']=='EXECUTED_RESEARCH_REPLAY' and meta['metrics']['n']==n, 'CI stream incomplete')
            require(meta['execution_git_sha']==GIT_SHA and meta['runtime_code_sha256']=={k:expected_code[k] for k in ('mcg.py','experiment.py')}, 'CI stream version')
            require(meta['source_hashes']==source_hashes, 'CI stream original model source')
            require(meta['config']==protocol['config'] and meta['config_sha256']==summary['protocol_config_sha256'], 'CI stream config')
            require(meta['archive_sha256']==sha(ARCHIVES/route/f'{route}_{stratum}.npz'), 'CI stream archive')
            require(meta['policy_lock_sha256']==sha(primary_lock) and meta['execution_policy_role']=='predeclared_diagnostic', 'CI diagnostic policy receipt')
            a=arrays(tp);old=arrays(ARCHIVES/route/f'{route}_{stratum}.npz')
            checked=check_numeric_trace(a,route,old,meta)
            if mode=='OFF':
                require(np.all(a['beta']==1.) and checked['damped_accepted_n']==0, 'OFF changed weights')
                for key in ('x','P','prior','Pprior','h','H','mu','Reff','K','nu','S'):
                    numeric_pass(a[key],old[key],'OFF archive:'+key)
            lp=ROOT/'results/active'/stratum/mode/f'{route}_{mode}.npz'
            lm=lp.with_suffix('.json')
            stream={'route':route,'stratum':stratum,'mode':mode,
                'remote_trace_sha256':sha(tp),'remote_metadata_sha256':sha(mp),'remote_checks':checked,
                'remote_metrics':meta['metrics'],
                'remote_environment':{k:meta[k] for k in ('python','numpy','scipy')},
                'remote_policy_lock_sha256':meta['policy_lock_sha256']}
            if not lp.is_file() or not lm.is_file():
                stream['reconciliation_status']='PENDING_CANONICAL_LOCAL_COMPLETION'
                result['pending_local_streams'].append(f'{stratum}/{route}/{mode}')
                result['streams'].append(stream)
                continue
            local_meta=read(lm);b=arrays(lp)
            require(local_meta['status']=='EXECUTED_RESEARCH_REPLAY' and local_meta['metrics']['n']==n, 'Local stream incomplete')
            require(local_meta['trace_sha256']==sha(lp), 'Local final trace SHA')
            require(local_meta['runtime_code_sha256']==meta['runtime_code_sha256'] and local_meta['source_hashes']==source_hashes, 'Local runtime/source differs')
            require(local_meta['config']==meta['config'] and local_meta['config_sha256']==meta['config_sha256'], 'Local runtime configuration differs')
            require(local_meta['archive_sha256']==meta['archive_sha256'], 'Local archive differs')
            require(local_meta['policy_lock_sha256']==sha(primary_lock if stratum=='B_FROZEN' else final_lock), 'Unexpected local lock snapshot')
            require(local_meta['execution_policy_role']==('parity_baseline' if mode=='OFF' else 'predeclared_tau2_diagnostic'), 'Unexpected local role')
            stream.update(reconciliation_status='PASS_REMOTE_LOCAL_TRACE_COMPARISON',
                local_trace_sha256=sha(lp),local_metadata_sha256=sha(lm),
                local_policy_lock_sha256=local_meta['policy_lock_sha256'],
                local_environment={k:local_meta[k] for k in ('python','numpy','scipy')},
                local_checks=check_numeric_trace(b,route,old,local_meta),
                comparison=compare_stream(a,b),metric_comparison=compare_metrics(meta['metrics'],local_meta['metrics']))
            result['streams'].append(stream)
    result['original_source_sha256']=source_hashes
    result['remote_streams_verified']=len(result['streams'])
    result['local_streams_reconciled']=sum(x['reconciliation_status']=='PASS_REMOTE_LOCAL_TRACE_COMPARISON' for x in result['streams'])
    result['remote_rows_total']=sum(x['remote_checks']['n'] for x in result['streams'])
    require(result['remote_streams_verified']==12, 'Not all twelve final remote streams verified')
    if result['pending_local_streams']:
        result['status']='PENDING_CANONICAL_LOCAL_COMPLETION'
        dump(CI/'CI_REMOTE_AUDIT_PROGRESS.json',result)
        if not allow_pending:
            raise RuntimeError(result['pending_local_streams'])
    else:
        result['status']='PASS_REMOTE_REPLAY_AND_LOCAL_RECONCILIATION'
        result['max_state_abs_difference']=max(x['comparison']['floating_fields']['x']['max_abs'] for x in result['streams'])
        result['max_beta_abs_difference']=max(x['comparison']['floating_fields']['beta']['max_abs'] for x in result['streams'])
        result['max_any_float_scaled_difference']=max(v['max_scaled'] for x in result['streams'] for v in x['comparison']['floating_fields'].values())
        result['all_gate_status_channel_use_and_damping_classifications_exact']=True
        require(result['local_streams_reconciled']==12, 'Local completion count')
        dump(CI/'CI_REMOTE_AUDIT.json',result)
        (CI/'CI_REMOTE_AUDIT_FAILURE.json').unlink(missing_ok=True)
        (CI/'CI_REMOTE_AUDIT_PROGRESS.json').unlink(missing_ok=True)
    print(json.dumps({k:result[k] for k in ('status','remote_streams_verified','local_streams_reconciled','pending_local_streams','remote_rows_total')},indent=2))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--allow-pending',action='store_true')
    args=p.parse_args()
    try:
        run(args.allow_pending)
    except BaseException as exc:
        dump(CI/'CI_REMOTE_AUDIT_FAILURE.json',{'status':'AUDIT_INCOMPLETE_OR_FAILED','error_type':type(exc).__name__,
            'error':str(exc),'traceback':traceback.format_exc(),'audit_code_sha256':sha(Path(__file__))})
        raise
