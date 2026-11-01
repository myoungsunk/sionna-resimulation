"""Pre-DEV3 technical-only tests of A010 input integrity; never accesses reserved field IDs."""
from __future__ import annotations
import io
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
import a10_canonical as A  # noqa: E402

GEN = ROOT / "results/P2_A010P0_GEN_run_41269011836"
FACTOR = GEN / "A010_LHALF_WORLDPOSE_V2.npy"
CANON = GEN / "A010_CANONICAL_INPUTS.zip"
LEDGER = GEN / "A010_INPUT_CANONICAL_SHA.csv"


def test_frozen_data_and_ledger():
    r = A.smoke_report(FACTOR, CANON, LEDGER)
    assert r["pass"] and r["array_ledger"]["checked"] == 48
    assert r["science_status"] == "NOT_RUN"
    assert r["holdout2_status"] == "CLOSED"
    L = A.load_frozen_factor(FACTOR)
    assert L.shape == (180, 180) and L.dtype.str == "<f8"


def test_exact_k1_estimator_payload_and_no_truth():
    d = A.read_forensic_bundle(CANON)
    estim = A.estimator_only(d, "K1")
    assert set(estim) == set(A.REQUIRED_ESTIMATOR)
    assert set(estim).isdisjoint(A.TRUTH_ONLY)
    assert A.exact_array_compare(estim, estim)["pass"]
    estim["z"][0, 0] = np.nextafter(estim["z"][0, 0], float("inf"))
    assert not A.exact_array_compare(A.estimator_only(d, "K1"), estim)["pass"]


def test_corrupted_factor_hash_fails(tmp_path):
    arr = bytearray(FACTOR.read_bytes())
    arr[-1] ^= 1
    fake = tmp_path / "L.npy"
    fake.write_bytes(arr)
    with pytest.raises(A.InputIntegrityError, match="HASH"):
        A.load_frozen_factor(fake)


def test_corrupted_canonical_zip_fails(tmp_path):
    arr = bytearray(CANON.read_bytes())
    arr[-1] ^= 1
    fake = tmp_path / "canonical.zip"
    fake.write_bytes(arr)
    with pytest.raises(A.InputIntegrityError, match="HASH"):
        A.read_forensic_bundle(fake)


def test_absent_input_and_unregistered_case_fail():
    d = A.read_forensic_bundle(CANON)
    d.pop("K2|x0")
    with pytest.raises(A.InputIntegrityError, match="MISSING"):
        A.estimator_only(d, "K2")
    with pytest.raises(A.InputIntegrityError, match="UNREGISTERED"):
        A.estimator_only(d, "DEV3_20")


def test_factor_kernel_mismatch_fails():
    L = A.load_frozen_factor(FACTOR)
    K = L @ L.T
    assert A.load_frozen_factor(FACTOR, Kp=K).shape == L.shape
    K[0, 1] += 0.1
    with pytest.raises(A.InputIntegrityError, match="ASYMMETRY"):
        A.load_frozen_factor(FACTOR, Kp=K)


def test_exact_array_ledger_covers_every_case():
    d = A.read_forensic_bundle(CANON)
    v = A.audit_array_ledger(d, LEDGER)
    assert v["pass"] and v["checked"] == 48
    d["K3|gy_m"][7] = np.nextafter(d["K3|gy_m"][7], float("inf"))
    v = A.audit_array_ledger(d, LEDGER)
    assert not v["pass"] and v["mismatches"] == ["K3|gy_m"]
