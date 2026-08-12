"""KORAIL Control Tower selector.

운영자 관점이므로 전 선사 배정을 집계·노출한다.
(선사 포털은 selectors/optimization.py 를 쓰며 타 선사 데이터를 절대 보지 않는다)

모든 값은 05_RESULTS/AXIS_INTEGRATED 의 canonical 결과에서만 계산한다.
"""

from __future__ import annotations

import math

import pandas as pd

from moveai.domain import CONTAINER_SIZES, HUBS, hub_name, hub_sort_key, weekday_ko
from moveai.result_store import ResultStore
from moveai.selectors import inventory as inv


def _num(value, default=0):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return default
    return value


def _text(value) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    return text or None


def carrier_label(carrier_id: str) -> str:
    """CARRIER_A → 'Carrier A'. 실제 선사명을 임의로 매핑하지 않는다."""
    if carrier_id.startswith("CARRIER_"):
        return f"Carrier {carrier_id.removeprefix('CARRIER_')}"
    return carrier_id


# --------------------------------------------------------------------- 열차

def trains(store: ResultStore) -> list[dict]:
    """선정 열차 목록 (FINAL_TRAIN_OPERATION_SUMMARY 기준)."""
    summary = store.train_operation_summary
    plan = store.train_plan.set_index("train_id")

    rows = []
    for _, r in summary.iterrows():
        train_id = r["train_id"]
        p = plan.loc[train_id] if train_id in plan.index else None
        rows.append(
            {
                "trainId": train_id,
                "route": r["route"],
                "serviceFamily": _text(p["service_family"]) if p is not None else None,
                "originTerminal": _text(p["origin_terminal"]) if p is not None else None,
                "destinationTerminal": _text(p["destination_terminal"])
                if p is not None
                else None,
                "departureTime": _text(r["actual_origin_departure"]),
                "arrivalTime": _text(r["actual_final_arrival"]),
                "formation": _text(r["formation"]),
                "wagons": int(_num(r["wagons"])),
                "capacityTeu": int(_num(r["capacity_teu"])),
                "assignedTeu": int(_num(r["assigned_teu"])),
                "loadFactor": float(_num(r["load_factor"])),
                "participatingCarrierCount": int(_num(r["participating_carrier_count"])),
                "boxes20ft": int(_num(r["20ft_boxes"])),
                "boxes40ft": int(_num(r["40ft_boxes"])),
                "totalBoxes": int(_num(r["total_container_boxes"])),
                "candidateSource": _text(r["candidate_source"]),
                "trainKm": float(_num(p["train_km"])) if p is not None else 0.0,
                "workStops": (_text(p["work_stops"]) or "").split("|")
                if p is not None
                else [],
            }
        )
    rows.sort(key=lambda x: x["departureTime"] or "")
    return rows


EMPTY_BOX_COUNTS = {
    "loadBoxes20ft": 0,
    "loadBoxes40ft": 0,
    "loadBoxesTotal": 0,
    "unloadBoxes20ft": 0,
    "unloadBoxes40ft": 0,
    "unloadBoxesTotal": 0,
}


def stop_box_counts(store: ResultStore) -> dict[tuple[str, str], dict]:
    """(train_id, hub) 별 규격 상·하차 박스 수.

    CARRIER_ALLOCATION 의 origin/destination 을 그대로 집계한다.
    - 상차: origin == hub
    - 하차: destination == hub

    TEU 에서 규격별 개수를 역산하거나 임의 비율로 나누지 않는다.
    40FT 1개 = 2TEU 이므로 20ft + 2*40ft 는 STOP_WORK_PLAN 의 TEU 와 일치해야 한다.
    """
    counts: dict[tuple[str, str], dict] = {}

    def entry(train_id: str, hub: str) -> dict:
        return counts.setdefault((train_id, hub), dict(EMPTY_BOX_COUNTS))

    for _, a in store.carrier_allocation.iterrows():
        train_id = a["train_id"]
        boxes = int(_num(a["boxes"]))
        is_20ft = a["container_size"] == "20FT"

        loaded = entry(train_id, a["origin"])
        loaded["loadBoxes20ft" if is_20ft else "loadBoxes40ft"] += boxes
        loaded["loadBoxesTotal"] += boxes

        unloaded = entry(train_id, a["destination"])
        unloaded["unloadBoxes20ft" if is_20ft else "unloadBoxes40ft"] += boxes
        unloaded["unloadBoxesTotal"] += boxes

    return counts


def _stop_timeline(store: ResultStore, train_id: str) -> list[dict]:
    """역별 작업 타임라인 (STOP_WORK_PLAN).

    KORAIL 화면이므로 열차 전체 load_teu/unload_teu 를 그대로 쓸 수 있다.
    """
    df = store.stop_work_plan
    df = df[df["train_id"] == train_id].sort_values("stop_sequence")
    boxes = stop_box_counts(store)

    stops = []
    for _, s in df.iterrows():
        stops.append(
            {
                "sequence": int(s["stop_sequence"]),
                "hubCode": s["hub"],
                "hubName": _text(s.get("hub_name")) or hub_name(s["hub"]),
                "stopType": _text(s.get("stop_type")),
                "loadStartTime": _text(s.get("actual_load_start_time")),
                "arrivalTime": _text(s.get("actual_arrival_time")),
                "departureTime": _text(s.get("actual_departure_time")),
                "availableTime": _text(s.get("actual_available_time")),
                "loadTeu": int(_num(s.get("load_teu"))),
                "unloadTeu": int(_num(s.get("unload_teu"))),
                **boxes.get((train_id, s["hub"]), dict(EMPTY_BOX_COUNTS)),
            }
        )
    return stops


def _segments(store: ResultStore, train_id: str) -> list[dict]:
    """구간별 적재율 (SEGMENT_LOAD).

    capacity 는 열차 총량이 아니라 각 구간을 실제 통과하는 물량 기준 모델을 유지한다.
    """
    df = store.segment_load
    df = df[df["train_id"] == train_id].sort_values("segment_sequence")

    return [
        {
            "sequence": int(s["segment_sequence"]),
            "fromHub": s["from_hub"],
            "fromHubName": hub_name(s["from_hub"]),
            "toHub": s["to_hub"],
            "toHubName": hub_name(s["to_hub"]),
            "loadedTeu": int(_num(s["loaded_teu"])),
            "capacityTeu": int(_num(s["capacity_teu"])),
            "loadFactor": float(_num(s["load_factor"])),
            "physicalDistanceKm": float(_num(s["physical_distance_km"])),
        }
        for _, s in df.iterrows()
    ]


def _allocation(store: ResultStore, train_id: str) -> list[dict]:
    """열차별 선사 배정 상세 — KORAIL 전용."""
    df = store.carrier_allocation
    df = df[df["train_id"] == train_id]

    rows = [
        {
            "carrierId": a["carrier_id"],
            "carrierLabel": carrier_label(a["carrier_id"]),
            "originHub": a["origin"],
            "originName": hub_name(a["origin"]),
            "destinationHub": a["destination"],
            "destinationName": hub_name(a["destination"]),
            "size": a["container_size"],
            "boxes": int(_num(a["boxes"])),
            "teu": int(_num(a["teu"])),
        }
        for _, a in df.iterrows()
    ]
    rows.sort(key=lambda x: (x["carrierId"], x["size"]))
    return rows


def train_detail(store: ResultStore, train_id: str) -> dict | None:
    summary = {t["trainId"]: t for t in trains(store)}
    if train_id not in summary:
        return None

    allocation = _allocation(store, train_id)

    # 선사별 소계 — Train Detail 상단 요약용
    by_carrier: dict[str, dict] = {}
    for row in allocation:
        entry = by_carrier.setdefault(
            row["carrierId"],
            {
                "carrierId": row["carrierId"],
                "carrierLabel": row["carrierLabel"],
                "boxes": 0,
                "teu": 0,
                "boxes20ft": 0,
                "boxes40ft": 0,
                "lanes": 0,
            },
        )
        entry["boxes"] += row["boxes"]
        entry["teu"] += row["teu"]
        entry["lanes"] += 1
        if row["size"] == "20FT":
            entry["boxes20ft"] += row["boxes"]
        else:
            entry["boxes40ft"] += row["boxes"]

    carriers = sorted(by_carrier.values(), key=lambda x: -x["teu"])

    return {
        **summary[train_id],
        "stops": _stop_timeline(store, train_id),
        "segments": _segments(store, train_id),
        "allocation": allocation,
        "carrierBreakdown": carriers,
    }


# ------------------------------------------------------------------ 수송 수요

def service_needs(store: ResultStore) -> dict:
    """철도 서비스 수요·배정 현황 (전 선사)."""
    df = store.service_need.copy()
    df["due_date"] = df["due_time"].dt.strftime("%Y-%m-%d")

    grouped = (
        df.groupby(
            ["carrier_id", "destination", "container_size", "due_date"], as_index=False
        )
        .agg(
            required=("quantity", "sum"),
            requiredTeu=("teu", "sum"),
            railServed=("rail_served_boxes", "sum"),
            railUnserved=("rail_unserved_boxes", "sum"),
            needCount=("need_id", "count"),
        )
        .sort_values(["due_date", "carrier_id", "destination"])
    )

    rows = []
    for _, r in grouped.iterrows():
        required = int(r["required"])
        served = int(r["railServed"])
        rows.append(
            {
                "carrierId": r["carrier_id"],
                "carrierLabel": carrier_label(r["carrier_id"]),
                "hubCode": r["destination"],
                "hubName": hub_name(r["destination"]),
                "size": r["container_size"],
                "date": r["due_date"],
                "weekday": weekday_ko(r["due_date"]),
                "requiredBoxes": required,
                "requiredTeu": int(r["requiredTeu"]),
                "railServedBoxes": served,
                "railUnservedBoxes": int(r["railUnserved"]),
                "needCount": int(r["needCount"]),
                # 상태는 데이터에서 직접 판정 가능한 것만 사용한다.
                "status": "배정 완료"
                if served == required
                else ("미배정" if served == 0 else "부분 배정"),
            }
        )

    return {
        "rows": rows,
        "totals": {
            "requiredBoxes": int(df["quantity"].sum()),
            "requiredTeu": int(df["teu"].sum()),
            "railServedBoxes": int(df["rail_served_boxes"].sum()),
            "railUnservedBoxes": int(df["rail_unserved_boxes"].sum()),
            "needCount": int(len(df)),
        },
    }


# -------------------------------------------------------------------- 재고

def hub_inventory(store: ResultStore) -> dict:
    """거점 재고 모니터링.

    hub total 은 운영 현황 집계일 뿐이며 선사 간 소유권을 섞지 않는다.
    선사별 breakdown 을 함께 제공한다.
    """
    timeline = store.inventory_timeline
    dates = inv.horizon_dates(store)
    last_date = dates[-1]

    ordered = timeline.sort_values("timestamp")
    closing = ordered.groupby(
        ["carrier_id", "hub_code", "container_size", "date"], as_index=False
    ).tail(1)
    week_end = closing[closing["date"] == last_date]

    flows = timeline.groupby(["hub_code", "container_size"], as_index=False)[
        ["demand", "external_supply", "rail_inbound_boxes", "rail_outbound_boxes",
         "baseline_unmet_demand", "post_rail_unmet_demand"]
    ].sum()
    flow_index = flows.set_index(["hub_code", "container_size"])

    hubs = []
    for meta in HUBS:
        code = meta["code"]
        sizes = {}
        for size in CONTAINER_SIZES:
            we = week_end[
                (week_end["hub_code"] == code) & (week_end["container_size"] == size)
            ]
            f = (
                flow_index.loc[(code, size)]
                if (code, size) in flow_index.index
                else None
            )
            sizes[size] = {
                "baselineInventory": int(we["baseline_inventory"].sum()),
                "postRailInventory": int(we["post_rail_inventory"].sum()),
                "demand": int(_num(f["demand"])) if f is not None else 0,
                "externalSupply": int(_num(f["external_supply"])) if f is not None else 0,
                "railInbound": int(_num(f["rail_inbound_boxes"])) if f is not None else 0,
                "railOutbound": int(_num(f["rail_outbound_boxes"])) if f is not None else 0,
                "baselineStockout": int(_num(f["baseline_unmet_demand"]))
                if f is not None
                else 0,
                "postRailStockout": int(_num(f["post_rail_unmet_demand"]))
                if f is not None
                else 0,
            }

        by_carrier = []
        for carrier_id in sorted(timeline["carrier_id"].unique()):
            entry = {
                "carrierId": carrier_id,
                "carrierLabel": carrier_label(carrier_id),
                "sizes": {},
            }
            for size in CONTAINER_SIZES:
                we = week_end[
                    (week_end["carrier_id"] == carrier_id)
                    & (week_end["hub_code"] == code)
                    & (week_end["container_size"] == size)
                ]
                sub = timeline[
                    (timeline["carrier_id"] == carrier_id)
                    & (timeline["hub_code"] == code)
                    & (timeline["container_size"] == size)
                ]
                entry["sizes"][size] = {
                    "baselineInventory": int(we["baseline_inventory"].sum()),
                    "postRailInventory": int(we["post_rail_inventory"].sum()),
                    "baselineStockout": int(sub["baseline_unmet_demand"].sum()),
                    "postRailStockout": int(sub["post_rail_unmet_demand"].sum()),
                    "railInbound": int(sub["rail_inbound_boxes"].sum()),
                    "railOutbound": int(sub["rail_outbound_boxes"].sum()),
                }
            by_carrier.append(entry)

        total_baseline_stockout = sum(s["baselineStockout"] for s in sizes.values())
        total_post_stockout = sum(s["postRailStockout"] for s in sizes.values())

        hubs.append(
            {
                "hubCode": code,
                "hubName": meta["name"],
                "shortName": meta["shortName"],
                "sizes": sizes,
                "byCarrier": by_carrier,
                "baselineStockout": total_baseline_stockout,
                "postRailStockout": total_post_stockout,
                "stockoutReduction": total_baseline_stockout - total_post_stockout,
                # 임의 안전재고 기준을 만들지 않는다. 데이터로 판정 가능한 상태만 쓴다.
                "status": "부족 해소"
                if total_baseline_stockout > 0 and total_post_stockout == 0
                else ("부족 잔존" if total_post_stockout > 0 else "정상"),
            }
        )

    hubs.sort(key=lambda h: hub_sort_key(h["hubCode"]))
    return {"dates": dates, "weekEndDate": last_date, "hubs": hubs}


# ------------------------------------------------------------- 거점 작업 계획

def station_operations(store: ResultStore) -> dict:
    """거점별 작업 계획 (STOP_WORK_PLAN 전체)."""
    df = store.stop_work_plan.copy()
    boxes = stop_box_counts(store)

    rows = []
    for _, s in df.iterrows():
        rows.append(
            {
                "trainId": s["train_id"],
                "sequence": int(s["stop_sequence"]),
                "hubCode": s["hub"],
                "hubName": _text(s.get("hub_name")) or hub_name(s["hub"]),
                "stopType": _text(s.get("stop_type")),
                "loadStartTime": _text(s.get("actual_load_start_time")),
                "arrivalTime": _text(s.get("actual_arrival_time")),
                "departureTime": _text(s.get("actual_departure_time")),
                "availableTime": _text(s.get("actual_available_time")),
                "loadTeu": int(_num(s.get("load_teu"))),
                "unloadTeu": int(_num(s.get("unload_teu"))),
                **boxes.get((s["train_id"], s["hub"]), dict(EMPTY_BOX_COUNTS)),
            }
        )

    def empty_hub(code: str, name: str) -> dict:
        return {
            "hubCode": code,
            "hubName": name,
            "operations": [],
            "totalLoadTeu": 0,
            "totalUnloadTeu": 0,
            "totalLoadBoxes": 0,
            "totalUnloadBoxes": 0,
        }

    by_hub: dict[str, dict] = {}
    for row in rows:
        entry = by_hub.setdefault(
            row["hubCode"], empty_hub(row["hubCode"], row["hubName"])
        )
        entry["operations"].append(row)
        entry["totalLoadTeu"] += row["loadTeu"]
        entry["totalUnloadTeu"] += row["unloadTeu"]
        entry["totalLoadBoxes"] += row["loadBoxesTotal"]
        entry["totalUnloadBoxes"] += row["unloadBoxesTotal"]

    hubs = []
    for meta in HUBS:
        entry = by_hub.get(meta["code"], empty_hub(meta["code"], meta["name"]))
        entry["shortName"] = meta["shortName"]
        # 작업 준비 시점 기준 정렬. loadStartTime 이 없으면 도착, 그것도 없으면 출발.
        # 정렬을 위해 임의 시각을 만들지 않는다.
        entry["operations"].sort(key=_operation_sort_key)
        entry["operationCount"] = len(entry["operations"])
        entry["totalHandlingTeu"] = entry["totalLoadTeu"] + entry["totalUnloadTeu"]
        hubs.append(entry)

    return {"hubs": hubs, "rows": rows}


def _operation_sort_key(row: dict) -> str:
    """작업 row 정렬 키 — loadStartTime → arrivalTime → departureTime.

    STOP_WORK_PLAN 에는 loadStartTime < arrivalTime 인 stop 이 존재하므로
    도착시각만으로 정렬하면 작업 준비 순서와 어긋난다.
    """
    return row["loadStartTime"] or row["arrivalTime"] or row["departureTime"] or ""


# --------------------------------------------------------------------- 개요

def overview(store: ResultStore) -> dict:
    summary = store.summary
    train_rows = trains(store)
    inventory = hub_inventory(store)
    needs = service_needs(store)

    return {
        "scenario": summary.get("scenario"),
        "serviceNeedTeu": int(_num(summary.get("service_need_teu"))),
        "railServedTeu": int(_num(summary.get("rail_served_teu"))),
        "railUnservedTeu": int(_num(summary.get("rail_unserved_teu"))),
        "railCoverage": float(_num(summary.get("rail_coverage"))),
        "selectedTrainCount": int(_num(summary.get("selected_train_count"))),
        "recommendationCount": int(_num(summary.get("recommendation_count"))),
        "boxes20ft": int(_num(summary.get("20ft_boxes"))),
        "boxes40ft": int(_num(summary.get("40ft_boxes"))),
        "totalBoxes": int(_num(summary.get("total_container_boxes"))),
        "trainKm": float(_num(summary.get("train_km"))),
        "wagonKm": float(_num(summary.get("wagon_km"))),
        "teuKm": float(_num(summary.get("teu_km"))),
        "avgLoadFactor": float(_num(summary.get("avg_distance_weighted_load_factor"))),
        "avgCarriersPerTrain": float(_num(summary.get("avg_carriers_per_train"))),
        "estimatedRailChargeKrw": float(_num(summary.get("estimated_rail_charge_krw"))),
        "participatingCarrierCount": int(
            store.carrier_allocation["carrier_id"].nunique()
        ),
        "trains": train_rows,
        "hubs": inventory["hubs"],
        "needTotals": needs["totals"],
    }


# ---------------------------------------------------------------- 운영 분석

def operational_insights(store: ResultStore) -> dict:
    """데이터에서 직접 계산되는 구조화 분석.

    생성형 AI 결과가 아니므로 화면에서 '운영 분석'으로 표기한다.
    """
    impact = store.inventory_impact
    grouped = (
        impact.groupby(["hub_code", "container_size"], as_index=False)[
            ["baseline_stockout_boxes", "post_rail_stockout_boxes",
             "stockout_reduction_boxes", "rail_inbound_boxes", "rail_outbound_boxes"]
        ].sum()
    )

    items = []
    for _, r in grouped.iterrows():
        baseline = int(r["baseline_stockout_boxes"])
        post = int(r["post_rail_stockout_boxes"])
        if baseline == 0 and post == 0:
            continue
        items.append(
            {
                "hubCode": r["hub_code"],
                "hubName": hub_name(r["hub_code"]),
                "size": r["container_size"],
                "baselineStockout": baseline,
                "postRailStockout": post,
                "reduction": int(r["stockout_reduction_boxes"]),
                "railInbound": int(r["rail_inbound_boxes"]),
                "railOutbound": int(r["rail_outbound_boxes"]),
                "resolved": post == 0,
            }
        )
    items.sort(key=lambda x: -x["baselineStockout"])

    segments = store.segment_load
    weakest = segments.nsmallest(3, "load_factor")
    strongest = segments.nlargest(3, "load_factor")

    def seg_row(df: pd.DataFrame) -> list[dict]:
        return [
            {
                "trainId": s["train_id"],
                "fromHubName": hub_name(s["from_hub"]),
                "toHubName": hub_name(s["to_hub"]),
                "loadedTeu": int(s["loaded_teu"]),
                "capacityTeu": int(s["capacity_teu"]),
                "loadFactor": float(s["load_factor"]),
            }
            for _, s in df.iterrows()
        ]

    return {
        "stockoutImpacts": items,
        "totals": {
            "baselineStockout": int(impact["baseline_stockout_boxes"].sum()),
            "postRailStockout": int(impact["post_rail_stockout_boxes"].sum()),
            "reduction": int(impact["stockout_reduction_boxes"].sum()),
        },
        "lowestLoadSegments": seg_row(weakest),
        "highestLoadSegments": seg_row(strongest),
    }
