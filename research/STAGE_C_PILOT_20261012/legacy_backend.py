"""On-demand Legacy Method-B RF backend for the body-probe loop (Stage C).
Same pipeline as the delivered traces: Sionna RT 2.0.1 PathSolver with unit isotropic V/H ports at 17 frequency nodes (rf_b_trace.trace_position),
then the frozen FFD banks and the antenna yaw are applied offline (rf_store.h_for_antenna_yaws). Interface = body_pose_channel.NativeSionnaAtPose.generate.
Not a Native-solver backend: the path solver is the one that produced the legacy traces; FFD patterns are NOT in the solver."""
from __future__ import annotations
import hashlib,json,math,sys,time
from pathlib import Path
import numpy as np
RT=Path('/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad/rtroot')     # git-archive of origin/codex/abc-gated-resume-20261011 + LFS banks
sys.path[:0]=[str(RT/'src'),str(RT/'scripts'),str(RT/'scripts'/'g2_completion'),str(RT/'scripts'/'drive_sim')]
import rf_b_trace as T                    # noqa: E402  (imports corridor_sionna_run, mitsuba, sionna.rt)
from qclean_uwb.drivesim import rf_store as RS   # noqa: E402
from qclean_uwb.drivesim.body_pose_channel import RFChannel,RFPoseRequest   # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup   # noqa: E402
class LegacyMethodBAtPose:
    def __init__(self,*,out_dir:Path,anchor_x_m:float,mount_deg:float,nodes:int=17,threads:int=1):
        import drjit as dr
        dr.set_thread_count(threads)
        self.setup=CorridorSetup(anchor_x_m=anchor_x_m);self.mount_deg=float(mount_deg)
        assert all(c['passed'] for c in self.setup.validate())
        C=T.C;self.cfg=json.loads(C.SOLVER_SOURCE.read_text())['solver']
        self.banks=RS.load_banks(RT)                    # SHA256-verified against BANK_MANIFEST
        self.freq=np.asarray(self.banks[0].freqs_hz,float);self.bins=T.node_bins(len(self.freq),str(nodes))
        self.scene,self.bindings=C.build_scene(self.setup,Path(out_dir))
        rt,mi=T.rt,T.mi
        self.scene.add(rt.Transmitter('tx',position=self.setup.anchor_position.tolist(),orientation=[0.,0.,0.]))
        self.scene.add(rt.Receiver('rx',position=self.setup.robot_position(*self.setup.example_xy_m[0]).tolist(),orientation=[0.,0.,0.]))
        self.scene.tx_array=rt.AntennaArray(T.Ports([T.IsoPort(0),T.IsoPort(1)]),mi.Point3f(0,0,0))
        self.scene.rx_array=rt.AntennaArray(T.Ports([T.IsoPort(0),T.IsoPort(1)]),mi.Point3f(0,0,0))
        self.solver=rt.PathSolver();self.cache={};self.calls=0;self.seconds=0.
        self.provenance=dict(source_id='LEGACY_METHOD_B_ON_DEMAND',solver=self.cfg,nodes=len(self.bins),mount_deg=self.mount_deg,anchor_x_m=anchor_x_m,
                             bank_sha256={n+'_bank.npz':hashlib.sha256((RT/(n+'_bank.npz')).read_bytes()).hexdigest() for n in RS.PORTS},
                             runner_sha256=hashlib.sha256(Path(T.__file__).read_bytes()).hexdigest(),
                             parity='validated against delivered traces/H by validate_backend.py; see STAGE_C_FINAL_KO.md')
    def trace(self,x,y):
        key=(round(float(x),6),round(float(y),6))
        if key in self.cache:return self.cache[key]
        t0=time.monotonic()
        jones,(tau,ang),status,counts,audit=T.trace_position(self.scene,self.solver,self.cfg,self.freq,self.bins,float(x),float(y),self.setup)
        tr=dict(jones=jones,tau=tau,ang=np.array(ang),node_bins=np.array(audit['nodes']),node_freq_hz=self.freq[audit['nodes']],present=audit['present'],status=status,x=float(x),y=float(y))
        self.calls+=1;self.seconds+=time.monotonic()-t0;self.cache[key]=tr;return tr
    @staticmethod
    def _los_only(tr):
        i0=int(np.argmin(tr['tau']));one=dict(tr)
        for k,sl in (('jones',lambda a:a[:,i0:i0+1]),('tau',lambda a:a[i0:i0+1]),('ang',lambda a:a[:,i0:i0+1]),('present',lambda a:a[:,i0:i0+1])):one[k]=sl(tr[k])
        return one
    def generate(self,req:RFPoseRequest)->RFChannel:
        req.validate()
        if not math.isclose(req.mount_deg,self.mount_deg,abs_tol=1e-12):raise ValueError('receiver mount mismatch')
        x,y,psi=req.true_pose_xyyaw;tr=self.trace(x,y);yaw=math.degrees(psi)+self.mount_deg
        if tr['status']!='OK':raise ValueError('TRACE_NOT_USABLE '+tr['status'])
        full=RS.h_for_antenna_yaws(tr,self.banks,[yaw])[0];los=RS.h_for_antenna_yaws(self._los_only(tr),self.banks,[yaw])[0]
        ch=RFChannel(request=req,freqs_hz=self.freq.copy(),H_full=full,H_los=los,provenance=dict(self.provenance,packet_id=req.packet_id,packet_t_s=req.t_s));ch.validate();return ch
