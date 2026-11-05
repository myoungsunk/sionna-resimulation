"""Independent posthoc retained C3 G3 data audit after forced execution exit. No production imports, RT, FFT or G4 model.
Usage: pinned-python -B INDEPENDENT_G3_RETAINED_VERIFIER_001.py PHASE_ROOT NEW_RESULT_JSON
Only NEW_RESULT_JSON may be written; the capture and repository are read-only.
"""
import argparse, csv, datetime, hashlib, importlib.metadata, json, math, os
import platform, subprocess, sys, traceback
from pathlib import Path
import numpy as np

PUBLICATION = "ce1f30da7637cef22bc952d029989b5edf939094"
CLEAN_VERIFIER_SHA = "1007498b4c3649e748122aee031a80d1e4e6e28dcdecf0d3fcc29d9add34252e"
FORCED_MANAGER_SHA = "b9abe69a8bb8162c8ce08e7e54ca1a1f4ded14ad9f5ebebd9173ad7431399dd5"
ROOT_MANIFEST_SHA = "dc433b7b935f5ea394d77d079050fd2d5d1b848187c2c94fa38ff27839dacb7a"
ROOT_INDEX_CSV_SHA = "464f35c5cdbb44ba77c1a19f3e9f5bc543ce4176b712df91396ca2b58b9cf38b"
G2_PUBLICATION = "febe06a5e819018698251a27dc7da16e20ff11c2"
G2_RECEIPT_SHA = "07894ecebf001388f76c7420ad4cfaee96f1627659fe18260178487803ee4996"
G2_PREREQUISITE_SHA = "3e8c4cb0909bba17e8a3aadcfd630f4b7cdbdc833e0eca9bd83e05397dbd1570"
G2_VERIFIER_SHA = "1b4c1d1ff984649c9ab0e6de063c681b77cf12f85378ed0145778497c8c92e26"
OLD_PUBLICATION = "ea9b4952edfdef3f09285736eb0d2c00a94d1949"
SPEC_SHA = "e60131061f73582d39e15b1c59a9c93ba097a138222cc4eae1261d2b5b92f339"
OLD_FIXED = {
    "GO_CANARY.json": "b679eeac391b815a8515a8093df73ff712846d516e6c96344b5b48949c832bbe",
    "CANARY_001/MANIFEST.json": "f97a5b159a5d1e6d2292083e196b8bf0c84f68090b49f276f20d6fa8050acf05",
    "CANARY_001/FAILURES.jsonl": "9d5acbe06d50fd16305086d9a81bafd3234c756aac811a309ac238722769f3be",
    "CANARY_001/ARTIFACT_HASHES.json": "f1611270b0c769f229ccd04f1ad0fc3b399a9ff62560d37682c0dfe4c3027928",
}
JOIN = ("a", "tau", "objects", "interactions", "primitives", "vertices",
        "valid", "theta_t", "phi_t", "theta_r", "phi_r", "source_index",
        "fields", "original_field")
RAW_REPEAT = JOIN + ("labels", "original_sum", "independent_sum", "direct_index",
                     "frequency_hz")
C0 = 299792458.0


def require(test, message):
    if not test:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def load(path):
    return json.loads(Path(path).read_bytes())


def mapped(path):
    text = str(path)
    if len(text) > 2 and text[1] == ":":
        return Path("/mnt/" + text[0].lower() + text[2:])
    return Path(text)


def arrays(path):
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def exact(actual, reference, label):
    require(actual.shape == reference.shape and actual.dtype == reference.dtype
            and np.array_equal(actual, reference), label + " exact schema/value")


def error(actual, reference):
    actual = np.asarray(actual, np.complex128)
    reference = np.asarray(reference, np.complex128)
    require(actual.shape == reference.shape and np.isfinite(actual).all()
            and np.isfinite(reference).all(), "nonfinite/shape in error metric")
    norm = float(np.linalg.norm(reference))
    peak = float(np.abs(reference).max())
    require(norm > 0 and peak > 0, "zero reference: no denominator floor")
    difference = actual - reference
    return {
        "relative_l2": float(np.linalg.norm(difference) / norm),
        "max_normalized": float(np.abs(difference).max() / peak),
        "max_absolute": float(np.abs(difference).max()),
    }


def closure(actual, reference):
    result = error(actual, reference)
    result["per_rx"] = [error(np.asarray(actual)[:, r],
                             np.asarray(reference)[:, r]) for r in range(2)]
    for row in [result, *result["per_rx"]]:
        require(row["relative_l2"] <= 1e-8 and row["max_normalized"] <= 1e-8,
                "frozen closure tolerance: " + repr(row))
    return result


def finite_arrays(data, label):
    for key, value in data.items():
        if value.dtype.kind in "fc":
            require(np.isfinite(value).all(), label + " nonfinite " + key)


def cfr_schema(value, shape):
    require(value.shape == shape and value.dtype == np.complex64
            and np.isfinite(value).all(), "native CFR schema/finiteness")


def index_check(root):
    root = root.resolve()
    indexed = load(root / "ARTIFACT_HASHES.json")
    require(isinstance(indexed, dict), "artifact index type")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*")
              if p.is_file() and p.name != "ARTIFACT_HASHES.json"}
    require(set(indexed) == actual, "artifact set completeness: " + str(root))
    for relative, expected in indexed.items():
        p = (root / relative).resolve()
        require(p.is_relative_to(root), "unsafe artifact path")
        require(sha(p) == expected, "artifact hash " + str(p))
    return len(indexed)


def assert_entry(entry):
    p = mapped(entry["path"])
    require(p.stat().st_size == entry["size"] and sha(p) == entry["sha256"],
            "locked input " + str(p))


def runtime_snapshot():
    env_keys = ("PYTHONHOME", "LD_LIBRARY_PATH", "PYTHONPATH",
                "DRJIT_LIBLLVM_PATH", "OPENBLAS_NUM_THREADS",
                "OMP_NUM_THREADS", "MKL_NUM_THREADS")
    llvm = Path(os.environ["DRJIT_LIBLLVM_PATH"])
    return {
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "cpu_model": [v.split(":", 1)[1].strip()
                      for v in Path("/proc/cpuinfo").read_text().splitlines()
                      if v.startswith("model name")][:1],
        "versions": {n: importlib.metadata.version(n) for n in
                     ("numpy", "scipy", "sionna-rt", "mitsuba", "drjit")},
        "all_distributions": {d.metadata["Name"]: d.version
                              for d in importlib.metadata.distributions(
                                  path=[os.environ["PYTHONPATH"]])},
        "llvm_path": str(llvm), "llvm_sha256": sha(llvm),
        "environment": {k: os.environ[k] for k in env_keys},
    }


def rotation_z(degrees):
    angle = math.radians(degrees)
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def matrix_zyx(values):
    z, y, x = values
    cz, sz, cy, sy, cx, sx = (math.cos(z), math.sin(z), math.cos(y),
                            math.sin(y), math.cos(x), math.sin(x))
    rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    return rz @ ry @ rx


def bilinear(bank, bin_index, theta, phi):
    th = np.deg2rad(bank["theta_deg"])
    ph = np.deg2rad(bank["phi_deg"])
    require(th.ndim == ph.ndim == 1 and np.all(np.diff(th) > 0)
            and np.all(np.diff(ph) > 0), "bank angle grid")
    pp = (phi - ph[0]) % (2 * np.pi) + ph[0]
    require(th[0] <= theta <= th[-1] and ph[0] <= pp <= ph[-1],
            "FFD interpolation domain")
    i = min(max(int(np.searchsorted(th, theta, side="right")) - 1, 0), len(th)-2)
    j = min(max(int(np.searchsorted(ph, pp, side="right")) - 1, 0), len(ph)-2)
    u, v = (theta-th[i])/(th[i+1]-th[i]), (pp-ph[j])/(ph[j+1]-ph[j])
    out = []
    for key in ("e_theta", "e_phi"):
        a = bank[key][bin_index]
        out.append((1-u)*(1-v)*a[i,j] + u*(1-v)*a[i+1,j]
                   + (1-u)*v*a[i,j+1] + u*v*a[i+1,j+1])
    return out


def direct_coefficient(banks, fi, frequency, xyz, yaw):
    tx = np.array([10.0, 0.0, 2.7-0.05])
    rx = np.asarray(xyz, float)
    vector = rx - tx
    distance = float(np.linalg.norm(vector))
    direction = vector / distance
    fields = {}
    for role, rotation in (("tx", np.diag([1.0, -1.0, -1.0])),
                           ("rx", rotation_z(yaw))):
        local = rotation.T @ (direction if role == "tx" else -direction)
        theta = math.acos(float(np.clip(local[2], -1, 1)))
        phi = math.atan2(float(local[1]), float(local[0]))
        et = np.array([math.cos(theta)*math.cos(phi),
                       math.cos(theta)*math.sin(phi), -math.sin(theta)])
        ep = np.array([-math.sin(phi), math.cos(phi), 0.0])
        vecs = []
        for bank in banks:
            t, p = bilinear(bank, fi, theta, phi)
            vecs.append(rotation @ (et*t + ep*p)
                        * math.sqrt(2*math.pi/376.730313668))
        fields[role] = np.asarray(vecs)
    return fields["rx"] @ fields["tx"].T * C0/frequency/(4*math.pi*distance)


def scalar_f64(coef, tau, frequency):
    result = np.empty((len(tau), 2), np.complex128)
    for j, delay in enumerate(tau):
        phase = -2*math.pi*float(frequency)*float(delay)
        c, s = math.cos(phase), math.sin(phase)
        for r in range(2):
            v = coef[r, 0, j]
            result[j, r] = complex(float(v.real)*c - float(v.imag)*s,
                                   float(v.real)*s + float(v.imag)*c)
    return result


def compensated(values):
    return np.array([complex(math.fsum(float(v.real) for v in values[:, r]),
                             math.fsum(float(v.imag) for v in values[:, r]))
                     for r in range(2)], np.complex128)


def label_from_raw(obj, interactions, lookup, valid):
    if not valid:
        return "INVALID"
    chain = []
    for oid, kind in zip(obj, interactions):
        oid, kind = int(oid), int(kind)
        if oid in (-1, 4294967295):
            require(kind == 0, "interaction without object")
            continue
        require(oid in lookup and kind != 0, "unknown object/empty interaction")
        chain.append([lookup[oid], kind])
    return json.dumps(chain, separators=(",", ":")) if chain else "DIRECT"


def verify_condition(capture, row, plan, go_sha, revision, frequencies,
                     banks, solver, expected_scene):
    m = load(capture / "MANIFEST.json")
    require(m["status"] == "C3_RAW_NUMERICAL_PASS" and m["condition"] == row,
            "condition terminal status/identity")
    require(m["code_revision"] == revision and m["go_sha256"] == go_sha,
            "condition revision/GO")
    require(m["primary_solver_calls"] == 257 and m["repeat_solver_calls"] == 3,
            "condition solver counts")
    require(m["solver"] == solver and m["scene_bindings"] == expected_scene,
            "solver/material binding")
    require(m["tx_position"] == [10.0, 0.0, 2.7-0.05]
            and m["rx_position"] == row["xyz"], "exact coordinates")
    require(m["selected_tx"] == "LP_plus45 column0"
            and m["rx_order"] == ["LP_plus45", "LP_minus45"], "port order")
    require(np.allclose(matrix_zyx(m["tx_orientation_zyx_rad"]),
                        np.diag([1., -1., -1.]), atol=1e-14, rtol=0)
            and np.allclose(matrix_zyx(m["rx_orientation_zyx_rad"]),
                            rotation_z(row["yaw_deg"]), atol=1e-14, rtol=0),
            "mount/rotation/ZYX convention")
    for surface in expected_scene:
        require(sha(capture/"scene"/(surface["object"]+".ply"))
                == surface["ply_sha256"], "scene PLY")
    indexed = index_check(capture)
    require(sha(capture/"RAW.npz") == m["raw_sha256"], "RAW manifest hash")
    require({p.name for p in (capture/"bins").iterdir()}
            == {f"{i:03d}.npz" for i in range(257)}, "257 primary bins")
    require({p.name for p in (capture/"repeat").iterdir()}
            == {f"{i:03d}.npz" for i in (0,128,256)}, "three repeat bins")
    a = arrays(capture/"RAW.npz")
    require(not any(k.startswith("archive_") for k in a), "fake archive")
    finite_arrays(a, "RAW")
    exact(a["frequencies_hz"], frequencies, "frequencies")
    require(a["a"].dtype == np.complex64 and a["tau"].dtype == np.float32
            and a["fields"].dtype == np.complex128
            and a["original_field"].dtype == np.complex64, "native precision")
    cfr_schema(a["native_cfr32"], (257,2))
    offsets = a["offsets"]
    require(offsets.shape == (258,) and offsets.dtype.kind in "iu"
            and offsets[0] == 0 and offsets[-1] == len(a["tau"])
            and np.all(np.diff(offsets) > 0), "raw offsets")
    n = int(offsets[-1])
    require(a["a"].shape == (n,2,2) and a["fields"].shape == (n,2)
            and a["original_field"].shape == (n,2), "raw coefficient shapes")
    require(a["valid"].dtype == np.bool_ and a["valid"].shape[0] == n,
            "valid flags")
    for key in JOIN:
        require(a[key].shape[0] == n, "path axis "+key)
    require(a["direct_source_index"].shape == (257,)
            and a["direct_source_index"].dtype.kind in "iu", "direct index schema")
    labels = a["group_labels"].tolist()
    ng = len(labels)
    require(labels == sorted(set(labels)) and labels.count("DIRECT") == 1,
            "semantic groups")
    require(a["group_ids"].tolist()
            == [hashlib.sha256(v.encode()).hexdigest() for v in labels],
            "semantic hashes")
    require(int(a["direct_group"]) == labels.index("DIRECT"), "DIRECT group")
    require(a["source_group"].shape == (n,) and a["source_group"].dtype.kind in "iu"
            and np.all((a["source_group"] >= 0) & (a["source_group"] < ng)),
            "source-group schema")
    lookup = {int(k): v for k,v in m["object_lookup"].items()}
    require(set(lookup.values()) == {v["object"] for v in expected_scene}
            and len(lookup) == len(expected_scene), "object lookup")
    legacy_groups = np.zeros((ng,257,2), np.complex128)
    f64_groups = np.zeros_like(legacy_groups)
    counts = np.zeros((ng,257), np.int32)
    scalar_native, scalar_legacy = [], []
    direct_actual, direct_expected = [], []
    per_bin_projection, repeats = [], []
    scalar_perray_peak = 0.0
    max_delay = 0.0
    for fi, f in enumerate(frequencies):
        lo, hi = map(int, offsets[fi:fi+2])
        b = arrays(capture/"bins"/f"{fi:03d}.npz")
        finite_arrays(b, "primary bin")
        for key in JOIN:
            exact(b[key], a[key][lo:hi], f"bin join {fi}/{key}")
        exact(b["cfr32"], a["native_cfr32"][fi], "CFR bin join")
        require(b["frequency_hz"].shape == () and float(b["frequency_hz"]) == f,
                "bin frequency")
        require(b["tau"].dtype == np.float32 and b["a"].dtype == np.complex64,
                "bin precision")
        require(np.array_equal(a["source_index"][lo:hi], np.arange(hi-lo)),
                "source path index")
        coef = np.array(a["a"][lo:hi].transpose(1,2,0), copy=True, order="C")
        tau = a["tau"][lo:hi]
        legacy = coef[:,0,:] * np.exp(-2j*np.pi*np.float64(f)*tau)[None,:]
        require(legacy.dtype == np.complex64, "legacy NumPy promotion")
        exact(legacy.T, a["original_field"][lo:hi], "legacy per-ray replay")
        exact(legacy.sum(axis=1), a["native_original32"][fi],
              "C-contiguous complex64 reduction")
        exact(b["original_sum"], a["native_original32"][fi], "saved bin reduction")
        vector = (coef[:,0,:].astype(np.complex128)
                  * np.exp(-2j*np.pi*float(f)*tau.astype(np.float64))[None,:]).T
        exact(vector, a["fields"][lo:hi], "F64 vector per-ray replay")
        independent = scalar_f64(coef, tau, f)
        scalar_perray_peak = max(scalar_perray_peak,
                                error(vector, independent)["max_absolute"])
        scalar_native.append(compensated(independent))
        scalar_legacy.append(compensated(legacy.T))
        exact(b["independent_sum"], a["native_f64"][fi],
              "saved scalar native/bin join")
        local_labels = []
        for j in range(hi-lo):
            valid = bool(a["valid"][lo+j].any())
            if not valid:
                require(np.all(coef[:,:,j] == 0), "nonzero invalid ray")
            label = label_from_raw(a["objects"][lo+j], a["interactions"][lo+j],
                                   lookup, valid)
            local_labels.append(label)
            require(label in labels, "unregistered semantic label")
            gi = labels.index(label)
            require(int(a["source_group"][lo+j]) == gi, "raw semantic membership")
            legacy_groups[gi,fi] += legacy[:,j]
            f64_groups[gi,fi] += vector[j]
            counts[gi,fi] += 1
        require(b["labels"].tolist() == local_labels, "bin semantic labels")
        direct_ids = [j for j,v in enumerate(local_labels) if v == "DIRECT"]
        require(direct_ids == [int(a["direct_source_index"][fi])]
                and int(b["direct_index"]) == direct_ids[0], "unique DIRECT")
        di = direct_ids[0]
        distance = float(np.linalg.norm(np.asarray(m["tx_position"])
                                        - np.asarray(m["rx_position"])))
        delay_error = abs(float(tau[di]) - distance/C0)
        require(delay_error <= 1e-12, "direct geometric delay")
        max_delay = max(max_delay, delay_error)
        expected = direct_coefficient(banks, fi, float(f), row["xyz"], row["yaw_deg"])
        observed = coef[:,:,di]
        pe = error(observed, expected)
        require(pe["relative_l2"] <= 1e-4, "direct per-bin projection")
        direct_actual.append(observed)
        direct_expected.append(expected)
        per_bin_projection.append(pe["relative_l2"])
        if fi in (0,128,256):
            repeat = arrays(capture/"repeat"/f"{fi:03d}.npz")
            finite_arrays(repeat, "repeat")
            require(set(repeat) == set(b)-{"cfr32"}, "repeat field completeness")
            for key in RAW_REPEAT:
                exact(repeat[key], b[key], f"repeat exact {fi}/{key}")
            re = error(repeat["original_sum"], b["original_sum"])
            require(re["relative_l2"] <= 1e-8 and re["max_normalized"] <= 1e-8,
                    "repeat channel tolerance")
            repeats.append({"bin": fi, "raw_exact": True, "channel_error": re})
    exact(counts, a["group_count"], "group counts")
    exact(counts == 0, a["group_missing"], "missing group masks")
    require(np.array_equal(counts.sum(axis=0), np.diff(offsets)), "path denominator")
    require(m["paths_per_bin"] == np.diff(offsets).tolist(), "manifest path counts")
    exact(f64_groups, a["group_fields"], "saved F64 group sum")
    exact(legacy_groups, a["legacy_group_fields"], "actual legacy groups")
    exact(legacy_groups.sum(axis=0), a["legacy_native_full"], "legacy Full")
    checks = {
        "f64_reconstruction": closure(f64_groups.sum(axis=0), scalar_native),
        "f64_saved_native": closure(a["native_f64"], scalar_native),
        "f64_saved_direct": closure(a["direct_f64"],
                                    f64_groups[labels.index("DIRECT")]),
        "legacy_reconstruction": closure(legacy_groups.sum(axis=0), scalar_legacy),
    }
    direct_actual, direct_expected = np.asarray(direct_actual), np.asarray(direct_expected)
    projection = error(direct_actual, direct_expected)
    projection["per_rx"] = [error(direct_actual[:,r], direct_expected[:,r])
                             for r in range(2)]
    for pe in [projection, *projection["per_rx"]]:
        require(pe["relative_l2"] <= 1e-4, "direct aggregate/RX projection")
    projection["max_bin_relative"] = max(per_bin_projection)
    projection["max_delay_s"] = max_delay
    q = load(capture/"QA.json")
    require(q["bins"] == 257 and q["semantic_replay"] == "EXACT"
            and q["numerical"]["status"] == "C3_RAW_NUMERICAL_PASS"
            and q["numerical"]["archive_comparison"] == "NOT_APPLICABLE_NEW_YAW",
            "saved QA scope/status")
    require(set(q["repeats"]) == {"0","128","256"}
            and all(q["repeats"][str(i)]["raw_exact"] for i in (0,128,256))
            and len(q["per_bin_direct_projection"]) == 257, "saved QA denominators")
    for key, independent_check in checks.items():
        saved = q["numerical"]["checks"][key]
        for key2 in ("relative_l2", "max_normalized", "max_absolute"):
            require(abs(saved[key2]-independent_check[key2]) <= 1e-14,
                    "saved closure metric mismatch "+key+"/"+key2)
        for r in range(2):
            for key2 in ("relative_l2", "max_normalized", "max_absolute"):
                require(abs(saved["per_rx"][r][key2]-independent_check["per_rx"][r][key2])
                        <= 1e-14, "saved per-RX closure metric")
    return {
        "condition": row, "decision": "ACCEPT",
        "raw_sha256": sha(capture/"RAW.npz"),
        "manifest_sha256": sha(capture/"MANIFEST.json"),
        "artifact_index_sha256": sha(capture/"ARTIFACT_HASHES.json"),
        "qa_sha256": sha(capture/"QA.json"), "indexed_artifacts": indexed,
        "bins": 257, "raw_paths": n, "groups": ng, "closure": checks,
        "direct_projection": projection,
        "scalar_perray_max_absolute_difference": scalar_perray_peak,
        "repeats": repeats,
    }



def recovery_index_check(root, capture, plan, whole, execution_manager):
    """Administrative reconstruction only; does not restore a natural-exit PASS."""
    frozen = {
        "audit/G3_METADATA_RECOVERY_001.json": "5d7b2ad752a9ddcf781580a1229b25608f51dbe9592251b381198ca473c4321b",
        "audit/RECOVERED_ROOT_ARTIFACT_HASHES_001.json": "f286d30658e7c7f1013befe938715d1beb361612760bee205b2744718cbcdbc3",
        "audit/C3_G3_EXECUTION_DEFECT_DISPOSITION_RESULT.json": "ef4b2c055b4231d105826dcc901773fab66af003d85995fdf7bf7dcae5896714",
        "G3_EXECUTION_INCIDENT_001_KO.md": "19ef5f66eca83cbda6a7e11469be56547100e8e251709f1c8a37597863c7188c",
        "logs/METADATA_RECOVERY_001_MANAGED.json": "eb42f4b8561aadabeea52ea0eea6afc46c87b1efeb19f34e23730e9ad909303a",
        "audit/G3_RECOVERY_PROVENANCE_001.json": "26151cdb6bf237465fe127025353418162a49898bc51c740845a8842980d2e0d"
    }
    for relative, expected in frozen.items():
        require(sha(root/relative) == expected, "frozen recovery evidence "+relative)
    record_path = root/"audit/G3_METADATA_RECOVERY_001.json"
    record = load(record_path)
    require(record["schema"] == "C3_G3_ADMINISTRATIVE_METADATA_RECOVERY_V1"
            and record["status"] == "RECOVERED_INDEX_ONLY_PENDING_INDEPENDENT_RETAINED_DATA_AUDIT"
            and record["original_execution"] == "FORCED_AFTER_ALL20_DATA_SAVED_NO_NATURAL_EXIT_PASS",
            "recovery record must preserve execution defect")
    require(record["original_capture_modified"] is False
            and record["original_root_index_absent"] is True
            and record["rt_calls"] == record["source_model_initializations"] == record["fft_calls"] == 0,
            "administrative scope only")
    require(record["forced_manager_receipt_sha256"] == FORCED_MANAGER_SHA
            and record["original_manifest_sha256"] == ROOT_MANIFEST_SHA
            and record["original_index_sha256"] == ROOT_INDEX_CSV_SHA
            and record["incident_sha256"] == frozen["G3_EXECUTION_INCIDENT_001_KO.md"]
            and record["disposition_sha256"] == frozen["audit/C3_G3_EXECUTION_DEFECT_DISPOSITION_RESULT.json"],
            "recovery original evidence bindings")
    disposition = load(root/"audit/C3_G3_EXECUTION_DEFECT_DISPOSITION_RESULT.json")
    require(disposition["decision"] == "REDIRECT"
            and disposition["original_clean_execution_acceptance"] is False
            and disposition["administrative_recovery_permitted_within_existing_scope"] is True,
            "independent bounded recovery disposition")
    require(record["recovered_index_path"] == "RECOVERED_ROOT_ARTIFACT_HASHES_001.json",
            "external recovered index path")
    recovered_path = record_path.parent/record["recovered_index_path"]
    require(not recovered_path.resolve().is_relative_to(capture)
            and sha(recovered_path) == record["recovered_index_sha256"],
            "external recovered index hash")
    recovered = load(recovered_path)
    actual = {v.relative_to(capture).as_posix() for v in capture.rglob("*")
              if v.is_file() and v.name != "ARTIFACT_HASHES.json"}
    require(isinstance(recovered, dict)
            and len(recovered) == record["indexed_files"] == 5383
            and set(recovered) == actual, "exact 5383 recovered inventory")
    for relative, expected in recovered.items():
        path = (capture/relative).resolve()
        require(path.is_relative_to(capture) and path.is_file()
                and sha(path) == expected, "recovered payload hash "+relative)
    condition_indices = record["original_condition_indexes"]
    require(set(condition_indices) == {
        row["id"]+"/ARTIFACT_HASHES.json" for row in plan["authorized"]},
        "all20 original condition index bindings")
    union = {}
    for relative, expected in condition_indices.items():
        path = capture/relative
        require(sha(path) == expected, "preserved condition index "+relative)
        values = load(path)
        for child, digest in values.items():
            key = path.parent.relative_to(capture).as_posix()+"/"+child
            require(key not in union and recovered.get(key) == digest,
                    "original condition index/recovered agreement "+key)
            union[key] = digest
    require(len(union) == 5380 and set(recovered)-set(union)
            == {"MANIFEST.json","INDEX.csv","FAILURES.jsonl"},
            "no missing/extra scientific payload")
    require(recovered["MANIFEST.json"] == ROOT_MANIFEST_SHA
            and recovered["INDEX.csv"] == ROOT_INDEX_CSV_SHA
            and (capture/"FAILURES.jsonl").read_bytes() == b"",
            "recovered root originals")
    manager_path = root/"logs/METADATA_RECOVERY_001_MANAGED.json"
    managers = load(manager_path)["processes"]
    require(len(managers) == 1, "metadata manager count")
    manager = managers[0]
    require(manager["id"] == record["managed_resource"] == "c6d9982e-62db-42a6-af79-2df18ce6bcb4"
            and manager["creator"] == record["managed_run"] == "bca34342-ac33-49ca-90ca-ce561376b355"
            and manager["exit_code"] == 0 and manager["termination"] == "cooperative"
            and manager["stop_reason"] == "root_exited" and manager["ref_count"] == 0
            and all(manager[k]["state"] == "absent" for k in
                    ("actual_process","actual_supervisor","job")),
            "metadata-only helper completion")
    require(datetime.datetime.fromisoformat(whole["end_utc"])
            < datetime.datetime.fromisoformat(execution_manager["ended"])
            < datetime.datetime.fromisoformat(record["timestamp_utc"]),
            "capture then forced exit then posthoc recovery chronology")
    provenance = load(root/"audit/G3_RECOVERY_PROVENANCE_001.json")
    require(provenance["scope"] == "POSTHOC_METADATA_RECOVERY_PROVENANCE_ONLY"
            and provenance["code_revision"] == PUBLICATION
            and provenance["original_execution_natural_exit"] is False,
            "recovery provenance claim boundary")
    expected_paths = set(plan["bound_files"]) | {
        plan["go_file"],plan["spec_audit_file"],"audit/C3_G3_CODE_RESULT.json",
        "audit/C3_G3_EXECUTION_DEFECT_DISPOSITION_RESULT.json",
        "audit/G3_METADATA_RECOVERY_001.json","audit/RECOVERED_ROOT_ARTIFACT_HASHES_001.json",
        "audit/METADATA_RECOVERY_SCRIPT_001.py","logs/METADATA_RECOVERY_001_MANAGED.json",
        "logs/G3_BATCH_001_MANAGED.json","G3_EXECUTION_INCIDENT_001_KO.md"}
    require(set(provenance["bindings"]) == expected_paths, "all recovery provenance paths")
    for relative, expected in provenance["bindings"].items():
        path = (root/relative).resolve()
        require(path.is_relative_to(root) and sha(path) == expected,
                "recovery provenance bytes "+relative)
    return len(recovered), {
        "record_status":"RECORD_RECOVERY_ONLY",
        "original_clean_execution_acceptance":False,
        "original_root_index_present":False,
        "original_final_stdout_present":False,
        "original_host_completion_receipt_present":False,
        "recovered_index_sha256":sha(recovered_path),
        "recovery_record_sha256":sha(record_path),
        "recovery_provenance_sha256":frozen["audit/G3_RECOVERY_PROVENANCE_001.json"],
        "execution_incident_sha256":record["incident_sha256"],
        "independent_disposition_sha256":record["disposition_sha256"],
        "metadata_manager_receipt_sha256":sha(manager_path),
        "original_condition_indexes":condition_indices,
        "recovered_nonindex_files":len(recovered),
        "independently_checked_original_condition_files":len(union),
    }


def audit(root):
    plan, lock = load(root/"PLAN.json"), load(root/"INPUT_LOCK.json")
    capture = mapped(plan["output_linux"]).resolve()
    require(capture == (root/"BATCH_001").resolve(), "fixed fresh G3 capture")
    # Reject partial execution before reading any raw, bins or captured payloads.
    whole = load(capture/"MANIFEST.json")
    require(whole["status"] == "C3_G3_EXECUTION_PASS_PENDING_INDEPENDENT_AUDIT",
            "INCOMPLETE_OR_STOP: no terminal G3 success")
    manager_path = root/"logs/G3_BATCH_001_MANAGED.json"
    manager = load(manager_path)["processes"]
    require(len(manager) == 1, "execution manager count")
    manager = manager[0]
    require(sha(manager_path) == FORCED_MANAGER_SHA
            and manager["exit_code"] == 3221225786
            and manager["termination"] == "forced"
            and manager["state"] == "terminated"
            and manager["ref_count"] == 0
            and all(manager[k]["state"] == "absent"
                    for k in ("actual_process","actual_supervisor","job")),
            "forced execution evidence or release/absence mismatch")
    require(manager["id"] == "adb9c5e3-fbdc-448d-b6dd-aa63e6bcda2c"
            and manager["creator"] == "d42b2198-9456-4813-b276-1425d6ed8fa2",
            "managed execution identity")
    go_path = root/plan["go_file"]
    go = load(go_path)
    require(go["schema"] == "C3_SM2_GO_V1" and go["decision"] == "GO"
            and go["authorized"] == plan["authorized"], "GO scope")
    expected_coordinates = [
        ("R5_982", [1.521387,-0.338994,0.45]),
        ("P10Yp", [10,0.35,0.45]), ("P10Yn", [10,-0.35,0.45]),
        ("P139Yp", [13.9,0.35,0.45]), ("P139Yn", [13.9,-0.35,0.45]),
    ]
    expected_rows = [
        {"id":"SM2_"+name+"_Y"+str(j), "coordinate":name, "xyz":xyz,
         "yaw_deg":yaw, "order":4*i+j}
        for i,(name,xyz) in enumerate(expected_coordinates)
        for j,yaw in enumerate([0.,180.,35.7,-35.7])]
    require(plan["authorized"] == expected_rows, "exact original remaining20 order")
    require(plan["go_file"] == "GO_G3_001.json"
            and plan["spec_audit_file"] == "audit/C3_G3_SPEC_RESULT.json"
            and plan["g2_accepted_head"] == G2_PUBLICATION, "G3 gate identity")
    require(plan["primary_calls"] == 5140 and plan["repeat_calls"] == 60
            and plan["max_total_solver_calls"] == go["max_total_solver_calls"] == 5200
            and plan["repeat_bins"] == go["repeat_bins"] == [0,128,256],
            "prospective call budget")
    require(plan["thresholds"] == {"relative_l2":1e-8, "max_normalized":1e-8,
                                  "direct_coefficient_relative":1e-4,
                                  "direct_delay_s":1e-12,
                                  "decomposition_absolute":1e-12}, "fixed thresholds")
    bound = {n:sha(root/n) for n in plan["bound_files"]}
    require(len(bound) == 11 and bound == go["bindings_sha256"]
            and whole["bindings_sha256"] == bound, "eleven code bindings")
    require(sha(root/plan["spec_audit_file"]) == SPEC_SHA == go["spec_audit_sha256"],
            "G3 SPEC receipt")
    require(load(root/plan["spec_audit_file"])["decision"] == "SPEC_APPROVED",
            "SPEC status")
    repo = root.parents[4]
    for name in [*plan["bound_files"], plan["go_file"], plan["spec_audit_file"]]:
        relative = (root/name).relative_to(repo).as_posix()
        git_bytes = subprocess.check_output(["git","-C",str(repo),"show",
                                              PUBLICATION+":"+relative])
        require(git_bytes == (root/name).read_bytes(), "published bytes "+name)
    launch_path = root/"logs/G3_BATCH_001.stdout.txt"
    launch_lines = launch_path.read_text(encoding="utf8").splitlines()
    require(launch_lines, "missing launch evidence")
    launch = json.loads(launch_lines[0])
    expected_command = [
        *plan["runtime_command"], "-B", str(root/"producer.py"),
        "--go", str(go_path), "--out", str(capture), "--revision", PUBLICATION]
    require(launch["published_revision"] == PUBLICATION
            and launch["managed_process_run"] == manager["creator"]
            and launch["command"] == expected_command, "immutable published launch identity")
    terminal_lines = [v[len("C3_RESULT "):] for v in launch_lines
                      if v.startswith("C3_RESULT ")]
    require(not terminal_lines, "original missing terminal stdout must remain absent")
    require(not (root/"logs/G3_BATCH_001.json").exists(),
            "original missing host completion receipt must remain absent")
    require(not (capture/"ARTIFACT_HASHES.json").exists(),
            "original missing root index must remain absent")
    require(sha(capture/"MANIFEST.json") == ROOT_MANIFEST_SHA
            and sha(capture/"INDEX.csv") == ROOT_INDEX_CSV_SHA,
            "original root metadata changed")
    require(sha(root/"audit/INDEPENDENT_G3_VERIFIER.py") == CLEAN_VERIFIER_SHA,
            "original prospective clean-exit verifier must remain unchanged")
    require(whole["command"] == expected_command[len(plan["runtime_command"])+1:],
            "executed producer argv")
    go_sha = sha(go_path)
    require(whole["go_sha256"] == go_sha and whole["code_revision"] == PUBLICATION,
            "executed code revision/GO")
    require(whole["primary_solver_calls"] == 5140
            and whole["repeat_solver_calls"] == 60
            and whole["completed_conditions"] == 20
            and whole["training_runs"] == whole["source_model_initializations"] == 0,
            "complete execution counts/no-model scope")
    require(whole["scientific_source_revision"] == plan["source_revision"]
            and whole["archive_comparison"] == "NOT_APPLICABLE_NEW_YAW",
            "scientific source/archive scope")
    require((capture/"FAILURES.jsonl").read_bytes() == b"", "G3 failure events")
    require(datetime.datetime.fromisoformat(whole["start_utc"])
            < datetime.datetime.fromisoformat(whole["end_utc"]), "execution timing")
    g2 = root.parent/"SM2_001"
    require(sha(root/"G2_PREREQUISITE.json") == G2_PREREQUISITE_SHA,
            "frozen G2 prerequisite map")
    prerequisite = load(root/"G2_PREREQUISITE.json")
    require(set(prerequisite) == {
        "GO_CANARY_002.json","CANARY_002/MANIFEST.json",
        "CANARY_002/ARTIFACT_HASHES.json","audit/C3_DATA_RESULT_AUDIT_RESULT.json",
        "audit/RESULT_FINDINGS_G2_KO.md"}, "G2 exact prerequisite paths")
    for relative, expected in prerequisite.items():
        path = g2/relative
        require(sha(path) == expected, "G2 prerequisite "+relative)
        published = subprocess.check_output([
            "git","-C",str(repo),"show",
            G2_PUBLICATION+":"+path.relative_to(repo).as_posix()])
        require(published == path.read_bytes(), "accepted G2 publication "+relative)
    require(sha(g2/"audit/C3_DATA_RESULT_AUDIT_RESULT.json") == G2_RECEIPT_SHA
            and load(g2/"audit/C3_DATA_RESULT_AUDIT_RESULT.json")["decision"] == "ACCEPT",
            "accepted G2 DATA prerequisite")
    require(sha(g2/"audit/INDEPENDENT_CANARY_VERIFIER.py") == G2_VERIFIER_SHA,
            "independent verifier derivation source")
    require(load(g2/"CANARY_002/MANIFEST.json")["status"]
            == "C3_CANARY_EXECUTION_PASS_PENDING_INDEPENDENT_AUDIT",
            "retained G2 terminal execution")
    for rel, expected in OLD_FIXED.items():
        require(sha(g2/rel) == expected, "old failure preservation "+rel)
    old = load(g2/"CANARY_001/MANIFEST.json")
    require(old["status"] == "STOP_ERROR" and old["primary_solver_calls"] == 0
            and old["repeat_solver_calls"] == old["completed_conditions"] == 0
            and old["code_revision"] == OLD_PUBLICATION, "old STOP unchanged")
    old_index_count = index_check(g2/"CANARY_001")
    # G2 numerical payload is not recomputed: the accepted frozen receipt is reused.
    for name in ("source_hash_manifest", "c1b_input_lock"):
        assert_entry(lock[name])
    source = mapped(lock["source_root"])
    require(load(mapped(lock["source_hash_manifest"]["path"])) == lock["source_sha256"],
            "whole source hash registry")
    for rel, expected in lock["source_sha256"].items():
        require(sha(source/rel) == expected, "source input hash "+rel)
    for category in ("banks", "legacy_dependencies", "source_model_g4"):
        for entry in lock[category].values():
            assert_entry(entry)
    for condition in lock["actual_yaw_read_only"].values():
        for entry in condition.values():
            assert_entry(entry)
    governance = load(root/"GOVERNANCE.json")
    for entry in governance["source"].values():
        assert_entry(entry)
    runtime = load(mapped(lock["legacy_dependencies"]["RUNTIME_LOCK.json"]["path"]))
    actual = runtime_snapshot()
    require(actual == whole["validated_runtime"], "actual versus executed runtime")
    for key, value in actual.items():
        require(runtime[key] == value, "frozen runtime "+key)
    require(np.__version__ == "1.26.4", "pinned NumPy promotion semantics")
    block = source/"results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C"
    frequencies = np.load(block/"freqs_hz.npy", allow_pickle=False)
    require(frequencies.shape == (257,) and frequencies.dtype == np.float64,
            "257-bin frequency schema")
    banks = [arrays(mapped(lock["banks"][name]["path"]))
             for name in ("LP_plus45_bank.npz","LP_minus45_bank.npz")]
    for bank in banks:
        exact(bank["freqs_hz"], frequencies, "bank frequency grid")
    solver = load(source/"results/SIONNA_NATIVE41_REFRESH_20260925_01a0d84e/CONFIG.json")["solver"]
    require(solver == dict(max_depth=3,samples_per_src=100000,
                          max_num_paths_per_src=1000000,synthetic_array=True,
                          los=True,specular_reflection=True,refraction=True,
                          diffraction=False,edge_diffraction=False,
                          diffuse_reflection=False,seed=20260924), "full solver config")
    expected_scene = load(block/"R4_aB_m0/MANIFEST.json")["material_bindings"]
    root_index_count, recovery_evidence = recovery_index_check(root, capture, plan, whole, manager)
    require({v.name for v in capture.iterdir() if v.is_dir()}
            == {v["id"] for v in plan["authorized"]}, "capture directory set")
    results = []
    for row in plan["authorized"]:
        result = verify_condition(capture/row["id"], row, plan, go_sha,
                                  PUBLICATION, frequencies, banks, solver,
                                  expected_scene)
        results.append(result)
        print("C3_INDEPENDENT_CONDITION_RESULT "+json.dumps(result, allow_nan=False),
              flush=True)
    with (capture/"INDEX.csv").open(newline="", encoding="utf8") as stream:
        index_rows = list(csv.DictReader(stream))
    require(len(index_rows) == 20, "INDEX row count")
    for record, row, result in zip(index_rows, plan["authorized"], results):
        require(record["condition_id"] == row["id"]
                and record["coordinate"] == row["coordinate"]
                and float(record["yaw_deg"]) == row["yaw_deg"]
                and record["status"] == "C3_RAW_NUMERICAL_PASS"
                and record["raw_sha256"] == result["raw_sha256"], "INDEX identity")
    return {
        "schema":"C3_G3_RETAINED_DATA_V1", "decision":"ACCEPT",
        "record_status":"RECORD_RECOVERY_ONLY",
        "execution_status":"FORCED_AFTER20",
        "original_clean_execution_acceptance":False,
        "posthoc_administrative_recovery":True,
        "scope":"G3_REMAINING20_POSTHOC_RETAINED_RAW_ONLY",
        "question_id":plan["question_id"], "published_code_revision":PUBLICATION,
        "bindings_sha256":bound, "go_sha256":go_sha, "spec_audit_sha256":SPEC_SHA,
        "capture_manifest_sha256":sha(capture/"MANIFEST.json"),
        "original_capture_artifact_index_sha256":None,
        "recovery_evidence":recovery_evidence,
        "execution_manager_receipt_sha256":sha(manager_path),
        "capture_index_sha256":sha(capture/"INDEX.csv"),
        "root_indexed_artifacts":root_index_count,
        "old_failure_indexed_artifacts_verified":old_index_count,
        "launch_stdout_sha256":sha(launch_path),
        "g2_prerequisite_sha256":G2_PREREQUISITE_SHA,
        "g2_data_acceptance_sha256":G2_RECEIPT_SHA,
        "g2_numerical_audit_reexecuted":False,
        "derivation_source_sha256":G2_VERIFIER_SHA,
        "counts":{"conditions":20,"primary_bins":5140,"repeat_bins":60,
                  "primary_solver_calls":5140,"repeat_solver_calls":60,
                  "direct_projection_bin_matrices":5140,
                  "direct_projection_complex_coefficients":20560},
        "conditions":results, "original_STOP_preserved":True,
        "additional_rt_calls":0,"source_model_initializations":0,"fft_calls":0,
        "claim_boundaries":["Posthoc retained numerical raw data acceptance only.",
                            "Original forced execution is not natural success; missing evidence remains missing.",
                            "Recovered index is an external administrative record, not the original producer index.",
                            "No G4 polarization decomposition or model evaluation.",
                            "G2 accepted raw receipt reused; no previous numerical audit rerun.",
                            "Combined24 raw capture does not establish physical/model effects.",
                            "No overall C3 scientific completion or adoption claim; NO-GO/HOLD remains."],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("output_json", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output_json.resolve()
    require(not output.exists(), "preserve previous independent verifier output")
    require(not output.is_relative_to(root/"BATCH_001")
            and not output.is_relative_to(root.parent/"SM2_001"),
            "verifier output must not modify G3 capture or any G2 evidence")
    require(output.parent.exists(), "output parent must already exist")
    try:
        result = audit(root)
    except Exception as exc:
        result = {"schema":"C3_G3_RETAINED_DATA_V1","decision":"STOP",
                  "record_status":"RECORD_RECOVERY_ONLY",
                  "execution_status":"FORCED_AFTER20",
                  "original_clean_execution_acceptance":False,
                  "scope":"G3_REMAINING20_POSTHOC_RETAINED_RAW_ONLY",
                  "error":repr(exc),"traceback":traceback.format_exc(),
                  "additional_rt_calls":0,"source_model_initializations":0,
                  "fft_calls":0}
    result["verifier_sha256"] = sha(Path(__file__))
    result["timestamp_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    payload = (json.dumps(result, indent=2, allow_nan=False)+"\n").encode("utf8")
    with output.open("xb") as stream:
        stream.write(payload)
    print("C3_DATA_VERIFIER_RESULT "+json.dumps(result, allow_nan=False), flush=True)
    raise SystemExit(0 if result["decision"] == "ACCEPT" else 1)


if __name__ == "__main__":
    main()
