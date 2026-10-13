"""S0 radial initialization and independent latent-input batch MCMC.

The first range is consumed by radial initialization, never by the subsequent
likelihood. A numerical tail truncation is audited separately from deliberately
bounded sensitivity runs. MCMC output remains an unapproved reference.
"""
from __future__ import annotations

import numpy as np
from scipy.integrate import quad, cumulative_simpson
from i2_batch import ConditionalBatchTarget, chain_diagnostics


class RadialTable:
    def __init__(self, z, sigma, dz, prior="area", cutoff_sigma=None):
        self.z, self.sigma, self.dz = float(z), float(sigma), abs(float(dz))
        if not np.all(np.isfinite([z, sigma, dz])) or sigma <= 0:
            raise ValueError("finite range/height and positive sigma required")
        if prior not in ("area", "radius", "halfnormal10", "halfnormal100"):
            raise ValueError("unknown radial prior")
        if cutoff_sigma is not None and float(cutoff_sigma) <= 0:
            raise ValueError("positive cutoff_sigma required")
        self.prior = prior
        self.offset = -.5 * ((max(self.dz, self.z) - self.z) / self.sigma) ** 2
        # This slant-distance upper boundary gives a Gaussian tail >=12 sigma
        # from the physical mode. Its omitted mass is independently bounded.
        slant_hi = max(self.dz, self.z) + 12 * self.sigma
        self.unbounded_hi = np.sqrt(slant_hi ** 2 - self.dz ** 2)
        self.hi = self.unbounded_hi if cutoff_sigma is None else np.sqrt(
            (max(self.dz, self.z) + float(cutoff_sigma) * self.sigma) ** 2 - self.dz ** 2)
        mode = np.sqrt(max(0., self.z ** 2 - self.dz ** 2))
        def mass(hi):
            return quad(self._density, 0, hi, points=[mode] if 0 < mode < hi else None,
                        epsabs=1e-13, epsrel=1e-12, limit=300)
        full, err = mass(self.unbounded_hi)
        self.norm, integration_error = mass(self.hi)
        # For rho>=hi, all non-area priors <=1 and d rho <= rho d rho/hi.
        # Transform the area tail to slant distance and integrate its smooth
        # Gaussian kernel over standardized range, avoiding narrow-tail misses.
        t0 = (slant_hi - self.z) / self.sigma
        area_tail = quad(lambda t: self.sigma * (self.z + self.sigma * t)
                         * np.exp(-.5*t*t-self.offset), t0, np.inf,
                         epsabs=1e-100, epsrel=1e-10)[0]
        bound = area_tail if prior == "area" else area_tail / self.unbounded_hi
        if full <= 0 or not np.isfinite(full) or bound / full > 1e-12:
            raise ValueError("radial normalization/tail audit failed")
        self.grid = np.linspace(0., self.hi, 65537)
        density = self._density(self.grid)
        raw = cumulative_simpson(density, x=self.grid, initial=0.)
        self.cdf = raw/raw[-1]
        coarse_grid = self.grid[::2]
        coarse = cumulative_simpson(density[::2], x=coarse_grid, initial=0.)
        coarse /= coarse[-1]
        cdf_error = float(np.max(np.abs(self.cdf[::2]-coarse)))
        quadrature_error = abs(raw[-1]-self.norm)/self.norm
        probabilities=np.linspace(.0001,.9999,1001)
        quantile_error=float(np.max(np.abs(np.interp(probabilities,self.cdf,self.grid)
                                 -np.interp(probabilities,coarse,coarse_grid))))
        if quadrature_error > 1e-9 or cdf_error > 1e-8 or quantile_error > 1e-5:
            raise ValueError("radial numerical-resolution audit failed")
        self.diagnostics = dict(prior=prior, cutoff_sigma=cutoff_sigma,
            normalization=float(self.norm), integration_error=float(integration_error),
            unbounded_normalization=float(full), unbounded_integration_error=float(err),
            numerical_tail_mass_bound=float(bound/full),
            excluded_mass_fraction=max(0., float(1-self.norm/full)),
            quadrature_relative_error=float(quadrature_error),
            cdf_resolution_error=cdf_error, numerical_upper_radius=float(self.hi),
            quantile_resolution_error_m=quantile_error,
            reference_measure="uniform 2D spatial density" if prior == "area" else prior)

    def _density(self, rho):
        rho = np.asarray(rho)
        loglike = -.5*((np.sqrt(rho*rho+self.dz*self.dz)-self.z)/self.sigma)**2-self.offset
        factor = rho if self.prior == "area" else np.ones_like(rho)
        if self.prior.startswith("halfnormal"):
            scale = float(self.prior.removeprefix("halfnormal"))
            loglike = loglike-.5*(rho/scale)**2
        return factor*np.exp(loglike)

    def sample(self, rng, n):
        return np.interp(rng.random(n), self.cdf, self.grid)

    def logpdf(self, rho):
        rho = np.asarray(rho)
        with np.errstate(divide="ignore", invalid="ignore"):
            out = np.log(self._density(rho))-np.log(self.norm)
        return np.where((rho >= 0)&(rho <= self.hi), out, -np.inf)


def radial_table(z, sigma, dz, prior="area", cutoff_sigma=None):
    return RadialTable(z, sigma, dz, prior, cutoff_sigma)


class S0BatchTarget(ConditionalBatchTarget):
    def __init__(self, public, cfg, arm, prior="area", cutoff_sigma=None):
        # The zero pose here is merely a container for inherited noise validation;
        # no initial pose density is evaluated or supplied by the caller.
        if "x0" in public:
            raise ValueError("S0 public input must not contain x0")
        allowed={"t_s","dt_s","ds_odom","dtheta_gyro","dtheta_odom","range_m","range_mask"}
        if set(public)!=allowed:
            raise ValueError("S0 requires exactly seven public observation keys")
        internal = dict(public, x0=np.zeros(6))
        original_std=np.asarray(cfg["p0_std"],dtype=float)
        if original_std.shape!=(6,) or not np.all(np.isfinite(original_std)) or np.any(original_std[:3]<0):
            raise ValueError("invalid S0 calibration/gauge standard deviations")
        # The inherited constructor validates a S1 container. These positive
        # dummy pose scales are never used by this class's S0 target/proposals.
        validation_cfg=dict(cfg,p0_std=np.r_[np.ones(3),original_std[3:]])
        super().__init__(internal, validation_cfg, arm)
        self.std = original_std[3:]
        if not np.allclose(self.anchor[:2], 0):
            raise ValueError("S0 horizontal anchor must be the gauge origin")
        self.table = None
        self.range_count = int(np.count_nonzero(self.mask[1:])) if arm == "RANGE" else 0
        if arm == "RANGE":
            if not self.mask[0]:
                raise ValueError("S0 RANGE requires first range")
            self.table = radial_table(self.ranges[0], self.sigma, self.z-self.anchor[2], prior, cutoff_sigma)
        self.mask = self.mask.copy()
        self.mask[0] = False

    def evaluate(self, parameter, znoise, trajectory=False):
        rho, delta = parameter[:2]
        state = np.r_[rho if self.arm == "RANGE" else 0., 0.,
                       delta if self.arm == "RANGE" else 0., self.std*parameter[2:]]
        cond = self.conditional(state)
        if cond is None:
            return (-np.inf, None) if trajectory else -np.inf
        md, mg, ld, lgd, lgg, ll = cond
        nd = md+ld*znoise[0]
        ng = mg+lgd*znoise[0]+lgg*znoise[1]
        bg, sf, eps = state[3:]
        a = (self.g-ng-bg*self.dt)/(1+sf)
        u = self.d-nd-eps*self.b*a/4
        yaw = state[2]+np.r_[0., np.cumsum(a)]
        step = u*np.sinc(a/(2*np.pi))
        x = state[0]+np.r_[0., np.cumsum(step*np.cos(yaw[:-1]+a/2))]
        y = np.r_[0., np.cumsum(step*np.sin(yaw[:-1]+a/2))]
        path = np.column_stack((x,y,yaw))
        if self.arm == "RANGE":
            r = np.sqrt(x[self.mask]**2+y[self.mask]**2+(self.z-self.anchor[2])**2)
            ll += -.5*np.sum(((self.ranges[self.mask]-r)/self.sigma)**2
                             +np.log(2*np.pi*self.sigma**2))
        return (float(ll), path) if trajectory else float(ll)


def batch_s0(public, cfg, arm, seed, settings, prior="area", cutoff_sigma=None):
    target = S0BatchTarget(public,cfg,arm,prior,cutoff_sigma)
    burn, retained, thin = [int(settings.get(k,d)) for k,d in
                           (("burn",2000),("retained",2000),("thin",1))]
    chains = int(settings.get("chains",4))
    beta = float(settings.get("pCN_beta",.03))
    if burn < 0 or retained < 4 or thin < 1 or chains < 4 or not 0 < beta <= 1:
        raise ValueError("invalid MCMC settings")
    all_samples, all_paths, initial, accepts = [], [], [], []
    for chain in range(chains):
        rng = np.random.default_rng(np.random.SeedSequence([seed,20261013,2205,chain]))
        p = np.r_[target.table.sample(rng,1)[0] if target.table else 0.,
                  -np.pi+2*np.pi*(chain+.5)/chains if target.table else 0.,rng.normal(size=3)]
        initial.append(np.r_[p[:2],target.std*p[2:]].tolist())
        noise = rng.normal(size=(2,len(target.dt)))
        ll = target.evaluate(p,noise)
        if not np.isfinite(ll):
            raise ValueError("invalid initial chain")
        steps = np.array([float(settings.get("heading_step",.15)),
                          *([float(settings.get("parameter_step",.08))]*3)])
        block = np.zeros(4); accepted=np.zeros(6); attempted=np.zeros(6)
        kept=[]; paths=[]
        for it in range(burn+retained*thin):
            # Independent draw from the INITIAL radial posterior: its density
            # cancels the MH proposal ratio. Future range likelihood remains.
            if target.table:
                q=p.copy(); q[0]=target.table.sample(rng,1)[0]
                qll=target.evaluate(q,noise)
                ok=np.log(rng.random())<qll-ll
                if ok: p,ll=q,qll
                if it>=burn: accepted[0]+=ok; attempted[0]+=1
            for j in range(1,5):
                if j==1 and not target.table: continue
                q=p.copy()
                if j==1:
                    q[j]=rng.uniform(-np.pi,np.pi) if rng.random()<.1 else (p[j]+steps[0]*rng.normal()+np.pi)%(2*np.pi)-np.pi
                    correction=0.
                else:
                    q[j]+=steps[j-1]*rng.normal()
                    correction=-.5*(q[j]**2-p[j]**2)
                qll=target.evaluate(q,noise)
                ok=np.log(rng.random())<qll-ll+correction
                if ok: p,ll=q,qll
                if it<burn: block[j-1]+=ok
                else: accepted[j]+=ok; attempted[j]+=1
            qn=np.sqrt(1-beta*beta)*noise+beta*rng.normal(size=noise.shape)
            qll=target.evaluate(p,qn); ok=np.log(rng.random())<qll-ll
            if ok: noise,ll=qn,qll
            if it>=burn: accepted[5]+=ok; attempted[5]+=1
            if it<burn and (it+1)%50==0:
                steps*=np.exp(np.clip(block/50-.3,-.2,.2));block[:]=0
            if it>=burn and (it-burn+1)%thin==0:
                kept.append(np.r_[p[:2],target.std*p[2:]])
                _,path=target.evaluate(p,noise,True);paths.append(path[-1])
        all_samples.append(kept);all_paths.append(paths)
        accepts.append(dict(zip(("rho","delta","bg","sf","eps","latent_pCN"),
                       np.divide(accepted,attempted,out=np.zeros(6),where=attempted>0).tolist()),
                       frozen_steps=steps.tolist()))
    samples=np.asarray(all_samples)
    diagnostic_samples=(np.concatenate((samples[:,:,2:],samples[:,:,:1],
                          np.sin(samples[:,:,1:2]),np.cos(samples[:,:,1:2])),axis=2)
                          if target.table else samples[:,:,2:])
    return dict(samples=samples, calibration_samples=samples[:,:,2:],
        cal_samples=samples[:,:,2:], pose_samples=np.asarray(all_paths),
        initial_chain_states=initial, acceptance=accepts,
        diagnostics=chain_diagnostics(diagnostic_samples),
        diagnostic_columns=(["bg","sf","eps","rho","sin_delta","cos_delta"]
                            if target.table else ["bg","sf","eps"]),
        calibration_diagnostics=chain_diagnostics(samples[:,:,2:]),
        radial_diagnostics=target.table.diagnostics if target.table else None,
        subsequent_range_count=target.range_count,
        initial_range_consumed=arm=="RANGE", seed=int(seed),
        reference_status="REFERENCE_NOT_VALIDATED",
        limitations=["full supplied-horizon smoothing", "conditional measured-input model",
                     "classical diagnostics cannot exclude unvisited modes"])
