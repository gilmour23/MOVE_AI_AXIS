"""
외부 KORAIL feasible path 교체 테스트용 fixture 생성 (지시서 §10).

의도적으로 prototype 과 다르게 만든다.
  - 첫 departure 가 horizon 시작이 아님 (06:00)
  - candidate_source = KORAIL_FEASIBLE_PATH
  - train_id = KTEST001 / KTEST002
  - prototype 과 다른 physical segment distance
  - prototype 과 다른 formation capacity
  - 분 단위 실제시각 -> normalization layer 로 slot 생성

이 fixture 로 다음을 증명한다.
  외부 후보를 넣으면 파일이 변경되지 않고, 그 거리/편성/source 가 그대로 KPI 에 반영된다.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta
from pathlib import Path


def _write(p: Path, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
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


# prototype 과 의도적으로 다른 거리 (검증에서 이 값이 쓰였는지 확인한다)
FIXTURE_SEGMENT_KM = {
    ("BUSAN", "YAKMOK"): 150.5,        # prototype 143.7
    ("UIWANG", "BUGANG"): 120.4,       # prototype 111.8
    ("BUGANG", "DONGSAN"): 140.9,      # prototype 130.2
    ("DONGSAN", "GWANGYANG"): 155.1,   # prototype 148.6
}
# prototype 과 의도적으로 다른 편성 (F33=66TEU 가 아니라 KF44=88TEU)
FIXTURE_FORMATION = {"formation_id": "KF44", "wagon_count": 44, "capacity_teu": 88}


def build(out_dir: Path, raw_dir: Path, horizon_start: str, horizon_hours: int = 168):
    start = datetime.strptime(horizon_start, "%Y-%m-%d %H:%M")

    specs = [
        # (train_id, path, 첫 상차 개시 offset(분), 구간 소요(분))
        ("KTEST001", ["BUSAN", "YAKMOK"], 3 * 60 + 0, [185]),
        ("KTEST002", ["UIWANG", "BUGANG", "DONGSAN", "GWANGYANG"],
         27 * 60 + 0, [125, 148, 162]),
    ]

    paths, stops, segs = [], [], []
    for tid, hubs, load_offset_min, leg_min in specs:
        work_stops = hubs
        # 실제 KORAIL 시각처럼 분 단위를 넣는다 (06:35 등)
        load_start = start + timedelta(minutes=load_offset_min + 35)
        departure = load_start + timedelta(minutes=180)   # 상차 3h
        for f in [FIXTURE_FORMATION]:
            paths.append({"train_id": tid, "service_family":
                          "GYEONGBU" if "YAKMOK" in hubs or "BUSAN" in hubs else "SOUTHWEST",
                           "path": "|".join(hubs),
                           "work_stops": "|".join(work_stops),
                          "candidate_source": "KORAIL_FEASIBLE_PATH",
                          "formation_id": f["formation_id"],
                          "wagon_count": f["wagon_count"],
                          "capacity_teu": f["capacity_teu"]})

        cur_dep = departure
        for i, hub in enumerate(hubs):
            if i == 0:
                arr = load_start
                dep = departure
                ls = load_start
            else:
                arr = cur_dep + timedelta(minutes=leg_min[i - 1])
                ls = arr
                dep = arr + timedelta(minutes=180) if i < len(hubs) - 1 else arr
                cur_dep = dep
            avail = arr + timedelta(minutes=180)
            stops.append({
                "train_id": tid, "stop_sequence": i + 1, "hub_code": hub,
                "stop_type": "WORK_STOP" if hub in work_stops else "PASS_THROUGH",
                "actual_load_start_time": ls.strftime("%Y-%m-%d %H:%M"),
                "actual_arrival_time": arr.strftime("%Y-%m-%d %H:%M"),
                "actual_departure_time": dep.strftime("%Y-%m-%d %H:%M"),
                "actual_available_time": avail.strftime("%Y-%m-%d %H:%M")})

        for i in range(len(hubs) - 1):
            pair = (hubs[i], hubs[i + 1])
            segs.append({"train_id": tid, "segment_sequence": i + 1,
                         "from_hub": pair[0], "to_hub": pair[1],
                         "segment_distance_km": FIXTURE_SEGMENT_KM[pair]})

    _write(raw_dir / "KORAIL_PATHS.csv", paths)
    _write(raw_dir / "KORAIL_PATH_STOPS.csv", stops)
    _write(raw_dir / "KORAIL_PATH_SEGMENTS.csv", segs)

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from normalize_korail_candidates_v7_1 import normalize
    res = normalize(raw_dir, out_dir, horizon_start, horizon_hours)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--horizon-start", default="2026-08-10 00:00")
    ap.add_argument("--horizon-hours", type=int, default=168)
    a = ap.parse_args()
    print(build(Path(a.out), Path(a.raw), a.horizon_start, a.horizon_hours))
