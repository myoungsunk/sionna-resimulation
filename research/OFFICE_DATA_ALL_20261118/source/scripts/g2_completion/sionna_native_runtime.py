"""Pinned Sionna RT producer. No custom path or propagation calculator."""
import argparse
import hashlib
import importlib.metadata
import inspect
import json
import time
from pathlib import Path

import numpy as np
import mitsuba as mi
mi.set_variant('llvm_ad_mono_polarized')
import drjit as dr
import sionna.rt as rt
from scipy.spatial.transform import Rotation
from scipy.interpolate import RegularGridInterpolator
from sionna.rt.antenna_pattern import AntennaPattern
ARMS = ['CP', 'LP_AXIS', 'LP_DIAG']


def write(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False), encoding='utf8')


class BankPort:
    """HFSS grid adapter only; native Sionna computes propagation."""
    def __init__(self, theta, phi, receive=False):
        self.t0, self.p0 = float(theta[0]), float(phi[0])
        self.dt, self.dp = float(theta[1]-theta[0]), float(phi[1]-phi[0])
        self.nt, self.np = len(theta), len(phi)
        self.receive = receive

    def update(self, et, ep):
        # Raw rE at 1 W incident power -> Sionna dimensionless field pattern.
        f = np.stack((et, ep), axis=-1)*np.sqrt(2*np.pi/376.730313668)
        if self.receive:
            f = np.conj(f)  # native receive conjugation -> reciprocal h^T E
        self.buffers = [mi.Float(np.asarray(v, np.float32).ravel()) for v in
                        (f[:,:,0].real, f[:,:,0].imag, f[:,:,1].real, f[:,:,1].imag)]

    def evaluate(self, theta, phi):
        tw = dr.clip((theta-self.t0)/self.dt, 0., self.nt-1.)
        wrapped = phi-self.p0
        wrapped -= dr.floor(wrapped/(2*np.pi))*(2*np.pi)
        pw = dr.clip(wrapped/self.dp, 0., self.np-1.)
        it = mi.UInt(dr.minimum(dr.floor(tw), self.nt-2))
        ip = mi.UInt(dr.minimum(dr.floor(pw), self.np-2))
        wt, wp = tw-mi.Float(it), pw-mi.Float(ip)
        vals = []
        for buf in self.buffers:
            a = dr.gather(mi.Float, buf, it*self.np+ip)
            b = dr.gather(mi.Float, buf, it*self.np+ip+1)
            c = dr.gather(mi.Float, buf, (it+1)*self.np+ip)
            d = dr.gather(mi.Float, buf, (it+1)*self.np+ip+1)
            vals.append((1-wt)*((1-wp)*a+wp*b)+wt*((1-wp)*c+wp*d))
        return mi.Complex2f(vals[0],vals[1]), mi.Complex2f(vals[2],vals[3])


class Ports(AntennaPattern):
    def __init__(self, ports):
        self.owners = ports
        self.patterns = [p.evaluate for p in ports]


def make_scene(root, row, manifest, txp, rxp):
    scene = rt.load_scene()
    objects, bindings = [], []
    for item in manifest[row['scene_id']]['materials']:
        model, name = item['material_id'], item['object_name']
        thickness = item['thickness_m']
        if model == 'EPS4_LOSSLESS':
            mat = rt.RadioMaterial(name='rm_'+name, thickness=thickness,
                                   relative_permittivity=4., conductivity=0.)
        else:
            mat = rt.ITURadioMaterial(name='rm_'+name,
                itu_type='metal' if model == 'PEC' else model,
                thickness=.001 if model == 'PEC' else thickness)
        objects.append(rt.SceneObject(fname=str(root/item['mesh']), name=name, radio_material=mat))
        bindings.append(dict(object=name, source_material=model,
                             native_material='metal' if model=='PEC' else model,
                             thickness_m=.001 if model=='PEC' else thickness))
    if row.get('dynamic_panel'):
        mat = rt.ITURadioMaterial(name='rm_dynamic_panel', itu_type='metal', thickness=.001)
        objects.append(rt.SceneObject(fname=str(root/row['dynamic_panel']),name='dynamic_panel',radio_material=mat))
        bindings.append(dict(object='dynamic_panel', source_material='PEC',native_material='metal',thickness_m=.001))
    scene.edit(add=objects)
    scene.tx_array = rt.AntennaArray(Ports(txp[:2]), mi.Point3f(0,0,0))
    scene.rx_array = rt.AntennaArray(Ports(rxp[:2]), mi.Point3f(0,0,0))
    for role, cls in [('tx',rt.Transmitter),('rx',rt.Receiver)]:
        angles = Rotation.from_matrix(row[role+'_rotation']).as_euler('ZYX')
        scene.add(cls(role,position=row[role],orientation=angles.tolist()))
    return scene, bindings


def los_fixture(banks, txp, rxp, indices):
    """Independent Cartesian receive/transmit contraction at rotated free space."""
    direction=np.array([.7,.4,.5]);direction/=np.linalg.norm(direction);distance=3.7
    angles={'tx':[.31,-.22,.17],'rx':[-.47,.26,-.13]};results=[]
    for fi in indices:
        f=float(banks[0]['freqs_hz'][fi]);scene=rt.load_scene();scene.frequency=f
        fields={}
        for role,ports in [('tx',txp),('rx',rxp)]:
            rotation=Rotation.from_euler('ZYX',angles[role]).as_matrix()
            d=(direction if role=='tx' else -direction)@rotation
            theta=np.arccos(np.clip(d[2],-1,1));phi=np.arctan2(d[1],d[0])
            vectors=[]
            for p,b in zip(ports,banks):
                p.update(b['e_theta'][fi],b['e_phi'][fi])
                th=np.deg2rad(b['theta_deg']);ph=np.deg2rad(b['phi_deg']);pp=(phi-ph[0])%(2*np.pi)+ph[0]
                e=RegularGridInterpolator((th,ph),np.stack((b['e_theta'][fi],b['e_phi'][fi]),axis=-1))([[theta,pp]])[0]
                et=np.array([np.cos(theta)*np.cos(phi),np.cos(theta)*np.sin(phi),-np.sin(theta)])
                ep=np.array([-np.sin(phi),np.cos(phi),0])
                vectors.append(rotation@(et*e[0]+ep*e[1])*np.sqrt(2*np.pi/376.730313668))
            fields[role]=np.array(vectors)
        scene.add(rt.Transmitter('tx',position=[0,0,0],orientation=angles['tx']))
        scene.add(rt.Receiver('rx',position=(direction*distance).tolist(),orientation=angles['rx']))
        for arm in range(3):
            ix=slice(2*arm,2*arm+2)
            scene.tx_array=rt.AntennaArray(Ports(txp[ix]),mi.Point3f(0,0,0))
            scene.rx_array=rt.AntennaArray(Ports(rxp[ix]),mi.Point3f(0,0,0))
            paths=rt.PathSolver()(scene,max_depth=0,los=True,specular_reflection=False,refraction=False)
            actual=(np.asarray(paths.a[0])+1j*np.asarray(paths.a[1])).reshape(2,2)
            expected=fields['rx'][ix]@fields['tx'][ix].T*299792458./f/(4*np.pi*distance)
            error=float(np.linalg.norm(actual-expected)/np.linalg.norm(expected))
            delay_error=float(np.max(abs(np.asarray(paths.tau)-distance/299792458.)))
            results.append(dict(bin=fi,arm=ARMS[arm],relative_complex_error=error,delay_error_s=delay_error,passed=error<1e-4 and delay_error<1e-12))
    return results


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True);ap.add_argument('--smoke',action='store_true')
    ap.add_argument('--start',type=int,default=0);ap.add_argument('--stop',type=int,default=41)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=False);dr.set_thread_count(4)
    c=json.loads((a.root/'CONFIG.json').read_text());rows=c['rows'][a.start:a.stop];rows=rows[:1] if a.smoke else rows
    manifest={s['scene_id']:s for s in json.loads((a.root/'SCENE_MESH_MANIFEST.json').read_text())['scenes']}
    banks=[]
    for name in c['ports']:
        p=a.root/'bank'/f'{name}_bank.npz'
        assert hashlib.sha256(p.read_bytes()).hexdigest()==c['bank_sha256'][p.name]
        with np.load(p) as z:
            banks.append({k:z[k] for k in z.files})
    freq=banks[0]['freqs_hz'];indices=[0,128,256] if a.smoke else list(range(len(freq)))
    txp=[BankPort(np.deg2rad(b['theta_deg']),np.deg2rad(b['phi_deg'])) for b in banks]
    rxp=[BankPort(np.deg2rad(b['theta_deg']),np.deg2rad(b['phi_deg']),True) for b in banks]
    solver=rt.PathSolver();receipts=[];calls=0
    if a.smoke:
        tests=los_fixture(banks,txp,rxp,indices);write(a.out/'LOS_FIXTURE.json',tests)
        assert all(t['passed'] for t in tests), 'FFD_NATIVE_LOS_ADAPTER_FAILED'
        print('LOS_FIXTURE_PASS',flush=True)
    write(a.out/'RUNTIME.json',dict(versions={n:importlib.metadata.version(n) for n in ['sionna-rt','mitsuba','drjit']},
        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        pathsolver_file=inspect.getfile(rt.PathSolver),pathsolver_sha256=hashlib.sha256(Path(inspect.getfile(rt.PathSolver)).read_bytes()).hexdigest(),
        calculator_file=inspect.getfile(type(solver._field_calculator)),
        calculator_sha256=hashlib.sha256(Path(inspect.getfile(type(solver._field_calculator))).read_bytes()).hexdigest(),
        custom_propagation=False,configuration=c['solver']))
    for row in rows:
        start=time.monotonic();scene,bindings=make_scene(a.root,row,manifest,txp,rxp)
        saved={};channels=[];counts=[]
        for fi in indices:
            scene.frequency=float(freq[fi])
            for i,b in enumerate(banks):
                txp[i].update(b['e_theta'][fi],b['e_phi'][fi]);rxp[i].update(b['e_theta'][fi],b['e_phi'][fi])
            arm_channels=[];arm_counts=[]
            for ai,arm in enumerate(ARMS):
                ix=slice(2*ai,2*ai+2)
                scene.tx_array=rt.AntennaArray(Ports(txp[ix]),mi.Point3f(0,0,0))
                scene.rx_array=rt.AntennaArray(Ports(rxp[ix]),mi.Point3f(0,0,0))
                paths=solver(scene,**c['solver']);calls+=1
                ar=np.asarray(paths.a[0])+1j*np.asarray(paths.a[1]);tau=np.asarray(paths.tau)
                n=ar.shape[-1];coef=ar.reshape(2,2,n);delay=tau.reshape(-1)
                assert len(delay)==n
                h=coef.astype(np.complex128)*np.exp(-2j*np.pi*float(freq[fi])*delay)[None,None,:]
                assert np.isfinite(h).all()
                arm_channels.append(h.sum(axis=-1));arm_counts.append(n)
                saved[f'{arm}_a_{fi:03d}']=coef;saved[f'{arm}_tau_{fi:03d}']=delay
                for key in ['vertices','interactions','objects','primitives','valid','theta_t','phi_t','theta_r','phi_r']:
                    saved[f'{arm}_{key}_{fi:03d}']=np.asarray(getattr(paths,key))
            channels.append(arm_channels);counts.append(arm_counts)
            if fi%32==0:print(json.dumps(dict(link=row['link_id'],bin=fi,paths=arm_counts,seconds=round(time.monotonic()-start,2))),flush=True)
        saved.update(H_arms=np.array(channels),arms=ARMS,frequencies_hz=freq[indices],tx_m=row['tx'],rx_m=row['rx'],ports=c['ports'])
        np.savez_compressed(a.out/(row['link_id']+'_NATIVE.npz'),**saved)
        receipt=dict(link_id=row['link_id'],scene_id=row['scene_id'],tx=row['tx'],rx=row['rx'],bins=indices,
                     path_counts=counts,bindings=bindings,elapsed_s=time.monotonic()-start,
                     object_indices={str(o.object_id):name for name,o in scene.objects.items()})
        write(a.out/(row['link_id']+'_RESULT.json'),receipt);receipts.append(receipt)
        print(json.dumps(dict(completed=row['link_id'],seconds=receipt['elapsed_s'])),flush=True)
    write(a.out/'STATUS.json',dict(status='NATIVE_SMOKE_COMPUTED' if a.smoke else 'NATIVE_BAND_COMPUTED',rows=len(rows),
                                  pathsolver_calls=calls,custom_propagation_calls=0))


if __name__=='__main__':main()
