"""SM0 V2: two independent, purpose-specific precision checks.

Archive compatibility is assessed against the *original complex64 expression*
using the saved per-ray legacy32 values. It is never assessed against the F64
independent checker. The latter remains the reference for coherent ray sum QA.

No simulator import, data alteration, threshold relaxation, or attribution.
"""
import numpy as np
from native_math import errors

PRECISION_CONTRACT = "SM0_DUAL_PRECISION_V2"
ARCHIVE_LOS_MODEL = "legacy_original_expression_complex64"
COHERENT_SUM_MODEL = "independent_scalar_float64"


def evaluate_precision(arrays, thresholds):
    required = ("a", "tau", "original_field", "offsets",
                "direct_source_index", "group_fields", "group_count",
                "direct_group", "native_f64", "native_original32",
                "archive_full", "archive_los")
    if any(k not in arrays for k in required):
        raise ValueError("missing raw precision-array keys")
    nfreq = len(arrays["native_f64"])
    offsets = np.asarray(arrays["offsets"], dtype=np.int64)
    indices = offsets[:-1] + np.asarray(arrays["direct_source_index"], dtype=np.int64)
    if nfreq != 257 or offsets.shape != (258,) or len(indices) != 257:
        raise ValueError("unexpected frequency/offset dimensions")
    if offsets[0] != 0 or offsets[-1] != len(arrays["original_field"]):
        raise ValueError("raw offsets corrupt")
    if np.any(np.diff(offsets) <= 0) or np.any(indices < offsets[:-1]) or np.any(indices >= offsets[1:]):
        raise ValueError("DIRECT index outside raw ray bin")
    if np.asarray(arrays["original_field"]).dtype != np.complex64:
        raise ValueError("legacy source expression must remain complex64")
    if np.asarray(arrays["a"]).dtype != np.complex64:
        raise ValueError("ray coefficient dtype changed")
    if np.asarray(arrays["tau"]).dtype != np.float32:
        raise ValueError("ray delay dtype changed")
    groups = np.asarray(arrays["group_fields"])
    gdirect = int(arrays["direct_group"])
    if groups.ndim != 3 or groups.shape[1:] != (257, 2) or not 0 <= gdirect < len(groups):
        raise ValueError("invalid semantic group spectrum")
    if not np.all(np.asarray(arrays["group_count"])[gdirect] == 1):
        raise ValueError("expected exactly one DIRECT ray per frequency")
    if np.asarray(arrays["native_f64"]).shape != (257, 2):
        raise ValueError("incorrect independent sum shape")
    if np.asarray(arrays["archive_full"]).shape != (257, 2) or np.asarray(arrays["archive_los"]).shape != (257, 2):
        raise ValueError("archive shape mismatch")
    if any(not np.isfinite(np.asarray(arrays[k])).all() for k in
           ("original_field", "group_fields", "native_f64", "native_original32",
            "archive_full", "archive_los")):
        raise ValueError("nonfinite channel values")

    legacy_direct = np.asarray(arrays["original_field"])[indices]
    f64_direct = groups[gdirect]
    f64_full = np.asarray(arrays["native_f64"])
    f64_groups = groups.sum(axis=0)
    legacy_full = np.asarray(arrays["native_original32"])

    reconstruction = errors(f64_groups, f64_full)
    los_legacy = errors(legacy_direct, arrays["archive_los"])
    los_f64 = errors(f64_direct, arrays["archive_los"])
    full_f64 = errors(f64_full, arrays["archive_full"])
    full_legacy = errors(legacy_full, arrays["archive_full"])

    passed = (
        reconstruction["relative_l2"] <= thresholds["reconstruction_relative_l2"]
        and reconstruction["max_normalized"] <= thresholds["reconstruction_max_normalized"]
        and los_legacy["relative_l2"] <= thresholds["archive_los_relative_l2"]
        and full_f64["relative_l2"] <= thresholds["archive_full_relative_l2"]
    )
    return dict(
        schema=PRECISION_CONTRACT,
        archive_los_model=ARCHIVE_LOS_MODEL,
        coherent_reference=COHERENT_SUM_MODEL,
        relative_thresholds=thresholds.copy(),
        archive_los_primary_legacy32=los_legacy,
        archive_los_diagnostic_f64=los_f64,
        archive_full_primary_f64=full_f64,
        archive_full_diagnostic_legacy32=full_legacy,
        reconstruction_primary_f64=reconstruction,
        # These must stay separate. A false F64-LoS PASS cannot justify physics.
        f64_los_is_gate=False,
        pass_all=bool(passed),
        direct_legacy32=legacy_direct,
    )
