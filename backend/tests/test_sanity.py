"""번들된 AXIS_INTEGRATED 결과에 대한 어댑터 sanity check (핸드오프 §21).

여기 있는 값은 UI 에 하드코딩하지 않는다. 어댑터가 결과 파일을 올바르게 읽는지
확인하기 위한 fixture 로만 사용한다.
"""

from __future__ import annotations

import pytest

from moveai.result_store import store
from moveai.selectors import inventory as inv
from moveai.selectors import korail as kr
from moveai.selectors import optimization as opt
from moveai.selectors import overview as ov

CARRIER = "CARRIER_A"


@pytest.fixture(scope="module", autouse=True)
def _require_results():
    health = store.health()
    if not health["ok"]:
        pytest.skip(f"결과 파일 없음: {health['missing']}")


# ------------------------------------------------------------------ 기본 메타

def test_horizon_is_one_week():
    dates = inv.horizon_dates(store)
    assert len(dates) == 7
    assert dates[0] == "2026-08-10"
    assert dates[-1] == "2026-08-16"


def test_summary_flags():
    summary = store.summary
    assert summary["all_stages_proven_optimal"] is True
    assert summary["carrier_korail_view_consistent"] is True
    assert summary["candidate_timetable_source"] == "PROTOTYPE_SYNTHETIC"


# ---------------------------------------------------------------- 추천 정합성

def test_recommendation_count_and_quantities():
    recs = opt.recommendations(store, CARRIER)
    assert len(recs) == 5

    boxes_20 = sum(r["quantityBoxes"] for r in recs if r["size"] == "20FT")
    boxes_40 = sum(r["quantityBoxes"] for r in recs if r["size"] == "40FT")
    assert boxes_20 == 31
    assert boxes_40 == 12
    assert boxes_20 + boxes_40 == 43

    # 40FT 1개 = 2TEU. box 와 TEU 를 섞으면 안 된다.
    assert sum(r["quantityTeu"] for r in recs) == 55
    for rec in recs:
        expected = rec["quantityBoxes"] * (2 if rec["size"] == "40FT" else 1)
        assert rec["quantityTeu"] == expected


def test_recommendations_sorted_by_departure():
    recs = opt.recommendations(store, CARRIER)
    departures = [r["departureTime"] for r in recs]
    assert departures == sorted(departures)


def test_uiwang_to_yakmok_times():
    recs = opt.recommendations(store, CARRIER)
    rec = next(
        r
        for r in recs
        if r["originHub"] == "UIWANG"
        and r["destinationHub"] == "YAKMOK"
        and r["size"] == "20FT"
    )
    assert rec["quantityBoxes"] == 7
    assert rec["departureTime"] == "2026-08-10 06:00"
    assert rec["arrivalTime"] == "2026-08-10 13:00"
    assert rec["availableTime"] == "2026-08-10 16:00"


# ------------------------------------------------------------- 부족량 정합성

def _weekly_shortage(mode: str) -> dict[tuple[str, str], int]:
    result = {}
    for size in ("20FT", "40FT"):
        matrix = inv.weekly_matrix(store, CARRIER, size, mode)
        for hub in matrix["hubs"]:
            shortage = hub["weeklyUnmetDemand"]
            if shortage:
                result[(hub["hubCode"], size)] = shortage
    return result


def test_baseline_weekly_stockout_totals():
    assert _weekly_shortage("baseline") == {
        ("DONGSAN", "20FT"): 1,
        ("GWANGYANG", "20FT"): 11,
        ("YAKMOK", "20FT"): 25,
        ("YAKMOK", "40FT"): 15,
    }


def test_post_rail_residual_stockout_is_not_zero():
    """최적화 후 부족이 항상 0 이라고 가정하면 안 된다 (§29-8)."""
    post = _weekly_shortage("postRail")
    assert post == {
        ("DONGSAN", "20FT"): 1,
        ("GWANGYANG", "20FT"): 3,
        ("YAKMOK", "20FT"): 2,
        ("YAKMOK", "40FT"): 3,
    }
    assert sum(post.values()) > 0


def test_inventory_is_never_negative():
    """재고는 0 에서 clip 된다. 임의로 음수화하지 않는다 (§9.2)."""
    for mode in ("baseline", "postRail"):
        for size in ("20FT", "40FT"):
            matrix = inv.weekly_matrix(store, CARRIER, size, mode)
            for hub in matrix["hubs"]:
                for day in hub["daily"]:
                    assert day["closingInventory"] >= 0
                    assert day["unmetDemand"] >= 0


# ------------------------------------------------------------------- 요약 계산

def test_hub_summary_matches_daily_values():
    summary = inv.hub_summary(store, CARRIER, "YAKMOK", "20FT", "baseline")
    closings = [d["closingInventory"] for d in summary["daily"]]

    assert len(summary["daily"]) == 7
    assert summary["initialInventory"] == 12  # carrier_initial_inventory.csv
    assert summary["weekEndInventory"] == closings[-1]
    assert summary["weeklyInventoryChange"] == closings[-1] - 12
    # §12.6 — 시간별 최솟값이 아니라 화면에 보이는 daily 값의 최솟값
    assert summary["minimumDisplayedInventory"] == min(closings)
    assert summary["weeklyUnmetDemand"] == 25
    assert summary["shortageDays"] == [
        d["weekday"] for d in summary["daily"] if d["unmetDemand"] > 0
    ]


# -------------------------------------------------------------- 재배치 영향

def test_impact_roles_and_movement():
    impacts = {(i["hubCode"], i["size"]): i for i in opt.inventory_impacts(store, CARRIER)}

    # 부강 20FT: 8개 반출만 있음
    bugang = impacts[("BUGANG", "20FT")]
    assert bugang["outboundBoxes"] == 8
    assert bugang["inboundBoxes"] == 0
    assert bugang["role"] == "출발"

    # 약목 20FT: 부산 16 + 의왕 7 = 23개 유입
    yakmok = impacts[("YAKMOK", "20FT")]
    assert yakmok["inboundBoxes"] == 23
    assert yakmok["role"] == "도착"
    assert yakmok["baselineStockoutBoxes"] == 25
    assert yakmok["postRailStockoutBoxes"] == 2
    assert yakmok["stockoutReductionBoxes"] == 23


def test_impact_min_inventory_matches_visible_matrix():
    """전/후 최저재고는 재고 화면의 daily closing 과 같은 값이어야 한다 (§17.4)."""
    impacts = opt.inventory_impacts(store, CARRIER)
    baseline_min = inv.weekly_min_by_hub_size(store, CARRIER, "baseline")
    post_min = inv.weekly_min_by_hub_size(store, CARRIER, "postRail")
    for item in impacts:
        key = (item["hubCode"], item["size"])
        assert item["baselineMinDisplayedInventory"] == baseline_min[key]
        assert item["postRailMinDisplayedInventory"] == post_min[key]


# ------------------------------------------------------- 열차 경로 / privacy

def test_recommendation_detail_uses_own_boxes_only():
    detail = opt.recommendation_detail(store, CARRIER, "REC0004")
    assert detail["trainId"] == "CAND0156"
    assert detail["route"] == "UIWANG > BUGANG > YAKMOK > BUSAN"

    stops = {s["hubCode"]: s for s in detail["stops"]}
    assert [s["hubCode"] for s in detail["stops"]] == [
        "UIWANG",
        "BUGANG",
        "YAKMOK",
        "BUSAN",
    ]

    # 의왕에서 자사 20FT 7개 + 40FT 3개 적재
    assert stops["UIWANG"]["ownLoadBoxes"] == {"20FT": 7, "40FT": 3}
    # 약목에서 동일 수량 하차, 사용 가능 시각 노출
    assert stops["YAKMOK"]["ownUnloadBoxes"] == {"20FT": 7, "40FT": 3}
    assert stops["YAKMOK"]["availableTime"] == "2026-08-10 16:00"

    # 자사 작업이 없는 정차역은 0 이어야 한다.
    # (STOP_WORK_PLAN 의 load_teu=37 같은 열차 전체 물량을 쓰면 안 된다 — §17.3)
    assert stops["BUGANG"]["hasOwnWork"] is False
    assert stops["BUSAN"]["ownUnloadBoxes"] == {"20FT": 0, "40FT": 0}


def test_train_total_boxes_exceed_own_boxes():
    """CAND0156 전체는 42박스지만 자사 물량은 10박스뿐임을 확인."""
    detail = opt.recommendation_detail(store, CARRIER, "REC0004")
    own_total = sum(
        s["ownLoadBoxes"]["20FT"] + s["ownLoadBoxes"]["40FT"] for s in detail["stops"]
    )
    assert own_total == 10

    plan = store.train_plan
    train_total = int(
        plan[plan["train_id"] == "CAND0156"]["total_container_boxes"].iloc[0]
    )
    assert train_total == 42
    assert own_total < train_total


# ------------------------------------------------------------------ 격리 검증

def test_selectors_never_leak_other_carriers():
    payload = {
        "overview": ov.overview(store, CARRIER),
        "needs": opt.service_needs(store, CARRIER),
        "recommendations": opt.recommendations(store, CARRIER),
        "impacts": opt.inventory_impacts(store, CARRIER),
        "inventory": inv.weekly_matrix(store, CARRIER, "20FT", "baseline"),
    }
    text = repr(payload)
    for other in ("CARRIER_B", "CARRIER_C", "CARRIER_D", "CARRIER_E", "CARRIER_F"):
        assert other not in text


def test_service_needs_grouped_by_hub_size_day():
    needs = opt.service_needs(store, CARRIER)
    assert needs
    keys = [(n["hubCode"], n["size"], n["date"]) for n in needs]
    assert len(keys) == len(set(keys))
    # 그룹 합계는 원본 need 합계와 같아야 한다.
    raw = store.service_need
    raw = raw[raw["carrier_id"] == CARRIER]
    assert sum(n["requiredBoxes"] for n in needs) == int(raw["quantity"].sum())
    assert sum(n["railUnservedBoxes"] for n in needs) == int(
        raw["rail_unserved_boxes"].sum()
    )


# ------------------------------------------------- KORAIL 거점 작업 규격별 박스

def test_stop_box_counts_match_stop_teu():
    """규격별 박스 수는 STOP_WORK_PLAN 의 TEU 와 정확히 맞아야 한다.

    40FT 1개 = 2TEU. TEU 에서 개수를 역산하지 않고 CARRIER_ALLOCATION 에서
    직접 집계하므로, 이 등식이 깨지면 집계 기준이 틀어진 것이다.
    """
    ops = kr.station_operations(store)
    checked = 0
    for row in ops["rows"]:
        assert row["loadBoxes20ft"] + 2 * row["loadBoxes40ft"] == row["loadTeu"], row
        assert row["unloadBoxes20ft"] + 2 * row["unloadBoxes40ft"] == row["unloadTeu"], row
        assert row["loadBoxes20ft"] + row["loadBoxes40ft"] == row["loadBoxesTotal"]
        assert row["unloadBoxes20ft"] + row["unloadBoxes40ft"] == row["unloadBoxesTotal"]
        checked += 1
    assert checked > 0


def test_hub_totals_match_operation_sum():
    """거점 total 은 해당 거점 작업 row 합계와 같아야 한다."""
    ops = kr.station_operations(store)
    for hub in ops["hubs"]:
        assert hub["totalLoadTeu"] == sum(o["loadTeu"] for o in hub["operations"])
        assert hub["totalUnloadTeu"] == sum(o["unloadTeu"] for o in hub["operations"])
        assert hub["totalLoadBoxes"] == sum(o["loadBoxesTotal"] for o in hub["operations"])
        assert hub["totalUnloadBoxes"] == sum(
            o["unloadBoxesTotal"] for o in hub["operations"]
        )
        assert hub["totalHandlingTeu"] == hub["totalLoadTeu"] + hub["totalUnloadTeu"]


def test_operations_sorted_by_work_start():
    """작업 row 는 loadStartTime → arrivalTime → departureTime 순으로 정렬된다."""
    ops = kr.station_operations(store)
    for hub in ops["hubs"]:
        keys = [
            o["loadStartTime"] or o["arrivalTime"] or o["departureTime"] or ""
            for o in hub["operations"]
        ]
        assert keys == sorted(keys), hub["hubCode"]


def test_train_detail_stops_carry_box_counts():
    """Train Detail 의 stop 도 같은 규격별 박스 수를 갖는다."""
    train_id = kr.trains(store)[0]["trainId"]
    detail = kr.train_detail(store, train_id)
    assert detail
    for stop in detail["stops"]:
        assert stop["loadBoxes20ft"] + 2 * stop["loadBoxes40ft"] == stop["loadTeu"]
        assert stop["unloadBoxes20ft"] + 2 * stop["unloadBoxes40ft"] == stop["unloadTeu"]
