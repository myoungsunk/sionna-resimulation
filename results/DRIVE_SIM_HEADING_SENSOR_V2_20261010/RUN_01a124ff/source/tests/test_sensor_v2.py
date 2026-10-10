"""Independent analytical, stochastic, legacy and correlation checks for sensor-v2."""
from __future__ import annotations
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import unittest
import numpy as np
from scipy.stats import chi2
from qclean_uwb.drivesim import sensors as old, filters as F, experiment as E
from qclean_uwb.drivesim import sensor_v2 as V
from qclean_uwb.drivesim.filter_v2 import transition, odometry_model, correlated_update, run_filter_v2

BASE='2337c33fe25917029c2aa95973e6ae7672386a5e'
RESULTS={}


def frozen(file,name):
    source=subprocess.check_output(['git','show',BASE+':src/qclean_uwb/drivesim/'+file],text=True)
    spec=importlib.util.spec_from_loader(name,loader=None); m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m; exec(compile(source,file,'exec'),m.__dict__); return m


def fd(fun,x):
    result=[]
    for j in range(len(x)):
        e=np.zeros_like(x);e[j]=1e-6
        result.append((np.asarray(fun(x+e))-np.asarray(fun(x-e)))/(2e-6))
    return np.array(result).T


class SensorV2Tests(unittest.TestCase):
    def test_01_legacy_regression(self):
        legacy=frozen('sensors.py','frozen_sensors'); lf=frozen('filters.py','frozen_filters'); le=frozen('experiment.py','frozen_experiment')
        for seed in (0,1,5,29,101):
            ds=np.r_[0.,np.full(180,.04)]; th=np.r_[0.,np.sin(np.arange(180))*.04]
            current=old.generate_inputs(ds,th,old.draw_drift(old.DRIFT_LEVELS[1],np.random.default_rng(seed)),old.SensorNoise(),.2,np.random.default_rng(seed+100))
            original=legacy.generate_inputs(ds,th,legacy.draw_drift(legacy.DRIFT_LEVELS[1],np.random.default_rng(seed)),legacy.SensorNoise(),.2,np.random.default_rng(seed+100))
            for key in current: np.testing.assert_array_equal(current[key],original[key])
            n=len(ds); obs=dict(detected=np.ones(n,bool),range_m=np.full(n,4.2),s=np.zeros(n),power=np.ones((n,2)))
            flags=dict(turn_phase=np.abs(th)>.03)
            for kind in ('ekf','iekf','ukf','gsf'):
                args=dict(kind=kind,use_s=False,use_range=True)
                a=F.run_filter(F.FilterConfig(**args),None,current,obs,flags,np.zeros(6))
                b=lf.run_filter(lf.FilterConfig(**args),None,original,obs,flags,np.zeros(6))
                for key in ('est','cov3'): np.testing.assert_array_equal(a[key],b[key])
                for key in a['stats']: np.testing.assert_array_equal(a['stats'][key],b['stats'][key])
            rows=[dict(t_s=k*.2,x=k*.04,y=0.,yaw_body_deg=0.,turn_phase=False,drive_g=k,probe_id=-1) for k in range(n)]
            world=E.World(rows,np.empty((n,0,2,2)),np.empty(0),0.,0.,None)
            a=E.run_one(world,obs,current,F.FilterConfig(use_s=False),None,np.zeros(6))
            b=le.run_one(world,obs,original,F.FilterConfig(use_s=False),None,np.zeros(6))
            for key in ('heading_err_deg','pos_err_m'): np.testing.assert_array_equal(a[key],b[key])
            for key in a['metrics']: np.testing.assert_equal(a['metrics'][key],b['metrics'][key])
        RESULTS['legacy_regression']='exact sensors, all 4 filters, experiment metrics; 5 seeds'

    def test_02_motion_and_geometry(self):
        ds=np.r_[0.,np.zeros(5),np.full(10,.1),np.full(10,-.1),np.zeros(10),np.full(10,.1)]
        a=np.r_[0.,np.zeros(25),np.full(10,.2),np.full(10,-.1)]
        t=np.arange(len(ds))*.2; pose=V.integrate(ds,a,(1.,2.,3.13))
        recovered=V.motion_increments(t,np.column_stack([pose[:,:2],V.wrap(pose[:,2])]))
        np.testing.assert_allclose(recovered[0],ds,atol=1e-10);np.testing.assert_allclose(recovered[1],a,atol=1e-10)
        np.testing.assert_allclose(V.integrate(*recovered,pose0=pose[0]),pose,atol=1e-10)
        inputs,ev=V.generate(t,ds,a,V.SensorV2Config(condition='none'),1)
        np.testing.assert_allclose(inputs['ds_odom'],ds,atol=1e-10)
        np.testing.assert_allclose(inputs['dtheta_odom'],a,atol=1e-10)
        np.testing.assert_allclose(V.integrate(inputs['ds_odom'],inputs['dtheta_gyro'],pose[0]),pose,atol=1e-10)
        for eb in (-.0075,0.,.0075):
            inp,ev=V.generate(t,ds,a,V.SensorV2Config(condition='asymmetry_wheelbase'),1,dict(wheel_asymmetry=.005,wheelbase=eb))
            for k in range(1,len(t)):
                x=np.array([0.,0.,0.,0.,0.,.005])
                h,_,_=odometry_model(x,inp['ds_odom'][k],inp['dtheta_gyro'][k],.2,.287,eb)
                self.assertAlmostEqual(h,inp['dtheta_odom'][k],places=12)
        RESULTS['motion']='stop/reverse/turn/arc/yaw-boundary recovered; known wheelbase measurement exact'

    def test_03_analytical_endpoints(self):
        T=50.;dt=.2;t=np.arange(251)*dt;ds=np.r_[0.,np.full(250,.2*dt)]
        values={}
        for term,omega in (('gyro_bias',math.radians(.05)),('wheel_asymmetry',.005*.2/.287)):
            a=np.r_[0.,np.full(250,omega*dt)]
            pred=V.integrate(ds,a)[-1]
            expected=np.array([.2*np.sin(omega*T)/omega,.2*(1-np.cos(omega*T))/omega,omega*T])
            np.testing.assert_allclose(pred,expected,atol=1e-9)
            cfg=V.SensorV2Config(condition=term)
            params={'gyro_bias':math.radians(.05)} if term=='gyro_bias' else {'wheel_asymmetry':.005}
            inp,_=V.generate(t,ds,np.zeros(251),cfg,22,params)
            yaw=inp['dtheta_gyro'] if term=='gyro_bias' else inp['dtheta_odom']
            np.testing.assert_allclose(V.integrate(inp['ds_odom'],yaw)[-1],expected,atol=1e-9)
            # Legacy previous-heading Euler is an explicitly different quadrature.
            theta=np.cumsum(a); xy=np.sum(ds[1:,None]*np.column_stack([np.cos(theta[:-1]),np.sin(theta[:-1])]),axis=0)
            values[term]=dict(endpoint=pred.tolist(),legacy_euler_endpoint_difference_m=float(np.linalg.norm(xy-pred[:2])))
        heading=math.radians(5.)
        np.testing.assert_allclose(V.integrate(ds,np.zeros(251),(0,0,heading))[-1], [10*np.cos(heading),10*np.sin(heading),heading],atol=1e-9)
        RESULTS['analytical_endpoints']=values

    def test_04_jacobians(self):
        r=np.random.default_rng(8001);maxima=dict(F=0.,G=0.,H=0.,B=0.)
        for k in range(100):
            x=r.normal(size=6)*np.array([1,1,.5,.001,.01,.01]);d=r.uniform(-.1,.1);g=r.uniform(-.2,.2);dt=.2;b=.287
            if k==0:g=x[3]*dt
            out,J,G=transition(x,d,g,dt,b)
            maxima['F']=max(maxima['F'],float(np.max(np.abs(fd(lambda xx:transition(xx,d,g,dt,b)[0],x)-J))))
            maxima['G']=max(maxima['G'],float(np.max(np.abs(fd(lambda u:transition(x,u[0],u[1],dt,b)[0],np.array([d,g]))-G[:,:2]))))
            h,H,B=odometry_model(x,d,g,dt,b,.0075)
            maxima['H']=max(maxima['H'],float(np.max(np.abs(fd(lambda xx:odometry_model(xx,d,g,dt,b,.0075)[0],x)-H))))
            grad=fd(lambda u:odometry_model(x,u[0],u[1],dt,b,.0075)[0],np.array([d,g]))
            maxima['B']=max(maxima['B'],float(np.max(np.abs(grad+B[:2]))))
        for value in maxima.values(): self.assertLess(value,2e-7)
        RESULTS['jacobian_max_abs_errors']=maxima

    def test_05_shared_noise(self):
        x=np.array([0.,0.,.2,.001,.01,.005]);_,Fj,G=transition(x,.05,.03,.2,.287)
        _,H,B=odometry_model(x,.05,.03,.2,.287)
        P0=np.diag([.01,.01,.01,1e-6,1e-4,1e-4]);Q=np.diag([1e-6,2e-8,1e-6])
        P=Fj@P0@Fj.T+G@Q@G.T;C=-G@Q@B;R=float(B@Q@B)
        _,posterior,S=correlated_update(x,P,H,0.,R,C)
        np.testing.assert_allclose(posterior,P-np.outer(P@H+C,P@H+C)/S,atol=1e-12)
        _,standard,S0=correlated_update(x,P,H,0.,R,np.zeros(6))
        np.testing.assert_allclose(standard,P-np.outer(P@H,P@H)/S0,atol=1e-12)
        draw=np.random.default_rng(88001);count=4096
        e0=draw.multivariate_normal(np.zeros(6),P0,count);n=draw.multivariate_normal(np.zeros(3),Q,count)
        em=e0@Fj.T-n@G.T;v=n@B;y=em@H+v
        ep=em-y[:,None]*(P@H+C)/S
        sample=np.cov(ep,rowvar=False);relative=float(np.linalg.norm(sample-posterior)/np.linalg.norm(posterior))
        self.assertLess(relative,.15)
        nees=np.einsum('ni,ij,nj->n',ep,np.linalg.inv(posterior),ep)
        mean=float(nees.mean());lo,hi=chi2.ppf([1e-6,1-1e-6],6*count)/count
        self.assertTrue(lo<=mean<=hi)
        coverage=float(np.mean(nees<=chi2.ppf(.95,6)));self.assertLess(abs(coverage-.95),6*np.sqrt(.95*.05/count))
        RESULTS['shared_noise_linear']=dict(covariance_relative_error=relative,mean_nees=mean,coverage95=coverage,interval=[lo,hi],wheel_distance_C_norm=float(np.linalg.norm(-G[:,0]*Q[0,0]*B[0])),gyro_C_norm=float(np.linalg.norm(-G[:,1]*Q[1,1]*B[1])))

    def test_06_variance_slip_sample_rate(self):
        results=[]
        for dt in (.1,.2,.4):
            t=np.arange(round(10/dt)+1)*dt;n=len(t);gyro=[];bias=[];wheels=[];events=0
            cfg=V.SensorV2Config(condition='all',bias_rw_rad_s_sqrt_s=1e-4)
            for seed in range(100,4196):
                inp,ev=V.generate(t,np.zeros(n),np.r_[0.,np.full(n-1,.1*dt)],cfg,seed,dict(gyro_bias=0.,gyro_sf=0.,wheel_asymmetry=0.,wheelbase=0.))
                # Gyro white noise separated from left-endpoint generated bias.
                gyro.append(np.sum(inp['dtheta_gyro']-ev['true_increments'][:,1]-np.r_[ev['true_bias_rad_s'][0],ev['true_bias_rad_s'][:-1]]*inp['dt_s']))
                bias.append(ev['true_bias_rad_s'][-1]);events+=int(ev['slip_event'].sum())
                noisy,_=V.generate(t,np.r_[0.,np.full(n-1,.2*dt)],np.r_[0.,np.full(n-1,.1*dt)],V.SensorV2Config(condition='wheel_noise'),seed)
                wheels.append([np.sum(noisy['ds_odom'])-2.,np.sum(noisy['dtheta_odom'])-1.])
            gv=float(np.var(gyro,ddof=1));bv=float(np.var(bias,ddof=1));wc=np.cov(wheels,rowvar=False)
            expectg=cfg.gyro_N_rad_sqrt_s**2*10;expectb=cfg.bias_rw_rad_s_sqrt_s**2*10
            expectw=np.diag([cfg.k_distance_m*2,cfg.k_yaw_rad+cfg.k_yaw_distance_rad2_m*2])
            self.assertLess(abs(gv/expectg-1),.15);self.assertLess(abs(bv/expectb-1),.15)
            self.assertTrue(np.all(np.abs(np.diag(wc)/np.diag(expectw)-1)<.15))
            p=-np.expm1(-cfg.slip_rate_per_s*dt);trials=4096*(n-1);expected_events=trials*p
            self.assertLess(abs(events-expected_events),6*np.sqrt(trials*p*(1-p)))
            A=V.wheel_transform(.287);qlr=V.wheel_covariance(expectw[0,0],expectw[1,1],.287)
            np.testing.assert_allclose(A@qlr@A.T,expectw,atol=1e-12)
            results.append(dict(dt_s=dt,gyro_variance=gv,gyro_expected=expectg,bias_variance=bv,bias_expected=expectb,wheel_covariance=wc.tolist(),wheel_expected=expectw.tolist(),slip_events=events,slip_expected=expected_events))
        RESULTS['independent_run_variances']=results

    def test_07_observability_and_refusals(self):
        def rank(rows):
            H=np.array([odometry_model(np.zeros(6),d,g,.2,.287)[1][3:] for d,g in rows]);s=np.linalg.svd(H,compute_uv=False)
            return dict(rank=int(np.linalg.matrix_rank(H,tol=1e-10)),singular_values=s.tolist())
        cases=dict(stop=[(0,0)]*20,constant_straight=[(.04,0)]*20,speed_change=[(d,0) for d in (.02,.04,.08)]*10,
                   bidirectional_turn=[(d,g) for d,g in ((0,.1),(0,-.1),(.04,0),(.08,0))]*10)
        measured={k:rank(v) for k,v in cases.items()}
        self.assertEqual([measured[k]['rank'] for k in cases],[1,1,2,3])
        for kind in ('iekf','ukf','gsf'):
            with self.assertRaisesRegex(ValueError,'supports EKF'):
                run_filter_v2(F.FilterConfig(model_version='sensor-v2',kind=kind,use_s=False),None,dict(dt_s=[0,.2],ds_odom=[0,0],dtheta_gyro=[0,0],dtheta_odom=[0,0]),{}, {},np.zeros(6))
        RESULTS['calibration_observability']=measured

    def test_08_configuration_raw_and_limits(self):
        from qclean_uwb.drivesim.evaluation_v2 import mixed_world, directional, IdealRatio
        from qclean_uwb.drivesim.hs_lut import s_model
        endpoints=[]
        for dt in (.1,.2,.4):
            world,ds,a=mixed_world(dt);endpoints.append(world.truth[-1])
            cfg=V.SensorV2Config(condition='wheelbase')
            inputs,ev=V.generate(world.t,ds,a,cfg,11,dict(wheelbase=.0075))
            filter_cfg=F.FilterConfig(model_version='sensor-v2',known_wheelbase_error=.0075,use_range=False,use_s=False,bias_rw_std=0.)
            x0=np.r_[world.truth[0],0.,0.,0.]
            out=run_filter_v2(filter_cfg,None,inputs,{},dict(turn_phase=world.turn_phase),x0)
            np.testing.assert_allclose(out['est'][:,:3],world.truth,atol=1e-10)
            self.assertEqual(out['cov_full'].shape,(len(ds),6,6))
            self.assertTrue((out['observation_trace']['range_status']=='disabled').all())
            self.assertLess(np.max(np.abs(out['cov_full']-out['cov_full'].transpose(0,2,1))),1e-12)
            self.assertGreaterEqual(np.min(np.linalg.eigvalsh(out['cov_full'])),-1e-10)
        np.testing.assert_allclose(np.array(endpoints),np.broadcast_to(endpoints[0],(3,3)),atol=1e-10)
        world,ds,a=mixed_world()
        for term in V.CONDITIONS:
            inputs,ev=V.generate(world.t,ds,a,V.SensorV2Config(condition=term),1)
            self.assertTrue(np.isfinite(inputs['encoder_angle_rad']).all())
        common,_=V.generate(world.t,ds,a,V.SensorV2Config(condition='common_scale',common_scale=.01),1)
        np.testing.assert_allclose(common['ds_odom'],1.01*ds,atol=1e-12)
        np.testing.assert_allclose(common['dtheta_odom'],1.01*a,atol=1e-12)
        timed,te=V.generate(world.t,ds,a,V.SensorV2Config(slip_mode='time'),33)
        legacy,le=V.generate(world.t,ds,a,V.SensorV2Config(slip_mode='legacy-event'),33)
        np.testing.assert_array_equal(te['slip_event'],le['slip_event'])
        np.testing.assert_array_equal(te['slip_yaw_rad'],le['slip_yaw_rad'])
        pose=np.zeros((3,3));pose[:,0]=[0,.1,.2];pose[:,2]=[0,.2,.4]
        pose[2,:2]=pose[1,:2]+.1*np.array([np.cos(.2),np.sin(.2)])
        with self.assertRaises(ValueError):V.motion_increments([0,.2,.4],pose)
        d,th=V.motion_increments([0,.2,.4],pose,convention='legacy-euler')
        np.testing.assert_allclose(d,[0,.1,.1],atol=1e-12)
        self.assertGreater(np.linalg.norm(V.integrate(d,th)[-1,:2]-pose[-1,:2]),1e-3)
        directions=directional(np.array([[4.,0.,0.],[4.,0.,.1],[3.9,0.,.1]]),np.zeros((3,6)),np.array([0.,0.,-.1]),np.zeros(3),(4.,0.,2.65))
        np.testing.assert_array_equal(directions['anchor_direction_valid'],[False,False,True])
        np.testing.assert_array_equal(directions['reverse_mask'],[False,False,True])
        # Ideal ratio Jacobian independently checked; no claim about physical LUT validity.
        x=np.array([1.3,.4,.2]);lut=IdealRatio()
        _,J=s_model(lut,(4.,0.,2.65),.45,*x,with_jac=True)
        np.testing.assert_allclose(J,fd(lambda xx:s_model(lut,(4.,0.,2.65),.45,*xx),x),atol=2e-7)
        RESULTS['configuration_raw_limits']='all conditions finite; common scale; known e_b corrected trajectory; PSD; dt path invariance; explicit Euler mismatch; masks; synthetic-s Jacobian'

    def test_09_observation_status(self):
        cfg=F.FilterConfig(model_version='sensor-v2',use_range=True,use_s=False,bias_rw_std=0.)
        inputs=dict(dt_s=np.array([0,.2,.2,.2]),ds_odom=np.zeros(4),dtheta_gyro=np.zeros(4),dtheta_odom=np.zeros(4))
        correct=np.sqrt(4**2+2.2**2)
        obs=dict(detected=np.array([False,True,False,True]),range_m=np.array([np.nan,100.,np.nan,correct]))
        out=run_filter_v2(cfg,None,inputs,obs,{},np.zeros(6))
        np.testing.assert_array_equal(out['observation_trace']['range_status'],['missing','rejected','missing','applied'])
        self.assertTrue(np.isfinite(out['observation_trace']['range_innovation'][1]))
        self.assertTrue(np.isnan(out['observation_trace']['range_innovation'][2]))
        RESULTS['observation_status']='missing/rejected/applied/disabled explicitly verified; R and S retained for rejection'

if __name__=='__main__':
    output=Path(sys.argv[1]) if len(sys.argv)>1 else None
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(SensorV2Tests)
    r=unittest.TextTestRunner(verbosity=2).run(suite)
    if output:
        if output.exists(): raise FileExistsError(output)
        output.write_text(json.dumps(dict(tests_run=r.testsRun,failures=len(r.failures),errors=len(r.errors),results=RESULTS),indent=2),encoding='utf8')
    sys.exit(not r.wasSuccessful())
