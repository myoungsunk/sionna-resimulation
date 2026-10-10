"""Exact-pose native Sionna channel adapter for noisy body-yaw probe packets.

The Sionna solver consumes ORACLE physical pose ONLY at RF emission time. The
EKF receives only first-path measurements, not true pose, path rays or H.
No resampling or lookup of fixed-XY ideal yaw banks is permitted here.

Import of heavy Mitsuba/DrJit/Sionna is intentionally LAZY; unit tests can
import this module without the pinned native Sionna environment.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import math
from pathlib import Path
import sys

import numpy as np

from .observation import observe, cir_batch, noise_var_from_snr, realised_snr_db


@dataclass(frozen=True)
class RFPoseRequest:
    packet_id: str
    t_s: float
    true_pose_xyyaw: tuple[float, float, float]  # EVALUATION / RF PHYSICS ONLY
    mount_deg: float
    station_id: int
    point_index: int

    def validate(self):
        values = (self.t_s, *self.true_pose_xyyaw, self.mount_deg)
        if not self.packet_id or not all(math.isfinite(float(v)) for v in values) or self.t_s < 0:
            raise ValueError("invalid physical RF pose request")
        if self.point_index < 0:
            raise ValueError("invalid probe point index")


@dataclass
class RFChannel:
    request: RFPoseRequest
    freqs_hz: np.ndarray
    H_full: np.ndarray
    H_los: np.ndarray | None
    provenance: dict

    def validate(self):
        self.request.validate()
        freqs = np.asarray(self.freqs_hz,dtype=float)
        if freqs.shape!=(257,) or not np.isfinite(freqs).all() or np.any(np.diff(freqs)<=0):
            raise ValueError("invalid RF frequency grid; expected 257 ascending bins")
        for name,h in (("H_full",self.H_full),("H_los",self.H_los)):
            if h is None:
                if name=="H_full": raise ValueError("missing native full RF H")
                continue
            h=np.asarray(h)
            if h.shape!=(257,2,2) or not np.isfinite(h).all():
                raise ValueError(f"bad {name} dimensions or finite check")


@dataclass(frozen=True)
class RFFilterPacket:
    """Only fields legitimately observed by the RF receiver or pre-calibrated."""
    packet_id: str
    t_s: float
    detected: bool
    range_m: float
    s: float
    power: tuple[float,float]
    selected_tap: int
    # Clean H based realized SNR is diagnostic ONLY; EKF never uses it to update.
    realized_snr_db: float = math.nan
    noise_cov_sr: np.ndarray | None = None
    covariance_model_id: str | None = None
    # Receiver-visible only if amplitude-CIR is exported. These are SIMULATION features.
    first_cluster_s: tuple[float,float,float] | None = None
    first_cluster_port_energy: tuple[tuple[float,float],...] | None = None
    first_cluster_window_taps: tuple[int,int,int] | None = None
    first_cluster_availability: str = "SIMULATED_AMPLITUDE_CIR_ONLY"


class FirstPathReceiver:
    """Project-native 30%-leading-edge/dual-LP observer, independent thermal RNG."""

    def __init__(self, *, snr_db:float=30., range_sigma_m:float=.05,
                 seed:int=0, rf_channel_kind:str="full"):
        if rf_channel_kind not in ("full","los"):
            raise ValueError("channel kind must be explicit")
        if not all(math.isfinite(x) for x in (snr_db,range_sigma_m)) or range_sigma_m<0:
            raise ValueError("invalid receiver noise")
        self.snr_db,self.range_sigma_m=snr_db,range_sigma_m
        self.kind=rf_channel_kind
        self.rng=np.random.default_rng([2201020,int(seed),1])
        self.range_rng=np.random.default_rng([2201020,int(seed),2])

    def receive(self, channel:RFChannel)->tuple[RFFilterPacket,dict]:
        channel.validate()
        H=channel.H_full if self.kind=="full" else channel.H_los
        if H is None:
            raise ValueError("requested LoS native channel unavailable")
        nvar=noise_var_from_snr(self.snr_db)
        obs=observe(H[None,...],channel.freqs_hz,nvar,self.rng,tx=0,return_h=True)
        # Only the magnitude/power profile leaves the simulated coherent H domain.
        # Same strongest-RX first-path leading edge for both orthogonal LP ports.
        cir_amplitude=np.abs(cir_batch(obs["h_noisy"]))[0]
        selected_tap=int(obs["index"][0])
        cluster_s=[]
        cluster_energy=[]
        for taps in (4,8,16):
            if selected_tap<0 or selected_tap+taps>len(cir_amplitude):
                cluster_s.append(math.nan)
                cluster_energy.append((math.nan,math.nan))
                continue
            e=np.square(cir_amplitude[selected_tap:selected_tap+taps,:]).sum(axis=0)
            cluster_energy.append((float(e[0]),float(e[1])))
            cluster_s.append(float((e[0]-e[1])/(e[0]+e[1])) if e.sum()>0 else math.nan)
        dist=float(obs["range_m"][0])
        if bool(obs["detected"][0]):
            dist+=self.range_sigma_m*self.range_rng.standard_normal()
        snr=float(realised_snr_db(H[None,...],nvar,tx=0)[0])
        p=tuple(float(x) for x in obs["power"][0])
        packet=RFFilterPacket(packet_id=channel.request.packet_id,t_s=channel.request.t_s,
                              detected=bool(obs["detected"][0]),range_m=dist,
                              s=float(obs["s"][0]),power=p,
                              selected_tap=int(obs["index"][0]),realized_snr_db=snr,
                              first_cluster_s=tuple(cluster_s),
                              first_cluster_port_energy=tuple(cluster_energy),
                              first_cluster_window_taps=(4,8,16))
        # Full complex H and true pose remain evaluation/provenance-only.
        oracle=dict(packet_id=packet.packet_id,physical_pose_xyyaw=channel.request.true_pose_xyyaw,
                    t_s=channel.request.t_s,mount_deg=channel.request.mount_deg,
                    source_id=channel.provenance.get("source_id","UNKNOWN"),
                    full_H_sha256=hashlib.sha256(np.ascontiguousarray(channel.H_full).tobytes()).hexdigest(),
                    los_H_sha256=hashlib.sha256(np.ascontiguousarray(channel.H_los).tobytes()).hexdigest()
                    if channel.H_los is not None else None,
                    noise_var_per_bin=nvar,realized_snr_db=snr,
                    physical_channel_kind=self.kind,rf_engine_provenance=channel.provenance)
        return packet,oracle


@dataclass(frozen=True)
class NativeSolverSettings:
    max_depth: int=3
    samples_per_src: int=100000
    max_num_paths_per_src: int=1000000
    seed: int=20260924
    compute_los: bool=True

    def parameters(self):
        if self.max_depth<0 or self.samples_per_src<1 or self.max_num_paths_per_src<1:
            raise ValueError("invalid native solver limits")
        return dict(max_depth=self.max_depth,samples_per_src=self.samples_per_src,
                    max_num_paths_per_src=self.max_num_paths_per_src,
                    synthetic_array=True,los=True,specular_reflection=True,
                    refraction=True,diffraction=False,edge_diffraction=False,
                    diffuse_reflection=False,seed=self.seed)


class NativeSionnaAtPose:
    """PathSolver full/LoS channels at actual x,y,yaw; NOT existing ideal grid.

    Factory arguments must point to real FFD banks+verified BANK_MANIFEST.
    Construction fails when Sionna or bank bytes are unavailable, rather
    than synthesizing fake channels or switching silently to legacy Method B.
    """

    def __init__(self, *, output_scene_dir: Path, bank_dir: Path, bank_manifest: Path,
                 anchor_x_m:float=4., mount_deg:float=0.,
                 settings:NativeSolverSettings=NativeSolverSettings()):
        from qclean_uwb.scenarios.corridor import CorridorSetup
        self.setup=CorridorSetup(anchor_x_m=anchor_x_m)
        self.mount_deg=float(mount_deg)
        if not math.isfinite(self.mount_deg):
            raise ValueError("invalid RX mount")
        if not Path(bank_manifest).is_file():
            raise FileNotFoundError(f"native FFD manifest missing: {bank_manifest}")
        if not Path(bank_dir).is_dir():
            raise FileNotFoundError(f"native FFD bank directory missing: {bank_dir}")
        root=Path(__file__).resolve().parents[3]
        scripts=str(root/"scripts")
        if scripts not in sys.path:sys.path.insert(0,scripts)
        try:
            import corridor_sionna_run as C
        except (ImportError,ModuleNotFoundError) as exc:
            raise RuntimeError("NATIVE_SIONNA_RUNTIME_UNAVAILABLE; pinned Mitsuba/Sionna needed") from exc
        # C.load_banks verifies NPZ hashes against the frozen manifest.
        C.BANK_DIR=Path(bank_dir)
        C.BANK_MANIFEST=Path(bank_manifest)
        self.C=C
        self.banks=C.load_banks()
        self.freqs=np.asarray(self.banks[0]["freqs_hz"],float)
        if self.freqs.shape!=(257,) or np.any(np.diff(self.freqs)<=0):
            raise ValueError("native bank frequency parity failed")
        C.dr.set_thread_count(1)
        self.scene,self.geometry_receipt=C.build_scene(self.setup,Path(output_scene_dir))
        from qclean_uwb.scenarios.corridor import ANCHOR_ROTATION
        self.scene.add(C.rt.Transmitter("tx",position=self.setup.anchor_position.tolist(),
                                       orientation=C.euler(ANCHOR_ROTATION)))
        self.scene.add(C.rt.Receiver("rx",position=self.setup.robot_position(7.,0.).tolist(),
                                    orientation=C.euler(self.setup.robot_rotation(0.))))
        self.txp,self.rxp=C.make_ports(self.banks)
        self.solver=C.rt.PathSolver()
        self.full_cfg=settings.parameters()
        self.los_cfg=dict(max_depth=0,los=True,specular_reflection=False,
                          refraction=False,diffraction=False,edge_diffraction=False,
                          diffuse_reflection=False,seed=settings.seed)
        self.compute_los=settings.compute_los
        self.provenance=dict(source_id="NATIVE_SIONNA_EXACT_POSE",
                             full_solver=self.full_cfg,los_solver=self.los_cfg if self.compute_los else None,
                             ports=dict(tx0="+45 LP",rx0="+45 LP",rx1="-45 LP"),
                             ffd_manifest_sha256=C.sha256(Path(bank_manifest)),
                             bank_sha256={x+"_bank.npz":C.sha256(Path(bank_dir)/(x+"_bank.npz")) for x in C.PORTS},
                             native_runner_sha256=C.sha256(Path(C.__file__)),
                             mount_deg=self.mount_deg,
                             LoS_parity="NOT_VERIFIED_BY_THIS_ADAPTER",
                             F01="OPEN",F02="OPEN",scientific_PASS=False)

    @staticmethod
    def _coherent_H(solver,scene,cfg,freq):
        p=solver(scene,**cfg)
        tau=np.asarray(p.tau,dtype=float).reshape(-1)
        aa=np.asarray(p.a[0])+1j*np.asarray(p.a[1])
        if aa.size!=4*tau.size:
            raise ValueError("native paths TX/RX shape mismatch")
        aa=aa.reshape(2,2,tau.size)
        valid=np.isfinite(tau)&(tau>=0)
        if not valid.any():return np.zeros((2,2),complex)
        if not np.isfinite(aa[...,valid]).all():
            raise ValueError("nonfinite native path amplitudes")
        return np.sum(aa[...,valid] * np.exp(-2j*np.pi*freq*tau[valid])[None,None,:],axis=-1)

    def generate(self,req:RFPoseRequest)->RFChannel:
        req.validate()
        if not math.isclose(req.mount_deg,self.mount_deg,abs_tol=1e-12):
            raise ValueError("receiver mount mismatch")
        x,y,psi=req.true_pose_xyyaw
        xlo,xhi=self.setup.robot_x_range_m
        if not xlo<=x<=xhi or abs(y)>self.setup.robot_y_limit_m:
            raise ValueError("TRUE_RF_POSE_OUTSIDE_CORRIDOR")
        C=self.C
        receiver=self.scene.receivers["rx"]
        receiver.position=C.mi.Point3f(*self.setup.robot_position(x,y).tolist())
        receiver.orientation=C.mi.Point3f(*C.euler(self.setup.robot_rotation(math.degrees(psi)+self.mount_deg)))
        full=np.empty((len(self.freqs),2,2),complex)
        los=np.empty_like(full) if self.compute_los else None
        for fi,freq in enumerate(self.freqs):
            C.set_bin(self.scene,self.banks,self.txp,self.rxp,fi,float(freq))
            full[fi]=self._coherent_H(self.solver,self.scene,self.full_cfg,float(freq))
            if los is not None:
                los[fi]=self._coherent_H(self.solver,self.scene,self.los_cfg,float(freq))
        pkt=RFChannel(request=req,freqs_hz=self.freqs.copy(),H_full=full,
                      H_los=los,provenance=dict(self.provenance,
                      packet_id=req.packet_id,packet_t_s=req.t_s))
        pkt.validate()
        return pkt
