"""JULY_W1W2_RESULTS 어댑터 sanity check.

여기 있는 값은 UI 에 하드코딩하지 않는다. 어댑터가 결과 파일을 올바르게 읽는지
확인하기 위한 fixture 로만 사용한다.

숫자 앵커는 핸드오프 `10_FINAL_QA_ACCEPTANCE.md` B절에 명시된 것만 쓴다.
그 외에는 결과가 바뀌어도 성립해야 하는 **관계식**으로 검증한다.
결과 스냅샷마다 상수를 쫓아다니면 테스트가 검증이 아니라 받아쓰기가 된다.
"""

from __future__ import annotations

import pytest

from moveai.selectors import inventory as inv
from moveai.selectors import korail as kr
from moveai.selectors import optimization as opt
from moveai.selectors import overview as ov
from moveai.weeks import registry

CARRIER = "CARRIER_A"
OTHER_CARRIERS = ("CARRIER_B", "CARRIER_C", "CARRIER_D", "CARRIER_E", "CARRIER_F")

# 핸드오프 10_FINAL_QA_ACCEPTANCE B절 검증값.
WEEK_ANCHORS = {
    "W01_2025-07-01": {
        "need": 194,
        "served": 148,
        "unserved": 46,
        "trains": 3,
        "boxes": 126,
        "carriers": 6,
        "allocationRows": 36,
        "start": "2025-07-01",
        "end": "2025-07-07",
    },
    "W02_2025-07-08": {
        "need": 141,
        "served": 107,
        "unserved": 34,
        "trains": 2,
        "boxes": 91,
        "carriers": 6,
        "allocationRows": 23,
        "start": "2025-07-08",
        "end": "2025-07-14",
    },
}

WEEK_IDS = list(WEEK_ANCHORS)


@pytest.fixture(scope="module", autouse=True)
def _require_results():
    if not registry.week_ids():
        pytest.skip(f"주차 결과 폴더 없음: {registry.root}")
    for week_id in WEEK_IDS:
        health = registry.store(week_id).health()
        if not health["ok"]:
            pytest.skip(f"{week_id} 결과 파일 없음: {health['missing']}")


@pytest.fixture(params=WEEK_IDS)
def week_id(request) -> str:
    return request.param


@pytest.fixture
def store(week_id):
    return registry.store(week_id)


# --------------------------------------------------------------- week manifest

def test_canonical_week_ids():
    """짧은 W01 이 아니라 폴더명이 canonical ID 다."""
    assert registry.week_ids() == WEEK_IDS


def test_week_meta_horizon_from_timeline(week_id):
    """날짜축은 요일 상수 배열이 아니라 실제 horizon 에서 나와야 한다."""
    anchor = WEEK_ANCHORS[week_id]
    meta = registry.meta(week_id)
    assert meta.start == anchor["start"]
    assert meta.end == anchor["end"]
    assert meta.short_id == week_id.split("_")[0]

    dates = inv.horizon_dates(registry.store(week_id))
    assert len(dates) == 7
    assert dates[0] == anchor["start"]
    assert dates[-1] == anchor["end"]


def test_weeks_are_independent():
    """두 주차를 14일 horizon 으로 합치지 않는다."""
    w1, w2 = (registry.meta(w) for w in WEEK_IDS)
    assert w1.end < w2.start
    assert w1.week_id != w2.week_id

    # 같은 CAND ID 가 두 주차에 모두 있다 — week 없는 전역 lookup 이 위험한 이유.
    ids1 = {t["trainId"] for t in kr.trains(registry.store(w1.week_id))}
    ids2 = {t["trainId"] for t in kr.trains(registry.store(w2.week_id))}
    assert ids1 & ids2, "CAND ID 중복이 사라졌다면 week scope 전제를 다시 확인해야 한다"


# ------------------------------------------------------------------ 기본 메타

def test_qa_anchor_totals(week_id, store):
    anchor = WEEK_ANCHORS[week_id]
    trains = kr.trains(store)
    allocation = store.carrier_allocation

    assert len(trains) == anchor["trains"]
    assert sum(t["totalBoxes"] for t in trains) == anchor["boxes"]
    assert sum(t["assignedTeu"] for t in trains) == anchor["served"]
    assert len(allocation) == anchor["allocationRows"]
    assert allocation["carrier_id"].nunique() == anchor["carriers"]

    summary = store.summary
    assert int(summary["service_need_teu"]) == anchor["need"]
    assert int(summary["rail_unserved_teu"]) == anchor["unserved"]
    assert anchor["need"] - anchor["served"] == anchor["unserved"]


def test_summary_flags(store):
    summary = store.summary
    assert summary["all_stages_proven_optimal"] is True
    assert summary["carrier_korail_view_consistent"] is True
    # 수요는 실측이지만 열차 시각표 후보는 여전히 합성이다. 숨기지 않는다.
    assert summary["candidate_timetable_source"] == "PROTOTYPE_SYNTHETIC"
    assert summary["carrier_data_source"] == "SYNTHETIC_CARRIER_LEVEL_DATA"


# ---------------------------------------------------------------- 추천 정합성

def test_box_teu_conversion(store):
    """40FT 1개 = 2TEU. box 와 TEU 를 섞으면 안 된다."""
    for rec in opt.recommendations(store, CARRIER):
        expected = rec["quantityBoxes"] * (2 if rec["size"] == "40FT" else 1)
        assert rec["quantityTeu"] == expected


def test_carrier_recommendation_teu_matches_allocation(week_id, store):
    """핸드오프 07 cross-portal rule 2 — 선사별 추천 TEU == 선사별 배정 TEU."""
    allocation = store.carrier_allocation
    for carrier_id in sorted(allocation["carrier_id"].unique()):
        rec_teu = sum(
            r["quantityTeu"] for r in opt.recommendations(store, carrier_id)
        )
        alloc_teu = int(allocation[allocation["carrier_id"] == carrier_id]["teu"].sum())
        assert rec_teu == alloc_teu, (week_id, carrier_id)


def test_train_allocation_matches_train_summary(store):
    """rule 3·4 — 열차별 배정 합 == 열차 요약."""
    allocation = store.carrier_allocation
    for train in kr.trains(store):
        rows = allocation[allocation["train_id"] == train["trainId"]]
        assert int(rows["teu"].sum()) == train["assignedTeu"]
        assert int(rows["boxes"].sum()) == train["totalBoxes"]


def test_recommendations_sorted_by_departure(store):
    departures = [r["departureTime"] for r in opt.recommendations(store, CARRIER)]
    assert departures == sorted(departures)


def test_recommendation_times_come_from_own_stops(store):
    """추천 시각은 열차 전체 출발/최종도착이 아니라 해당 OD stop 에서 온다.

    열차 하나에 여러 OD 가 섞여 있으므로, final arrival 을 모든 목적지에
    대입하면 조용히 틀린 시각이 화면에 나간다.
    """
    stops_by_train: dict[str, dict[str, dict]] = {}
    for train in kr.trains(store):
        detail = kr.train_detail(store, train["trainId"])
        stops_by_train[train["trainId"]] = {s["hubCode"]: s for s in detail["stops"]}

    checked = 0
    for rec in opt.recommendations(store, CARRIER):
        stops = stops_by_train[rec["trainId"]]
        origin = stops[rec["originHub"]]
        destination = stops[rec["destinationHub"]]
        assert rec["departureTime"] == origin["departureTime"]
        assert rec["arrivalTime"] == destination["arrivalTime"]
        assert rec["availableTime"] == destination["availableTime"]
        checked += 1
    assert checked > 0


def test_need_ids_join_within_carrier_and_week(store):
    """recommendation.needIds 는 같은 주차·같은 선사의 detail 에만 붙어야 한다.

    need_ids 는 파이프로 이어붙인 문자열이라 구분자를 잘못 잡으면 join 이
    통째로 비는데, 화면에는 '연결된 수요 없음'처럼 보여서 오류로 안 읽힌다.
    """
    detail = store.recommendation_detail
    own_details = detail[detail["carrier_id"] == CARRIER]
    own_need_ids = set(own_details["need_id"])

    joined = 0
    for rec in opt.recommendations(store, CARRIER):
        assert rec["needIds"], rec["recommendationId"]
        assert len(rec["needIds"]) == rec["needCount"], rec["recommendationId"]
        for need_id in rec["needIds"]:
            assert need_id in own_need_ids, (rec["recommendationId"], need_id)
            joined += 1
    assert joined > 0


def test_unserved_reason_is_not_treated_as_proven(store):
    """미배정 사유는 모델 진단 분류다. 확정 원인으로 쓰지 않는다."""
    rows = opt.unserved(store, CARRIER)
    for row in rows:
        assert isinstance(row["reasonIsProvenCause"], bool)
        assert row["unservedBoxes"] > 0

    summary = opt.carrier_service_summary(store, CARRIER)
    assert sum(r["unservedTeu"] for r in rows) == summary["railUnservedTeu"]


def test_rail_charge_is_present_and_not_labelled_revenue(store):
    """추정 철도운임은 추천마다 있어야 한다. 매출/이익이 아니다."""
    recs = opt.recommendations(store, CARRIER)
    assert recs
    for rec in recs:
        assert rec["estimatedRailChargeKrw"] > 0
        # 철도거리와 운임산정거리는 다른 값이다. 섞어 쓰지 않는다.
        assert rec["physicalDistanceKm"] > 0
        assert rec["tariffDistanceKm"] > 0


# ------------------------------------------------------------- 부족량 정합성

def _weekly_shortage(store, mode: str) -> dict[tuple[str, str], int]:
    result = {}
    for size in ("20FT", "40FT"):
        matrix = inv.weekly_matrix(store, CARRIER, size, mode)
        for hub in matrix["hubs"]:
            if hub["weeklyUnmetDemand"]:
                result[(hub["hubCode"], size)] = hub["weeklyUnmetDemand"]
    return result


def test_rail_reduces_shortage_but_may_not_clear_it(store):
    """최적화 후 부족이 항상 0 이라고 가정하면 안 된다.

    현재 두 주차 모두 커버리지가 76% 근처이므로 잔존 부족이 있는 것이 정상이다.
    """
    baseline = _weekly_shortage(store, "baseline")
    post = _weekly_shortage(store, "postRail")

    assert baseline, "baseline 부족이 0 이면 재배치 효과를 검증할 수 없다"
    for key, value in post.items():
        assert value <= baseline.get(key, 0), key
    assert sum(post.values()) <= sum(baseline.values())


def test_inventory_is_never_negative(store):
    """재고는 0 에서 clip 된다. 임의로 음수화하지 않는다."""
    for mode in ("baseline", "postRail"):
        for size in ("20FT", "40FT"):
            matrix = inv.weekly_matrix(store, CARRIER, size, mode)
            for hub in matrix["hubs"]:
                for day in hub["daily"]:
                    assert day["closingInventory"] >= 0
                    assert day["unmetDemand"] >= 0


# ------------------------------------------------------------------- 요약 계산

def test_hub_summary_matches_daily_values(store):
    summary = inv.hub_summary(store, CARRIER, "YAKMOK", "20FT", "baseline")
    closings = [d["closingInventory"] for d in summary["daily"]]

    assert len(summary["daily"]) == 7
    assert summary["weekEndInventory"] == closings[-1]
    assert (
        summary["weeklyInventoryChange"]
        == closings[-1] - summary["initialInventory"]
    )
    # 시간별 최솟값이 아니라 화면에 보이는 daily 값의 최솟값
    assert summary["minimumDisplayedInventory"] == min(closings)
    assert summary["shortageDays"] == [
        d["weekday"] for d in summary["daily"] if d["unmetDemand"] > 0
    ]


def test_initial_inventory_comes_from_timeline_start(store):
    """초기재고는 그 주차 timeline 의 첫 시점 값이다.

    예전에는 optimizer 입력 파일을 읽었는데, 주차별 결과로 바뀐 뒤로는
    그 파일이 어느 주차의 것인지 보장되지 않는다.
    """
    timeline = store.inventory_timeline
    init = store.initial_inventory
    assert len(init) > 0

    for _, row in init.iterrows():
        subset = timeline[
            (timeline["carrier_id"] == row["carrier_id"])
            & (timeline["hub_code"] == row["hub_code"])
            & (timeline["container_size"] == row["container_size"])
        ].sort_values("timestamp")
        assert int(row["initial_inventory"]) == int(
            subset.iloc[0]["baseline_inventory"]
        )


# -------------------------------------------------------------- 재배치 영향

def test_impact_movement_matches_allocation(store):
    """거점별 반입/반출 박스는 자사 allocation 에서 그대로 나와야 한다."""
    allocation = store.carrier_allocation
    own = allocation[allocation["carrier_id"] == CARRIER]

    for item in opt.inventory_impacts(store, CARRIER):
        key_size = item["size"]
        outbound = int(
            own[(own["origin"] == item["hubCode"]) & (own["container_size"] == key_size)][
                "boxes"
            ].sum()
        )
        inbound = int(
            own[
                (own["destination"] == item["hubCode"])
                & (own["container_size"] == key_size)
            ]["boxes"].sum()
        )
        assert item["outboundBoxes"] == outbound, (item["hubCode"], key_size)
        assert item["inboundBoxes"] == inbound, (item["hubCode"], key_size)
        assert (
            item["stockoutReductionBoxes"]
            == item["baselineStockoutBoxes"] - item["postRailStockoutBoxes"]
        )


def test_impact_min_inventory_matches_visible_matrix(store):
    """전/후 최저재고는 재고 화면의 daily closing 과 같은 값이어야 한다."""
    baseline_min = inv.weekly_min_by_hub_size(store, CARRIER, "baseline")
    post_min = inv.weekly_min_by_hub_size(store, CARRIER, "postRail")
    for item in opt.inventory_impacts(store, CARRIER):
        key = (item["hubCode"], item["size"])
        assert item["baselineMinDisplayedInventory"] == baseline_min[key]
        assert item["postRailMinDisplayedInventory"] == post_min[key]


# ------------------------------------------------------- 열차 경로 / privacy

def test_recommendation_detail_uses_own_boxes_only(store):
    """자사 작업이 없는 정차역은 0 이어야 한다.

    STOP_WORK_PLAN 의 load_teu 같은 열차 전체 물량을 자사 값으로 쓰면 안 된다.
    """
    recs = opt.recommendations(store, CARRIER)
    assert recs
    rec = recs[0]
    detail = opt.recommendation_detail(store, CARRIER, rec["recommendationId"])
    assert detail is not None

    stops = {s["hubCode"]: s for s in detail["stops"]}
    assert rec["originHub"] in stops
    assert rec["destinationHub"] in stops

    origin = stops[rec["originHub"]]
    destination = stops[rec["destinationHub"]]
    assert origin["ownLoadBoxes"][rec["size"]] >= rec["quantityBoxes"]
    assert destination["ownUnloadBoxes"][rec["size"]] >= rec["quantityBoxes"]

    own_hubs = {rec["originHub"], rec["destinationHub"]}
    for code, stop in stops.items():
        if code in own_hubs:
            continue
        if not stop["hasOwnWork"]:
            assert stop["ownLoadBoxes"] == {"20FT": 0, "40FT": 0}
            assert stop["ownUnloadBoxes"] == {"20FT": 0, "40FT": 0}


def test_train_total_boxes_exceed_own_boxes(store):
    """공동 운송이므로 열차 전체 물량은 자사 물량보다 크다."""
    recs = opt.recommendations(store, CARRIER)
    assert recs
    detail = opt.recommendation_detail(store, CARRIER, recs[0]["recommendationId"])

    own_total = sum(
        s["ownLoadBoxes"]["20FT"] + s["ownLoadBoxes"]["40FT"] for s in detail["stops"]
    )
    plan = store.train_plan
    train_total = int(
        plan[plan["train_id"] == detail["trainId"]]["total_container_boxes"].iloc[0]
    )
    assert own_total > 0
    assert own_total < train_total


# ------------------------------------------------------------------ 격리 검증

def test_selectors_never_leak_other_carriers(store):
    payload = {
        "overview": ov.overview(store, CARRIER),
        "needs": opt.service_needs(store, CARRIER),
        "recommendations": opt.recommendations(store, CARRIER),
        "impacts": opt.inventory_impacts(store, CARRIER),
        "inventory": inv.weekly_matrix(store, CARRIER, "20FT", "baseline"),
    }
    text = repr(payload)
    for other in OTHER_CARRIERS:
        assert other not in text


def test_service_needs_grouped_by_hub_size_day(store):
    needs = opt.service_needs(store, CARRIER)
    assert needs
    keys = [(n["hubCode"], n["size"], n["date"]) for n in needs]
    assert len(keys) == len(set(keys))

    raw = store.service_need
    raw = raw[raw["carrier_id"] == CARRIER]
    assert sum(n["requiredBoxes"] for n in needs) == int(raw["quantity"].sum())
    assert sum(n["railUnservedBoxes"] for n in needs) == int(
        raw["rail_unserved_boxes"].sum()
    )


# ------------------------------------------------- KORAIL 거점 작업 규격별 박스

def test_stop_box_counts_match_stop_teu(store):
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


# ----------------------------------------- KORAIL stop breakdown / segment onboard

def test_stop_breakdown_matches_stop_total(store):
    """stop 의 선사×규격×OD breakdown 합은 그 stop 의 총량과 같아야 한다.

    breakdown 은 화면이 '누구의 무엇을' 보여주는 근거다. 합이 어긋나면
    화면이 canonical 결과와 다른 이야기를 하게 된다.
    """
    checked = 0
    for train in kr.trains(store):
        detail = kr.train_detail(store, train["trainId"])
        for stop in detail["stops"]:
            assert sum(i["boxes"] for i in stop["loadBreakdown"]) == stop["loadBoxesTotal"]
            assert sum(i["teu"] for i in stop["loadBreakdown"]) == stop["loadTeu"]
            assert (
                sum(i["boxes"] for i in stop["unloadBreakdown"]) == stop["unloadBoxesTotal"]
            )
            assert sum(i["teu"] for i in stop["unloadBreakdown"]) == stop["unloadTeu"]
            checked += 1
    assert checked > 0


def test_segment_onboard_matches_loaded_teu(store):
    """구간 onboard 합은 SEGMENT_LOAD 의 loaded_teu 와 같아야 한다.

    onboard 는 stop sequence 로 derive 하므로, 어긋나면 통과 판정
    (origin <= from < destination) 이 틀어진 것이다.
    """
    checked = 0
    for train in kr.trains(store):
        detail = kr.train_detail(store, train["trainId"])
        for segment in detail["segments"]:
            assert segment["onboardTeu"] == segment["loadedTeu"], segment
            assert segment["onboardBoxes"] == sum(
                i["boxes"] for i in segment["onboardBreakdown"]
            )
            assert segment["onboardCarrierCount"] == len(
                {i["carrierId"] for i in segment["onboardBreakdown"]}
            )
            checked += 1
    assert checked > 0


def test_breakdown_ordering_is_deterministic(store):
    """같은 데이터에서 두 번 만들면 순서까지 같아야 한다."""
    for train in kr.trains(store):
        first = kr.train_detail(store, train["trainId"])
        second = kr.train_detail(store, train["trainId"])
        assert first["stops"] == second["stops"]
        assert first["segments"] == second["segments"]


def test_no_handling_stop_has_empty_breakdown(store):
    """상하차가 없는 stop 은 breakdown 도 비어 있어야 한다.

    화면이 그 stop 에 작업창을 그리지 않는 근거가 된다.

    현재 July 결과에는 상하차가 0 인 stop 이 하나도 없어 이 검사는 통과만 한다.
    데이터가 바뀌면 다시 의미를 갖도록 규칙 자체는 남겨둔다.
    (구 2026-08 스냅샷에서는 CAND0156 BUGANG 이 이 경우였다)
    """
    for train in kr.trains(store):
        detail = kr.train_detail(store, train["trainId"])
        for stop in detail["stops"]:
            if stop["loadTeu"] == 0 and stop["unloadTeu"] == 0:
                assert stop["loadBreakdown"] == []
                assert stop["unloadBreakdown"] == []
