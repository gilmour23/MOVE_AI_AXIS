"""
AXIS v7.1 — KORAIL Candidate Normalization Layer  (지시서 §5)

실제 KORAIL feasible path 는 06:35 출발 / 09:12 도착 처럼 분 단위 시각을 갖는다.
MILP 의 계획 해상도는 1시간 정수 slot 이므로, 실제 시각을 **보수적으로** slot 으로
변환하는 별도 계층을 둔다. MILP core 의 해상도는 이번 MVP 에서 바꾸지 않는다.

원본 실제 시각은 절대 버리지 않고 `actual_*` 컬럼으로 함께 보존한다.

보수적 변환 규칙 (자세한 근거는 01_DOCS/TIME_SLOT_CONVENTION.md)
--------------------------------------------------------------
    model_load_start_slot = floor(actual_load_start)   상차 개시를 앞당김
                                                       -> 재고를 더 일찍 요구 (보수적)
    model_departure_slot  = ceil (actual_departure)
    model_arrival_slot    = ceil (actual_arrival)      도착을 늦춤
    model_available_slot  = ceil (actual_available)    사용가능을 늦춤 -> 기한 판정 보수적

즉 "서비스 가능성을 과대평가하지 않는" 방향으로만 반올림한다.

입력 (KORAIL 제공 원본, 분 단위 허용)
------------------------------------
KORAIL_PATHS.csv
    train_id, service_family, path, candidate_source,
    formation_id, wagon_count, capacity_teu           (train 당 여러 행 가능)
KORAIL_PATH_STOPS.csv
    train_id, stop_sequence, hub_code,
    actual_load_start_time, actual_arrival_time,
    actual_departure_time, actual_available_time      ("YYYY-MM-DD HH:MM")
KORAIL_PATH_SEGMENTS.csv
    train_id, segment_sequence, from_hub, to_hub, segment_distance_km

출력 (AXIS candidate 표준 4파일 + 실제시각 보존)
"""
from __future__ import annotations

import argparse
import csv
import math
from datetime import datetime
from pathlib import Path


def _rows(p: Path):
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _write(p: Path, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        p.write_text("", encoding="utf-8")
        return
    fields, seen = [], set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                fields.append(k)
    with p.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def _hours(ts: datetime, start: datetime) -> float:
    return (ts - start).total_seconds() / 3600.0


def normalize(raw_dir: Path, out_dir: Path, horizon_start: str, horizon_hours: int):
    start = datetime.strptime(horizon_start, "%Y-%m-%d %H:%M")
    paths = _rows(raw_dir / "KORAIL_PATHS.csv")
    stops = _rows(raw_dir / "KORAIL_PATH_STOPS.csv")
    segs = _rows(raw_dir / "KORAIL_PATH_SEGMENTS.csv")

    by_train = {}
    formations = []
    for r in paths:
        tid = r["train_id"]
        source = r.get("candidate_source", "KORAIL_FEASIBLE_PATH")
        work_stops = tuple(h for h in (r.get("work_stops") or "").split("|") if h)
        if source == "KORAIL_FEASIBLE_PATH" and not work_stops:
            raise ValueError(f"{tid}: KORAIL_PATHS.csv requires explicit work_stops")
        by_train.setdefault(tid, {
            "service_family": r.get("service_family", "GYEONGBU"),
            "path": tuple(r["path"].split("|")),
            "work_stops": work_stops,
            "candidate_source": source})
        formations.append({
            "train_id": tid, "formation_id": r["formation_id"],
            "wagon_count": int(float(r["wagon_count"])),
            "capacity_teu": int(float(r["capacity_teu"])),
            "basis": "KORAIL_PROVIDED"})

    seg_rows, dist_by_train = [], {}
    for r in segs:
        tid = r["train_id"]
        d = float(r["segment_distance_km"])
        dist_by_train[tid] = dist_by_train.get(tid, 0.0) + d
        seg_rows.append({"train_id": tid,
                         "segment_sequence": int(r["segment_sequence"]),
                         "from_hub": r["from_hub"], "to_hub": r["to_hub"],
                         "segment_distance_km": d})
    seg_rows.sort(key=lambda x: (x["train_id"], x["segment_sequence"]))

    stop_rows = []
    origin_dep, final_arr = {}, {}
    dropped = []
    by_stop = {}
    for r in stops:
        by_stop.setdefault(r["train_id"], []).append(r)

    for tid, rs in by_stop.items():
        rs.sort(key=lambda x: int(x["stop_sequence"]))
        built = []
        ok = True
        for r in rs:
            def parse(col):
                return datetime.strptime(r[col], "%Y-%m-%d %H:%M")
            a_load = parse("actual_load_start_time")
            a_arr = parse("actual_arrival_time")
            a_dep = parse("actual_departure_time")
            a_avl = parse("actual_available_time")
            # 보수적 변환
            m_load = math.floor(_hours(a_load, start))
            m_arr = math.ceil(_hours(a_arr, start))
            m_dep = math.ceil(_hours(a_dep, start))
            m_avl = math.ceil(_hours(a_avl, start))
            if m_load < 0 or m_avl >= horizon_hours:
                ok = False
                break
            built.append({
                "train_id": tid, "stop_sequence": int(r["stop_sequence"]),
                "hub_code": r["hub_code"],
                "stop_type": ("WORK_STOP" if r["hub_code"] in by_train[tid]["work_stops"]
                              else "PASS_THROUGH"),
                "actual_load_start_time": a_load.strftime("%Y-%m-%d %H:%M"),
                "actual_arrival_time": a_arr.strftime("%Y-%m-%d %H:%M"),
                "actual_departure_time": a_dep.strftime("%Y-%m-%d %H:%M"),
                "actual_available_time": a_avl.strftime("%Y-%m-%d %H:%M"),
                "load_start_slot": m_load, "arrival_slot": m_arr,
                "departure_slot": m_dep, "available_slot": m_avl,
                "slot_mapping_rule": "load=floor, arrival/departure/available=ceil"})
        if not ok:
            dropped.append(tid)
            continue
        stop_rows.extend(built)
        origin_dep[tid] = built[0]["actual_departure_time"]
        final_arr[tid] = built[-1]["actual_arrival_time"]

    cand_rows = []
    for tid, info in by_train.items():
        if tid in dropped or tid not in origin_dep:
            continue
        cand_rows.append({
            "train_id": tid, "service_family": info["service_family"],
            "origin_terminal": info["path"][0],
            "destination_terminal": info["path"][-1],
            "path": "|".join(info["path"]),
            "work_stops": "|".join(info["work_stops"]),
            "stop_pattern": "".join("S" if h in info["work_stops"] else "P"
                                    for h in info["path"]),
            "work_stop_count": len(info["work_stops"]),
            "origin_departure_time": origin_dep[tid],
            "destination_arrival_time": final_arr[tid],
            "service_distance_km": round(dist_by_train.get(tid, 0.0), 3),
            "candidate_source": info["candidate_source"],
            "timetable_basis": "KORAIL_PROVIDED_NORMALIZED"})

    keep = {r["train_id"] for r in cand_rows}
    _write(out_dir / "TRAIN_CANDIDATE.csv", cand_rows)
    _write(out_dir / "TRAIN_STOP_TIME.csv",
           [r for r in stop_rows if r["train_id"] in keep])
    _write(out_dir / "TRAIN_SEGMENT.csv",
           [r for r in seg_rows if r["train_id"] in keep])
    _write(out_dir / "TRAIN_FORMATION_OPTION.csv",
           [r for r in formations if r["train_id"] in keep])

    return {"trains": len(cand_rows), "dropped_outside_horizon": dropped,
            "output_dir": str(out_dir)}


def main():
    ap = argparse.ArgumentParser(
        description="Normalize real KORAIL feasible paths into AXIS candidate files")
    ap.add_argument("--raw", required=True, help="directory with KORAIL_PATHS*.csv")
    ap.add_argument("--out", required=True, help="output candidate directory")
    ap.add_argument("--horizon-start", required=True, help='"YYYY-MM-DD HH:MM"')
    ap.add_argument("--horizon-hours", type=int, default=168)
    a = ap.parse_args()
    res = normalize(Path(a.raw), Path(a.out), a.horizon_start, a.horizon_hours)
    print(res)
    print("\nNext: validate with")
    print(f"  python 02_CODE/axis_milp_v7_1.py --candidates {a.out} ...")


if __name__ == "__main__":
    main()
