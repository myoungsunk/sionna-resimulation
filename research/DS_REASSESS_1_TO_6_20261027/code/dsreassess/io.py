"""Frozen-data adapters, manifest checks, case validation, and write isolation.

This module intentionally uses legacy v_replay ONLY to obtain the original
SourceFFD physics and previously specified sensor-input generator. It never
uses the legacy EKF update/predict to produce new experiment results.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
import hashlib, json, os, subprocess, sys
import numpy as np
import pandas as pd
from .numerics import wrap

BASE_REL = Path('research/DS_MASK_CAUSAL_X1_X2_20261026')
COMMIT = '2ee731336fc2b37ffcd67f96a07bdaf3dccc2898'
PRIMARY = ('R2_aA_m45','R4_aA_m0','R4_aB_m0')


def sha256(p: Path):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def check_real(path: Path, name: str, *, binary=False):
    if not path.is_file():
        raise FileNotFoundError(f"{name}: missing {path}")
    if path.stat().st_size == 0:
        raise RuntimeError(f"{name}: empty {path}")
    with path.open('rb') as f:
        prefix=f.read(130)
    if b'version https://git-lfs.github.com/spec/v1' in prefix:
        raise RuntimeError(f"{name}: Git LFS pointer, run `git lfs pull`: {path}")
    if binary and not prefix.startswith(b'PK'):
        raise RuntimeError(f"{name}: invalid ZIP/NPZ magic: {path}")
    return path


def read_json(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def write_json(p, obj):
    def convert(x):
        if isinstance(x,(np.integer,)):return int(x)
        if isinstance(x,(np.floating,)):return float(x)
        if isinstance(x, (np.bool_,)):return bool(x)
        if isinstance(x,Path):return str(x)
        if isinstance(x,np.ndarray):return x.tolist()
        raise TypeError(type(x).__name__)
    p=Path(p)
    p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False,default=convert)+'\n',encoding='utf-8')


def parquet_safe_csv(df, p):
    df.to_csv(p,index=False,float_format='%.16g',na_rep='NA')


@dataclass(frozen=True)
class Config:
    repo_root: Path
    source_root: Path
    artifacts_root: Path
    output_root: Path
    cases: tuple[str,...] = ('R2_aA_m45','R4_aA_m0','R4_aB_m0','R2_aA_m0','R2_aB_m0','R5_aA_m0','R5_aB_m0')
    biases: tuple[str,...] = ('B0','L2')
    fd_stride: int = 20
    block_seconds: float = 8.0
    cov_shrink: float = 0.5
    min_train_n: int = 30
    strict_source: bool = True
    augmented_br_prior_std_m: float = 0.08
    augmented_br_q_std_m_per_sqrt_s: float = 0.0
    tangent_q_std_m_per_sqrt_s: float = 0.01
    post_exit_seconds: float = 30.0

    def __post_init__(self):
        for name in ('repo_root','source_root','artifacts_root','output_root'):
            object.__setattr__(self,name,Path(getattr(self,name)).expanduser().resolve())
        if not 0 <= self.cov_shrink <= 1:
            raise ValueError('cov-shrink must be in [0,1]')
        if self.fd_stride < 1 or self.block_seconds <= 0 or self.min_train_n < 2:
            raise ValueError('fd-stride/block-seconds/min-train-n invalid')
        if self.augmented_br_prior_std_m <= 0 or self.tangent_q_std_m_per_sqrt_s < 0:
            raise ValueError('process/bias std invalid')
        if self.post_exit_seconds <= 0:
            raise ValueError('post-exit-seconds must be positive')
        if self.repo_root == self.output_root or self.repo_root in self.output_root.parents:
            raise ValueError('output-root MUST be outside the frozen Git checkout')
        if self.source_root == self.output_root or self.source_root in self.output_root.parents:
            raise ValueError('output-root MUST be outside the original frozen source snapshot')
        if self.artifacts_root == self.output_root or self.artifacts_root in self.output_root.parents:
            raise ValueError('output-root MUST be outside the frozen artifacts snapshot')


@dataclass
class CaseData:
    case: dict
    bias: str
    t: np.ndarray
    ids: np.ndarray
    truth: np.ndarray
    z: np.ndarray
    mu_b: np.ndarray
    mu_ex: np.ndarray
    mu_exds: np.ndarray
    mu_s: np.ndarray
    R: np.ndarray
    mask: np.ndarray
    controls: dict
    x0: np.ndarray
    ref: dict
    b_old: float
    sha_inputs: dict

    @property
    def key(self):
        return f"{self.case['id']}_{self.bias}"


class Context:
    def __init__(self,cfg:Config):
        self.cfg=cfg
        self._checks=[]
        self._verified={}
        self._mod=None
        self._bank=None
        self._mr=None
        self.cfg.output_root.mkdir(parents=True,exist_ok=True)
        self._input_preflight()

    @property
    def base(self):
        return self.cfg.repo_root / BASE_REL

    def _input_preflight(self):
        for path,name in ((self.base/'e1_e4/OUTPUT_SHA256.json','E1 digest manifest'),
                          (self.base/'e1_e4/E1/R2_aA_m45_B0.npz','E1 reference'),
                          (self.cfg.source_root/'research/PJ_DS_GATED_20261021/v_replay.py','v_replay'),
                          (self.cfg.source_root.parent/'BANK_MANIFEST.json','bank manifest'),
                          (self.base/'x1/source_blob_lock.json','source identity lock'),
                          (self.cfg.repo_root/'research/PJ_DS_GATED_20261021/results_murec/MR_SERIES.csv.gz','MR series')):
            check_real(path,name,binary=path.suffix=='.npz')
        try:
            head=subprocess.run(['git','-C',str(self.cfg.repo_root),'rev-parse','HEAD'],check=True,capture_output=True,text=True).stdout.strip()
            ok=subprocess.run(['git','-C',str(self.cfg.repo_root),'merge-base','--is-ancestor',COMMIT,head],capture_output=True).returncode==0
            if not ok:
                raise RuntimeError(f'repository HEAD {head} does not contain evidence commit {COMMIT}')
        except FileNotFoundError:
            raise RuntimeError('git CLI required to validate evidence checkout')
        self.repo_head=head
        # Frozen training output is part of the E1 input lock, not a replaceable
        # current model. EX counterfactual is invalid if this identity fails.
        orig_input_lock=read_json(self.base/'e1_e4/INPUT_LOCK.json')
        mr_records=[x for x in orig_input_lock['files']
                    if x['path'].replace('\\','/').endswith('/MR_SERIES.csv.gz')]
        if len(mr_records)!=1:
            raise RuntimeError('Unable to identify unique frozen MR_SERIES in E1 INPUT_LOCK')
        mr_repo=self.cfg.repo_root/'research/PJ_DS_GATED_20261021/results_murec/MR_SERIES.csv.gz'
        actual_mr_sha=sha256(mr_repo)
        if actual_mr_sha!=mr_records[0]['sha256']:
            raise RuntimeError('FROZEN_MR_SERIES_SHA_MISMATCH: EX-vs-EXDS invalid')
        self._verified[mr_repo.resolve()]=actual_mr_sha
        # Verify exact source blobs, not merely matching file names.
        if self.cfg.strict_source:
            lock=read_json(self.base/'x1/source_blob_lock.json')
            for entry in lock['files']+lock['reference_files']:
                p=check_real(self.cfg.source_root/entry['path'],'source identity')
                content=p.read_bytes()
                git_sha=hashlib.sha1(b'blob '+str(len(content)).encode()+b'\0'+content).hexdigest()
                if git_sha != entry['sha']:
                    raise RuntimeError('FROZEN_SOURCE_BLOB_MISMATCH: '+str(p))
            self._checks.append({'kind':'frozen_source_git_blobs','count':len(lock['files'])+len(lock['reference_files']),'status':'PASS'})

    def verify_manifest_file(self,p:Path):
        p=p.resolve()
        if p in self._verified:return self._verified[p]
        roots=[(self.base/'e1_e4',self.base/'e1_e4/OUTPUT_SHA256.json'),
               (self.base/'pass_rs_azimuth',self.base/'pass_rs_azimuth/OUTPUT_SHA256.json')]
        for root,manifest in roots:
            try:rel=p.relative_to(root).as_posix()
            except ValueError:continue
            files={x['path']:x['sha256'] for x in read_json(manifest)['files']}
            if rel not in files:
                raise RuntimeError(f'Missing manifest entry {rel} in {manifest}')
            actual=sha256(p)
            if actual != files[rel]:
                raise RuntimeError(f'HASH FAIL {p}: expected {files[rel]}, got {actual}')
            self._verified[p]=actual
            return actual
        self._verified[p]=sha256(p)
        return self._verified[p]

    @cached_property
    def V(self):
        # Import order is identical to frozen v_replay, with all writes redirected.
        src=self.cfg.source_root
        os.environ['PJ_SOURCE_ROOT']=str(src)
        os.environ['PJ_ART']=str(self.cfg.artifacts_root)
        scratch=self.cfg.output_root/'_reference_runtime'
        scratch.mkdir(exist_ok=True)
        os.environ['PJ_OUT']=str(scratch)
        sys.path.insert(0,str(src/'research/PJ_DS_GATED_20261021'))
        import v_replay as V
        V.OUT=scratch
        import p0_initial, source_model
        p0_initial.OUT=scratch
        source_model.OUT=scratch
        if V.MANIFEST['cases'] is None:raise RuntimeError('missing frozen manifest')
        self._bank=(p0_initial, source_model)
        from p3_rf_adapter4 import B_OLD
        self.b_old=float(B_OLD)
        return V

    @cached_property
    def model(self):
        model=self.V.SourceFFD()
        return model

    @cached_property
    def MR(self):
        p=check_real(self.cfg.repo_root/'research/PJ_DS_GATED_20261021/results_murec/MR_SERIES.csv.gz','MR predictions')
        data=pd.read_csv(p,compression='gzip')
        required={'case','bias','channel','pose_id','MU_R_EX__meas_r_cm','MU_R_EXDS__meas_r_cm'}
        if missing:=required-set(data.columns):
            raise RuntimeError(f'MR_SERIES missing columns: {missing}')
        return data

    @cached_property
    def passes(self):
        p=self.base/'pass_rs_azimuth/P2_PASSES_GT.csv'
        self.verify_manifest_file(p)
        d=pd.read_csv(p)
        for key in ('case','bias','pass_id','primary','window_start_s','window_end_s','post_start_s','post_end_s'):
            if key not in d.columns:raise RuntimeError(f'bad pass file: {key}')
        return d

    def first_pass(self,key,bias):
        d=self.passes
        rows=d[(d['case']==key)&(d['bias']==bias)&(d['pass_id']==1)]
        if len(rows)!=1:raise RuntimeError(f'first pass missing/duplicate {key} {bias}')
        return rows.iloc[0]

    def native_fp(self,d:CaseData):
        """Recompute the *measured* FP tap from frozen native Full Sionna RF.

        No OCR or imputed tap labels. Array is memory-mapped; bins use exactly
        the strong-port, Hann, 4x IFFT, 30%-leading-edge detector convention.
        B0/L2 share RF: cache by case, never count them as independent RF.
        """
        if not hasattr(self,'_native_fp_cache'):
            self._native_fp_cache={}
        cid=d.case['id']
        if cid in self._native_fp_cache:
            return self._native_fp_cache[cid]
        p=check_real(self.cfg.source_root/d.case['full_path'],'native Full RF .npy')
        sample=check_real(self.cfg.source_root/d.case['samples_path'],'raw sample IDs')
        raw_ids=pd.DataFrame(read_json(sample))['pose_id'].to_numpy()
        rf=np.load(p,mmap_mode='r',allow_pickle=False)
        if rf.ndim!=4 or rf.shape[1]!=257 or rf.shape[2]!=2 or rf.shape[0]!=len(raw_ids):
            raise RuntimeError(f'Native Full RF shape/order unexpected {cid} {rf.shape}')
        index=pd.Index(raw_ids)
        if index.has_duplicates:
            raise RuntimeError('duplicate native RF pose ID')
        row_index=index.get_indexer(d.ids)
        if np.any(row_index<0) or len(np.unique(row_index))!=len(d.ids):
            raise RuntimeError('native RF pose IDs not aligned to E1')
        nf=rf.shape[1]
        window=.5-.5*np.cos(2*np.pi*np.arange(nf)/(nf-1))
        count=len(d.t)
        measured_tap=np.empty(count,dtype=int)
        measured_margin=np.empty(count)
        measured_s=np.empty(count)
        for a in range(0,count,32):
            b=min(a+32,count)
            h=np.asarray(rf[row_index[a:b],:,:,0],np.complex128)
            ci=np.fft.ifft(h*window[None,:,None],n=4*nf,axis=1)*nf
            amp=np.abs(ci)
            ii=np.arange(len(h))
            port=amp.max(axis=1).argmax(axis=1)
            strongest=amp[ii,:,port]
            peak=strongest.max(axis=1)
            if np.any(peak<=0):
                raise RuntimeError(f'All-zero CIR detected in native RF {cid}')
            threshold=.3*peak
            tap=(strongest>=threshold[:,None]).argmax(axis=1)
            cf=ci[ii,tap]
            power=np.abs(cf)**2
            den=power.sum(axis=1)
            if np.any(den<=0):
                raise RuntimeError(f'Invalid native power at FP tap {cid}')
            measured_tap[a:b]=tap
            measured_s[a:b]=(power[:,0]-power[:,1])/den
            last=strongest[ii,np.maximum(tap-1,0)]
            below=threshold-np.where(tap>0,last,0)
            above=strongest[ii,tap]-threshold
            measured_margin[a:b]=np.minimum(above,below)/peak
        if np.max(abs(measured_s-d.z[:,1]))>1e-9:
            raise RuntimeError(f'NATIVE_RF_SFP_VS_E1_MISMATCH {cid}: '
                               f'{np.max(abs(measured_s-d.z[:,1]))}')
        val={'tap':measured_tap,'margin':measured_margin,'s_fp':measured_s}
        self._native_fp_cache[cid]=val
        self._verified[p]=sha256(p)
        self._verified[sample]=sha256(sample)
        return val

    def cases(self):
        lookup={c['id']:c for c in self.V.MANIFEST['cases']}
        missing=set(self.cfg.cases)-set(lookup)
        if missing:raise RuntimeError(f'cases absent from manifest: {missing}')
        for key in self.cfg.cases:
            for bias in self.cfg.biases:
                yield self.load_case(lookup[key],bias)

    def load_case(self,case:dict,bias:str)->CaseData:
        p=self.base/'e1_e4/E1'/f"{case['id']}_{bias}.npz"
        check_real(p,'E1 LFS NPZ',binary=True)
        self.verify_manifest_file(p)
        with np.load(p,allow_pickle=False) as raw:
            ref={k:raw[k].copy() for k in raw.files}
        names=[str(v) for v in ref['names']]
        if names!=['A0','A0.25','A0.5','A0.75','A1']:
            raise RuntimeError(f'E1 names changed: {names}')
        n=len(ref['t_s'])
        truth=np.asarray(ref['truth_scoring_only'],float)
        if truth.shape!=(n,4) or ref['x'].shape!=(n,5,4):
            raise RuntimeError('unexpected E1 shapes')
        t=np.asarray(ref['t_s'],float)
        ids=np.asarray(ref['pose_id'])
        if not np.all(np.diff(t)>0) or len(np.unique(ids))!=n:
            raise RuntimeError('bad pose ID/time uniqueness')
        h=np.asarray(ref['h'],float); mu=np.asarray(ref['mu'],float);nu=np.asarray(ref['nu'],float)
        z=nu[:,0,:]+h[:,0,:]+mu[:,0,:]
        if np.max(abs((nu+h+mu)-z[:,None,:]))>1e-11:
            raise RuntimeError('reference E1 observed measurement differs between arms')
        mask=np.asarray(ref['acc'][:,0],bool)
        if not np.array_equal(ref['acc'],np.broadcast_to(mask[:,None],ref['acc'].shape)):
            raise RuntimeError('E1 mask must be common A_B')
        if np.max(abs(ref['R']-ref['R'][:,0,None,:,:]))>1e-12:
            raise RuntimeError('reference E1 R differs by alpha')
        if np.any(ref['R'][:,0,0,0]<=0) or np.any(ref['R'][:,0,1,1]<=0):
            raise RuntimeError('nonpositive measurement variance')
        if abs(float(ref['R'][:,0,0,1].max()))>1e-12 or abs(float(ref['R'][:,0,1,0].max()))>1e-12:
            raise RuntimeError('original Crs is nonzero: change policy, do not silently ignore')
        m=self.MR
        sel=m[(m['case']==case['id']) & (m['bias']==bias)&(m['channel']=='full')]
        if len(sel)!=n or sel['pose_id'].duplicated().any():
            raise RuntimeError(f'MR source incomplete: {case["id"]}_{bias}: {len(sel)} != {n}')
        sel=sel.set_index('pose_id').loc[ids]
        mu_b=mu[:,0,0].copy()
        mu_exds=mu[:,4,0].copy()
        # e_r - mu_M = stored_meas_r_cm/100; do not read e_r label at runtime.
        mu_ex=mu_exds + (sel['MU_R_EXDS__meas_r_cm'].to_numpy(float)-sel['MU_R_EX__meas_r_cm'].to_numpy(float))/100
        if np.max(np.abs(mu_exds-mu[:,0,0]-(mu[:,4,0]-mu[:,0,0])))>1e-13:
            raise RuntimeError('alpha EXDS mismatch')
        obs_delta=sel['MU_R_EXDS__meas_r_cm'].to_numpy(float)-sel['BASE__meas_r_cm'].to_numpy(float)
        if np.max(abs((mu_b-mu_exds)-obs_delta/100))>1e-10:
            raise RuntimeError('recovered EXDS/BASE residual differential mismatch')
        controls, x0=self.V.build_positive_bias_controls(t,truth[:,:3],bias)
        if not np.array_equal(np.asarray(controls['t_s']),t):
            raise RuntimeError('sensor controls timestamps mismatch')
        # Original x0 in E1 initial prior is after initial sensor perturbation;
        # exact reconstructed states must pass independent numerical replay.
        if abs(float(wrap(truth[0,2]-x0[2])))>np.pi:
            raise RuntimeError('initial yaw control invalid')
        return CaseData(case,bias,t,ids,truth,z,mu_b,mu_ex,mu_exds,mu[:,0,1].copy(),
                        ref['R'][:,0].copy(),mask,controls,np.asarray(x0,float),ref,
                        self.b_old,{'E1_NPZ':self._verified[p],
                                    'MR_SERIES':sha256(self.cfg.repo_root/'research/PJ_DS_GATED_20261021/results_murec/MR_SERIES.csv.gz')})

    def evidence_metadata(self):
        package_root=Path(__file__).resolve().parents[1]
        code_files=sorted(package_root.glob('dsreassess/*.py'))+[package_root/'run.py']
        return {'repo_head':self.repo_head,'evidence_commit':COMMIT,'source_root':str(self.cfg.source_root),
                'package_code_sha256':{str(p.relative_to(package_root)):sha256(p) for p in code_files},
                'source_identity':self._checks,'input_sha256':{str(p):h for p,h in sorted(self._verified.items())},
                'config':{k:(str(v) if isinstance(v,Path) else v) for k,v in vars(self.cfg).items()}}


class StageWriter:
    def __init__(self,ctx:Context,name:str):
        self.ctx=ctx
        self.dir=ctx.cfg.output_root/name
        self.dir.mkdir(parents=False,exist_ok=False)
        self.name=name
        self.checks=[]
    def check(self,label,got,expected,atol=1e-10):
        g=np.asarray(got);e=np.asarray(expected)
        if g.shape!=e.shape:raise AssertionError(f'{label}: shape {g.shape}!={e.shape}')
        if g.dtype.kind in ('b','U','S') or e.dtype.kind in ('b','U','S'):
            diff=0 if np.array_equal(g,e) else 1
        else:
            diff=float(np.max(abs(g-e))) if g.size else 0
        if not np.isfinite(diff) or diff>atol:
            raise AssertionError(f'{label} PARITY FAILED max {diff}, tol {atol}')
        self.checks.append({'label':label,'max_abs':diff,'atol':atol,'status':'PASS'})
    def csv(self,name,frame):
        parquet_safe_csv(pd.DataFrame(frame),self.dir/name)
    def json(self,name,d):write_json(self.dir/name,d)
    def npz(self,name,**arrays):
        np.savez_compressed(self.dir/name,**arrays)
    def finish(self,extra=None):
        self.json('CHECKS.json',self.checks)
        out={p.name:sha256(p) for p in sorted(self.dir.iterdir()) if p.is_file()}
        self.json('OUTPUT_SHA256.json',out)
        self.json('RUN_STATUS.json',{'status':'CODE_EXECUTION_PASS_NOT_SCIENTIFIC_VALIDATION',
                                    'stage':self.name,'files':len(out),'checks':len(self.checks),
                                    'inputs':self.ctx.evidence_metadata(),**(extra or {})})
    def abort(self,exc):
        self.json('RUN_FAILURE.json',{'stage':self.name,'error_type':type(exc).__name__,'error':str(exc)})
        raise exc
