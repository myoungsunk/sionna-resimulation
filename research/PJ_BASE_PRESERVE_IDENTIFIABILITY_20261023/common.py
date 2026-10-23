"""Data boundaries, immutable inputs, provenance and fail-closed stage receipts."""
from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Iterable
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
import numpy as np
import pandas as pd

REFERENCE_SHA = '0686b23ceeefb696bc158b32b39f8077c564ef5d'
CASES = ('R2_aA_m0', 'R2_aA_m45', 'R2_aB_m0', 'R4_aA_m0', 'R4_aB_m0', 'R5_aA_m0', 'R5_aB_m0')
BIASES = ('B0', 'L2')
SEEDS = tuple(range(12))
OFFSETS = (0, -8, -4, -2, -1, 1, 2, 4, 8)
BASE_FEATURES = ('sF_+0', 'log_fp_power', 'fp_full') + tuple(f'sF_{o:+d}' for o in OFFSETS[1:]) + tuple(f'ds_{o:+d}' for o in OFFSETS[1:])
CANDIDATES = ('P1_MU', 'P2_DB', 'P3_VS', 'P4_PERP', 'P4_SHUFFLE', 'P5_CROSSFIT')
PRIMARY_ARMS = ('BASE', 'PWIDE_NOES', 'ORACLE')
DENIED = ('truth', 'los', 'fp_shift', 'e_true', 'r_B', 'gt', 'future', 'heading_error')
STATUS = ('PASS', 'BLOCKED', 'QA_FAIL', 'SUPPORT', 'CONTRARY', 'INCONCLUSIVE')

class ContractError(ValueError):
    """An implementation/data invariant failed; never silently skip this row."""

class BlockedError(RuntimeError):
    """A required asset, upstream evidence, or permission is unavailable."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): canonical(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonical(v) for v in value]
    if isinstance(value, np.ndarray):
        return canonical(value.tolist())
    if isinstance(value, np.generic):
        return canonical(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, Path):
        return str(value)
    return value


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(canonical(value), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def blob_hash(path: Path) -> str:
    b = Path(path).read_bytes()
    return hashlib.sha1(b'blob ' + str(len(b)).encode() + b'\0' + b).hexdigest()


def array_hash(*arrays: np.ndarray) -> str:
    h = hashlib.sha256()
    for a in arrays:
        a = np.ascontiguousarray(a)
        require(a.dtype != object, 'Object arrays are not permitted')
        h.update(str(a.dtype).encode()); h.update(str(a.shape).encode()); h.update(a.tobytes())
    return h.hexdigest()


def code_hash(root: Path | None = None) -> str:
    root = root or Path(__file__).parent
    names = [p for p in root.rglob('*') if p.is_file() and (p.suffix == '.py' or p.name in ('manifest.json', 'requirements.txt'))]
    contents={str(p.relative_to(root)): file_hash(p) for p in sorted(names)}
    launcher=root.parents[1]/'scripts/base_rf_identifiability_v2.py'
    if launcher.is_file():contents['../../scripts/base_rf_identifiability_v2.py']=file_hash(launcher)
    return digest(contents)


def write_json(path: Path, value: Any) -> None:
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(canonical(value), ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    tmp.replace(path)


def read_json(path: Path) -> dict:
    if not Path(path).is_file():
        raise BlockedError(f'Missing JSON: {path}')
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_table(path: Path, rows: Iterable[dict] | pd.DataFrame, *, provenance: dict, columns=None) -> None:
    frame = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows, columns=columns)
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, compression='gzip' if str(path).endswith('.gz') else None)
    write_json(Path(str(path) + '.provenance.json'), {**provenance, 'rows': len(frame), 'columns': list(frame.columns), 'sha256': file_hash(path)})


def exact_rows(frame: pd.DataFrame, keys: list[str], requested: pd.DataFrame) -> pd.DataFrame:
    """Left join with strict cardinality/order. No silent inner joins or dropna."""
    require(not frame.duplicated(keys).any(), f'Duplicate source keys: {keys}')
    require(not requested.duplicated(keys).any(), f'Duplicate requested keys: {keys}')
    req = requested.copy(); req['_requested_order'] = np.arange(len(req))
    joined = req.merge(frame, on=keys, how='left', validate='one_to_one', indicator=True, sort=False)
    require((joined['_merge'] == 'both').all(), f'Missing keys: {joined.loc[joined._merge != "both", keys].head().to_dict("records")}')
    return joined.sort_values('_requested_order').drop(columns=['_requested_order', '_merge']).reset_index(drop=True)


def readonly(value, *, shape=None, finite=True, dtype=np.float64) -> np.ndarray:
    a = np.array(value, dtype=dtype, copy=True)
    if shape is not None:
        require(a.shape == shape, f'Expected {shape}, got {a.shape}')
    if finite:
        require(np.isfinite(a).all(), 'Nonfinite input')
    a.setflags(write=False)
    return a


@dataclass(frozen=True)
class Packet:
    """Only observable current-packet values. No truth, LoS or future fields."""
    pose_id: int
    t: float
    z: np.ndarray
    mu: np.ndarray
    R: np.ndarray
    cir_features: np.ndarray
    profile: np.ndarray
    profile_valid: np.ndarray
    fp: int
    profile_power: np.ndarray

    def __post_init__(self):
        for name, shape, finite, dtype in (
            ('z', (2,), True, np.float64), ('mu', (2,), True, np.float64), ('R', (2, 2), True, np.float64),
            ('cir_features', (len(BASE_FEATURES),), False, np.float64), ('profile', (len(OFFSETS),), False, np.float64),
            ('profile_valid', (len(OFFSETS),), True, bool), ('profile_power', (len(OFFSETS),), True, np.float64)):
            object.__setattr__(self, name, readonly(getattr(self, name), shape=shape, finite=finite, dtype=dtype))
        require(np.isfinite(self.t), 'Invalid packet timestamp')
        require(np.isfinite(self.profile[self.profile_valid]).all(), 'Valid tap is nonfinite')
        require((np.abs(self.profile[self.profile_valid]) <= 1 + 1e-10).all(), 'Polarization outside [-1,1]')
        require((self.profile_power >= 0).all(), 'Negative power')
        require(not np.isinf(self.cir_features).any(), 'Infinite predictor feature')

    @classmethod
    def from_mapping(cls, values: dict) -> 'Packet':
        # Explicit allowlist: additions to an upstream dataframe cannot leak into a predictor.
        return cls(**{f.name: values[f.name] for f in fields(cls)})


@dataclass(frozen=True)
class Inputs:
    case: str
    route: str
    bias: str
    channel: str
    seed_idx: int
    seed: int
    packets: tuple[Packet, ...]
    controls: np.ndarray  # ds [m], integrated gyro [rad], dt [s]
    x0: np.ndarray
    P0: np.ndarray
    anchor: np.ndarray
    robot_z: float
    source_hash: str

    def __post_init__(self):
        n = len(self.packets)
        require(n > 0, 'Empty input')
        t = np.array([p.t for p in self.packets]); ids = [p.pose_id for p in self.packets]
        require((np.diff(t) > 0).all(), 'Time must be strictly increasing')
        require(len(set(ids)) == n, 'Duplicate pose IDs')
        object.__setattr__(self, 'packets', tuple(self.packets))
        object.__setattr__(self, 'controls', readonly(self.controls, shape=(n, 3)))
        object.__setattr__(self, 'x0', readonly(self.x0, shape=(4,)))
        object.__setattr__(self, 'P0', readonly(self.P0, shape=(4, 4)))
        object.__setattr__(self, 'anchor', readonly(self.anchor, shape=(3,)))
        require(np.allclose(self.controls[1:, 2], np.diff(t), rtol=0, atol=1e-10), 'Control/timestamp mismatch')
        require((self.controls[1:, 2] > 0).all(), 'dt must be positive')

    @property
    def t(self):
        return np.array([p.t for p in self.packets])

    @property
    def tag(self):
        return f'{self.case}__{self.channel}__{self.bias}__seed{self.seed_idx}'

    @property
    def identity(self):
        return dict(case=self.case, route=self.route, bias=self.bias, channel=self.channel, seed_idx=self.seed_idx, seed=self.seed)

    def checksum(self) -> str:
        return array_hash(self.controls, self.x0, self.P0, self.t,
                          np.stack([np.r_[p.z, p.mu, p.R.ravel(), p.cir_features, p.profile, p.profile_valid, p.profile_power] for p in self.packets]))


@dataclass
class Trace:
    arrays: dict[str, np.ndarray]
    metadata: dict

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, **self.arrays)
        write_json(path.with_suffix('.json'), {**self.metadata, 'file_sha256': file_hash(path), 'array_schema': {k: {'shape': list(v.shape), 'dtype': str(v.dtype)} for k, v in self.arrays.items()}})

    @classmethod
    def load(cls, path: Path):
        meta = read_json(path.with_suffix('.json'))
        require(meta['file_sha256'] == file_hash(path), 'Trace checksum failed')
        with np.load(path, allow_pickle=False) as a:
            return cls({k: a[k] for k in a.files}, meta)


class Workspace:
    def __init__(self, root: Path, config: dict):
        self.root = Path(root).resolve()
        for name in ('reference_root','source_root','artifact_root','l4models_root','grid_root'):
            if config.get(name):
                source=Path(config[name]).resolve()
                require(not (self.root==source or source in self.root.parents or self.root in source.parents),
                        f'Output and immutable {name} must be disjoint')
        self.root.mkdir(parents=True, exist_ok=True)
        require(config.get('allow_real_experiments_by_default',False) is False,'Implicit RF execution is prohibited')
        require(config.get('noninferiority_margin',0.)==0.,'This frozen protocol has no approved nonzero application margins')
        for name,allowed in (('cases',CASES),('biases',BIASES),('seeds',SEEDS)):
            values=config.get(name,allowed)
            require(bool(values) and len(values)==len(set(values)) and set(values)<=set(allowed),f'Invalid/duplicate {name} scope')
        self.config = config; self.config_hash = digest(config)

    def provenance(self, stage: str, **extra):
        return dict(stage=stage, reference_sha=REFERENCE_SHA, code_sha256=code_hash(), config_sha256=self.config_hash,
                    utc=datetime.now(timezone.utc).isoformat(), command=sys.argv, python=platform.python_version(),
                    classification='RF_FIXED_DEVELOPMENT_DATA' if stage.upper() != 'AUDIT' else 'SYNTHETIC_UNIT_TESTS_ONLY', **extra)

    def receipt(self, stage: str, state: str, **extra):
        require(state in STATUS, f'Unknown status: {state}')
        write_json(self.root / f'{stage}_STATUS.json', {**self.provenance(stage), 'status': state, **extra})

    def require_stage(self, stage: str):
        rec = read_json(self.root / f'{stage}_STATUS.json')
        if rec.get('status') != 'PASS':
            raise BlockedError(f'{stage} is not PASS: {rec.get("status")}')
        require(rec.get('code_sha256') == code_hash(), f'{stage}: code changed; regenerate receipt')
        require(rec.get('config_sha256') == self.config_hash, f'{stage}: configuration mismatch')
        for path, expected in rec.get('outputs', {}).items():
            require((self.root / path).is_file() and file_hash(self.root / path) == expected, f'{stage}: changed/missing output {path}')
        return rec

    def table(self, stage, name, rows, **extra):
        write_table(self.root / stage / name, rows, provenance=self.provenance(stage, **extra))

    def finish(self, stage, **extra):
        folder = self.root / stage
        outputs = {str(p.relative_to(self.root)): file_hash(p) for p in sorted(folder.rglob('*')) if p.is_file()} if folder.exists() else {}
        self.receipt(stage, 'PASS', outputs=outputs, **extra)
