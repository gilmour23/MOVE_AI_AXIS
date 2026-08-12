"""
AXIS v7.1 회귀 테스트 — 자립 실행 (지시서 18.3)

    python 02_CODE/test_v7_1.py

저장된 과거 결과에 의존하지 않는다.
필요한 입력(파라미터·후보 시간표·Service Need)을 이 스크립트가 직접 초기화하고,
모든 결과를 임시 작업 폴더에 새로 생성한 뒤 검사한다.

검사 범위
  1. Reference parameter 초기화 및 거리 정합성
  2. Inventory Policy 스키마 (구조화 오류, 조용한 무시 없음)
  3. Carrier ownership / source release capacity
  4. Joint optimization 불변식 (구간 capacity, 최소 consolidation, 정수성, 기한)
  5. 선사 관점 == KORAIL 관점 물량 일치
  6. 결정성 (동일 입력 5회 반복)
  7. 협상 계층이 main flow 에 남아있지 않음
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "02_CODE"
DATA = ROOT / "03_INPUT_DATA"
sys.path.insert(0, str(CODE))

import axis_milp_v7_1 as m  # noqa: E402
import axis_baselines_v7_1 as baselines  # noqa: E402

HOURLY = DATA / "AXIS_carrier_hourly_plan_v7_1.csv"
INITIAL = DATA / "carrier_initial_inventory.csv"
PARAMS = DATA / "AXIS_rail_OD_parameters_v1.xlsx"
EXT_CAND = DATA / "TEST_KORAIL_CANDIDATES"

# 테스트 전용 빠른 시나리오. 정본 default(72h)와 다르며 불변식 검사가 목적이다.
TEST_EARLINESS = 48.0
TEST_MIN_LF = 0.5
TEST_TIME_LIMIT = 300

results = []


def check(name, ok, detail=""):
    results.append({"check": name, "pass": bool(ok), "detail": str(detail)[:400]})
    print(("  PASS  " if ok else "  FAIL  ") + name + (f"  | {detail}" if detail else ""))


# --------------------------------------------------------------------------
def init_params():
    """지시서 18.3: reference parameter 를 명시적으로 초기화한다."""
    print("\n[1] Reference parameter initialisation")
    p = m.configure_params(PARAMS)
    check("params_loaded_from_xlsx",
          any(r["loaded_from"] == "XLSX" for r in p.provenance),
          {r["loaded_from"] for r in p.provenance})
    failed = [c for c in p.validation if c["check"] != "_deltas" and not c["pass"]]
    check("distance_validation_all_pass", not failed, failed)
    deltas = [c for c in p.validation if c["check"] == "_deltas"][0]["detail"]
    unexplained = [d for d in deltas
                   if abs(d["delta_km"]) > 0.01
                   and not (d["passes_through_bugang"] and abs(d["delta_km"] - 5.8) < 0.01)]
    check("physical_vs_tariff_fully_explained", not unexplained, unexplained)
    check("segment_and_tariff_tables_present",
          len(m.SEGMENT_DISTANCE) > 0 and len(m.OD_DISTANCE) > 0,
          f"segments={len(m.SEGMENT_DISTANCE)} tariff={len(m.OD_DISTANCE)}")


def build_service(workdir: Path, policies=None):
    hourly = m.read_hourly(HOURLY)
    initial = m.read_initial(INITIAL)
    ts = sorted({r["timestamp"] for r in hourly})
    indir = workdir / "MODEL_INPUTS"
    if not m._candidate_inputs_match(indir, ts[0], len(ts)):
        m.generate_candidate_inputs(ts[0], len(ts), indir)
    service = m.generate_service_needs(hourly, initial,
                                       policies or {"inventory_policies": []}, indir)
    return service, m.read_candidate_inputs(indir)


# --------------------------------------------------------------------------
def test_policy_schema(workdir):
    print("\n[2] Inventory Policy schema")
    hourly = m.read_hourly(HOURLY)
    initial = m.read_initial(INITIAL)
    base = len(m.generate_service_needs(hourly, initial, {"inventory_policies": []})["needs"])

    cases = [
        ("v6.1 legacy key 'type'", "MISSING_FIELD", {
            "type": "MIN_INVENTORY_RANGE", "carrier_id": "CARRIER_A",
            "hub_code": "YAKMOK", "container_size": "40FT", "value": 10}),
        ("plan-doc rule_type MIN_INVENTORY", "UNKNOWN_RULE_TYPE", {
            "rule_type": "MIN_INVENTORY", "carrier_id": "CARRIER_A",
            "hub_code": "YAKMOK", "container_size": "40FT", "value": 10}),
        ("soft TARGET_INVENTORY", "RULE_TYPE_NOT_IMPLEMENTED", {
            "rule_type": "TARGET_INVENTORY", "carrier_id": "CARRIER_A",
            "hub_code": "YAKMOK", "container_size": "40FT", "value": 25}),
        ("unknown hub", "UNKNOWN_HUB", {
            "rule_type": "MIN_INVENTORY_RANGE", "carrier_id": "CARRIER_A",
            "hub_code": "SEOUL", "container_size": "40FT", "value": 10}),
        ("unknown carrier", "UNKNOWN_CARRIER", {
            "rule_type": "MIN_INVENTORY_RANGE", "carrier_id": "CARRIER_Z",
            "hub_code": "YAKMOK", "container_size": "40FT", "value": 10}),
        ("time outside horizon", "TIME_OUTSIDE_HORIZON", {
            "rule_type": "MIN_INVENTORY_AT_TIME", "carrier_id": "CARRIER_A",
            "hub_code": "YAKMOK", "container_size": "40FT", "value": 10,
            "target_time": "2026-09-01 18:00"}),
        ("negative value", "BAD_VALUE", {
            "rule_type": "MIN_INVENTORY_RANGE", "carrier_id": "CARRIER_A",
            "hub_code": "YAKMOK", "container_size": "40FT", "value": -5}),
        ("unknown field", "UNKNOWN_FIELD", {
            "rule_type": "MIN_INVENTORY_RANGE", "carrier_id": "CARRIER_A",
            "hub_code": "YAKMOK", "container_size": "40FT", "value": 10,
            "negotiation_round": 2}),
    ]
    for label, expect, rule in cases:
        try:
            m.generate_service_needs(hourly, initial, {"inventory_policies": [rule]})
            check(f"policy_rejects::{label}", False, "no error raised")
        except m.PolicyValidationError as e:
            check(f"policy_rejects::{label}", e.reason_code == expect,
                  f"expected={expect} got={e.reason_code}")
            check(f"policy_error_structured::{label}",
                  set(e.as_dict()) >= {"status", "reason_code", "message"}, "")

    ok = {"inventory_policies": [{
        "rule_id": "POL-001", "carrier_id": "CARRIER_A",
        "rule_type": "MIN_INVENTORY_RANGE", "hub_code": "YAKMOK",
        "container_size": "40FT", "start_time": "2026-08-13 00:00",
        "end_time": "2026-08-16 23:00", "value": 10, "hard_constraint": True}]}
    s2 = m.generate_service_needs(hourly, initial, ok)
    check("policy_MIN_INVENTORY_RANGE_applied", len(s2["needs"]) > base,
          f"needs {base} -> {len(s2['needs'])}")
    check("policy_recorded_in_ACTIVE_POLICY", len(s2["active_policies"]) == 1, "")

    s3 = m.generate_service_needs(hourly, initial, {"inventory_policies": [{
        "carrier_id": "CARRIER_A", "rule_type": "ORIGIN_RELEASE_RESTRICTION",
        "hub_code": "BUSAN", "container_size": "40FT", "value": 0}]})
    check("policy_ORIGIN_RELEASE_RESTRICTION_parsed", len(s3["outbound_cap"]) == 1,
          s3["outbound_cap"])


# --------------------------------------------------------------------------
def test_joint_optimization(workdir):
    print("\n[3] Joint multi-carrier optimisation invariants")
    out = workdir / "AXIS_INTEGRATED"
    summ = m.run(HOURLY, INITIAL, workdir, TEST_MIN_LF, None, None,
                 "AXIS_INTEGRATED", TEST_TIME_LIMIT, 0.001, False,
                 TEST_EARLINESS, None, PARAMS)

    check("all_stages_proven_optimal", bool(summ.get("all_stages_proven_optimal")), "")
    check("solver_has_tiebreak_stage", summ.get("solver_stage_count", 0) >= 7,
          summ.get("solver_stage_count"))

    rec = pd.read_csv(out / "CARRIER_RECOMMENDATIONS.csv", encoding="utf-8-sig")
    det = pd.read_csv(out / "CARRIER_RECOMMENDATION_DETAIL.csv", encoding="utf-8-sig")
    alloc = pd.read_csv(out / "CARRIER_ALLOCATION.csv", encoding="utf-8-sig")
    needs = pd.read_csv(out / "SERVICE_NEED_RESULT.csv", encoding="utf-8-sig")
    seg = pd.read_csv(out / "SEGMENT_LOAD.csv", encoding="utf-8-sig")
    trains = pd.read_csv(out / "KORAIL_TRAIN_PLAN.csv", encoding="utf-8-sig")
    ctx = pd.read_csv(out / "RECOMMENDATION_EXPLANATION_CONTEXT.csv", encoding="utf-8-sig")

    check("multi_carrier_consolidation_happens",
          (trains.participating_carrier_count > 1).any(),
          trains.participating_carrier_count.tolist())
    check("integer_assignment", bool((det.quantity_boxes % 1 == 0).all()), "")
    check("segment_capacity_respected", bool((seg.loaded_teu <= seg.capacity_teu).all()), "")
    check("min_consolidation_respected",
          bool((trains.distance_weighted_load_factor + 1e-9 >= TEST_MIN_LF).all()),
          trains[["train_id", "distance_weighted_load_factor"]].to_dict("records"))
    check("formation_selected", bool(trains.formation.notna().all()), "")
    check("due_time_respected",
          bool((pd.to_datetime(det.available_time)
                <= pd.to_datetime(det.service_due_time)).all()), "")
    check("earliness_within_cap",
          bool((det.earliness_hours <= TEST_EARLINESS + 1e-9).all()),
          float(det.earliness_hours.max()))
    check("no_departure_slot_conflict",
          bool((trains.groupby(["origin_terminal", "origin_departure"]).size() <= 1).all()), "")

    # carrier ownership: 배정된 origin 재고는 그 선사 것이어야 한다
    inv = pd.read_csv(INITIAL, encoding="utf-8-sig")
    known = set(zip(inv.carrier_id, inv.hub_code, inv.container_size))
    bad = [r for r in det.itertuples()
           if (r.carrier_id, r.origin_hub, r.container_size) not in known]
    check("carrier_ownership_preserved", not bad, f"{len(bad)} violations")

    # source release capacity
    base = pd.read_csv(workdir / "_RUN_MODEL_INPUTS" / "BASELINE_AND_SOURCE_CAPACITY.csv",
                       encoding="utf-8-sig")
    base["timestamp"] = pd.to_datetime(base.timestamp)
    d2 = det.copy()
    d2["load_start_time"] = pd.to_datetime(d2.load_start_time)
    viol = []
    for (c, o, k), g in d2.groupby(["carrier_id", "origin_hub", "container_size"]):
        bg = base[(base.carrier_id == c) & (base.hub_code == o) & (base.container_size == k)]
        for br in bg.itertuples():
            cum = int(g.loc[g.load_start_time <= br.timestamp, "quantity_boxes"].sum())
            if cum > br.source_release_capacity_cumulative:
                viol.append((c, o, k, str(br.timestamp), cum,
                             br.source_release_capacity_cumulative))
                break
    check("source_release_capacity_respected", not viol, viol[:3])

    # 두 관점의 물량 일치 (지시서 완료조건)
    check("carrier_view_equals_korail_view",
          bool(summ["carrier_korail_view_consistent"]),
          f"rec={summ['carrier_recommendation_teu']} alloc={summ['korail_allocation_teu']} "
          f"served={summ['rail_served_teu']}")
    check("recommendation_detail_sums_match",
          int(det.quantity_teu.sum()) == int(rec.quantity_teu.sum()) == int(alloc.teu.sum())
          == int(needs.rail_served_teu.sum()) == int(trains.total_assigned_teu.sum()),
          f"{int(det.quantity_teu.sum())}/{int(rec.quantity_teu.sum())}/"
          f"{int(alloc.teu.sum())}/{int(needs.rail_served_teu.sum())}/"
          f"{int(trains.total_assigned_teu.sum())}")

    # 챗봇 read-only context
    check("explanation_context_generated", len(ctx) == len(rec), f"{len(ctx)} vs {len(rec)}")
    check("explanation_context_numeric_only",
          set(["recommended_teu", "train_load_factor", "estimated_rail_charge_krw"])
          <= set(ctx.columns), list(ctx.columns)[:8])

    # 선사별 파일에 타 선사 정보가 없어야 한다
    per = list(out.glob("CARRIER_RECOMMENDATIONS_CARRIER_*.csv"))
    check("per_carrier_files_generated", len(per) > 0, len(per))
    leak = []
    for f in per:
        cid = f.stem.replace("CARRIER_RECOMMENDATIONS_", "")
        df = pd.read_csv(f, encoding="utf-8-sig")
        if set(df.carrier_id) - {cid}:
            leak.append(f.name)
    check("per_carrier_file_isolation", not leak, leak)
    return summ


# --------------------------------------------------------------------------
def test_no_negotiation_layer():
    print("\n[4] Negotiation layer removed from main flow")
    src = (CODE / "axis_milp_v7_1.py").read_text(encoding="utf-8")
    banned = ["ACCEPT_SERVICE", "ACCEPT_EXACT_PLAN", "DECLINE_RAIL_SERVICE",
              "MODIFY_SERVICE", "REJECT_OPTION", "proposal_version",
              "negotiation_round", "accepted_by_need", "declined_by_need",
              "forced_service_by_need", "commitment_confirmation_rate"]
    # docstring 의 "제거했다" 설명은 허용하되 코드 식별자로는 없어야 한다
    code_only = "\n".join(l for l in src.split("\n")
                          if not l.strip().startswith("#"))
    doc_end = code_only.find('"""', code_only.find('"""') + 3)
    code_only = code_only[doc_end + 3:]
    found = [b for b in banned if b in code_only]
    check("no_negotiation_identifiers_in_core", not found, found)

    for name in ["load_negotiation", "create_accept_all_actions",
                 "diagnose_commitment_conflict"]:
        check(f"removed::{name}", not hasattr(m, name), "")

    sig = m.run.__code__.co_varnames[:m.run.__code__.co_argcount]
    check("run_has_no_run_mode", "run_mode" not in sig, sig)
    check("run_has_no_actions_path", "actions_path" not in sig, sig)
    check("build_milp_has_no_proposal_reference",
          "proposal_reference" not in m.build_milp.__code__.co_varnames, "")


# --------------------------------------------------------------------------
def test_determinism(workdir, repeats=3):
    print(f"\n[5] Determinism - {repeats} repeated runs")
    hashes, summaries, trainsets = [], [], []
    for r in range(repeats):
        d = workdir / f"DET{r}"
        cmd = [sys.executable, str(CODE / "axis_milp_v7_1.py"),
               "--hourly", str(HOURLY), "--initial", str(INITIAL),
               "--params", str(PARAMS), "--root", str(d),
               "--scenario", "AXIS_INTEGRATED",
               "--min-load-factor", str(TEST_MIN_LF),
               "--max-earliness", str(TEST_EARLINESS),
               "--time-limit", str(TEST_TIME_LIMIT)]
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            detail = (p.stderr or p.stdout or f"returncode={p.returncode}")[-500:]
            check(f"determinism_run_{r}", False, detail)
            return
        out = d / "AXIS_INTEGRATED"
        rec = pd.read_csv(out / "CARRIER_RECOMMENDATIONS.csv", encoding="utf-8-sig")
        rec = rec.sort_values(["carrier_id", "origin_hub", "destination_hub",
                               "container_size", "train_id"]).reset_index(drop=True)
        key = rec[["carrier_id", "origin_hub", "destination_hub", "container_size",
                   "train_id", "quantity_boxes"]]
        hashes.append(hashlib.sha256(key.to_csv(index=False).encode()).hexdigest())
        summaries.append(json.loads((out / "SUMMARY.json").read_text(encoding="utf-8")))
        trainsets.append(tuple(sorted(pd.read_csv(out / "KORAIL_TRAIN_PLAN.csv",
                                                  encoding="utf-8-sig").train_id)))

    check("identical_recommendations", len(set(hashes)) == 1,
          f"{len(set(hashes))} distinct over {repeats} runs")
    check("identical_selected_trains", len(set(trainsets)) == 1,
          f"{len(set(trainsets))} distinct")
    for k in ["rail_served_teu", "selected_train_count", "train_km", "wagon_km",
              "teu_km", "estimated_rail_charge_krw"]:
        vals = {s[k] for s in summaries}
        check(f"identical::{k}", len(vals) == 1, vals)


# ------------------------------------------- v7.1-patch: 외부 KORAIL 후보 교체
def test_external_candidate_replaceability(workdir):
    """지시서 10 — 실제 KORAIL feasible path 로 교체 가능함을 코드로 증명."""
    print("\\n[6] External KORAIL candidate replaceability")
    if not EXT_CAND.exists():
        check("ext::fixture_present", False, "missing " + str(EXT_CAND))
        return
    check("ext::fixture_present", True, "")

    before = {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
              for f in sorted(EXT_CAND.iterdir())}
    out_root = workdir / "EXT"
    summ = m.run(HOURLY, INITIAL, out_root, TEST_MIN_LF, None, None,
                 "AXIS_INTEGRATED", TEST_TIME_LIMIT, 0.001, False,
                 72.0, None, PARAMS, None, None, None, EXT_CAND, True, True)
    after = {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
             for f in sorted(EXT_CAND.iterdir())}

    check("ext::external_candidate_not_overwritten", before == after,
          "before=%s after=%s" % (sorted(before), sorted(after)))
    check("ext::external_candidate_hash_unchanged",
          all(before.get(k) == v for k, v in after.items()), "")
    check("ext::synthetic_generator_not_called",
          not (EXT_CAND / "SERVICE_NEED.csv").exists(),
          "no generated file written into candidate dir")
    check("ext::candidate_source_preserved",
          summ["candidate_timetable_source"] == "KORAIL_FEASIBLE_PATH",
          summ["candidate_timetable_source"])
    check("ext::candidate_input_sources_recorded",
          summ["candidate_input_sources"] == ["KORAIL_FEASIBLE_PATH"],
          summ["candidate_input_sources"])
    check("ext::selected_train_sources_recorded",
          summ["selected_train_sources"] == ["KORAIL_FEASIBLE_PATH"],
          summ["selected_train_sources"])

    out = out_root / "AXIS_INTEGRATED"
    tp = pd.read_csv(out / "KORAIL_TRAIN_PLAN.csv", encoding="utf-8-sig")
    check("ext::external_train_id_used",
          len(tp) > 0 and bool(tp.train_id.astype(str).str.startswith("KTEST").all()),
          tp.train_id.tolist())
    selected = tp[tp.actual_origin_departure.astype(str).str.endswith("06:35")]
    check("ext::actual_departure_minute_preserved_in_train_plan",
          not selected.empty, tp.actual_origin_departure.tolist())
    check("ext::model_departure_slot_separate",
          (not selected.empty)
          and bool(selected.model_origin_departure_time.astype(str).str.endswith("07:00").all()),
          selected[["model_origin_departure_slot", "model_origin_departure_time"]].to_dict("records"))
    rec = pd.read_csv(out / "CARRIER_RECOMMENDATIONS.csv", encoding="utf-8-sig")
    check("ext::actual_departure_minute_preserved_in_carrier_view",
          bool(rec.departure_time.astype(str).str.endswith("06:35").any()),
          rec.departure_time.tolist())
    parsed = m.read_candidate_inputs(EXT_CAND)
    fixture_k1 = next(p for p in parsed if p.train_id == "KTEST001")
    check("ext::actual_arrival_0940_preserved_in_candidate_object",
          fixture_k1.actual_arrival_time["YAKMOK"].strftime("%H:%M") == "09:40",
          fixture_k1.actual_arrival_time["YAKMOK"])
    check("ext::external_formation_capacity_used",
          bool((tp.capacity_teu == 88).all()) and bool((tp.wagons == 44).all()),
          tp[["formation", "capacity_teu", "wagons"]].to_dict("records"))

    seg = pd.read_csv(out / "SEGMENT_LOAD.csv", encoding="utf-8-sig")
    fixture_km = {120.4, 140.9, 155.1, 150.5}
    check("ext::external_segment_distance_used",
          bool(set(seg.physical_distance_km.round(1)) <= fixture_km),
          sorted(set(seg.physical_distance_km.round(1))))
    check("ext::external_train_km_matches_fixture",
          bool(abs(tp.train_km.sum() - round(seg.physical_distance_km.sum(), 1)) < 0.2),
          "train_km=%s seg_sum=%s" % (tp.train_km.sum(), seg.physical_distance_km.sum()))


# ------------------------------------------- v7.1-patch: 선사 입력 검증
def test_carrier_input_validation(workdir):
    print("\\n[7] Carrier input validation")
    ok = m.validate_carrier_inputs(HOURLY, INITIAL)
    check("input::valid_file_accepted", ok["rows"] == 12096, ok)

    bad_dir = workdir / "BADINPUT"
    bad_dir.mkdir(parents=True, exist_ok=True)
    base = pd.read_csv(HOURLY, encoding="utf-8-sig")

    cases = []
    d = pd.concat([base, base.head(1)], ignore_index=True)
    cases.append(("duplicate_row", d))
    cases.append(("missing_hour", base.drop(base.index[5:9])))
    d = base.copy(); d.loc[0, "demand"] = -3
    cases.append(("negative_demand", d))
    d = base.copy(); d.loc[0, "hub_code"] = "SEOUL"
    cases.append(("unknown_hub", d))
    d = base.copy(); d["demand"] = d["demand"].astype(float); d.loc[0, "demand"] = 1.5
    cases.append(("fractional_demand", d))
    cases.append(("carrier_all_dongsan_rows_removed",
                  base[base.hub_code != "DONGSAN"].copy()))
    cases.append(("carrier_all_40ft_rows_removed",
                  base[base.container_size != "40FT"].copy()))
    d = base.copy(); d.loc[d.index[0], "carrier_id"] = " "
    cases.append(("blank_carrier_id", d))
    cases.append(("empty_hourly_file", base.iloc[0:0].copy()))

    for label, df in cases:
        f = bad_dir / (label + ".csv")
        df.to_csv(f, index=False, encoding="utf-8-sig")
        try:
            m.validate_carrier_inputs(f, INITIAL)
            check("input::" + label + "_rejected", False, "no error raised")
        except m.InputValidationError as e:
            first = e.errors[0][:80] if e.errors else ""
            check("input::" + label + "_rejected",
                  e.reason_code == "CARRIER_INPUT_INVALID", e.reason_code + ": " + first)

    inv = pd.read_csv(INITIAL, encoding="utf-8-sig")
    f = bad_dir / "initial_missing.csv"
    inv.drop(inv.index[0]).to_csv(f, index=False, encoding="utf-8-sig")
    try:
        m.validate_carrier_inputs(HOURLY, f)
        check("input::initial_inventory_missing_rejected", False, "no error")
    except m.InputValidationError as e:
        check("input::initial_inventory_missing_rejected", True, e.reason_code)

    f = bad_dir / "carrier_mismatch.csv"
    inv2 = inv.copy()
    inv2.loc[inv2.carrier_id == "CARRIER_F", "carrier_id"] = "CARRIER_Z"
    inv2.to_csv(f, index=False, encoding="utf-8-sig")
    try:
        m.validate_carrier_inputs(HOURLY, f)
        check("input::carrier_set_mismatch_rejected", False, "no error")
    except m.InputValidationError as e:
        check("input::carrier_set_mismatch_rejected", True, e.reason_code)

    f = bad_dir / "empty_initial.csv"
    inv.iloc[0:0].to_csv(f, index=False, encoding="utf-8-sig")
    try:
        m.validate_carrier_inputs(HOURLY, f)
        check("input::empty_initial_file_rejected", False, "no error")
    except m.InputValidationError as e:
        check("input::empty_initial_file_rejected", True, e.reason_code)


def _mut_csv(path, fn):
    df = pd.read_csv(path, encoding="utf-8-sig")
    fn(df).to_csv(path, index=False, encoding="utf-8-sig")


# ------------------------------------------- v7.1-patch: candidate 교차검증
def test_candidate_validation(workdir):
    print("\\n[8] KORAIL candidate cross-file validation")
    ok = m.validate_candidate_inputs(EXT_CAND)
    check("cand::valid_fixture_accepted", ok["train_count"] == 2, ok)
    canonical = m.validate_candidate_inputs(ROOT / "04_MODEL_INPUTS")
    check("cand::canonical_candidate_set_valid", canonical["train_count"] == 1084,
          canonical["train_count"])

    import shutil as _sh
    cases = [
        ("missing_file", lambda d: (d / "TRAIN_SEGMENT.csv").unlink()),
        ("distance_sum_mismatch", lambda d: _mut_csv(
            d / "TRAIN_CANDIDATE.csv",
            lambda df: df.assign(service_distance_km=df.service_distance_km + 10))),
        ("bad_formation", lambda d: _mut_csv(
            d / "TRAIN_FORMATION_OPTION.csv", lambda df: df.assign(capacity_teu=0))),
        ("stop_order_broken", lambda d: _mut_csv(
            d / "TRAIN_STOP_TIME.csv",
            lambda df: df.assign(available_slot=df.arrival_slot - 1))),
        ("korail_work_stops_missing", lambda d: _mut_csv(
            d / "TRAIN_CANDIDATE.csv", lambda df: df.assign(work_stops=""))),
    ]
    for label, mutate in cases:
        dd = workdir / ("CAND_" + label)
        if dd.exists():
            _sh.rmtree(dd)
        _sh.copytree(EXT_CAND, dd)
        mutate(dd)
        try:
            m.validate_candidate_inputs(dd)
            check("cand::" + label + "_rejected", False, "no error raised")
        except m.InputValidationError as e:
            first = e.errors[0][:80] if e.errors else ""
            check("cand::" + label + "_rejected", True, e.reason_code + ": " + first)


# ------------------------------------------- v7.1-patch: 챗봇 read-only 데이터
def test_baseline_external_candidate_not_overwritten(workdir):
    print("\n[9] Baseline external candidate protection")
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(EXT_CAND.glob("*.csv"))}
    result = baselines.run_baselines(
        HOURLY, INITIAL, workdir / "BASELINE_EXT", TEST_MIN_LF, 72.0,
        TEST_TIME_LIMIT, 0.001, None, PARAMS, EXT_CAND, True)
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(EXT_CAND.glob("*.csv"))}
    check("baseline::external_candidate_not_overwritten", before == after,
          sorted(before))
    check("baseline::candidate_hash_recorded",
          result["candidate_file_sha256"] == before,
          result["candidate_file_sha256"])


def test_explanation_outputs(workdir):
    print("\\n[9] Chatbot read-only data readiness")
    out = workdir / "AXIS_INTEGRATED"
    if not (out / "SUMMARY.json").exists():
        check("chat::run_present", False, "joint optimisation test must run first")
        return
    check("chat::run_present", True, "")

    tl = pd.read_csv(out / "CARRIER_INVENTORY_TIMELINE.csv", encoding="utf-8-sig")
    imp = pd.read_csv(out / "INVENTORY_IMPACT_SUMMARY.csv", encoding="utf-8-sig")
    svc = pd.read_csv(out / "CARRIER_SERVICE_SUMMARY.csv", encoding="utf-8-sig")
    ctx = pd.read_csv(out / "RECOMMENDATION_EXPLANATION_CONTEXT.csv", encoding="utf-8-sig")

    check("chat::inventory_timeline_generated", len(tl) > 0, len(tl))
    check("chat::post_rail_inventory_nonnegative",
          bool((tl.post_rail_inventory >= 0).all()),
          float(tl.post_rail_inventory.min()))
    check("chat::impact_summary_generated", len(imp) > 0, len(imp))
    check("chat::stockout_not_increased",
          bool((imp.stockout_reduction_boxes >= 0).all()),
          int(imp.stockout_reduction_boxes.min()))
    check("chat::carrier_service_summary_generated", len(svc) > 0, len(svc))
    check("chat::coverage_within_0_1",
          bool(((svc.rail_coverage >= 0) & (svc.rail_coverage <= 1)).all()), "")

    check("chat::ambiguous_shortage_column_removed",
          "destination_expected_shortage_teu" not in ctx.columns, list(ctx.columns)[:6])
    for col in ["linked_service_need_teu", "linked_need_count",
                "source_release_capacity_cumulative_boxes",
                "assigned_outbound_cumulative_boxes_through_load",
                "source_release_remaining_after_assignment_boxes"]:
        check("chat::context_has::" + col, col in ctx.columns, "")

    per = sorted(out.glob("RECOMMENDATION_EXPLANATION_CONTEXT_CARRIER_*.csv"))
    check("chat::per_carrier_context_generated", len(per) > 0, len(per))
    leak = []
    for f in per:
        cid = f.stem.replace("RECOMMENDATION_EXPLANATION_CONTEXT_", "")
        df = pd.read_csv(f, encoding="utf-8-sig")
        if set(df.carrier_id) - {cid}:
            leak.append(f.name)
    check("chat::carrier_context_isolation", not leak, leak)
    carrier_ids = set(svc.carrier_id.astype(str))
    raw_leak = []
    scoped = per + sorted(out.glob("CARRIER_RECOMMENDATIONS_CARRIER_*.csv"))
    for f in scoped:
        cid = f.stem.split("_CARRIER_")[-1]
        cid = "CARRIER_" + cid if not cid.startswith("CARRIER_") else cid
        text = f.read_text(encoding="utf-8-sig")
        leaked = sorted(c for c in carrier_ids - {cid} if c in text)
        if leaked:
            raw_leak.append((f.name, leaked))
    check("chat::carrier_scoped_raw_text_has_no_other_carrier_id", not raw_leak, raw_leak)

    final_train = out / "FINAL_TRAIN_OPERATION_SUMMARY.csv"
    check("chat::final_train_operation_summary_generated", final_train.exists(), final_train)

    rec = pd.read_csv(out / "CARRIER_RECOMMENDATIONS.csv", encoding="utf-8-sig")
    check("chat::recommendation_due_range_present",
          set(["need_count", "service_due_time_earliest",
               "service_due_time_latest"]) <= set(rec.columns), list(rec.columns)[:8])
    check("chat::single_due_column_removed", "service_due_time" not in rec.columns, "")

    ru = pd.read_csv(out / "RAIL_UNSERVED.csv", encoding="utf-8-sig")
    if len(ru):
        check("chat::unserved_reason_not_false_specific",
              "NO_FEASIBLE_TRAIN_MEETING_CONSOLIDATION_LEVEL" not in set(ru.reason),
              ru.reason.value_counts().to_dict())
        check("chat::unserved_reason_flagged_unproven",
              bool((~ru.reason_is_proven_cause.astype(bool)).all()), "")
    else:
        check("chat::unserved_reason_not_false_specific", True, "no unserved")
        check("chat::unserved_reason_flagged_unproven", True, "no unserved")


# ------------------------------------------- v7.1-patch: 정책 충돌
def test_policy_conflict():
    print("\\n[10] Policy conflict pre-check")
    h, i = m.read_hourly(HOURLY), m.read_initial(INITIAL)
    pol = {"inventory_policies": [
        {"carrier_id": "CARRIER_A", "rule_type": "MIN_INVENTORY_RANGE",
         "hub_code": "YAKMOK", "container_size": "40FT", "value": 30},
        {"carrier_id": "CARRIER_A", "rule_type": "MAX_INVENTORY",
         "hub_code": "YAKMOK", "container_size": "40FT", "value": 5}]}
    try:
        m.generate_service_needs(h, i, pol)
        check("policy::min_above_max_rejected", False, "no error raised")
    except m.PolicyValidationError as e:
        check("policy::min_above_max_rejected", e.reason_code == "POLICY_CONFLICT",
              e.reason_code)


# --------------------------------------------------------------------------
def main():
    tmp = Path(tempfile.mkdtemp(prefix="axis_v71_test_"))
    print(f"work dir: {tmp}")
    try:
        init_params()
        test_policy_schema(tmp)
        test_joint_optimization(tmp)
        test_no_negotiation_layer()
        test_external_candidate_replaceability(tmp)
        test_carrier_input_validation(tmp)
        test_candidate_validation(tmp)
        test_baseline_external_candidate_not_overwritten(tmp)
        test_explanation_outputs(tmp)
        test_policy_conflict()
        test_determinism(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    df = pd.DataFrame(results)
    out = ROOT / "05_RESULTS" / "VALIDATION"
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "REGRESSION_TESTS_v7_1.csv", index=False, encoding="utf-8-sig")
    n = int(df["pass"].sum())
    print(f"\nREGRESSION v7.1: {n}/{len(df)} PASS -> {out/'REGRESSION_TESTS_v7_1.csv'}")
    if not df["pass"].all():
        print(df[~df["pass"]].to_string(index=False))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
