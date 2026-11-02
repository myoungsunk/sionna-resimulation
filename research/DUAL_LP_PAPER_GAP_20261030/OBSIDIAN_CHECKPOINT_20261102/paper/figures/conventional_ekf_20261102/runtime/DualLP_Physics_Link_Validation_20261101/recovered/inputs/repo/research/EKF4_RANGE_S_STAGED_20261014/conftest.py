"""Enforce source-bound pre-run audit before each pytest validation session.

This file is imported by pytest collection; it does not audit scientific
correctness by itself. Audit receipt is generated BEFORE pip/pytest/diagnosis.
"""
import os
from pre_run_audit import require_audit_receipt

def pytest_sessionstart(session):
    require_audit_receipt(os.environ.get('EKF4_AUDIT_RECEIPT'))
