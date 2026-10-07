import pytest

from qclean_uwb.drivesim.config import build_manifest, canonical_json, config_sha256, file_sha256, param, validate_params


def test_hash_is_order_independent_and_changes_with_value():
    a = {"x": param(1, "assumption", "t"), "y": param(2, "adopted", "t")}
    b = {"y": param(2, "adopted", "t"), "x": param(1, "assumption", "t")}
    assert config_sha256(a) == config_sha256(b)
    assert config_sha256(a) != config_sha256({**a, "x": param(3, "assumption", "t")})


def test_param_rejects_unknown_status_and_validate_finds_missing_tags():
    with pytest.raises(ValueError):
        param(1, "guess", "t")
    errs = validate_params({"a": {"value": 1}, "b": {"c": param(1, "derived", "t")}})
    assert len(errs) == 2 and errs[0].startswith("a:")


def test_nan_is_rejected_by_canonical_json():
    with pytest.raises(ValueError):
        canonical_json({"v": float("nan")})


def test_manifest_records_hashes(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hello")
    m = build_manifest(config={"k": param(1, "adopted", "t")}, inputs=[f], outputs=[f], command=["cmd"], timestamp=0.0)
    assert m["inputs"][0]["sha256"] == file_sha256(f) and m["timestamp_utc"] == "1970-01-01T00:00:00Z" and m["command"] == ["cmd"]
