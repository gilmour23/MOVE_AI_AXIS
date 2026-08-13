"""주차(week) 레지스트리.

결과 정본은 `reference_data/JULY_W1W2_RESULTS/` 하나이고, 그 안에 주차별 폴더가 있다.
W01 과 W02 는 **서로 독립된 7일 최적화 결과**다. 14일 horizon 으로 합치지 않는다.

canonical weekId 는 폴더명이다.

    W01_2025-07-01
    W02_2025-07-08

`W01` 같은 짧은 키를 내부 식별자로 쓰지 않는다. 같은 `CAND0158` 이 두 주차에
모두 존재하므로, 주차를 잃어버린 식별자는 조용히 다른 주차의 열차를 가리키게 된다.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from moveai import config
from moveai.domain import weekday_ko
from moveai.result_store import ResultStore

SUMMARY_FILE = "RESULTS_SUMMARY.csv"


@dataclass(frozen=True)
class WeekMeta:
    """화면과 export 가 함께 쓰는 주차 메타데이터."""

    week_id: str
    short_id: str
    start: str
    end: str
    label: str
    source_folder: str
    selected_train_count: int
    need_teu: float
    served_teu: float
    unserved_teu: float
    coverage: float

    def to_dict(self) -> dict:
        return {
            "weekId": self.week_id,
            "shortId": self.short_id,
            "start": self.start,
            "end": self.end,
            "label": self.label,
            "sourceFolder": self.source_folder,
            "selectedTrainCount": self.selected_train_count,
            "needTeu": self.need_teu,
            "servedTeu": self.served_teu,
            "unservedTeu": self.unserved_teu,
            "coverage": self.coverage,
        }


def _short_id(week_id: str) -> str:
    """W01_2025-07-01 → W01. 표시 라벨 용도로만 쓴다."""
    return week_id.split("_", 1)[0]


def _label(week_id: str, start: str, end: str) -> str:
    """W01 · 07.01(화)~07.07(월)."""

    def stamp(value: str) -> str:
        d = datetime.fromisoformat(value)
        return f"{d.month:02d}.{d.day:02d}({weekday_ko(value)})"

    return f"{_short_id(week_id)} · {stamp(start)}~{stamp(end)}"


class WeekRegistry:
    """결과 root 하위의 주차 폴더를 발견하고 주차별 ResultStore 를 보관한다."""

    def __init__(self, root: Path):
        self.root = root
        self._stores: dict[str, ResultStore] = {}
        self._week_ids: tuple[str, ...] | None = None

    # ------------------------------------------------------------- 발견

    def _summary_rows(self) -> list[dict]:
        path = self.root / SUMMARY_FILE
        if not path.exists():
            return []
        with open(path, encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    def _discover(self) -> tuple[str, ...]:
        """폴더명을 canonical weekId 로 삼는다.

        RESULTS_SUMMARY.csv 의 `week` 열은 W01 처럼 짧으므로 그것만으로 폴더를
        찾지 않고, 실제 존재하는 폴더를 정렬해서 쓴다.
        """
        if self._week_ids is None:
            if not self.root.exists():
                self._week_ids = ()
            else:
                self._week_ids = tuple(
                    sorted(p.name for p in self.root.iterdir() if p.is_dir())
                )
        return self._week_ids

    def week_ids(self) -> list[str]:
        return list(self._discover())

    def exists(self, week_id: str) -> bool:
        return week_id in self._discover()

    def default_week_id(self) -> str | None:
        ids = self.week_ids()
        return ids[0] if ids else None

    def resolve(self, week_id: str | None) -> str:
        """None 이거나 없는 주차면 첫 주차로 떨어진다.

        화면이 잘못된 주차를 조용히 보여주지 않도록, 호출부는 필요하면
        `exists()` 로 먼저 확인한다.
        """
        if week_id and self.exists(week_id):
            return week_id
        default = self.default_week_id()
        if default is None:
            raise FileNotFoundError(f"주차 결과 폴더가 없다: {self.root}")
        return default

    # ------------------------------------------------------------- store

    def store(self, week_id: str | None = None) -> ResultStore:
        resolved = self.resolve(week_id)
        if resolved not in self._stores:
            self._stores[resolved] = ResultStore(self.root / resolved, resolved)
        return self._stores[resolved]

    def reload(self) -> None:
        for store in self._stores.values():
            store.reload()
        self._week_ids = None
        self._stores.clear()

    # -------------------------------------------------------------- meta

    def meta(self, week_id: str) -> WeekMeta:
        resolved = self.resolve(week_id)
        store = self.store(resolved)
        summary = store.summary

        # horizon 은 실제 timeline 에서 만든다. 요일/날짜를 상수 배열로 두지 않는다.
        timeline = store.inventory_timeline
        start = timeline["timestamp"].min().date().isoformat()
        end = timeline["timestamp"].max().date().isoformat()

        row = next(
            (r for r in self._summary_rows() if r.get("week") == _short_id(resolved)),
            {},
        )

        def num(key: str, fallback) -> float:
            value = row.get(key)
            if value in (None, ""):
                return float(fallback or 0)
            return float(value)

        return WeekMeta(
            week_id=resolved,
            short_id=_short_id(resolved),
            start=start,
            end=end,
            label=_label(resolved, start, end),
            source_folder=resolved,
            selected_train_count=int(summary.get("selected_train_count") or 0),
            need_teu=num("need_teu", summary.get("service_need_teu")),
            served_teu=num("served_teu", summary.get("rail_served_teu")),
            unserved_teu=float(summary.get("rail_unserved_teu") or 0),
            coverage=num("coverage", summary.get("rail_coverage")),
        )

    def all_meta(self) -> list[WeekMeta]:
        return [self.meta(w) for w in self.week_ids()]


registry = WeekRegistry(config.RESULT_ROOT)
