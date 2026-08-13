"""공컨 최적화 페이지 selector (핸드오프 §17).

모든 조회는 current carrier 로 먼저 필터링한 뒤 집계한다.
"""

from __future__ import annotations

import math

import pandas as pd

from moveai.domain import hub_name, hub_sort_key, weekday_ko
from moveai.result_store import ResultStore
from moveai.selectors import inventory as inv


def _fmt_time(value) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    return text or None


def _num(value, default=0):
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    return value


def service_needs(store: ResultStore, carrier_id: str) -> list[dict]:
    """재배치 필요 현황 — 거점 / 규격 / 요일 로 group (§17.1)."""
    df = store.service_need
    df = df[df["carrier_id"] == carrier_id]
    if df.empty:
        return []

    df = df.copy()
    df["due_date"] = df["due_time"].dt.strftime("%Y-%m-%d")

    grouped = (
        df.groupby(["destination", "container_size", "due_date"], as_index=False)
        .agg(
            quantity=("quantity", "sum"),
            railServed=("rail_served_boxes", "sum"),
            railUnserved=("rail_unserved_boxes", "sum"),
            needCount=("need_id", "count"),
        )
        .sort_values(["due_date", "destination", "container_size"])
    )

    rows = []
    for _, r in grouped.iterrows():
        rows.append(
            {
                "hubCode": r["destination"],
                "hubName": hub_name(r["destination"]),
                "size": r["container_size"],
                "date": r["due_date"],
                "weekday": weekday_ko(r["due_date"]),
                # 필요량 단위는 개(box)
                "requiredBoxes": int(r["quantity"]),
                "railServedBoxes": int(r["railServed"]),
                "railUnservedBoxes": int(r["railUnserved"]),
                "needCount": int(r["needCount"]),
            }
        )
    return rows


def recommendations(store: ResultStore, carrier_id: str) -> list[dict]:
    """자사 철도 재배치 제안 (§17.2). 수량은 quantity_boxes."""
    df = store.recommendations(carrier_id)
    if df.empty:
        return []

    df = df.sort_values("departure_time")
    rows = []
    for _, r in df.iterrows():
        rows.append(
            {
                "recommendationId": r["recommendation_id"],
                "size": r["container_size"],
                "quantityBoxes": int(r["quantity_boxes"]),
                "quantityTeu": int(r["quantity_teu"]),
                "originHub": r["origin_hub"],
                "originName": r.get("origin_name") or hub_name(r["origin_hub"]),
                "destinationHub": r["destination_hub"],
                "destinationName": r.get("destination_name")
                or hub_name(r["destination_hub"]),
                "trainId": r["train_id"],
                "departureTime": _fmt_time(r["departure_time"]),
                "arrivalTime": _fmt_time(r["arrival_time"]),
                "availableTime": _fmt_time(r["available_time"]),
                "needCount": int(_num(r.get("need_count"))),
                # 이 추천이 덮는 수요의 납기 구간. 단일 시각이 아니라 범위다.
                "serviceDueEarliest": _fmt_time(r.get("service_due_time_earliest")),
                "serviceDueLatest": _fmt_time(r.get("service_due_time_latest")),
                "maxEarlinessHours": float(_num(r.get("max_earliness_hours"))),
                # 철도거리(physical)와 운임산정거리(tariff)는 다르다. 섞어 쓰지 않는다.
                "physicalDistanceKm": float(_num(r.get("physical_distance_km"))),
                "tariffDistanceKm": float(_num(r.get("tariff_distance_km"))),
                # 추정 철도운임. 매출·수익·이익이 아니다.
                "estimatedRailChargeKrw": float(
                    _num(r.get("estimated_rail_charge_krw"))
                ),
                # 공동운송 집계값은 노출 허용 (§10)
                "participatingCarrierCount": int(
                    _num(r.get("participating_carrier_count"))
                ),
                "trainLoadFactor": float(_num(r.get("train_load_factor"))),
                "needIds": _split_need_ids(r.get("need_ids")),
            }
        )
    return rows


def _split_need_ids(value) -> list[str]:
    """`need_ids` 는 파이프로 이어붙인 문자열이다 (NEED0012|NEED0013).

    구분자를 하나로 단정하지 않는다. 잘못 자르면 need join 이 통째로 비는데,
    화면에는 '연결된 수요 없음'처럼 보여서 오류로 안 읽힌다.
    """
    text = "" if value is None else str(value)
    if not text or text.lower() == "nan":
        return []
    for separator in ("|", ";", ","):
        text = text.replace(separator, "\x00")
    return [part.strip() for part in text.split("\x00") if part.strip()]


def explanation_context(store: ResultStore, carrier_id: str) -> list[dict]:
    """`왜 이 추천인가` 의 근거. 결과 파일에 있는 사실만 옮긴다.

    solver 의 인과증명이 아니다. 수치를 해석하거나 원인을 추론하지 않는다.
    """
    df = store.explanation_context(carrier_id)
    if df.empty:
        return []

    rows = []
    for _, r in df.iterrows():
        rows.append(
            {
                "recommendationId": r["recommendation_id"],
                "destinationHub": r.get("destination_hub"),
                "size": r.get("container_size"),
                "linkedServiceNeedTeu": int(_num(r.get("linked_service_need_teu"))),
                "linkedNeedCount": int(_num(r.get("linked_need_count"))),
                "linkedNeedDueMin": _fmt_time(r.get("linked_need_due_min")),
                "linkedNeedDueMax": _fmt_time(r.get("linked_need_due_max")),
                "originHub": r.get("origin_hub"),
                # 출발거점에서 그 시점까지 실제로 내어줄 수 있었던 물량과 그 소진 상황.
                "sourceReleaseCapacityBoxes": int(
                    _num(r.get("source_release_capacity_cumulative_boxes"))
                ),
                "assignedOutboundBoxes": int(
                    _num(r.get("assigned_outbound_cumulative_boxes_through_load"))
                ),
                "sourceReleaseRemainingBoxes": int(
                    _num(r.get("source_release_remaining_after_assignment_boxes"))
                ),
                "recommendedBoxes": int(_num(r.get("recommended_boxes"))),
                "recommendedTeu": int(_num(r.get("recommended_teu"))),
                "earlinessHours": float(_num(r.get("earliness_hours"))),
            }
        )
    rows.sort(key=lambda x: x["recommendationId"])
    return rows


def unserved(store: ResultStore, carrier_id: str) -> list[dict]:
    """철도로 배정되지 못한 자사 수요.

    `reasonIsProvenCause=False` 는 모델이 붙인 진단 분류일 뿐 확정 원인이 아니다.
    화면에서 미배정의 확정 원인처럼 표현하지 않는다.
    """
    df = store.rail_unserved
    if df.empty:
        return []
    df = df[df["carrier_id"] == carrier_id]
    if df.empty:
        return []

    rows = []
    for _, r in df.sort_values("due_time").iterrows():
        rows.append(
            {
                "needId": r["need_id"],
                "destinationHub": r["destination"],
                "destinationName": r.get("destination_name")
                or hub_name(r["destination"]),
                "size": r["container_size"],
                "quantityBoxes": int(_num(r.get("quantity"))),
                "quantityTeu": int(_num(r.get("teu"))),
                "dueTime": _fmt_time(r.get("due_time")),
                "priority": int(_num(r.get("priority"))),
                "needReason": r.get("need_reason"),
                "unservedBoxes": int(_num(r.get("rail_unserved_boxes"))),
                "unservedTeu": int(_num(r.get("rail_unserved_teu"))),
                "reason": r.get("reason"),
                "reasonIsProvenCause": str(r.get("reason_is_proven_cause")).strip().lower()
                == "true",
            }
        )
    return rows


def _own_stop_work(df: pd.DataFrame, hub_code: str) -> dict[str, int]:
    """해당 stop 에서의 자사 상/하차량.

    STOP_WORK_PLAN 의 load_teu/unload_teu 는 열차 전체 물량이므로 사용하지 않고,
    자사 recommendation 을 같은 train_id 로 집계한다 (§17.3).
    """
    load = df[df["origin_hub"] == hub_code]
    unload = df[df["destination_hub"] == hub_code]

    def boxes(frame: pd.DataFrame, size: str) -> int:
        sub = frame[frame["container_size"] == size]
        return int(sub["quantity_boxes"].sum()) if len(sub) else 0

    return {
        "load20": boxes(load, "20FT"),
        "load40": boxes(load, "40FT"),
        "unload20": boxes(unload, "20FT"),
        "unload40": boxes(unload, "40FT"),
    }


def recommendation_detail(
    store: ResultStore, carrier_id: str, recommendation_id: str
) -> dict | None:
    """추천 상세 + 자사 관점 열차 경로 (§17.3)."""
    recs = store.recommendations(carrier_id)
    if recs.empty:
        return None
    match = recs[recs["recommendation_id"] == recommendation_id]
    if match.empty:
        return None

    rec = match.iloc[0]
    train_id = rec["train_id"]

    # 같은 열차에 실린 자사 추천 전체 (타 선사 물량은 포함하지 않는다)
    own_on_train = recs[recs["train_id"] == train_id]

    plan = store.train_plan
    plan_row = plan[plan["train_id"] == train_id]
    route = plan_row["route"].iloc[0] if len(plan_row) else None
    candidate_source = (
        plan_row["candidate_source"].iloc[0] if len(plan_row) else None
    )

    stops_df = store.stop_work_plan
    stops_df = stops_df[stops_df["train_id"] == train_id].sort_values("stop_sequence")

    stops = []
    for _, s in stops_df.iterrows():
        work = _own_stop_work(own_on_train, s["hub"])
        has_own_work = any(work.values())
        stops.append(
            {
                "sequence": int(s["stop_sequence"]),
                "hubCode": s["hub"],
                "hubName": s.get("hub_name") or hub_name(s["hub"]),
                "arrivalTime": _fmt_time(s.get("actual_arrival_time")),
                "departureTime": _fmt_time(s.get("actual_departure_time")),
                # 하차가 있는 정차역에서만 의미가 있는 값
                "availableTime": _fmt_time(s.get("actual_available_time"))
                if work["unload20"] or work["unload40"]
                else None,
                "ownLoadBoxes": {"20FT": work["load20"], "40FT": work["load40"]},
                "ownUnloadBoxes": {"20FT": work["unload20"], "40FT": work["unload40"]},
                "hasOwnWork": has_own_work,
            }
        )

    return {
        "recommendationId": recommendation_id,
        "trainId": train_id,
        "route": route,
        "candidateSource": candidate_source,
        "stops": stops,
        "participatingCarrierCount": int(
            _num(rec.get("participating_carrier_count"))
        ),
        "trainLoadFactor": float(_num(rec.get("train_load_factor"))),
        "estimatedRailChargeKrw": float(_num(rec.get("estimated_rail_charge_krw"))),
        "physicalDistanceKm": float(_num(rec.get("physical_distance_km"))),
        "tariffDistanceKm": float(_num(rec.get("tariff_distance_km"))),
        "serviceDueTimeEarliest": _fmt_time(rec.get("service_due_time_earliest")),
        "serviceDueTimeLatest": _fmt_time(rec.get("service_due_time_latest")),
    }


def _role(inbound: int, outbound: int) -> str:
    if outbound > 0 and inbound == 0:
        return "출발"
    if inbound > 0 and outbound == 0:
        return "도착"
    if inbound > 0 and outbound > 0:
        return "출발·도착"
    return "영향 없음"


def inventory_impacts(store: ResultStore, carrier_id: str) -> list[dict]:
    """거점별 재배치 영향 (§17.4).

    전/후 최저재고는 재고 화면과 값을 맞추기 위해 daily closing 기준 주간 최저를 쓴다.
    canonical stockout 값은 별도 필드로 함께 내려준다.
    """
    df = store.inventory_impact
    df = df[df["carrier_id"] == carrier_id]
    if df.empty:
        return []

    baseline_min = inv.weekly_min_by_hub_size(store, carrier_id, "baseline")
    post_min = inv.weekly_min_by_hub_size(store, carrier_id, "postRail")

    rows = []
    for _, r in df.iterrows():
        hub_code = r["hub_code"]
        size = r["container_size"]
        inbound = int(r["rail_inbound_boxes"])
        outbound = int(r["rail_outbound_boxes"])
        rows.append(
            {
                "hubCode": hub_code,
                "hubName": hub_name(hub_code),
                "size": size,
                "role": _role(inbound, outbound),
                "inboundBoxes": inbound,
                "outboundBoxes": outbound,
                "baselineMinDisplayedInventory": baseline_min.get((hub_code, size), 0),
                "postRailMinDisplayedInventory": post_min.get((hub_code, size), 0),
                "baselineStockoutBoxes": int(r["baseline_stockout_boxes"]),
                "postRailStockoutBoxes": int(r["post_rail_stockout_boxes"]),
                "stockoutReductionBoxes": int(r["stockout_reduction_boxes"]),
            }
        )

    rows.sort(key=lambda x: (hub_sort_key(x["hubCode"]), x["size"]))
    return rows


def carrier_service_summary(store: ResultStore, carrier_id: str) -> dict | None:
    """자사 서비스 커버리지 요약. 타 선사 행은 포함하지 않는다."""
    df = store.carrier_service_summary
    row = df[df["carrier_id"] == carrier_id]
    if row.empty:
        return None
    r = row.iloc[0]
    return {
        "serviceNeedTeu": int(_num(r.get("service_need_teu"))),
        "railServedTeu": int(_num(r.get("rail_served_teu"))),
        "railUnservedTeu": int(_num(r.get("rail_unserved_teu"))),
        "railCoverage": float(_num(r.get("rail_coverage"))),
        "recommendationCount": int(_num(r.get("recommendation_count"))),
        "assignedTrainCount": int(_num(r.get("assigned_train_count"))),
    }
