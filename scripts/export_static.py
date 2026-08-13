"""MILP 결과 → 정적 JSON 내보내기.

백엔드 API가 계산해서 내려주던 것과 **완전히 동일한 응답**을 파일로 뽑는다.
selectors 를 그대로 재사용하므로 화면에 표시되는 숫자는 동적 배포와 같다.

MILP 를 재실행해 05_RESULTS 가 갱신되면 이 스크립트를 다시 돌린 뒤 커밋한다.

    python scripts/export_static.py

핵심 원칙 (핸드오프 §10):
  현재 선사로 필터링·집계한 결과만 내보낸다.
  정적 배포에서는 내보낸 파일이 곧 공개이므로 타 선사 데이터가 섞이면 안 된다.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

# Windows 콘솔 기본 코드페이지(cp949)에서 한글·기호 출력이 깨지거나 죽는다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from moveai import config  # noqa: E402
from moveai.domain import CONTAINER_SIZES, HUBS  # noqa: E402
from moveai.weeks import registry  # noqa: E402
from moveai.selectors import inventory as inv  # noqa: E402
from moveai.selectors import korail as kr  # noqa: E402
from moveai.selectors import optimization as opt  # noqa: E402
from moveai.selectors import overview as ov  # noqa: E402
from moveai.selectors import transport as tr  # noqa: E402

OUT_ROOT = PROJECT_ROOT / "frontend" / "public" / "data"
MODES = ["baseline", "postRail"]

# 내보낼 선사. 여러 선사를 배포하려면 여기에 추가한다.
# (각 선사는 자기 데이터만 담긴 파일을 받는다)
CARRIERS = [config.DEMO_CARRIER_ID]

_written: list[Path] = []


def write(relative: str, payload) -> None:
    path = OUT_ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=None, separators=(",", ":")),
        encoding="utf-8",
    )
    _written.append(path)


def build_meta() -> dict:
    """주차와 무관한 전역 메타. 화면의 week selector 가 이것만 보고 그린다."""
    return {
        "weeks": [m.to_dict() for m in registry.all_meta()],
        "defaultWeekId": registry.default_week_id(),
        "hubs": HUBS,
        "currentCarrierId": config.DEMO_CARRIER_ID,
        # 정적 배포에는 dev mode carrier selector 가 없다.
        "devMode": False,
        "availableCarriers": [],
    }


def build_week_meta(store) -> dict:
    """주차별 horizon 과 provenance.

    horizon 날짜는 timeline 에서 만든다. 요일 상수 배열을 두지 않는다.
    """
    summary = store.summary
    timeline = store.inventory_timeline
    candidate_source = summary.get("candidate_timetable_source")
    carrier_source = summary.get("carrier_data_source")
    meta = registry.meta(store.week_id)

    return {
        **meta.to_dict(),
        "scenario": summary.get("scenario"),
        "horizonStart": timeline["timestamp"].min().isoformat(),
        "horizonEnd": timeline["timestamp"].max().isoformat(),
        "horizonDates": inv.horizon_dates(store),
        "carrierDataSource": carrier_source,
        "candidateTimetableSource": candidate_source,
        # 수요는 실측이지만 열차 시각표 후보는 합성이다. 둘을 구분해서 보존한다.
        "isSyntheticCarrierData": carrier_source == "SYNTHETIC_CARRIER_LEVEL_DATA",
        "isPrototypeTimetable": candidate_source == "PROTOTYPE_SYNTHETIC",
        "allStagesProvenOptimal": bool(summary.get("all_stages_proven_optimal")),
        "carrierKorailViewConsistent": bool(
            summary.get("carrier_korail_view_consistent")
        ),
        "operationalConstraintsActive": bool(
            summary.get("operational_constraints_active")
        ),
        "returnWagonMovementIncluded": bool(
            summary.get("return_wagon_movement_included")
        ),
        "recommendationCount": summary.get("recommendation_count"),
    }


def export_carrier(store, carrier_id: str) -> None:
    base = f"carrier/{carrier_id}/weeks/{store.week_id}"

    write(f"{base}/overview.json", ov.overview(store, carrier_id))

    write(
        f"{base}/optimization.json",
        {
            "weekId": store.week_id,
            "carrierId": carrier_id,
            "needs": opt.service_needs(store, carrier_id),
            "recommendations": opt.recommendations(store, carrier_id),
            "impacts": opt.inventory_impacts(store, carrier_id),
            "serviceSummary": opt.carrier_service_summary(store, carrier_id),
            "explanations": opt.explanation_context(store, carrier_id),
            "unserved": opt.unserved(store, carrier_id),
        },
    )

    for size in CONTAINER_SIZES:
        for mode in MODES:
            write(
                f"{base}/inventory/{size}_{mode}.json",
                inv.weekly_matrix(store, carrier_id, size, mode),
            )
            for hub in HUBS:
                write(
                    f"{base}/inventory/{hub['code']}_{size}_{mode}_summary.json",
                    inv.hub_summary(store, carrier_id, hub["code"], size, mode),
                )

    for rec in opt.recommendations(store, carrier_id):
        rec_id = rec["recommendationId"]
        detail = opt.recommendation_detail(store, carrier_id, rec_id)
        write(f"{base}/optimization/recommendations/{rec_id}.json", detail)

    # Rail vs Truck 비교 — rail 값은 canonical, truck 값만 data/ 입력
    write(f"{base}/transport_comparison.json", tr.transport_comparison(store, carrier_id))


def export_korail(store) -> None:
    """KORAIL Control Tower — 운영자 관점이므로 전 선사 배정을 포함한다."""
    base = f"korail/weeks/{store.week_id}"

    write(f"{base}/overview.json", kr.overview(store))
    write(f"{base}/trains.json", {"trains": kr.trains(store)})
    write(f"{base}/service_needs.json", kr.service_needs(store))
    write(f"{base}/inventory.json", kr.hub_inventory(store))
    write(f"{base}/station_operations.json", kr.station_operations(store))
    write(f"{base}/transport_allocations.json", kr.transport_allocations(store))
    write(f"{base}/insights.json", kr.operational_insights(store))

    # train_details 는 반드시 week 아래에 둔다.
    # CAND0158·CAND0170 이 두 주차에 모두 있어서, week 없는 경로로 쓰면
    # 뒤 주차가 앞 주차를 덮어쓰고 화면은 아무 경고 없이 다른 주차를 보여준다.
    for train in kr.trains(store):
        train_id = train["trainId"]
        write(f"{base}/train_details/{train_id}.json", kr.train_detail(store, train_id))


def verify_consistency(store) -> None:
    """Single Source of Truth 정합성 검증.

    Σ Recommendation TEU == Σ Carrier Allocation TEU
                         == Σ Train Assigned TEU
                         == Rail Served TEU
    """
    summary = store.summary
    recs = store.all_recommendations
    alloc = store.carrier_allocation
    ops = store.train_operation_summary

    rec_teu = int(recs["quantity_teu"].sum())
    alloc_teu = int(alloc["teu"].sum())
    train_teu = int(ops["assigned_teu"].sum())
    served_teu = int(summary["rail_served_teu"])

    print("\n  [정합성] TEU 4중 검증")
    print(f"    Recommendation TEU  = {rec_teu}")
    print(f"    Allocation TEU      = {alloc_teu}")
    print(f"    Train Assigned TEU  = {train_teu}")
    print(f"    Rail Served TEU     = {served_teu}")

    if not (rec_teu == alloc_teu == train_teu == served_teu):
        raise SystemExit(
            f"TEU 불일치: rec={rec_teu} alloc={alloc_teu} "
            f"train={train_teu} served={served_teu}"
        )

    selected = set(ops["train_id"])
    rec_trains = set(recs["train_id"])
    if not rec_trains <= selected:
        raise SystemExit(f"선정 열차에 없는 train_id: {rec_trains - selected}")
    print(f"    recommendation train_id ⊆ 선정 열차 {sorted(selected)}  OK")

    # 열차별 allocation 합 == train assigned TEU
    per_train = alloc.groupby("train_id")["teu"].sum()
    for _, r in ops.iterrows():
        expected = int(r["assigned_teu"])
        actual = int(per_train.get(r["train_id"], 0))
        if expected != actual:
            raise SystemExit(
                f"{r['train_id']} allocation 합 {actual} != assigned {expected}"
            )
    print("    열차별 allocation 합 == assigned TEU  OK")


def verify_transport_join(store) -> None:
    """Transport 비교가 canonical recommendation 과 정확히 join 되는지 검증."""
    for carrier_id in CARRIERS:
        payload = tr.transport_comparison(store, carrier_id)
        rec_ids = {r["recommendationId"] for r in opt.recommendations(store, carrier_id)}
        row_ids = {r["recommendationId"] for r in payload["rows"]}

        if rec_ids != row_ids:
            raise SystemExit(
                f"{carrier_id} transport join 불일치: "
                f"누락={rec_ids - row_ids} 초과={row_ids - rec_ids}"
            )

        if not payload["truckAvailable"]:
            # 트럭 자료가 주차에 스코프되지 않으면 연결하지 않는 것이 정상이다.
            # 0 이나 임의값을 만들지 않고 화면이 사유를 그대로 말한다.
            print(
                f"    {carrier_id} 트럭 비교 미연결 ({payload['truckStatus']}) - "
                f"rail 측 {len(row_ids)}건만 노출"
            )
        elif payload["missingTruckComparison"]:
            print(
                f"    경고: 트럭 비교값 없는 recommendation "
                f"{payload['missingTruckComparison']}"
            )

        # rail 측 값이 canonical 과 같은지 재확인
        raw = store.recommendations(carrier_id).set_index("recommendation_id")
        for row in payload["rows"]:
            src = raw.loc[row["recommendationId"]]
            assert row["boxes"] == int(src["quantity_boxes"])
            assert row["teu"] == int(src["quantity_teu"])
            assert row["trainId"] == src["train_id"]
            assert row["originHub"] == src["origin_hub"]
            assert row["destinationHub"] == src["destination_hub"]
            assert abs(row["railChargeKrw"] - float(src["estimated_rail_charge_krw"])) < 0.01

        print(f"    {carrier_id} transport join {len(row_ids)}건 · rail 값 canonical 일치  OK")


def verify_stop_box_counts(store) -> None:
    """거점 작업의 규격별 박스 수가 canonical TEU 와 맞는지 검증.

    40FT 1개 = 2TEU. CARRIER_ALLOCATION 에서 직접 집계한 값이므로
    이 등식이 깨지면 집계 기준이 틀어진 것이다 (TEU 역산 금지).
    """
    ops = kr.station_operations(store)

    for row in ops["rows"]:
        load = row["loadBoxes20ft"] + 2 * row["loadBoxes40ft"]
        unload = row["unloadBoxes20ft"] + 2 * row["unloadBoxes40ft"]
        if load != row["loadTeu"] or unload != row["unloadTeu"]:
            raise SystemExit(
                f"{row['trainId']} @ {row['hubCode']} 규격별 박스 합이 TEU 와 불일치: "
                f"상차 {load} vs {row['loadTeu']} · 하차 {unload} vs {row['unloadTeu']}"
            )

    for hub in ops["hubs"]:
        if hub["totalLoadBoxes"] != sum(o["loadBoxesTotal"] for o in hub["operations"]):
            raise SystemExit(f"{hub['hubCode']} 상차 박스 total 불일치")
        if hub["totalUnloadBoxes"] != sum(
            o["unloadBoxesTotal"] for o in hub["operations"]
        ):
            raise SystemExit(f"{hub['hubCode']} 하차 박스 total 불일치")

    total_boxes = sum(h["totalLoadBoxes"] for h in ops["hubs"])
    print(
        f"  [거점작업] {len(ops['rows'])}개 stop 규격별 박스 합 = TEU 일치 · "
        f"총 상차 {total_boxes}개  OK"
    )


def verify_korail_breakdowns(store) -> None:
    """stop 상하차 breakdown 과 segment onboard manifest 의 정합성 검증.

    breakdown 은 화면이 '누구의 무엇을' 보여주는 근거이므로, 합이 stop/segment
    총량과 어긋나면 화면이 canonical 결과와 다른 이야기를 하게 된다.
    """
    stop_count = 0
    segment_count = 0

    for train in kr.trains(store):
        train_id = train["trainId"]
        detail = kr.train_detail(store, train_id)

        for stop in detail["stops"]:
            for kind, boxes_key, teu_key in (
                ("loadBreakdown", "loadBoxesTotal", "loadTeu"),
                ("unloadBreakdown", "unloadBoxesTotal", "unloadTeu"),
            ):
                boxes = sum(i["boxes"] for i in stop[kind])
                teu = sum(i["teu"] for i in stop[kind])
                if boxes != stop[boxes_key] or teu != stop[teu_key]:
                    raise SystemExit(
                        f"{train_id} @ {stop['hubCode']} {kind} 합 불일치: "
                        f"{boxes}개/{teu}TEU vs {stop[boxes_key]}개/{stop[teu_key]}TEU"
                    )
            stop_count += 1

        for segment in detail["segments"]:
            if segment["onboardTeu"] != segment["loadedTeu"]:
                raise SystemExit(
                    f"{train_id} {segment['fromHub']}>{segment['toHub']} "
                    f"onboard TEU 불일치: {segment['onboardTeu']} vs {segment['loadedTeu']}"
                )
            if segment["onboardBoxes"] != sum(
                i["boxes"] for i in segment["onboardBreakdown"]
            ):
                raise SystemExit(
                    f"{train_id} {segment['fromHub']}>{segment['toHub']} onboard 박스 합 불일치"
                )
            segment_count += 1

    print(
        f"  [breakdown] {stop_count}개 stop 상하차 합 = stop total · "
        f"{segment_count}개 구간 onboard TEU = loaded TEU  OK"
    )


def verify_transport_allocations(store) -> None:
    """운송물량이 열차 요약과 맞고, 시각이 실제 stop 에서 온 값인지 검증."""
    payload = kr.transport_allocations(store)
    rows = payload["rows"]

    if payload["skipped"]:
        raise SystemExit(f"운송물량에서 제외된 allocation: {payload['skipped']}")

    stops = {
        (s["train_id"], s["hub"]): s for _, s in store.stop_work_plan.iterrows()
    }

    for row in rows:
        origin = stops[(row["trainId"], row["originHub"])]
        destination = stops[(row["trainId"], row["destinationHub"])]
        if row["originDepartureTime"] != kr._text(origin.get("actual_departure_time")):
            raise SystemExit(f"{row['trainId']} 출발시각이 origin stop 과 다름")
        if row["destinationArrivalTime"] != kr._text(
            destination.get("actual_arrival_time")
        ):
            raise SystemExit(f"{row['trainId']} 도착시각이 destination stop 과 다름")
        if int(origin["stop_sequence"]) >= int(destination["stop_sequence"]):
            raise SystemExit(f"{row['trainId']} stop 순서 역전")

    # 열차별 합계가 열차 요약과 일치해야 한다.
    for train in kr.trains(store):
        mine = [r for r in rows if r["trainId"] == train["trainId"]]
        boxes = sum(r["boxes"] for r in mine)
        teu = sum(r["teu"] for r in mine)
        if boxes != train["totalBoxes"] or teu != train["assignedTeu"]:
            raise SystemExit(
                f"{train['trainId']} 운송물량 합 불일치: "
                f"{boxes}개/{teu}TEU vs 요약 {train['totalBoxes']}개/{train['assignedTeu']}TEU"
            )

    print(
        f"  [운송물량] {len(rows)}건 · OD stop 시각 join 검증 · "
        f"열차별 Box/TEU 합 = 열차 요약 일치  OK"
    )


def verify_no_other_carriers() -> None:
    """내보낸 파일에 다른 선사 식별자가 없는지 검증한다."""
    allowed = set(CARRIERS)
    others = sorted(
        {
            carrier
            for week_id in registry.week_ids()
            for carrier in registry.store(week_id).known_carriers()
            if carrier not in allowed
        }
    )
    leaked: list[str] = []

    # carrier/ 이하만 검사한다.
    # korail/ 은 운영자 관점이므로 전 선사 배정을 포함하는 것이 정상이다.
    checked = 0
    for path in _written:
        if "carrier" not in path.relative_to(OUT_ROOT).parts[:1]:
            continue
        checked += 1
        text = path.read_text(encoding="utf-8")
        for other in others:
            if other in text:
                leaked.append(f"{path.relative_to(OUT_ROOT)} <- {other}")

    if leaked:
        raise SystemExit(
            "선사 포털 파일에 타 선사 데이터가 포함되었습니다:\n  "
            + "\n  ".join(leaked)
        )
    print(f"\n  [격리] carrier/ {checked}개 파일에 {', '.join(others)} 미포함  OK")


def main() -> None:
    if not registry.week_ids():
        raise SystemExit(f"주차 결과 폴더 없음: {registry.root}")

    if OUT_ROOT.exists():
        shutil.rmtree(OUT_ROOT)

    write("meta.json", build_meta())

    for week_id in registry.week_ids():
        store = registry.store(week_id)
        health = store.health()
        if not health["ok"]:
            raise SystemExit(f"{week_id} 결과 파일 없음: {health['missing']}")

        write(f"shared/weeks/{week_id}/meta.json", build_week_meta(store))
        for carrier_id in CARRIERS:
            export_carrier(store, carrier_id)
        export_korail(store)

        verify_consistency(store)
        verify_stop_box_counts(store)
        verify_korail_breakdowns(store)
        verify_transport_allocations(store)
        verify_transport_join(store)

    verify_no_other_carriers()

    total = sum(p.stat().st_size for p in _written)
    carrier_files = sum(1 for p in _written if "carrier" in p.relative_to(OUT_ROOT).parts[:1])
    korail_files = sum(1 for p in _written if "korail" in p.relative_to(OUT_ROOT).parts[:1])
    print(
        f"\n  {len(_written)}개 파일 / {total / 1024:.1f} KB"
        f"  (carrier {carrier_files} · korail {korail_files})"
    )
    print(f"  출력 위치: {OUT_ROOT}")


if __name__ == "__main__":
    main()
