#!/usr/bin/env python3
"""Negative diagnostic checks on fabricated affine logs; no RF or R1 replay."""
from __future__ import annotations
import copy
import datetime
import json
import numpy as np
from p3_pre_run_review import ROOT, OUT, ADAPTER, CORE, digest, module

def main():
    adapter = module("independent_rejected_adapter", ADAPTER)
    hmat = np.array([[.8, .1, 0., 0.], [.01, -.04, .7, 0.]])
    offset = np.array([.2, -.15])
    class ArtificialAffineSource:
        def batch(self, states, case, gradient=True, return_diagnostics=False):
            states = np.atleast_2d(states)
            values = states @ hmat.T + offset
            jac = np.broadcast_to(hmat, (len(states), 2, 4)).copy()
            diag = dict(tap=np.zeros(len(states), int), strong_port=np.zeros(len(states), int),
                        cells=np.zeros((len(states), 6), int))
            return (values, jac, diag) if return_diagnostics else (values, jac)
    source = ArtificialAffineSource()
    x = np.array([1., .3, .2, .001])
    p = np.diag([.02, .03, .01, .0001])
    h = hmat @ x + offset
    nu = np.array([3., -2.])
    z = h + nu
    s = hmat @ p @ hmat.T + adapter.R0
    gain = p @ hmat.T @ np.linalg.inv(s)
    nis = float(nu @ np.linalg.inv(s) @ nu)
    assert nis > adapter.GATE
    data = dict(xprior=x[None], Pprior=p[None], xpost=x[None].copy(), Ppost=p[None].copy(),
                h=h[None], H=hmat[None], S=s[None], K=gain[None], innovation=nu[None],
                accepted=np.array([False]), nis=np.array([nis]), F=np.eye(4)[None],
                G=np.zeros((1, 4, 3)), Q_input=np.zeros((1, 3, 3)))
    cases = []
    for mutation in ["none", "rejected_S", "rejected_K"]:
        sample = copy.deepcopy(data)
        if mutation == "rejected_S":
            sample["S"][0, 0, 0] += .05
        elif mutation == "rejected_K":
            sample["K"][0, 0, 0] += .1
        try:
            _, qa, _ = adapter.offline_diagnostics(sample, z[None], np.array([True]), (h + [.02, .01])[None], source)
            stopped, reason = False, None
        except RuntimeError as error:
            stopped, reason = True, str(error)
        expected_stop = mutation != "none"
        cases.append(dict(mutation=mutation, expected_stop=expected_stop,
                          observed_stop=stopped, reason=reason, passed=stopped == expected_stop))
    result = dict(schema="DLP_R1B_REJECTED_LOG_NEGATIVE_TEST_V1", reviewer="/root/ekf_contract_review",
                  not_human_signoff=True, real_R1_RF_or_filter_executed=False,
                  adapter_sha256=digest(ADAPTER), reviewer_code_sha256=digest(__file__),
                  inputs="fabricated affine single-row REJECT log; no project trajectory or SourceFFD data",
                  status="PASS" if all(x["passed"] for x in cases) else "FAIL", checks=cases,
                  utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    target = OUT / ("P3_REJECTED_LOG_QA_" + digest(ADAPTER)[:12] + ".json")
    if target.exists():
        raise RuntimeError("REFUSE_OVERWRITE_AUDIT_EVIDENCE:" + str(target))
    target.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
