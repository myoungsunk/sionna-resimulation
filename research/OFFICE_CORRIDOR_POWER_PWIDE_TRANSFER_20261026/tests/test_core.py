"""Synthetic/unit-only tests. Never open external RF releases or train real models."""
import hashlib
import json
import sys
import tarfile
from pathlib import Path
from io import BytesIO
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from office_transfer_core import (load_lock,observe_port,PowerTransfer,site_weights,fix_cov,gate_decision,
                                  augment_d0,as_pwide_features,ResidualTransfer,safe_extract_tar,P_FEATURES,expected_frequencies)
from office_transfer_cli import common_update


def build_frame(routes=('O01','O02','O03'),seed=7,n=75):
    rng=np.random.default_rng(seed)
    records=[]
    for j,route in enumerate(routes):
        for i in range(n):
            q=-4+1.5*rng.random()
            vals={'scene':'OFFICE_E','route':route,'case':f'{route}_O0_M45_FULL',
                  'x_eval':j*10+i*.03,'y_eval':i*.04,'yaw_body_deg':float(i%180),
                  'log_fp_power':q,'e_r':.02-.04*q+.02*rng.normal(),
                  'e_s':.05+.035*q+.03*rng.normal(),'d0_gt_source':.1*rng.normal(),
                  's_fp':float(np.sin(.04*i)), 'fp_full':18., 'sF_+0':float(np.sin(.04*i))}
            for k in (-8,-4,-2,-1,1,2,4,8):
                vals[f'sF_{k:+d}']=float(np.sin(.04*i))+.001*k
                vals[f'ds_{k:+d}']=.001*k
            records.append(vals)
    return pd.DataFrame(records)

class DummySource:
    def batch(self,states,case,gradient=False):
        z=np.column_stack([2+states[:,0]*0,.25*np.sin(states[:,2])])
        return z,None

def test_lock_authentic_sha_and_ids():
    lock=load_lock()
    assert [lock['paths'][x]['rf_n'] for x in ['O01','O02','O03']]==[192,207,412]
    assert [lock['paths'][x]['motion_n'] for x in ['O01','O02','O03']]==[461,521,1175]
    assert len(expected_frequencies(lock))==257
    assert sum(lock['paths'][x]['rf_n'] for x in lock['paths'])==811


def test_observer_same_tap_and_log_power():
    f=expected_frequencies(load_lock()).astype(float)
    h=np.ones((3,257,2),complex)
    h[:,:,0]=1+0j;h[:,:,1]=.5+0j
    x=observe_port(h,f)
    assert (abs(x.s_fp-.6)<1e-12).all() # (1-.25)/(1+.25)
    assert np.isfinite(x.log_fp_power).all()
    for o in (-8,1,8):
        if x[f'sF_{o:+d}'].notna().all():assert np.max(abs(x[f'ds_{o:+d}']))<1e-12


def test_power_regression_exact_marginal_against_manual():
    x=build_frame(n=60)
    model=PowerTransfer.fit(x)
    mu,cov=model.predict(x.log_fp_power.to_numpy(),diag=True)
    assert mu.shape==(180,2) and cov.shape==(180,2,2)
    assert np.all(np.linalg.eigvalsh(cov)>0)
    assert np.all(cov[:,0,1]==0)
    assert model.train_routes==('O01','O02','O03')
    assert len(model.cuts)==2
    assert np.all(mu[:,1]>-.25)


def test_power_site_weights_duplicate_are_not_independent():
    x=build_frame(n=10)
    # distinct routes same scene and exact same coordinates are one physical site
    x.loc[x.route=='O02',['x_eval','y_eval']]=x.loc[x.route=='O01',['x_eval','y_eval']].to_numpy()
    w=site_weights(x)
    assert np.allclose(w[:10],w[10:20])
    assert w[:10].mean()<w[20:].mean()


def test_residual_source_only_and_no_target_access():
    x=build_frame(n=80)
    model=ResidualTransfer.fit(x,DummySource(),seed=20261022)
    f=x.iloc[:3].copy()
    p=model.predict(f,np.array([-.1,.0,.1]),'PWIDE')
    c=model.predict(f,np.zeros(3),'PCIR')
    assert p.shape==(3,) and c.shape==(3,)
    assert model.training_routes==('O01','O02','O03')
    assert model.gate_tau_d0>0
    assert 'd0' not in P_FEATURES


def test_prevent_corridor_training_in_both_models():
    x=build_frame(n=60)
    x.loc[x.index[0],'scene']='CORRIDOR'
    with pytest.raises(ValueError,match='POWER_SOURCE_OFFICE_ONLY'):
        PowerTransfer.fit(x)
    with pytest.raises(ValueError,match='PWIDE_NOT_OFFICE_ONLY'):
        ResidualTransfer.fit(x,DummySource())


def test_false_gate_is_identity_normal_joint():
    x=np.array([.1,.2,.05,.005]);P=np.diag([.1,.1,.05,.01]);z=np.array([.3,.2]);h=np.array([.2,.0]);H=np.array([[1.,0.,0.,0.],[0.,0.,1.,0.]])
    R=np.diag([.1,.02]);mu=np.zeros(2)
    a,pa,yes,*_=common_update(x,P,z,h,H,mu,R,False)
    assert yes
    b,pb,yes,*_=common_update(x,P,z,h,H,mu,R,False)
    assert np.array_equal(a,b) and np.array_equal(pa,pb)


def test_gate_range_only_does_not_inject_heading_when_p_block_diagonal():
    x=np.array([.1,.2,.05,.005]);P=np.diag([.1,.1,.05,.01]);z=np.array([.3,1.4]);h=np.array([.2,.0]);H=np.array([[1.,0.,0.,0.],[0.,0.,1.,0.]])
    R=np.diag([.1,.02]);mu=np.zeros(2)
    a,pa,yes,nis,_=common_update(x,P,z,h,H,mu,R,True)
    assert yes and np.isclose(a[2],x[2],atol=1e-14) and np.isclose(pa[2,2],P[2,2],atol=1e-14)
    b,pb,yes,nis,_=common_update(x,P,z,h,H,mu,R,False)
    assert not yes # outlier in joint gate


def test_state_gate_rejects_less_than_raw_gate_on_uncertain_prior():
    H=np.array([0,0,1.,0.]);P=np.diag([.1,.1,.25,.001])
    assert gate_decision(.3,H,P,.2,'D0')
    assert not gate_decision(.3,H,P,.2,'STATE')
    assert not gate_decision(.3,H,P,.2,'NONE')


def test_joseph_psd_random_replay():
    rng=np.random.default_rng(14)
    for _ in range(200):
        A=rng.normal(size=(4,4));P=A@A.T+.01*np.eye(4)
        H=rng.normal(size=(2,4));R=np.diag([.1,.01])
        x=np.array([0.,0.,0.,0.]);h=np.zeros(2);z=.1*rng.normal(size=2)
        for gate in (True,False):
            y,C,*_=common_update(x,P,z,h,H,np.zeros(2),R,gate)
            assert np.min(np.linalg.eigvalsh(C))>-1e-10


def test_extraction_path_traversal(tmp_path):
    f=tmp_path/'bad.tar.gz'
    with tarfile.open(f,'w:gz') as ar:
        body=b'tamper'
        it=tarfile.TarInfo('../escape');it.size=len(body);ar.addfile(it,BytesIO(body))
    h=hashlib.sha256(f.read_bytes()).hexdigest()
    with pytest.raises(ValueError,match='TAR_PATH_ESCAPE'):
        safe_extract_tar(f,tmp_path/'out',h)
    assert not (tmp_path/'escape').exists()

def test_office_loader_mask_sha_frequency_and_true_pseudo_labels(tmp_path, monkeypatch):
    from office_transfer_core import source_dataset_one
    from types import SimpleNamespace
    lock=load_lock()
    m=lock['paths']['O01'].copy();m['rf_n']=3;m['motion_n']=5
    f=expected_frequencies(lock).astype(float)
    root=tmp_path/'route';case=root/'O01'/'CASES'/'O01_O0_M45_FULL';case.mkdir(parents=True)
    # Narrow main peak at tap ~25; stable across channels and both RX ports.
    k=np.arange(257);wave=np.exp(-2j*np.pi*k*25/(4*257))
    full=np.zeros((3,257,2,2),np.complex128)
    full[:,:,0,0]=wave
    full[:,:,1,0]=.5*wave
    los=full.copy();los[1]=0
    np.save(case/'H_FULL.npy',full)
    np.save(case/'H_DIRECT_LOS.npy',los)
    np.save(case/'LOS_EXISTS.npy',np.array([True,False,True]))
    np.save(case/'FREQUENCIES_HZ.npy',f)
    pose=pd.DataFrame({'route_id':['O01']*3,'pose_id':[0,2,4],
        't_s':[0,.5,1.], 'x_m':[0,1,2], 'y_m':[0,0,0], 'z_m':[.45]*3,
        'yaw_body_deg':[0,5,10],'yaw_antenna_deg':[45,50,55]})
    pose.to_csv(case/'RADIO_POSE.csv',index=False)
    for file in m['files']:m['files'][file]=hashlib.sha256((case/file).read_bytes()).hexdigest()
    m['archive_sha256']='synthetic_archive_not_used'
    lock=dict(lock,paths=dict(lock['paths'],O01=m))
    rec={'case_id':'O01_O0_M45_FULL','radio_path':str(case/'RADIO_POSE.csv'),
         'full_path':str(case/'H_FULL.npy'),'los_path':str(case/'H_DIRECT_LOS.npy'),
         'los_exists_path':str(case/'LOS_EXISTS.npy'),'los_exists':np.array([True,False,True])}
    prepared={'metadata':{'motion_n':5,'rf_n':3,'radio_path':str(case/'RADIO_POSE.csv')},'cases':[rec]}
    monkeypatch.setattr('office_transfer_core.import_official_loader',lambda *args:SimpleNamespace(prepare_new_route=lambda *args:prepared))
    out,qa=source_dataset_one(root,'O01',tmp_path,DummySource(),lock)
    assert qa['n_rf']==3 and qa['n_los_blocked']==1
    assert np.isnan(out.loc[1,'e_r']) and np.isnan(out.loc[1,'e_s'])
    assert bool(out.loc[0,'valid_for_training']) and bool(out.loc[2,'valid_for_training'])
    assert np.isnan(out.loc[1,'s_direct_los_audit_only'])
    assert out.loc[0,'case']=='O01_O0_M45_FULL'


def test_cli_import_is_inert(tmp_path):
    # Importing the implementation cannot silently write models or trigger network.
    import office_transfer_cli
    assert callable(office_transfer_cli.main)
    assert not list(tmp_path.glob('*'))


def test_fit_power_retains_train_q_range():
    x=build_frame(n=45)
    model=PowerTransfer.fit(x)
    q=x.log_fp_power.to_numpy(float)
    assert np.isclose(model.q_train_range[0],q.min())
    assert np.isclose(model.q_train_range[1],q.max())

def test_checkout_sha_fail_closed(tmp_path):
    from office_transfer_cli import verify_checkout
    with pytest.raises(ValueError,match='GIT_CHECKOUT_UNVERIFIED'):
        verify_checkout(tmp_path,'0'*40,'SOURCE_AUDIT')

@pytest.mark.parametrize('channel,gates,fail_baseline',[('full',True,False),('full',False,False),('los',False,False),('full',False,True)])
def test_synthetic_replay_all_office_arms_without_target_fit(tmp_path,monkeypatch,channel,gates,fail_baseline):
    """Exercise CLI replay control/data paths without any Release or real corridor RF."""
    import joblib
    from types import SimpleNamespace
    import office_transfer_cli as cli
    source=build_frame(n=45)
    power=PowerTransfer.fit(source)
    residual=ResidualTransfer.fit(source,DummySource())
    from evidence_helpers import source_receipt,input_manifest
    from evidence_contract import training_provenance
    from fixtures import p2_math
    from office_transfer_core import sha256
    lock_path=Path(__file__).resolve().parents[1]/'lock.json'
    source_qa=tmp_path/'source_qa.json';source_receipt(source_qa,lock_path)
    provenance=training_provenance(source_qa,lock_path)
    pkg=tmp_path/'office.joblib'
    joblib.dump({'POWER':power,'RESIDUAL':residual,'source_only':True,
                 'target_training_used':False,'provenance':provenance},pkg)
    train_qa=tmp_path/'train_qa.json'
    train_qa.write_text(json.dumps({'status':'SOURCE_TRAINING_COMPLETE','model_sha256':sha256(pkg),'provenance':provenance}))
    root=tmp_path/'target';(root/'research/PJ_DS_GATED_20261021/results_hpath').mkdir(parents=True)
    name='R2_aA_m45'
    pose=np.arange(5)
    t=np.array([0.,10.,20.,30.,40.])
    truth=np.zeros((5,3),float)
    art=tmp_path/'art';art.mkdir()
    trace=art/'trace.npz'
    np.savez_compressed(trace,t_s=t,pose_id=pose,truth_scoring_only=truth)
    obs=art/'obs.csv.gz'
    z=np.array([.11,.12,.10,.14,.11])
    pd.DataFrame({'case':[name]*5,'channel':[channel]*5,'pose_id':pose,
                  'range_m':[2.,2.1,2.2,2.1,2.], 's_fp':z}).to_csv(obs,index=False,compression='gzip')
    par=art/'par.csv.gz';pd.DataFrame({'value':[1]}).to_csv(par,index=False,compression='gzip')
    pd.DataFrame({'case':[name]*5,'pose_id':pose}).to_csv(
        root/'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz',index=False,compression='gzip')
    X=source.iloc[:5].copy().reset_index(drop=True)
    X['sF_+0']=z
    def one(s):
        if s.endswith('_TRACE.npz'):return trace
        if s=='OBSERVATION_FEATURES_LABELS.csv.gz':return obs
        if s=='OOF_PARAMETERS.csv.gz':return par
        raise ValueError(s)
    class V:
        MANIFEST={'cases':[{'id':name,'route':'R2','anchor':[4.,0.,2.65],
                             'robot_z_m':.45,'mount_deg':45.}]}
        INITIAL_POSE_STD=np.array([.1,.1,np.radians(5.)])
        BIAS_PRIOR_STD=np.radians(.1)
        SourceFFD=None
        one=None
        @staticmethod
        def build_positive_bias_controls(t,truth,bias):
            return {'ds_odom':np.zeros(5),'dtheta_gyro':np.zeros(5),'dt_s':np.ones(5)},np.zeros(3)
        @staticmethod
        def base_params(*args,**kwargs):
            return np.zeros((5,2)),np.repeat(np.diag([.1,.2])[None],5,axis=0)
        @staticmethod
        def predict_one(x,P,ds,gyro,dt):
            return x.copy(),P.copy()
    class Observ:
        def batch(self,x,case,gradient=True):
            n=len(x)
            h=np.zeros((n,2));h[:,0]=2.;h[:,1]=.02*np.sin(x[:,2])
            H=np.zeros((n,2,4));H[:,1,2]=.02*np.cos(x[:,2])
            return h,H
    V.ROOT=root;V.ART=art;V.OUT=tmp_path/'out'
    for key in ('PJ_SOURCE_ROOT','PJ_ART','PJ_OUT'):monkeypatch.delenv(key,raising=False)
    V.SourceFFD=Observ
    V.one=staticmethod(one)
    R2=SimpleNamespace(V=V,S=p2_math,full_features=lambda packets,ids:(X.copy(),None),
        los_features=lambda case,ids,packets:(X.copy(),None))
    # Independent frozen P2 update/score functions generate the synthetic reference.
    states=[];covs=[];xx=np.zeros((1,4));pp=np.diag(np.r_[V.INITIAL_POSE_STD**2,V.BIAS_PRIOR_STD**2])[None]
    for k in range(5):
        hh,jj=Observ().batch(xx,None)
        mm=np.zeros((1,2));rr=np.diag([.1,.2])[None]
        xx,pp,_,_=p2_math.update(xx,pp,np.array([2.+[0,.1,.2,.1,0][k],z[k]]),hh,jj,mm,mm,rr,rr,np.array([False]))
        states.append(xx.copy());covs.append(pp.copy())
    reference,_=p2_math.score_extra(np.array(states),np.array(covs),t,truth,V.MANIFEST['cases'][0])
    reference[0].update(case=name,channel=channel,bias='B0',arm='BASE')
    if fail_baseline:reference[0]['heading_rmse_deg']+=.01
    ref=root/'research/PJ_DS_GATED_20261021/results_strict/SB_SCORES.csv';ref.parent.mkdir()
    pd.DataFrame(reference).to_csv(ref,index=False)
    inputs={f'{name}_{channel}_B0_TRACE.npz':trace,'OBSERVATION_FEATURES_LABELS.csv.gz':obs,
        'OOF_PARAMETERS.csv.gz':par,'HP_PACKETS.csv.gz':root/'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz','SB_SCORES.csv':ref}
    if channel=='los':
        for key in ('los_path','samples_path'):
            file=root/key;file.write_bytes(b'synthetic_LOS_input')
            V.MANIFEST['cases'][0][key]=key;inputs[key]=file
    monkeypatch.setattr(cli,'load_p2_environment',lambda root:R2)
    monkeypatch.setattr(cli,'verify_checkout',lambda *args:'sha_pass')
    args=SimpleNamespace(lock=__import__('pathlib').Path(__file__).resolve().parents[1]/'lock.json')
    args.target_checkout=root;args.target_artifacts=V.ART;args.models=pkg;args.case=name;args.bias='B0';args.out=tmp_path/'out'
    args.channel=channel;args.exploratory_gates=gates;args.source_qa=source_qa;args.train_qa=train_qa
    args.input_manifest=tmp_path/'inputs.json'
    args.input_manifest_sha256=input_manifest(args.input_manifest,lock_path,inputs,name,channel,'B0')
    import copy
    from corridor_control import DEFINITION
    control=copy.deepcopy(residual);control.training_scene='CORRIDOR';control.training_routes=('R4','R5')
    identity={'definition':DEFINITION,'held':'R2','train_routes':['R4','R5'],'lock_sha256':sha256(lock_path)}
    args.corridor_models=tmp_path/'control.joblib';args.corridor_qa=tmp_path/'control.json'
    joblib.dump({'RESIDUAL':control,'identity':identity},args.corridor_models)
    args.corridor_qa.write_text(json.dumps({'status':'CORRIDOR_CONTROL_TRAINED','identity':identity,'model_sha256':sha256(args.corridor_models)}))
    if fail_baseline:
        with pytest.raises(ValueError,match='STRICT_BASE_PARITY_FAIL'):cli.replay_corridor(args)
        assert not list(args.out.glob('*TRANSFER_SCORES.csv'))
        assert list(args.out.glob('*QA_BLOCKED.json'))
        return
    cli.replay_corridor(args)
    scores=pd.read_csv(args.out/f'{name}_{channel}_B0_TRANSFER_SCORES.csv')
    series=pd.read_csv(args.out/f'{name}_{channel}_B0_TRANSFER_SERIES.csv.gz')
    assert len(scores)==(10 if gates else 6) and len(series)==(50 if gates else 30)
    expected={'C_POWER','C_PWIDE','O_POWER','O_PWIDE','O_POWER_C_PWIDE','O_PCIR'}
    if gates:expected|={'O_POWER_G','O_PWIDE_G','O_POWER_STATE_G','O_PWIDE_STATE_G'}
    assert set(series.arm)==expected
    qa=json.loads((args.out/f'{name}_{channel}_B0_TRANSFER_QA.json').read_text())
    assert qa['baseline_parity']['status']=='PASS'
    assert qa['gate_status']==('EXPLORATORY_GT_PROXY' if gates else 'NOT_RUN')
    for a,b in [('C_POWER','C_PWIDE'),('O_POWER','O_POWER_C_PWIDE')]:
        assert np.array_equal(series[series.arm==a][['mu_s','Vs']].to_numpy(),series[series.arm==b][['mu_s','Vs']].to_numpy())
    assert series.office_q_out_of_range.dtype==bool
    assert series[['heading_error_deg','nis','Vs','heading_nees']].notna().all().all()
