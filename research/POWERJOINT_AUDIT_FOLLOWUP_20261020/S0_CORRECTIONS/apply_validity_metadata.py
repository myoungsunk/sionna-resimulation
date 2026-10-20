"""Add posthoc applicability metadata; never recompute RF or rewrite CSV/DECISION.

Run from the followup checkout. Originals are raw text bytes, not reserialized JSON.
Existing JSON values and protocol parameters remain immutable.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path

STATUS = "INVALID_DESIGN_ZERO_RANGE_JACOBIAN"
KEY = "posthoc_validity_20261020"
REASON = (
    "Range 행 Jacobian = 0으로 직접 Range 감도 제거, C_rs·gate 영향만 남음. Range 교정 근거로 사용 불가\n"
    "SRC_TAP은 양자화된 정수 검출 tap으로 range를 예측하므로 tap 내부에서 "
    "range의 위치 Jacobian이 0이다. 이를 연속 EKF의 range 관측으로 사용하면 "
    "range의 직접 위치 관측 정보가 제거되고 range–s joint gain·gate·교차공분산 "
    "경로가 달라진다. 따라서 잔차 0과 안정 tap FD 0은 range 관측식 교정의 "
    "유효성 증거가 아니며, SRC_TAP 재귀 arm 및 그 파생 표·개입·변화량은 "
    "INVALID_DESIGN_ZERO_RANGE_JACOBIAN이다. B_OLD와 B_REFIT_ONLY에는 적용하지 않는다."
)
POPULATION = (
    "과거 '요청 9,519점 중 2,268점 미확보이므로 BLOCKED_INPUT'이라는 현재 판정은 "
    "철회한다. 7,251점 실행 기록과 원문은 보존하며, 서로 다른 모집단의 대응은 "
    "별도 S0 모집단 감사에서 판정한다. 이 정정은 새 모집단 수치나 대응 인증을 주장하지 않는다."
)
EXECUTION = (
    "구현1/canonical의 현재 지위는 검증된 실행 기준이다. 구현2·3은 "
    "DEFERRED_SOURCE_UNAVAILABLE이며 원본 비교·동등성 검증을 완료한 것으로 간주하지 않는다. "
    "파일명 CANONICAL_RESULTS.csv와 역사적 정본 표기는 원문 식별자로 보존한다."
)
POLICY = (
    "T7B NO_GO는 사전 고정한 v2 정책(특징·label·학습·행동 규칙)의 평가 결과에만 적용한다. "
    "효용 target 접근 전체나 가능한 다른 정책의 기각으로 일반화하지 않는다."
)


def digest(path):
    data = path.read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    args = ap.parse_args()
    root = args.root.resolve()
    audit = root / "research/POWERJOINT_AUDIT_RERUN_20261020"
    own = root / "research/POWERJOINT_AUDIT_FOLLOWUP_20261020/S0_CORRECTIONS"
    originals = own / "ORIGINALS"
    index_path = own / "VALIDITY_INDEX.json"
    if index_path.exists():
        raise SystemExit("Already applied: inspect VALIDITY_INDEX.json; originals must not be replaced.")

    def rel(p):
        return p.relative_to(root).as_posix()

    protected = sorted(p for p in audit.rglob("*") if p.is_file() and (
        p.name.endswith((".csv", ".csv.gz")) or
        (p.suffix == ".json" and p.name.startswith("DECISION"))))
    before = {rel(p): digest(p) for p in protected}
    snapshots = {}
    changes = []

    def snapshot(p):
        target = originals / p.relative_to(audit)
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = p.read_bytes()
        if target.exists():
            assert target.read_bytes() == raw, f"Conflicting original: {target}"
        else:
            target.write_bytes(raw)
        snapshots[rel(p)] = {**digest(target), "original_path": rel(target)}

    def metadata(kind):
        m = {
            "record_type": "POSTHOC_APPLICABILITY_CORRECTION_NOT_PREREGISTRATION",
            "source_audit_base": "034e57a",
            "preservation_commit": "f7a0ef37d98719ec58fa5231927d6af1e3b117e8",
            "preservation_actions_run_id": "39367272729",
            "original_parameters_and_decisions_unchanged": True,
            "validity_index": rel(index_path),
        }
        if kind in ("src", "mixed", "t6"):
            m.update(status=STATUS, reason_ko=REASON,
                     scope="SRC_TAP arms and SRC-derived values only",
                     unaffected_range_models=["B_OLD", "B_REFIT_ONLY"],
                     diagnostic_limit="Raw detector residual/FD evidence is preserved; no EKF correction-validity claim.")
        if kind == "t6":
            m["historical_population_blocker_withdrawn"] = True
            m["population_correction_ko"] = POPULATION
        if kind == "t1":
            m.update(current_engine_designation="검증된 실행 기준",
                     implementation_2="DEFERRED_SOURCE_UNAVAILABLE",
                     implementation_3="DEFERRED_SOURCE_UNAVAILABLE", reason_ko=EXECUTION)
        if kind == "t7":
            m.update(current_policy_scope="FIXED_V2_POLICY_ONLY", reason_ko=POLICY)
        return m

    def patch_json(p, kind):
        old = json.loads(p.read_text(encoding="utf-8-sig"))
        assert isinstance(old, dict), p
        assert KEY not in old, p
        snapshot(p)
        new = dict(old)
        new[KEY] = metadata(kind)
        dump(p, new)
        actual = json.loads(p.read_text(encoding="utf-8"))
        assert {k: v for k, v in actual.items() if k != KEY} == old, p
        changes.append({"path": rel(p), "kind": kind, "existing_json_values_unchanged": True})

    def patch_md(p, kind):
        snapshot(p)
        old = p.read_text(encoding="utf-8-sig")
        texts = ["## 2026-10-20 사후 적용성 정정", ""]
        if kind in ("src", "mixed", "t6"):
            texts += [f"**{STATUS} — SRC_TAP에 한정.** {REASON}", ""]
        if kind == "t6":
            texts += [POPULATION, ""]
        if kind == "t1":
            texts += [EXECUTION, ""]
        if kind == "t7":
            texts += [POLICY, ""]
        texts += ["아래는 보존된 당시 보고 내용이다. 현재 해석은 이 사후 정정을 우선한다. "
                  "원래 숫자 CSV·DECISION·사전 등록 파라미터는 변경하지 않았고 원문 bytes/SHA는 "
                  "후속 S0_CORRECTIONS/ORIGINALS와 VALIDITY_INDEX.json에 보존했다.", "", "---", ""]
        p.write_text("\n".join(texts) + "\n" + old, encoding="utf-8")
        changes.append({"path": rel(p), "kind": kind, "historical_body_preserved": True})

    # Only current reports/manifests/locks and SRC-derived output branches.
    json_targets = {}
    md_targets = {}
    for task, kind in (("T1_MEMORY", "t1"), ("T6_RANGE", "t6"), ("T7_POLICY", "t7")):
        for name in ("MANIFEST.json", "PROTOCOL_LOCK.json"):
            json_targets[audit / task / name] = kind
        md_targets[audit / task / "RESULTS_KO.md"] = kind
    md_targets[audit / "T1_MEMORY/IMPLEMENTATION_DIFF.md"] = "t1"
    md_targets[audit / "T6_RANGE/DESIGN_KO.md"] = "t6"
    for name in ("PARAMETER_MANIFEST.json",):
        json_targets[audit / "T6_RANGE" / name] = "t6"
    for branch in ("native_execution_r01", "replay_execution_r01"):
        for name in ("MANIFEST.json", "PARAMETER_MANIFEST.json"):
            p = audit / "T6_RANGE" / branch / name
            if p.exists():
                json_targets[p] = "t6"
        p = audit / "T6_RANGE" / branch / "RESULTS_KO.md"
        if p.exists():
            md_targets[p] = "t6"
    for task in ("T3_SOURCEFFD_TABLES", "T4_F1_EVENT"):
        json_targets[audit / task / "MANIFEST.json"] = "mixed"
        md_targets[audit / task / "RESULTS_KO.md"] = "mixed"
        for p in (audit / task).rglob("*"):
            if not p.is_file():
                continue
            is_src = any("src" in part.lower() for part in p.relative_to(audit / task).parts)
            if not is_src:
                continue
            if p.name == "MANIFEST.json" or (p.name.startswith("PROTOCOL_LOCK") and p.suffix == ".json"):
                json_targets[p] = "src"
            elif p.name == "RESULTS_KO.md":
                md_targets[p] = "src"
    for p, kind in sorted(json_targets.items()):
        if p.exists():
            patch_json(p, kind)
    for p, kind in sorted(md_targets.items()):
        if p.exists():
            patch_md(p, kind)

    # The summary is current-facing: withdraw the population blocker and narrow claims.
    p = audit / "00_SUMMARY_KO.md"
    snapshot(p)
    text = p.read_text(encoding="utf-8-sig")
    text = text.replace("정본", "검증된 실행 기준")
    text = text.replace("구현2/3 원본 BLOCKED_INPUT", "구현2/3 DEFERRED_SOURCE_UNAVAILABLE")
    text = text.replace("인증한 기억 구현1 원본", "검증된 실행 기준인 기억 구현1 원본")
    text = text.replace("세 구현의 완전한 원인 diff는 BLOCKED_INPUT이다.",
                        "세 구현의 완전한 원인 diff는 DEFERRED_SOURCE_UNAVAILABLE이다.")
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("| T3 |"):
            lines[i] = "| T3 | SourceFFD 통일 | B_OLD 계산 PASS; SRC_TAP 설계 무효 | B_OLD NOT_ESTABLISHED; SRC_TAP INVALID_DESIGN_ZERO_RANGE_JACOBIAN | B_OLD L2 J4 M0 .298943°, M45 .180166°; 구 LUT 변경6칸 | run39358530627,39361112976 / artifact12236606373,12237193562 |"
        elif line.startswith("| T4 |"):
            lines[i] = "| T4 | F1 흡수 경로 | B_OLD 10이벤트 완료; SRC_TAP 설계 무효 | B_OLD NOT_ESTABLISHED; SRC_TAP INVALID_DESIGN_ZERO_RANGE_JACOBIAN | B_OLD POST30 지지0/5; R5 V1 skip +7.740819° | scope lock52b1212 / run39359599833,39361156858,39361448922 / T4 MANIFEST |"
        elif line.startswith("| T6 |"):
            lines[i] = "| T6 | 검출 tap Range | 당시 계산 기록 보존; SRC_TAP 설계 무효 | INVALID_DESIGN_ZERO_RANGE_JACOBIAN; 과거 모집단 BLOCKED_INPUT 사유 철회 | 잔차0·안정 tap FD0은 연속 EKF range 교정 증거가 아님; B_OLD/B_REFIT_ONLY 유효 | run39358085714,39359601219 / artifact12236256727,12236414588 |"
        elif line.startswith("| T7B |"):
            lines[i] = line.replace("NOT_ESTABLISHED, NO_GO", "NOT_ESTABLISHED, 고정 v2 정책 NO_GO")
        elif line.startswith("| R5 A B0 POWER1 range 변경 |"):
            lines[i] = line.rsplit("|", 2)[0] + "| SRC_TAP 및 변화량은 INVALID_DESIGN_ZERO_RANGE_JACOBIAN; 교정 증거에서 제외 |"
        elif line.startswith("2. T6 원 요청9,519점"):
            lines[i] = "2. T6의 과거 2,268점 미확보 BLOCKED_INPUT 주장은 철회했다. 모집단 대응은 후속 S0 감사의 별도 항목이며, 이 문서는 새 대응 인증이나 수치를 주장하지 않는다. SRC_TAP의 현재 제외 사유는 입력 누락이 아니라 0 range Jacobian 설계다."
        elif line.startswith("1. T1 구현2 원본"):
            lines[i] = line + " 현재 분류는 DEFERRED_SOURCE_UNAVAILABLE이며 검증된 구현1 실행 기준의 재현을 무효화하는 전역 차단 사유는 아니다."
        elif line.startswith("- B_OLD SourceFFD와 T6 SRC_TAP"):
            lines[i] = "- " + REASON + " T3/SRC_TAP, T4/SRC_TAP·POST30_SRC_TAP은 원래 수치·판정을 보존하되 교정·F1 검증 증거에서 제외한다."
    text = "\n".join(lines) + "\n"
    banner = ("2026-10-20 S0 사후 적용성 정정: " + REASON + "\n\n" + EXECUTION + "\n\n" +
              POPULATION + "\n\n" + POLICY + "\n\n" +
              "수정 전 원문은 후속 S0_CORRECTIONS/ORIGINALS에 보존했다. 숫자 CSV와 원래 DECISION은 변경하지 않았다.\n\n")
    first, rest = text.split("\n", 1)
    p.write_text(first + "\n\n" + banner + rest.lstrip("\n"), encoding="utf-8")
    changes.append({"path": rel(p), "kind": "current_summary"})

    csv_entries = []
    for p in protected:
        if not p.name.endswith((".csv", ".csv.gz")):
            continue
        rp = p.relative_to(audit)
        parts = rp.parts
        in_t6 = parts[0] == "T6_RANGE"
        in_src = parts[0] in ("T3_SOURCEFFD_TABLES", "T4_F1_EVENT") and any("src" in x.lower() for x in parts[1:])
        if not (in_t6 or in_src):
            continue
        opener = gzip.open if p.name.endswith(".gz") else open
        with opener(p, "rt", encoding="utf-8-sig", newline="") as stream:
            header = next(csv.reader(stream), [])
        entry = {"path": rel(p), "original_unchanged": before[rel(p)], "status": STATUS,
                 "reason_ko": REASON, "kind": "CSV_VALIDITY_SIDECAR"}
        if p.name == "RANGE_REPLAY.csv":
            entry.update(invalid_rows={"range_model": ["SRC_TAP"]}, valid_rows={"range_model": ["B_OLD", "B_REFIT_ONLY"]})
        elif p.name == "RANGE_COMPARISON.csv":
            entry.update(invalid_columns=[c for c in header if c.endswith(("_src", "_delta"))],
                         unaffected_columns=[c for c in header if c.endswith("_old")])
        elif in_t6 and p.name.endswith("NATIVE_RESIDUALS.csv"):
            entry.update(invalid_columns=["predicted_src_m", "error_src_m"],
                         valid_columns=["distance_m", "theta_deg", "observed_m", "error_old_m", "error_refit_m", "refit_offset_m"],
                         scope="Only named SRC prediction/error columns invalid as Range correction evidence; observed/geometric/B_OLD/refit columns remain valid.")
        elif in_t6 and p.name in ("REPLAY_CHECKS.csv",):
            entry.update(scope="SRC_TAP checks describe computation only; B_OLD/B_REFIT_ONLY checks remain valid.")
        elif in_t6 and "OOF_PARAMETERS" not in p.name:
            entry.update(scope="Detector residual/FD descriptive evidence only; excluded as EKF correction-validity evidence.")
        else:
            entry.update(scope="All SRC_TAP-derived numerical outcome columns; identity columns are identifiers only.")
        csv_entries.append(entry)

    summary_entries = []
    for p in sorted(audit.rglob("SUMMARY.json")):
        parts = p.relative_to(audit).parts
        if parts[0] == "T6_RANGE" or (parts[0] in ("T3_SOURCEFFD_TABLES", "T4_F1_EVENT") and any("src" in x.lower() for x in parts[1:])):
            summary_entries.append({"path": rel(p), "original_unchanged": digest(p),
                                    "status": STATUS, "reason_ko": REASON,
                                    "scope": "SRC_TAP-derived values excluded as Range correction/F1 evidence; original SUMMARY and historical decision unchanged.",
                                    "kind": "JSON_VALIDITY_SIDECAR"})

    after = {rel(p): digest(p) for p in protected}
    assert before == after, "CSV or original DECISION modified"
    receipts_path = originals / "RECEIPTS.json"
    dump(receipts_path, snapshots)
    index = {
        "schema": 1, "record_type": "POSTHOC_APPLICABILITY_CORRECTION_NOT_PREREGISTRATION",
        "status": STATUS, "reason_ko": REASON,
        "source_audit_base": "034e57a",
        "preservation_commit": "f7a0ef37d98719ec58fa5231927d6af1e3b117e8",
        "preservation_actions_run_id": "39367272729",
        "unaffected_range_models": ["B_OLD", "B_REFIT_ONLY"],
        "population_correction_ko": POPULATION, "execution_basis_ko": EXECUTION,
        "t7_policy_scope_ko": POLICY, "changed_text_files": changes,
        "original_text_receipts": rel(receipts_path), "csv_validity_sidecars": csv_entries,
        "json_validity_sidecars": summary_entries,
        "immutable_file_checks": {"result": "PASS", "count": len(protected),
                                  "csv_count": sum(p.name.endswith((".csv", ".csv.gz")) for p in protected),
                                  "decision_count": sum(p.suffix == ".json" and p.name.startswith("DECISION") for p in protected),
                                  "before": before, "after": after},
        "json_existing_values_unchanged": True,
        "execution": "Metadata/text corrections only; no RF, recursion, statistics, or model execution.",
    }
    dump(index_path, index)
    print(json.dumps({"changed_text_files": len(changes), "original_snapshots": len(snapshots),
                      "csv_sidecars": len(csv_entries), "immutable_checks": index["immutable_file_checks"]["count"],
                      "csv_count": index["immutable_file_checks"]["csv_count"],
                      "decision_count": index["immutable_file_checks"]["decision_count"],
                      "index_sha256": digest(index_path)["sha256"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
