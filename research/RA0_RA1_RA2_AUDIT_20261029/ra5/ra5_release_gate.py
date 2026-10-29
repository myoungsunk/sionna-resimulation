#!/usr/bin/env python3
"""RA5 stage-accounting and external-data fail-closed report. Does not invent a test scene."""
import argparse,csv,datetime,hashlib,json,os,pathlib,sys

def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def main(p2,p35,out):
    out=pathlib.Path(out);out.mkdir(exist_ok=True,parents=True)
    p2=pathlib.Path(p2)/"RA5_P2_QA.json"
    p35=pathlib.Path(p35)/"RA5_P35_QA.json"
    if not p2.is_file() or not p35.is_file():raise RuntimeError("ERR_MISSING_UPSTREAM_QA")
    a=json.loads(p2.read_text());b=json.loads(p35.read_text())
    if a["status"]!="PASS_RETROSPECTIVE_RESIDUAL_DIAGNOSTIC":raise RuntimeError("ERR_RA5_2_QA")
    if b["status"]!="PASS_P3_P5_CONTROLLED_DIAGNOSTICS_ONLY":raise RuntimeError("ERR_RA5_3_5_QA")
    gates=[
      dict(stage="A4",status="PASS_ALL28_IDENTITY_AND_3CASE_FACTORIAL",
           claim="controlled computational intervention and initialization/noise sensitivity, archived source"),
      dict(stage="RA5-0",status="PASS_7_CASE_SOURCE_REPLAY",
           claim="H/LoS, 257 fgrid, packet source parity; not physical truth"),
      dict(stage="RA5-1",status="PASS_SYNTHETIC_MATH_FIXTURES",
           claim="two-tap invertible transform, duplicate zero info, MA1, Schur method"),
      dict(stage="RA5-2",status="PASS_RETROSPECTIVE_ONLY__FIELD_TIME_BLOCKED",
           claim="frozen Full-LoS deterministic error cross-cov; static single RF realization cannot isolate time"),
      dict(stage="RA5-3",status="PASS_MATCHED_PRIOR_FFD_JxR_SYNTHETIC_DIAGNOSTIC",
           claim="true archived LoS Jacobian x synthetic covariance scale, not independent physics"),
      dict(stage="RA5-4",status="BLOCKED_CALIBRATED_J1_R_OLD_HARDWARE",
           claim="no independently calibrated same-packet raw-tap stochastic 3x3 covariance, no valid online adjacent-tap derivative"),
      dict(stage="RA5-5",status="DIAGNOSTIC_GRAMIAN_ONLY__BLOCKED_4v5_FILTER",
           claim="physical b_s time dynamics and white-colored split unidentifiable, no 4-state-v-5-state release"),
      dict(stage="RA5-6",status="BLOCKED_NEW_INDEPENDENT_TEST_NOT_REGISTERED",
           claim="no pre-frozen unseen environment or independent real measurement in this execution; Corridor/seen Office are DEV")]
    qa=dict(status="TECHNICAL_RETROSPECTIVE_PARTIAL_STOP_GATES_ENFORCED",
        stages=gates,upstream_p2_sha256=sha(p2),upstream_p35_sha256=sha(p35),
        source_H_physical_truth="NOT_PROVEN",
        independent_noise_covariance="NOT_ESTABLISHED",
        online_delta_s="ADJACENT_TAP_CONDITIONAL_NO_HARDWARE",
        latent_state="NOT_DEPLOYABLE",
        independent_auditor="NOT_OBTAINED",generalization="NOT_TESTED",
        original_data_unchanged=True,science_release=False,
        created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        execution_sha=os.getenv("GITHUB_SHA","UNKNOWN"))
    (out/"RA5_STAGE_VERDICTS.json").write_text(json.dumps(qa,ensure_ascii=False,indent=2)+"\n")
    lines=["# RA5 단계별 실행 판정 (2026-10-29)","",
      "원본 2026-10-07 RT/H, 기존 RA4 score, 기존 원본 계약을 변경하지 않았습니다.","",
      "| 단계 | 판정 | 근거와 한계 |","|---|---|---|"]
    for z in gates:lines.append("| "+z["stage"]+" | "+z["status"]+" | "+z["claim"]+" |")
    lines+=["","## 다음 제약",
      "RA5-4 / RA5-5 정식 실행은 독립적으로 검증된 추가 tap 응답 Jacobian, 관측 r/s0/ds1 결합 센서잡음, white/colored decomposition, 원래 raw 전처리/선택 편향의 train-only 추정이 선행되어야 합니다.",
      "RA5-6의 확증은 학습·설계에 보이지 않은 신규 scene/measurement와 독립 감사 승인 없이는 할 수 없습니다.",
      "새 데이터가 없는 한 기존 Corridor/Office 재분석은 SUPPORTED_RETROSPECTIVE만 가능합니다.",
      "모든 결과는 SELF_REVIEW_ONLY이며 독립적 science release는 보류합니다.",""]
    (out/"RA5_EXECUTION_REPORT_KO.md").write_text("\n".join(lines))
    print("RA5_RELEASE_FINAL "+json.dumps(qa,ensure_ascii=False),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--p2",required=True);p.add_argument("--p35",required=True);p.add_argument("--out",required=True)
    x=p.parse_args();main(x.p2,x.p35,x.out)
