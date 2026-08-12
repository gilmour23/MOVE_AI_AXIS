"""
AXIS v7.1 — Sensitivity Runner

  EARLINESS_SENSITIVITY.csv     0 / 24 / 48 / 72 / unrestricted
  LOAD_FACTOR_SENSITIVITY.csv   0.5 / 0.6 / 0.7
  HANDLING_TIME_SENSITIVITY.csv 0h / 3h / 6h

최적성을 증명하지 못한 조합은 숨기지 않고 status 로 기록한다.
지시서 §6: 특정 숫자가 나오도록 parameter 를 조정하지 않는다.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import axis_milp_v7_1 as m


def one_run(hourly, initial, root, *, min_lf, max_earliness, handling,
            time_limit, mip_gap, params_xlsx, label):
    t0 = time.perf_counter()
    row = {"label": label, "min_load_factor": min_lf,
           "max_earliness_hours": "unrestricted" if max_earliness is None else max_earliness,
           "handling_hours": handling}
    try:
        m.configure_params(params_xlsx, handling, handling, handling)
        hourly_rows = m.read_hourly(hourly)
        initial_map = m.read_initial(initial)
        ts = sorted({r["timestamp"] for r in hourly_rows})
        indir = root / "_candidates" / f"h{handling}"
        if not m._candidate_inputs_match(indir, ts[0], len(ts)):
            m.generate_candidate_inputs(ts[0], len(ts), indir)
        m.validate_candidate_inputs(indir, ts)
        service = m.generate_service_needs(hourly_rows, initial_map,
                                           {"inventory_policies": []},
                                           root / "_RUN_MODEL_INPUTS" / f"h{handling}")
        trains = m.read_candidate_inputs(indir)
        meta, lo, up, integ = m.build_milp(service, trains, min_lf, {},
                                           max_earliness, None)
        row["candidate_assignments"] = len(meta["assignments"])
        row["candidate_trains"] = len(meta["trains"])
        row["service_need_teu"] = sum(n["teu"] for n in service["needs"])
        if not meta["assignments"]:
            row.update(status="NO_FEASIBLE_ASSIGNMENT", rail_served_teu=0,
                       rail_unserved_teu=row["service_need_teu"], train_count=0,
                       train_km=0.0, wagon_km=0.0, teu_km=0.0,
                       avg_distance_weighted_load_factor=0.0, avg_carriers_per_train=0.0,
                       avg_earliness_hours=0.0, max_earliness_observed=0.0,
                       estimated_rail_charge_krw=0.0)
            row["runtime_sec"] = round(time.perf_counter() - t0, 1)
            return row
        result, summary, audit = m.solve_lex(meta, lo, up, integ, time_limit, mip_gap)
        out = root / "_runs" / label
        summ = m.extract(meta, result, summary, out, label, audit, service=service)

        det = []
        import csv as _csv
        p = out / "CARRIER_RECOMMENDATION_DETAIL.csv"
        if p.exists() and p.stat().st_size:
            with p.open(encoding="utf-8-sig", newline="") as f:
                det = list(_csv.DictReader(f))
        earl = [float(r["earliness_hours"]) for r in det] or [0.0]
        wts = [int(r["quantity_teu"]) for r in det] or [1]
        row.update(
            status="OPTIMAL",
            rail_served_teu=summ["rail_served_teu"],
            rail_unserved_teu=summ["rail_unserved_teu"],
            train_count=summ["selected_train_count"],
            train_km=summ["train_km"], wagon_km=summ["wagon_km"], teu_km=summ["teu_km"],
            avg_distance_weighted_load_factor=summ["avg_distance_weighted_load_factor"],
            avg_carriers_per_train=summ["avg_carriers_per_train"],
            avg_earliness_hours=round(sum(e * w for e, w in zip(earl, wts)) / sum(wts), 2),
            max_earliness_observed=round(max(earl), 1),
            estimated_rail_charge_krw=summ["estimated_rail_charge_krw"])
    except RuntimeError as exc:
        row.update(status="NOT_PROVEN_OPTIMAL", error=str(exc)[:200])
    except Exception as exc:  # noqa: BLE001
        row.update(status=f"ERROR_{type(exc).__name__}", error=str(exc)[:200])
    row["runtime_sec"] = round(time.perf_counter() - t0, 1)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hourly", required=True)
    ap.add_argument("--initial", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--params", default=None)
    ap.add_argument("--time-limit", type=float, default=900)
    ap.add_argument("--mip-gap", type=float, default=0.001)
    ap.add_argument("--base-earliness", type=float, default=72.0)
    ap.add_argument("--base-lf", type=float, default=0.5)
    ap.add_argument("--base-handling", type=float, default=3.0)
    ap.add_argument("--which", default="all",
                    choices=["all", "earliness", "loadfactor", "handling"])
    a = ap.parse_args()

    hourly, initial, root = Path(a.hourly), Path(a.initial), Path(a.root)
    m.validate_carrier_inputs(hourly, initial)
    xlsx = Path(a.params) if a.params else None
    common = dict(time_limit=a.time_limit, mip_gap=a.mip_gap, params_xlsx=xlsx)

    if a.which in ("all", "earliness"):
        rows = []
        for e in [0, 24, 48, 72, None]:
            lab = f"E_{'UNR' if e is None else int(e)}"
            print("running", lab, flush=True)
            rows.append(one_run(hourly, initial, root, min_lf=a.base_lf, max_earliness=e,
                                handling=a.base_handling, label=lab, **common))
            m.write_csv(root / "EARLINESS_SENSITIVITY.csv", rows)

    if a.which in ("all", "loadfactor"):
        rows = []
        for lf in [0.5, 0.6, 0.7]:
            lab = f"LF_{int(lf*100)}"
            print("running", lab, flush=True)
            rows.append(one_run(hourly, initial, root, min_lf=lf,
                                max_earliness=a.base_earliness,
                                handling=a.base_handling, label=lab, **common))
            m.write_csv(root / "LOAD_FACTOR_SENSITIVITY.csv", rows)

    if a.which in ("all", "handling"):
        rows = []
        for hh in [0.0, 3.0, 6.0]:
            lab = f"H_{int(hh)}"
            print("running", lab, flush=True)
            rows.append(one_run(hourly, initial, root, min_lf=a.base_lf,
                                max_earliness=a.base_earliness,
                                handling=hh, label=lab, **common))
            m.write_csv(root / "HANDLING_TIME_SENSITIVITY.csv", rows)

    print("SENSITIVITY_DONE", flush=True)


if __name__ == "__main__":
    main()
