"""
AXIS v7.1 — Baseline Comparison

동일한 service need / candidate timetable / formation / minimum load factor /
handling time / operating assumption 아래에서 세 시나리오를 비교한다.

  A. No Repositioning   철도 재배치 없음. 부족이 얼마나 발생하는가.
  B. Carrier Separate   각 선사가 독립적으로 철도서비스를 구성. 열차 공유 없음.
  C. AXIS Integrated    전체 선사 물량을 하나의 KORAIL capacity 에 공동 배정.

주의 (지시서 Phase 3):
  B 가 0편이 나오도록 모델을 조정하지 않는다. 결과는 있는 그대로 제시한다.

B 구현 방식:
  동일한 need 집합을 유지한 채 carrier 단위로 MILP 를 따로 풀고 합산한다.
  각 선사가 자기 열차만 쓰므로 열차 공유가 원천적으로 불가능하다.
  후보 시간표·편성옵션·최소적재율은 C 와 완전히 동일하다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import axis_milp_v7_1 as m


def _kpi(summary, train_plan_rows, detail_rows):
    load = [r["distance_weighted_load_factor"] for r in train_plan_rows]
    return {
        "rail_served_teu": summary.get("rail_served_teu", 0),
        "rail_unserved_teu": summary.get("rail_unserved_teu", 0),
        "train_count": summary.get("selected_train_count", 0),
        "train_km": summary.get("train_km", 0.0),
        "wagon_km": summary.get("wagon_km", 0.0),
        "teu_km": summary.get("teu_km", 0.0),
        "avg_distance_weighted_load_factor": round(sum(load) / len(load), 4) if load else 0.0,
        "avg_carriers_per_train": summary.get("avg_carriers_per_train", 0.0),
        "estimated_rail_charge_krw": summary.get("estimated_rail_charge_krw", 0.0),
        "movement_count": len(detail_rows),
    }


def _read_rows(path: Path):
    import csv as _csv
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(_csv.DictReader(f))


def _num(rows, col, cast=float):
    out = []
    for r in rows:
        try:
            out.append(cast(r[col]))
        except (KeyError, ValueError, TypeError):
            pass
    return out


def run_baselines(hourly: Path, initial: Path, root: Path, min_load_factor: float,
                  max_earliness, time_limit: float, mip_gap: float,
                  policies: Path | None = None, params_xlsx: Path | None = None,
                  candidates_dir: Path | None = None, strict: bool = True):
    root.mkdir(parents=True, exist_ok=True)
    m.validate_carrier_inputs(hourly, initial)
    # 세 시나리오가 완전히 동일한 파라미터를 쓰도록 먼저 로드한다.
    m.configure_params(params_xlsx)
    hourly_rows = m.read_hourly(hourly)
    initial_map = m.read_initial(initial)
    timestamps = sorted({r["timestamp"] for r in hourly_rows})
    if candidates_dir is not None:
        input_dir = Path(candidates_dir)
        m.validate_candidate_inputs(input_dir, timestamps)
    else:
        input_dir = root / "MODEL_INPUTS"
        if not m._candidate_inputs_match(input_dir, timestamps[0], len(timestamps)):
            m.generate_candidate_inputs(timestamps[0], len(timestamps), input_dir)
        m.validate_candidate_inputs(input_dir, timestamps)
    candidate_files = [input_dir / n for n in (
        "TRAIN_CANDIDATE.csv", "TRAIN_STOP_TIME.csv", "TRAIN_SEGMENT.csv",
        "TRAIN_FORMATION_OPTION.csv")]
    candidate_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in candidate_files}
    policy_obj = m.read_json(policies, {"inventory_policies": []})
    # 실행 생성물은 후보 디렉터리와 분리한다 (외부 candidate 오염 방지)
    service = m.generate_service_needs(hourly_rows, initial_map, policy_obj,
                                       root / "_RUN_MODEL_INPUTS")
    carriers = service["carriers"]

    # ---------------------------------------------------------------- A
    # 철도 재배치가 없을 때의 부족. generate_service_needs 가 만든 물리 baseline 을 쓴다.
    a_rows = []
    for r in service["baseline_rows"]:
        if int(r["no_rail_unmet"]) > 0:
            a_rows.append(r)
    unmet_teu = sum(int(r["no_rail_unmet"]) * m.TEU[r["container_size"]]
                    for r in service["baseline_rows"])
    m.write_csv(root / "BASELINE_NO_REPOSITIONING.csv", a_rows)
    scen_a = {
        "scenario": "A_NO_REPOSITIONING",
        "rail_served_teu": 0, "rail_unserved_teu": sum(n["teu"] for n in service["needs"]),
        "train_count": 0, "train_km": 0.0, "wagon_km": 0.0, "teu_km": 0.0,
        "avg_distance_weighted_load_factor": 0.0, "avg_carriers_per_train": 0.0,
        "estimated_rail_charge_krw": 0.0, "movement_count": 0,
        "no_rail_unmet_demand_teu": unmet_teu,
        "shortage_event_count": len(a_rows),
    }

    # ---------------------------------------------------------------- B
    per_carrier = []
    for c in carriers:
        out = root / f"B_SEPARATE_{c}"
        meta, lo, up, integ = m.build_milp(service, m.read_candidate_inputs(input_dir),
                                           min_load_factor, {}, max_earliness, {c})
        if not meta["assignments"]:
            # 이 선사만으로는 최소 consolidation 조건을 만족하는 열차가 없다.
            summ = {"rail_served_teu": 0, "rail_unserved_teu":
                    sum(n["teu"] for n in service["needs"] if n["carrier_id"] == c),
                    "selected_train_count": 0, "train_km": 0.0, "wagon_km": 0.0,
                    "teu_km": 0.0, "avg_carriers_per_train": 0.0,
                    "estimated_rail_charge_krw": 0.0}
            per_carrier.append({"carrier_id": c, **_kpi(summ, [], []),
                                "feasible_assignments": 0})
            continue
        result, summary, audit = m.solve_lex(meta, lo, up, integ, time_limit, mip_gap,
                                             strict_lexicographic=strict)
        summ = m.extract(meta, result, summary, out, f"B_SEPARATE_{c}", audit, service=service)
        tp = _read_rows(out / "KORAIL_TRAIN_PLAN.csv")
        tp = [{"distance_weighted_load_factor": float(r["distance_weighted_load_factor"])}
              for r in tp]
        dt = _read_rows(out / "CARRIER_RECOMMENDATION_DETAIL.csv")
        per_carrier.append({"carrier_id": c, **_kpi(summ, tp, dt),
                            "feasible_assignments": len(meta["assignments"])})

    m.write_csv(root / "BASELINE_CARRIER_SEPARATE.csv", per_carrier)
    tot_trains = sum(r["train_count"] for r in per_carrier)
    lf_weighted = ([r["avg_distance_weighted_load_factor"] for r in per_carrier
                    if r["train_count"] > 0])
    scen_b = {
        "scenario": "B_CARRIER_SEPARATE",
        "rail_served_teu": sum(r["rail_served_teu"] for r in per_carrier),
        "rail_unserved_teu": sum(r["rail_unserved_teu"] for r in per_carrier),
        "train_count": tot_trains,
        "train_km": round(sum(r["train_km"] for r in per_carrier), 3),
        "wagon_km": round(sum(r["wagon_km"] for r in per_carrier), 3),
        "teu_km": round(sum(r["teu_km"] for r in per_carrier), 1),
        "avg_distance_weighted_load_factor":
            round(sum(lf_weighted) / len(lf_weighted), 4) if lf_weighted else 0.0,
        "avg_carriers_per_train": 1.0 if tot_trains else 0.0,
        "estimated_rail_charge_krw":
            round(sum(r["estimated_rail_charge_krw"] for r in per_carrier), 2),
        "movement_count": sum(r["movement_count"] for r in per_carrier),
        "carriers_with_rail_service": sum(1 for r in per_carrier if r["train_count"] > 0),
    }

    # ---------------------------------------------------------------- C
    out_c = root / "C_AXIS_INTEGRATED"
    meta, lo, up, integ = m.build_milp(service, m.read_candidate_inputs(input_dir),
                                       min_load_factor, {}, max_earliness, None)
    result, summary, audit = m.solve_lex(meta, lo, up, integ, time_limit, mip_gap,
                                             strict_lexicographic=strict)
    summ_c = m.extract(meta, result, summary, out_c, "C_AXIS_INTEGRATED", audit, service=service)
    tp = [{"distance_weighted_load_factor": float(r["distance_weighted_load_factor"])}
          for r in _read_rows(out_c / "KORAIL_TRAIN_PLAN.csv")]
    dt = _read_rows(out_c / "CARRIER_RECOMMENDATION_DETAIL.csv")
    scen_c = {"scenario": "C_AXIS_INTEGRATED", **_kpi(summ_c, tp, dt)}
    m.write_csv(root / "AXIS_INTEGRATED_RESULT.csv", [scen_c])

    # ---------------------------------------------------------------- 비교
    cols = ["scenario", "rail_served_teu", "rail_unserved_teu", "train_count",
            "train_km", "wagon_km", "teu_km", "avg_distance_weighted_load_factor",
            "avg_carriers_per_train", "estimated_rail_charge_krw", "movement_count"]
    comparison = [{k: s.get(k, "") for k in cols} for s in (scen_a, scen_b, scen_c)]
    m.write_csv(root / "BASELINE_COMPARISON.csv", comparison)

    meta_out = {
        "min_load_factor": min_load_factor,
        "default_max_earliness_hours": max_earliness,
        "total_service_need_teu": sum(n["teu"] for n in service["needs"]),
        "total_service_need_count": len(service["needs"]),
        "carriers": carriers,
        "return_wagon_movement_included": False,
        "candidate_directory": str(input_dir.resolve()),
        "candidate_train_count": len(m.read_candidate_inputs(input_dir)),
        "candidate_file_sha256": candidate_hashes,
        "parameter_file_sha256": (hashlib.sha256(Path(params_xlsx).read_bytes()).hexdigest()
                                  if params_xlsx else None),
        "scenarios": {"A": scen_a, "B": scen_b, "C": scen_c},
        "note": "B is not tuned to produce zero trains; identical timetable, formation "
                "options, minimum load factor and handling assumptions as C.",
    }
    (root / "BASELINE_COMPARISON.json").write_text(
        json.dumps(meta_out, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta_out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hourly", required=True)
    ap.add_argument("--initial", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--min-load-factor", type=float, default=0.5)
    ap.add_argument("--max-earliness", type=float, default=72.0)
    ap.add_argument("--time-limit", type=float, default=900)
    ap.add_argument("--mip-gap", type=float, default=0.001)
    ap.add_argument("--policies", default=None)
    ap.add_argument("--params", default=None)
    ap.add_argument("--candidates", default=None)
    ap.add_argument("--no-strict", action="store_true")
    a = ap.parse_args()
    res = run_baselines(Path(a.hourly), Path(a.initial), Path(a.root), a.min_load_factor,
                        a.max_earliness, a.time_limit, a.mip_gap,
                        Path(a.policies) if a.policies else None,
                        Path(a.params) if a.params else None,
                        Path(a.candidates) if a.candidates else None,
                        not a.no_strict)
    print(json.dumps(res["scenarios"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
