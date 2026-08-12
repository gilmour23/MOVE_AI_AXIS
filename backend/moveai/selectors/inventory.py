"""요일 단위 재고 집계 (핸드오프 §12).

UI 는 시간별 데이터를 그대로 보여주지 않는다. 하루의 마지막 timestamp 재고를
그날의 closing inventory 로, 하루의 unmet 은 시간별 합으로 집계한다.
재고는 0 에서 clip 되어 있으므로 절대 음수로 만들지 않고, 부족은 별도 필드로 표시한다.
"""

from __future__ import annotations

import pandas as pd

from moveai.domain import (
    MODE_COLUMNS,
    hub_name,
    hub_sort_key,
    weekday_ko,
)
from moveai.result_store import ResultStore


def horizon_dates(store: ResultStore) -> list[str]:
    """계획기간에 포함된 날짜 목록 (오름차순)."""
    return sorted(store.inventory_timeline["date"].unique().tolist())


def day_axis(store: ResultStore) -> list[dict]:
    return [{"date": d, "weekday": weekday_ko(d)} for d in horizon_dates(store)]


def _slice(store: ResultStore, carrier_id: str, size: str) -> pd.DataFrame:
    df = store.carrier_timeline(carrier_id)
    return df[df["container_size"] == size]


def daily_points(
    store: ResultStore, carrier_id: str, size: str, mode: str
) -> pd.DataFrame:
    """hub_code / date 별 closing inventory 와 unmet 을 계산한다.

    반환 컬럼: hub_code, date, closing_inventory, unmet_demand
    """
    cols = MODE_COLUMNS[mode]
    df = _slice(store, carrier_id, size)
    if df.empty:
        return pd.DataFrame(
            columns=["hub_code", "date", "closing_inventory", "unmet_demand"]
        )

    ordered = df.sort_values("timestamp")

    closing = (
        ordered.groupby(["hub_code", "date"], as_index=False)
        .tail(1)[["hub_code", "date", cols["inventory"]]]
        .rename(columns={cols["inventory"]: "closing_inventory"})
    )

    unmet = (
        ordered.groupby(["hub_code", "date"], as_index=False)[cols["unmet"]]
        .sum()
        .rename(columns={cols["unmet"]: "unmet_demand"})
    )

    merged = closing.merge(unmet, on=["hub_code", "date"], how="left")
    merged["unmet_demand"] = merged["unmet_demand"].fillna(0)
    return merged


def weekly_matrix(
    store: ResultStore, carrier_id: str, size: str, mode: str
) -> dict:
    """거점 × 요일 재고 매트릭스."""
    dates = horizon_dates(store)
    points = daily_points(store, carrier_id, size, mode)

    hubs: list[dict] = []
    for hub_code in sorted(points["hub_code"].unique(), key=hub_sort_key):
        rows = points[points["hub_code"] == hub_code].set_index("date")
        daily = []
        for date in dates:
            if date in rows.index:
                row = rows.loc[date]
                closing = int(row["closing_inventory"])
                unmet = int(row["unmet_demand"])
            else:
                closing, unmet = 0, 0
            daily.append(
                {
                    "date": date,
                    "weekday": weekday_ko(date),
                    "closingInventory": closing,
                    "unmetDemand": unmet,
                }
            )
        hubs.append(
            {
                "hubCode": hub_code,
                "hubName": hub_name(hub_code),
                "daily": daily,
                "weeklyUnmetDemand": sum(d["unmetDemand"] for d in daily),
            }
        )

    return {
        "mode": mode,
        "size": size,
        "days": day_axis(store),
        "hubs": hubs,
    }


def hub_summary(
    store: ResultStore, carrier_id: str, hub_code: str, size: str, mode: str
) -> dict:
    """선택 거점의 주간 요약 (핸드오프 §12.3~§12.7)."""
    df = _slice(store, carrier_id, size)
    df = df[df["hub_code"] == hub_code]

    points = daily_points(store, carrier_id, size, mode)
    points = points[points["hub_code"] == hub_code].sort_values("date")

    daily = [
        {
            "date": row["date"],
            "weekday": weekday_ko(row["date"]),
            "closingInventory": int(row["closing_inventory"]),
            "unmetDemand": int(row["unmet_demand"]),
        }
        for _, row in points.iterrows()
    ]

    init_df = store.initial_inventory
    init_row = init_df[
        (init_df["carrier_id"] == carrier_id)
        & (init_df["hub_code"] == hub_code)
        & (init_df["container_size"] == size)
    ]
    initial_inventory = int(init_row["initial_inventory"].iloc[0]) if len(init_row) else 0

    week_end = daily[-1]["closingInventory"] if daily else 0
    closings = [d["closingInventory"] for d in daily]
    weekly_unmet = sum(d["unmetDemand"] for d in daily)

    return {
        "hubCode": hub_code,
        "hubName": hub_name(hub_code),
        "size": size,
        "mode": mode,
        "daily": daily,
        "weeklyDemand": int(df["demand"].sum()),
        "weeklyExternalSupply": int(df["external_supply"].sum()),
        "initialInventory": initial_inventory,
        "weekEndInventory": week_end,
        "weeklyInventoryChange": week_end - initial_inventory,
        # 화면에 보이는 7개 daily closing 의 최솟값 (§12.6)
        "minimumDisplayedInventory": min(closings) if closings else 0,
        "weeklyUnmetDemand": weekly_unmet,
        "shortageDays": [d["weekday"] for d in daily if d["unmetDemand"] > 0],
        # postRail 화면 subtext 용 — 외부 공급과 섞지 않는다 (§12.4)
        "railInboundBoxes": int(df["rail_inbound_boxes"].sum()),
        "railOutboundBoxes": int(df["rail_outbound_boxes"].sum()),
    }


def weekly_min_by_hub_size(
    store: ResultStore, carrier_id: str, mode: str
) -> dict[tuple[str, str], int]:
    """(hub, size) → daily closing 기준 주간 최저재고.

    거점별 재배치 영향 표가 재고 화면과 같은 값을 쓰도록 하기 위한 헬퍼 (§17.4).
    """
    result: dict[tuple[str, str], int] = {}
    for size in ("20FT", "40FT"):
        points = daily_points(store, carrier_id, size, mode)
        if points.empty:
            continue
        grouped = points.groupby("hub_code")["closing_inventory"].min()
        for hub_code, value in grouped.items():
            result[(hub_code, size)] = int(value)
    return result
