"""
AXIS v7.1 전체 검증  (지시서 18.4 / 23 완료조건)

    python 02_CODE/verify_v7_1.py .

지시서 18.4: 저장된 CSV 의 PASS 문자열을 읽는 방식만 쓰지 않는다.
이 스크립트는

  A. 데이터 생성기를 실제로 다시 실행하고 배포본과 바이트 단위로 비교한다.
  B. Joint MILP 를 실제로 다시 실행하고 불변식을 직접 검사한다.
  C. 회귀 테스트 스위트를 실제로 다시 실행한다.
  D. 배포된 산출물의 내부 일관성을 검사한다.
  E. 패키지 구조와 협상 계층 제거 여부를 검사한다.

--quick 을 주면 B 를 빠른 시나리오(48h)로 수행한다. 기본은 정본 default(72h).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

checks = []


def add(name, ok, detail=""):
    checks.append({"check": name, "pass": bool(ok), "detail": str(detail)[:400]})


def _read(p):
    p = Path(p)
    if not p.exists() or p.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(p, encoding="utf-8-sig")


def _json(p):
    p = Path(p)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def verify(root: Path, quick: bool, approximate_quick: bool = False):
    CODE = root / "02_CODE"
    DATA = root / "03_INPUT_DATA"
    RES = root / "05_RESULTS"
    sys.path.insert(0, str(CODE))
    import axis_milp_v7_1 as m

    HOURLY = DATA / "AXIS_carrier_hourly_plan_v7_1.csv"
    INITIAL = DATA / "carrier_initial_inventory.csv"
    PARAMS = DATA / "AXIS_rail_OD_parameters_v1.xlsx"
    MASTER = DATA / "AXIS_hourly_empty_demand_supply_v8_6hubs.xlsx"
    SNAP = DATA / "public_snapshot_2026-08-09.csv"

    tmp = Path(tempfile.mkdtemp(prefix="axis_v71_verify_"))
    try:
        # ============================================================ A
        # 데이터 생성기를 실제로 다시 실행한다
        gen_out = tmp / "regen"
        p = subprocess.run([sys.executable, str(CODE / "axis_data_gen_v7_1.py"),
                            "--master", str(MASTER), "--snapshot", str(SNAP),
                            "--outdir", str(gen_out)],
                           capture_output=True, text=True)
        add("A::data_generator_reruns", p.returncode == 0, p.stdout.strip()[-120:] or p.stderr[-200:])
        regen_checks = _read(gen_out / "AGGREGATE_PRESERVATION_CHECK.csv")
        add("A::aggregate_preservation_recomputed",
            (not regen_checks.empty) and bool(regen_checks["pass"].all()),
            f"{int(regen_checks['pass'].sum())}/{len(regen_checks)}" if not regen_checks.empty else "missing")
        for key in ["aggregate_demand_preservation", "aggregate_supply_total_preservation",
                    "aggregate_initial_inventory_preservation", "six_hubs_distinct_prior",
                    "demand_supply_structural_asymmetry", "temporal_continuity_block_share",
                    "no_structural_carrier_exclusion", "realized_share_tracks_design"]:
            row = regen_checks[regen_checks.check == key] if not regen_checks.empty else pd.DataFrame()
            add(f"A::{key}", (not row.empty) and bool(row.iloc[0]["pass"]),
                row.iloc[0]["detail"] if not row.empty else "missing")
        if (gen_out / "AXIS_carrier_hourly_plan_v7_1.csv").exists() and HOURLY.exists():
            h1 = hashlib.sha256((gen_out / "AXIS_carrier_hourly_plan_v7_1.csv").read_bytes()).hexdigest()
            h2 = hashlib.sha256(HOURLY.read_bytes()).hexdigest()
            add("A::regenerated_data_byte_identical", h1 == h2, f"{h1[:24]} vs {h2[:24]}")
        else:
            add("A::regenerated_data_byte_identical", False, "file missing")

        # ============================================================ B
        # Joint MILP 를 실제로 다시 실행한다
        earl = 48.0 if (quick or approximate_quick) else 72.0
        strict = not approximate_quick
        run_root = tmp / "run"
        try:
            summ = m.run(HOURLY, INITIAL, run_root, 0.5, None, None,
                         "AXIS_INTEGRATED", 900, 0.001, False, earl, None, PARAMS,
                         None, None, None, root / "04_MODEL_INPUTS", strict, True)
            add("B::joint_milp_reruns", True,
                f"max_earliness={earl}, strict_lexicographic={strict}")
        except Exception as exc:  # noqa: BLE001
            add("B::joint_milp_reruns", False, f"{type(exc).__name__}: {exc}")
            summ = None

        if summ:
            out = run_root / "AXIS_INTEGRATED"
            det = _read(out / "CARRIER_RECOMMENDATION_DETAIL.csv")
            rec = _read(out / "CARRIER_RECOMMENDATIONS.csv")
            alloc = _read(out / "CARRIER_ALLOCATION.csv")
            seg = _read(out / "SEGMENT_LOAD.csv")
            trains = _read(out / "KORAIL_TRAIN_PLAN.csv")
            ctx = _read(out / "RECOMMENDATION_EXPLANATION_CONTEXT.csv")
            sa = _read(out / "SOLVER_AUDIT.csv")

            add("B::all_stages_proven_optimal", bool(summ.get("all_stages_proven_optimal")), "")
            add("B::solver_all_status_zero",
                (not sa.empty) and bool((sa.status == 0).all()),
                sa[["stage", "status"]].to_dict("records") if not sa.empty else "missing")
            add("B::solver_core_stages_zero_gap",
                (not sa.empty) and bool(
                    (sa[sa.stage.isin(["Z1_unserved_teu", "Z2_train_count"])]
                     .mip_gap_requested == 0).all()), "")
            add("B::solver_has_tiebreak",
                (not sa.empty) and bool(sa.stage.str.contains("tiebreak", case=False).any()), "")

            add("B::multi_carrier_consolidation",
                (not trains.empty) and bool((trains.participating_carrier_count > 1).any()),
                trains.participating_carrier_count.tolist() if not trains.empty else "no trains")
            add("B::segment_capacity",
                seg.empty or bool((seg.loaded_teu <= seg.capacity_teu).all()), "")
            add("B::min_consolidation_level",
                trains.empty or bool((trains.distance_weighted_load_factor + 1e-9 >= 0.5).all()),
                trains[["train_id", "distance_weighted_load_factor"]].to_dict("records")
                if not trains.empty else "")
            add("B::formation_selected", trains.empty or bool(trains.formation.notna().all()), "")
            add("B::integer_assignment", det.empty or bool((det.quantity_boxes % 1 == 0).all()), "")
            add("B::due_time_respected",
                det.empty or bool((pd.to_datetime(det.available_time)
                                   <= pd.to_datetime(det.service_due_time)).all()), "")
            add("B::earliness_within_cap",
                det.empty or bool((det.earliness_hours <= earl + 1e-9).all()),
                float(det.earliness_hours.max()) if not det.empty else "")
            add("B::no_departure_slot_conflict",
                trains.empty or bool(
                    (trains.groupby(["origin_terminal", "origin_departure"]).size() <= 1).all()), "")

            inv = _read(INITIAL)
            known = set(zip(inv.carrier_id, inv.hub_code, inv.container_size))
            bad = [] if det.empty else [r for r in det.itertuples()
                                        if (r.carrier_id, r.origin_hub, r.container_size) not in known]
            add("B::carrier_ownership_preserved", not bad, f"{len(bad)} violations")

            base = _read(run_root / "_RUN_MODEL_INPUTS" / "BASELINE_AND_SOURCE_CAPACITY.csv")
            viol = []
            if not det.empty and not base.empty:
                base["timestamp"] = pd.to_datetime(base.timestamp)
                d2 = det.copy()
                d2["load_start_time"] = pd.to_datetime(d2.load_start_time)
                for (c, o, k), g in d2.groupby(["carrier_id", "origin_hub", "container_size"]):
                    bg = base[(base.carrier_id == c) & (base.hub_code == o)
                              & (base.container_size == k)]
                    for br in bg.itertuples():
                        cum = int(g.loc[g.load_start_time <= br.timestamp, "quantity_boxes"].sum())
                        if cum > br.source_release_capacity_cumulative:
                            viol.append((c, o, k, str(br.timestamp)))
                            break
            add("B::source_release_capacity", not viol, viol[:3])

            add("B::carrier_view_equals_korail_view",
                bool(summ.get("carrier_korail_view_consistent")),
                f"rec={summ.get('carrier_recommendation_teu')} "
                f"alloc={summ.get('korail_allocation_teu')} served={summ.get('rail_served_teu')}")
            add("B::explanation_context_generated", len(ctx) == len(rec), f"{len(ctx)}/{len(rec)}")
            add("B::candidate_source_recorded",
                trains.empty or bool((trains.candidate_source == "PROTOTYPE_SYNTHETIC").all()),
                trains.candidate_source.unique().tolist() if not trains.empty else "")
            add("B::synthetic_flags_in_summary",
                summ.get("carrier_data_source") == "SYNTHETIC_CARRIER_LEVEL_DATA"
                and summ.get("candidate_timetable_source") == "PROTOTYPE_SYNTHETIC"
                and summ.get("candidate_input_sources") == ["PROTOTYPE_SYNTHETIC"]
                and summ.get("selected_train_sources") == ["PROTOTYPE_SYNTHETIC"], "")
            add("B::return_wagon_flag",
                summ.get("return_wagon_movement_included") is False, "")

            dv = _read(out / "DISTANCE_VALIDATION.csv")
            add("B::distance_validation_all_pass",
                (not dv.empty) and bool(dv["pass"].all()),
                dv[~dv["pass"]].to_dict("records") if not dv.empty else "missing")
            prov = _read(out / "RAIL_PARAMETER_PROVENANCE.csv")
            add("B::parameter_provenance_recorded",
                (not prov.empty) and bool((prov.loaded_from == "XLSX").any()),
                prov.loaded_from.value_counts().to_dict() if not prov.empty else "missing")

            oa = _read(out / "OPERATIONAL_CONSTRAINT_AUDIT.csv")
            add("B::no_data_constraints_recorded",
                (not oa.empty) and bool((oa.status == "NOT_APPLIED_NO_DATA").any()), "")
            add("B::conflict_constraints_applied",
                (not oa.empty) and bool(oa.type.isin(
                    ["DEPARTURE_SLOT_CONFLICT", "SHARED_TRUNK_CONFLICT"]).any()), "")

        # ============================================================ C
        # 회귀 테스트를 실제로 다시 실행한다
        p = subprocess.run([sys.executable, str(CODE / "test_v7_1.py")],
                           capture_output=True, text=True)
        tail = (p.stdout or "").strip().split("\n")[-1] if p.stdout else p.stderr[-200:]
        add("C::regression_suite_reruns_and_passes", p.returncode == 0, tail)

        # ============================================================ D
        # 배포된 산출물의 내부 일관성
        main = RES / "AXIS_INTEGRATED"
        s = _json(main / "SUMMARY.json")
        add("D::shipped_axis_integrated_exists", s is not None, str(main))
        if s:
            add("D::shipped_view_consistency", bool(s.get("carrier_korail_view_consistent")), "")
            add("D::shipped_default_earliness_72",
                s.get("default_max_earliness_hours") == 72.0,
                s.get("default_max_earliness_hours"))
            add("D::shipped_default_min_load_factor_0_5",
                s.get("min_load_factor") == 0.5, s.get("min_load_factor"))
            rec = _read(main / "CARRIER_RECOMMENDATIONS.csv")
            alloc = _read(main / "CARRIER_ALLOCATION.csv")
            needs = _read(main / "SERVICE_NEED_RESULT.csv")
            trains = _read(main / "KORAIL_TRAIN_PLAN.csv")
            add("D::shipped_recommendation_alloc_match",
                (not rec.empty) and int(rec.quantity_teu.sum()) == int(alloc.teu.sum())
                == int(needs.rail_served_teu.sum()) == int(trains.total_assigned_teu.sum()),
                f"{int(rec.quantity_teu.sum()) if not rec.empty else 0}"
                f"/{int(alloc.teu.sum()) if not alloc.empty else 0}")
            for f in ["CARRIER_RECOMMENDATIONS.csv", "CARRIER_RECOMMENDATION_DETAIL.csv",
                      "RECOMMENDATION_EXPLANATION_CONTEXT.csv", "KORAIL_TRAIN_PLAN.csv",
                      "CARRIER_ALLOCATION.csv", "STOP_WORK_PLAN.csv", "SEGMENT_LOAD.csv",
                      "SERVICE_NEED_RESULT.csv", "SOLVER_AUDIT.csv", "ACTIVE_POLICY.json",
                      "FINAL_TRAIN_OPERATION_SUMMARY.csv"]:
                add(f"D::output::{f}", (main / f).exists(), "")

        cmp_df = _read(RES / "BASELINES" / "BASELINE_COMPARISON.csv")
        add("D::baseline_comparison_exists", not cmp_df.empty, "")
        if not cmp_df.empty:
            for sc in ["A_NO_REPOSITIONING", "B_CARRIER_SEPARATE", "C_AXIS_INTEGRATED"]:
                add(f"D::baseline::{sc}", sc in set(cmp_df.scenario), sorted(set(cmp_df.scenario)))
        for f, need in [("EARLINESS_SENSITIVITY.csv", 5), ("LOAD_FACTOR_SENSITIVITY.csv", 3),
                        ("HANDLING_TIME_SENSITIVITY.csv", 3)]:
            d = _read(RES / "SENSITIVITY" / f)
            add(f"D::sensitivity::{f}", len(d) >= need, f"{len(d)} rows (need {need})")
        lf = _read(RES / "SENSITIVITY" / "LOAD_FACTOR_SENSITIVITY.csv")
        add("D::sensitivity_lf_covers_50_60_70",
            (not lf.empty) and {0.5, 0.6, 0.7}.issubset(set(lf.min_load_factor)),
            sorted(set(lf.min_load_factor)) if not lf.empty else "")

        # ============================================================ E
        # 구조 / 협상 계층 제거
        src = (CODE / "axis_milp_v7_1.py").read_text(encoding="utf-8")
        code_only = src[src.find('"""', src.find('"""') + 3) + 3:]
        code_only = "\n".join(l for l in code_only.split("\n") if not l.strip().startswith("#"))
        banned = ["ACCEPT_SERVICE", "ACCEPT_EXACT_PLAN", "DECLINE_RAIL_SERVICE",
                  "MODIFY_SERVICE", "REJECT_OPTION", "proposal_version",
                  "negotiation_round", "accepted_by_need", "declined_by_need"]
        found = [b for b in banned if b in code_only]
        add("E::no_negotiation_in_core", not found, found)
        add("E::run_is_one_shot",
            "run_mode" not in m.run.__code__.co_varnames
            and "actions_path" not in m.run.__code__.co_varnames, "")
        add("E::legacy_folder_separated",
            (root / "future_extensions" / "negotiation_legacy").exists(),
            "future_extensions/negotiation_legacy")
        for d in ["01_DOCS", "02_CODE", "03_INPUT_DATA", "04_MODEL_INPUTS",
                  "05_RESULTS", "06_POLICY_EXAMPLES"]:
            add(f"E::package::{d}", (root / d).exists(), "")
        for f in ["run_data_generation.bat", "run_axis_integrated.bat", "run_baselines.bat",
                  "run_sensitivity.bat", "run_tests.bat", "run_verification.bat",
                  "run_all.bat", "00_START_HERE.md"]:
            add(f"E::script::{f}", (root / f).exists(), "")
        BADC = set(range(0, 9)) | {11, 12} | set(range(14, 32))
        dirty = []
        for f in sorted(root.glob("*.bat")):
            t = f.read_bytes().decode("utf-8", errors="replace")
            if any(ord(c) in BADC for c in t):
                dirty.append(f.name)
        add("E::bat_files_have_no_control_chars", not dirty, dirty)

        # ============================================================ F
        # v7.1-patch: 실제 데이터 교체 가능성 (지시서 26)
        EXT = DATA / "TEST_KORAIL_CANDIDATES"
        if not EXT.exists():
            add("F::external_candidate_fixture_present", False, str(EXT))
        else:
            add("F::external_candidate_fixture_present", True, "")
            before = {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
                      for f in sorted(EXT.iterdir())}
            ext_root = tmp / "ext"
            try:
                esum = m.run(HOURLY, INITIAL, ext_root, 0.5, None, None,
                             "AXIS_INTEGRATED", 900, 0.001, False, 72.0, None,
                             PARAMS, None, None, None, EXT, True, True)
                ok_run = True
            except Exception as exc:  # noqa: BLE001
                add("F::external_candidate_run", False, f"{type(exc).__name__}: {exc}")
                ok_run = False
                esum = None
            if ok_run:
                add("F::external_candidate_run", True, "")
                after = {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
                         for f in sorted(EXT.iterdir())}
                add("F::external_candidate_not_overwritten", before == after,
                    f"{sorted(before)} vs {sorted(after)}")
                add("F::external_candidate_hash_unchanged",
                    all(before.get(k) == v for k, v in after.items()), "")
                add("F::synthetic_generator_not_called",
                    not (EXT / "SERVICE_NEED.csv").exists(), "")
                add("F::external_candidate_source_preserved",
                    esum["candidate_timetable_source"] == "KORAIL_FEASIBLE_PATH",
                    esum["candidate_timetable_source"])
                add("F::external_candidate_source_lists",
                    esum["candidate_input_sources"] == ["KORAIL_FEASIBLE_PATH"]
                    and esum["selected_train_sources"] == ["KORAIL_FEASIBLE_PATH"],
                    (esum["candidate_input_sources"], esum["selected_train_sources"]))
                etp = _read(ext_root / "AXIS_INTEGRATED" / "KORAIL_TRAIN_PLAN.csv")
                eseg = _read(ext_root / "AXIS_INTEGRATED" / "SEGMENT_LOAD.csv")
                add("F::external_formation_capacity_used",
                    (not etp.empty) and bool((etp.capacity_teu == 88).all())
                    and bool((etp.wagons == 44).all()),
                    etp[["formation", "capacity_teu", "wagons"]].to_dict("records")
                    if not etp.empty else "no trains")
                add("F::external_segment_distance_used",
                    (not eseg.empty) and set(eseg.physical_distance_km.round(1))
                    <= {120.4, 140.9, 155.1, 150.5},
                    sorted(set(eseg.physical_distance_km.round(1)))
                    if not eseg.empty else "no segments")
                add("F::external_candidate_summary_source_correct",
                    esum["candidate_timetable_source"] != "PROTOTYPE_SYNTHETIC", "")
                minute_rows = (etp[etp.actual_origin_departure.astype(str).str.endswith("06:35")]
                               if not etp.empty else pd.DataFrame())
                add("F::external_actual_time_preserved",
                    (not minute_rows.empty)
                    and bool(minute_rows.model_origin_departure_time.astype(str)
                             .str.endswith("07:00").all()),
                    minute_rows[["actual_origin_departure", "model_origin_departure_slot",
                                 "model_origin_departure_time"]].to_dict("records")
                    if not minute_rows.empty else "no selected 06:35 train")

        # 입력 검증 계층
        try:
            m.validate_carrier_inputs(HOURLY, INITIAL)
            add("F::carrier_input_validation_accepts_valid", True, "")
        except Exception as exc:  # noqa: BLE001
            add("F::carrier_input_validation_accepts_valid", False, str(exc)[:150])
        bad = tmp / "bad.csv"
        _bh = _read(HOURLY)
        if not _bh.empty:
            _bh.loc[0, "demand"] = -1
            _bh.to_csv(bad, index=False, encoding="utf-8-sig")
            try:
                m.validate_carrier_inputs(bad, INITIAL)
                add("F::carrier_negative_demand_rejected", False, "no error")
            except m.InputValidationError as exc:
                add("F::carrier_negative_demand_rejected",
                    exc.reason_code == "CARRIER_INPUT_INVALID", exc.reason_code)
        if EXT.exists():
            try:
                m.validate_candidate_inputs(EXT)
                add("F::candidate_validation_accepts_valid", True, "")
            except Exception as exc:  # noqa: BLE001
                add("F::candidate_validation_accepts_valid", False, str(exc)[:150])

        # 설명 데이터 (지시서 26 Output explanation)
        main_out = RES / "AXIS_INTEGRATED"
        tl = _read(main_out / "CARRIER_INVENTORY_TIMELINE.csv")
        imp = _read(main_out / "INVENTORY_IMPACT_SUMMARY.csv")
        svc = _read(main_out / "CARRIER_SERVICE_SUMMARY.csv")
        ctx = _read(main_out / "RECOMMENDATION_EXPLANATION_CONTEXT.csv")
        rec2 = _read(main_out / "CARRIER_RECOMMENDATIONS.csv")
        ru = _read(main_out / "RAIL_UNSERVED.csv")
        add("F::inventory_timeline_generated", len(tl) > 0, len(tl))
        add("F::post_rail_inventory_nonnegative",
            tl.empty or bool((tl.post_rail_inventory >= 0).all()),
            float(tl.post_rail_inventory.min()) if not tl.empty else "")
        add("F::inventory_impact_summary_generated", len(imp) > 0, len(imp))
        add("F::carrier_service_summary_generated", len(svc) > 0, len(svc))
        add("F::recommendation_due_range_valid",
            (not rec2.empty) and {"need_count", "service_due_time_earliest",
                                  "service_due_time_latest"} <= set(rec2.columns),
            list(rec2.columns)[:8] if not rec2.empty else "")
        add("F::ambiguous_shortage_column_removed",
            (not ctx.empty) and "destination_expected_shortage_teu" not in ctx.columns, "")
        add("F::unserved_reason_not_false_specific",
            ru.empty or "NO_FEASIBLE_TRAIN_MEETING_CONSOLIDATION_LEVEL" not in set(ru.reason),
            ru.reason.value_counts().to_dict() if not ru.empty else "no unserved")
        leak = []
        for f in sorted(main_out.glob("RECOMMENDATION_EXPLANATION_CONTEXT_CARRIER_*.csv")):
            cid = f.stem.replace("RECOMMENDATION_EXPLANATION_CONTEXT_", "")
            df = _read(f)
            if not df.empty and set(df.carrier_id) - {cid}:
                leak.append(f.name)
        add("F::carrier_context_isolation", not leak, leak)

        # Solver strict (지시서 26 Solver)
        if s:
            add("F::canonical_strict_lexicographic", bool(s.get("strict_lexicographic")),
                s.get("solver_exactness"))
        sa2 = _read(main_out / "SOLVER_AUDIT.csv")
        if not sa2.empty and "mip_gap_requested" in sa2.columns:
            z7 = sa2[sa2.stage.str.contains("tiebreak", case=False)]
            add("F::z7_gap_zero",
                (not z7.empty) and bool((z7.mip_gap_requested == 0).all()),
                z7[["stage", "mip_gap_requested"]].to_dict("records")
                if not z7.empty else "missing")
            add("F::all_stages_gap_zero_in_canonical",
                bool((sa2.mip_gap_requested == 0).all()),
                sorted(set(sa2.mip_gap_requested)))

        # 패키지 정리 (지시서 24)
        add("F::policy_examples_renamed", (root / "06_POLICY_EXAMPLES").exists(), "")
        add("F::legacy_docs_moved",
            (root / "08_AUDIT" / "legacy_docs").exists()
            and not (root / "01_DOCS" / "MILP_FORMULATION_v7.md").exists(), "")
        for d in ["CARRIER_INPUT_SCHEMA.md", "KORAIL_CANDIDATE_SCHEMA.md",
                  "TIME_SLOT_CONVENTION.md", "CHATBOT_READ_ONLY_DATA_GUIDE.md"]:
            add(f"F::doc::{d}", (root / "01_DOCS" / d).exists(), "")
        for t in ["CARRIER_SUBMISSION_TEMPLATE.csv",
                  "CARRIER_INITIAL_INVENTORY_TEMPLATE.csv"]:
            add(f"F::template::{t}", (DATA / "templates" / t).exists(), "")
        rt = _read(RES / "SENSITIVITY" / "ROLE_TILT_SENSITIVITY.csv")
        add("F::role_tilt_sensitivity_generated", len(rt) >= 3, f"{len(rt)} rows")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    out = pd.DataFrame(checks)
    vdir = root / "05_RESULTS" / "VALIDATION"
    vdir.mkdir(parents=True, exist_ok=True)
    out.to_csv(vdir / "VERIFICATION_CHECKS_v7_1.csv", index=False, encoding="utf-8-sig")
    n = int(out["pass"].sum())
    print(out.to_string(index=False))
    print(f"\nVERIFICATION v7.1: {n}/{len(out)} PASS")
    if not out["pass"].all():
        print("\nFAILED:")
        print(out[~out["pass"]].to_string(index=False))
        return 1
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--quick", action="store_true",
                    help="re-run the joint MILP at 48h instead of the 72h default")
    ap.add_argument("--approximate-quick", action="store_true",
                    help="48h diagnostic run allowing nonzero gaps in Z3-Z6")
    a = ap.parse_args()
    sys.exit(verify(Path(a.root).resolve(), a.quick, a.approximate_quick))
