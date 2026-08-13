"""Rail vs Truck 운송 비교 selector.

Rail 측 값은 전부 canonical MILP 결과에서 읽는다.
  - 수량·OD·규격·열차·운임: CARRIER_RECOMMENDATIONS_<CARRIER>.csv
  - end-to-end 시간: STOP_WORK_PLAN.csv
      출발역 actual_load_start_time → 도착역 actual_available_time

Truck 측 값(및 CO₂ 비교값)은 결과 패키지 안의 주차별 폴더에서 읽는다.
    mode_comparison/outputs/<weekId>/TRUCK_COMPARISON_BY_RECOMMENDATION.csv

REC ID 는 주차마다 다시 매겨지므로 ID 일치만으로 붙이지 않고
선사·OD·규격·수량까지 확인한 뒤 join 한다.

비용 비교는 계산기의 rail_cost_krw(거리운임 + 하역비)를 쓴다. 트럭도 상·하차를
포함한 end-to-end 라 기준을 맞춰야 하기 때문이다. MILP 의
estimated_rail_charge_krw 는 거리운임만이므로 정본 값으로 따로 보존한다.
"""

from __future__ import annotations

import math
from datetime import datetime

from moveai.result_store import ResultStore
from moveai.selectors import optimization as opt


TRUCK_STATUS_TEXT = {
    "MISSING_FILE": "트럭 비교 데이터가 연결되지 않았습니다.",
    "NO_ROWS_FOR_WEEK": "이 계획주차의 트럭 비교 데이터가 아직 없습니다.",
    "OK": None,
}


EMPTY_TRUCK = {
    "roadDistanceKm": None,
    "truckVehicles": None,
    "truckCostKrw": None,
    "truckHours": None,
    "truckCo2Kg": None,
    "railCo2Kg": None,
    "railCompareCostKrw": None,
    "railDistanceFareKrw": None,
    "railHandlingCostKrw": None,
    "truckRateType": None,
    "truckCapacityRule": None,
    "truckCombineApplied": None,
    "costSavingKrw": None,
    "costSavingRate": None,
    "timeGapHours": None,
    "carbonSavingKg": None,
    "carbonSavingRate": None,
}


def _text(value) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    return text or None


def _same_shipment(row: dict, truck) -> bool:
    """트럭 행이 정말 같은 운송 건인지 확인한다.

    ID 만 믿지 않는 이유: REC ID 는 주차마다 1번부터 다시 매겨진다.
    엉뚱한 건이 붙어도 화면에는 그럴듯한 숫자로 보여 눈으로 못 잡는다.
    """
    return (
        row["carrierId"] == truck.get("carrier_id")
        and row["originHub"] == truck.get("origin_hub")
        and row["destinationHub"] == truck.get("destination_hub")
        and row["size"] == truck.get("container_size")
        and int(_num(row["boxes"])) == int(_num(truck.get("quantity_boxes")))
    )


def _num(value, default=0.0):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return default
    return value


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace(" ", "T"))


def _rail_end_to_end_hours(
    store: ResultStore, train_id: str, origin_hub: str, destination_hub: str
) -> tuple[float | None, str | None, str | None]:
    """출발역 상차 시작 → 도착역 사용 가능 시각까지의 시간.

    트럭도 상·하차를 포함한 end-to-end 기준이므로 비교 기준이 같다.
    """
    stops = store.stop_work_plan
    stops = stops[stops["train_id"] == train_id]

    origin = stops[stops["hub"] == origin_hub]
    dest = stops[stops["hub"] == destination_hub]
    if origin.empty or dest.empty:
        return None, None, None

    start_text = str(origin.iloc[0].get("actual_load_start_time") or "").strip() or None
    end_text = str(dest.iloc[0].get("actual_available_time") or "").strip() or None
    start, end = _parse(start_text), _parse(end_text)
    if not start or not end:
        return None, start_text, end_text

    return (end - start).total_seconds() / 3600.0, start_text, end_text


def transport_comparison(store: ResultStore, carrier_id: str) -> dict:
    recommendations = opt.recommendations(store, carrier_id)
    truck = store.truck_comparison
    truck_index = (
        truck.set_index("recommendation_id") if not truck.empty else None
    )
    # 운임은 추천 CSV 원본에서 그대로 읽는다 (MILP 정본).
    raw = store.recommendations(carrier_id).set_index("recommendation_id")

    rows: list[dict] = []
    missing_truck: list[str] = []
    mismatched: list[str] = []

    for rec in recommendations:
        rec_id = rec["recommendationId"]
        rail_hours, load_start, available = _rail_end_to_end_hours(
            store, rec["trainId"], rec["originHub"], rec["destinationHub"]
        )

        row = {
            # ── canonical MILP (정본) ─────────────────────────────
            "recommendationId": rec_id,
            "trainId": rec["trainId"],
            "carrierId": carrier_id,
            "originHub": rec["originHub"],
            "originName": rec["originName"],
            "destinationHub": rec["destinationHub"],
            "destinationName": rec["destinationName"],
            "size": rec["size"],
            "boxes": rec["quantityBoxes"],
            "teu": rec["quantityTeu"],
            "departureTime": rec["departureTime"],
            "arrivalTime": rec["arrivalTime"],
            "availableTime": rec["availableTime"],
            "railChargeKrw": float(
                _num(raw.loc[rec_id, "estimated_rail_charge_krw"])
            ),
            "railDistanceKm": float(_num(rec["physicalDistanceKm"])),
            "participatingCarrierCount": rec["participatingCarrierCount"],
            "trainLoadFactor": rec["trainLoadFactor"],
            "railLoadStartTime": load_start,
            "railAvailableTime": available,
            "railHours": round(rail_hours, 4) if rail_hours is not None else None,
        }

        rows.append(row)

    for row in rows:
        rec_id = row["recommendationId"]

        if truck_index is None or rec_id not in truck_index.index:
            missing_truck.append(rec_id)
            row.update(EMPTY_TRUCK)
            continue

        t = truck_index.loc[rec_id]

        # join 안전장치. REC ID 는 주차마다 다시 매겨지므로 ID 일치만으로는
        # 같은 건이라고 볼 수 없다. 선사·OD·규격·수량이 모두 같아야 붙인다.
        if not _same_shipment(row, t):
            mismatched.append(rec_id)
            row.update(EMPTY_TRUCK)
            continue

        truck_cost = float(_num(t["truck_cost_krw"]))
        truck_hours = float(_num(t["truck_end_to_end_hours"]))
        truck_co2 = float(_num(t["truck_co2_kg"]))
        rail_co2 = float(_num(t["rail_co2_kg"]))

        # 비용 비교는 계산기의 rail_cost_krw(거리운임 + 하역비)를 쓴다.
        # 트럭도 상·하차를 포함한 end-to-end 라 기준이 같아야 한다.
        # MILP 의 estimated_rail_charge_krw 는 거리운임만이라 그대로 비교하면
        # 철도가 실제보다 싸 보인다. 정본 값은 railChargeKrw 로 따로 유지한다.
        rail_cost = float(_num(t["rail_cost_krw"]))
        rail_hours = row["railHours"]

        row.update(
            {
                "roadDistanceKm": float(_num(t["road_distance_km"])),
                "truckVehicles": int(_num(t["truck_vehicle_count"])),
                "truckCostKrw": truck_cost,
                "truckHours": truck_hours,
                "truckCo2Kg": truck_co2,
                "railCo2Kg": rail_co2,
                # 비교용 철도비용 = 거리운임 + 하역비
                "railCompareCostKrw": rail_cost,
                "railDistanceFareKrw": float(_num(t["rail_distance_fare_krw"])),
                "railHandlingCostKrw": float(_num(t["rail_handling_cost_krw"])),
                "truckRateType": _text(t.get("truck_rate_type")),
                "truckCapacityRule": _text(t.get("truck_capacity_rule")),
                "truckCombineApplied": str(t.get("truck_combine_applied")).strip().lower()
                == "true",
                "costSavingKrw": truck_cost - rail_cost,
                "costSavingRate": (truck_cost - rail_cost) / truck_cost
                if truck_cost
                else None,
                # 철도 - 트럭. 음수면 철도가 더 오래 걸린다.
                "timeGapHours": (rail_hours - truck_hours)
                if rail_hours is not None
                else None,
                "carbonSavingKg": truck_co2 - rail_co2,
                "carbonSavingRate": (truck_co2 - rail_co2) / truck_co2
                if truck_co2
                else None,
            }
        )

    complete = [r for r in rows if r["truckCostKrw"] is not None]
    totals = None
    if complete:
        # 합계도 비교 기준(거리운임 + 하역비)으로 맞춘다.
        total_rail_cost = sum(r["railCompareCostKrw"] for r in complete)
        total_truck_cost = sum(r["truckCostKrw"] for r in complete)
        total_rail_co2 = sum(r["railCo2Kg"] for r in complete)
        total_truck_co2 = sum(r["truckCo2Kg"] for r in complete)
        count = len(complete)
        avg_rail_hours = sum(r["railHours"] or 0 for r in complete) / count
        avg_truck_hours = sum(r["truckHours"] for r in complete) / count

        totals = {
            "recommendationCount": count,
            "boxes": sum(r["boxes"] for r in complete),
            "teu": sum(r["teu"] for r in complete),
            "boxes20ft": sum(r["boxes"] for r in complete if r["size"] == "20FT"),
            "boxes40ft": sum(r["boxes"] for r in complete if r["size"] == "40FT"),
            "trainIds": sorted({r["trainId"] for r in complete}),
            "railChargeKrw": total_rail_cost,
            "railModelChargeKrw": sum(r["railChargeKrw"] for r in complete),
            "truckCostKrw": total_truck_cost,
            "costSavingKrw": total_truck_cost - total_rail_cost,
            "costSavingRate": (total_truck_cost - total_rail_cost) / total_truck_cost
            if total_truck_cost
            else None,
            "avgRailHours": avg_rail_hours,
            "avgTruckHours": avg_truck_hours,
            "timeGapHours": avg_rail_hours - avg_truck_hours,
            "railCo2Kg": total_rail_co2,
            "truckCo2Kg": total_truck_co2,
            "carbonSavingKg": total_truck_co2 - total_rail_co2,
            "carbonSavingRate": (total_truck_co2 - total_rail_co2) / total_truck_co2
            if total_truck_co2
            else None,
        }

    status = store.truck_comparison_status

    return {
        "weekId": store.week_id,
        "carrierId": carrier_id,
        "rows": rows,
        "totals": totals,
        "missingTruckComparison": missing_truck,
        # 화면이 "왜 비었는지"를 말할 수 있어야 한다. 0 이나 임의값을 만들지 않는다.
        "truckStatus": status,
        "truckAvailable": status == "OK" and not missing_truck and not mismatched,
        "mismatchedTruckComparison": mismatched,
        "truckUnavailableReason": TRUCK_STATUS_TEXT.get(status),
        "basis": {
            "rail": "출발역 상차 시작 → 도착역 사용 가능 (STOP_WORK_PLAN)",
            "truck": "상·하차 포함 end-to-end",
            "railCost": "거리운임(20FT 516×0.74, 40FT 800×0.74원/컨테이너-km) + 하역비(20FT 16,000 / 40FT 20,000원)",
            "truckCost": "2026 수출입컨테이너 거리별 안전운임(왕복). 20FT 2개/대 COMBINE 시 단가 180%",
            "co2": "디젤 배출계수 기준. 철도는 열차 총배출량을 추천 TEU / 열차 capacity 로 배분",
            "railModelCharge": "MILP estimated_rail_charge_krw 는 거리운임만이라 비교값과 다르다",
            "truckSource": "mode_comparison/outputs/<주차>/TRUCK_COMPARISON_BY_RECOMMENDATION.csv",
        },
    }
