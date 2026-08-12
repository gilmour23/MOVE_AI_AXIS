"""MILP 결과 파일 로더.

- CSV 는 결과 패키지에 따라 UTF-8 또는 CP949 로 저장되어 있어 인코딩을 자동 판별한다.
- 파일은 프로세스 기동 시 1회 읽어 캐시한다. MILP 재실행 후에는 reload() 로 갱신한다.
  (사용자에게 재최적화 버튼을 노출하지 않는다 — 핸드오프 §23)
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pandas as pd

from moveai import config

_ENCODINGS = ("utf-8-sig", "cp949")


class ResultFilesMissingError(RuntimeError):
    """결과 파일을 찾지 못했을 때."""

    def __init__(self, path: Path):
        super().__init__(f"결과 파일을 찾을 수 없습니다: {path}")
        self.path = path


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise ResultFilesMissingError(path)
    last: Exception | None = None
    for enc in _ENCODINGS:
        try:
            return pd.read_csv(path, encoding=enc)
        except UnicodeDecodeError as exc:  # 다음 인코딩으로 재시도
            last = exc
    raise RuntimeError(f"인코딩을 판별하지 못했습니다: {path}") from last


class ResultStore:
    """결과 디렉터리 하나에 대한 read-only 캐시."""

    def __init__(self, result_dir: Path, input_dir: Path):
        self.result_dir = result_dir
        self.input_dir = input_dir
        # 파생 캐시(timeline)가 원본 캐시(_result_csv)를 다시 읽으므로 재진입 가능해야 한다.
        self._lock = threading.RLock()
        self._cache: dict[str, object] = {}

    # ------------------------------------------------------------------ 로딩

    def reload(self) -> None:
        with self._lock:
            self._cache.clear()

    def _cached(self, key: str, loader):
        if key not in self._cache:
            with self._lock:
                if key not in self._cache:
                    self._cache[key] = loader()
        return self._cache[key]

    def _result_csv(self, filename: str) -> pd.DataFrame:
        return self._cached(
            f"result:{filename}", lambda: _read_csv(self.result_dir / filename)
        )

    def _input_csv(self, filename: str) -> pd.DataFrame:
        return self._cached(
            f"input:{filename}", lambda: _read_csv(self.input_dir / filename)
        )

    # ------------------------------------------------------------------ 상태

    def health(self) -> dict:
        """필수 파일 존재 여부를 확인한다."""
        required = [
            "SUMMARY.json",
            "CARRIER_INVENTORY_TIMELINE.csv",
            "INVENTORY_IMPACT_SUMMARY.csv",
            "SERVICE_NEED_RESULT.csv",
            "KORAIL_TRAIN_PLAN.csv",
            "STOP_WORK_PLAN.csv",
        ]
        missing = [f for f in required if not (self.result_dir / f).exists()]
        if not (self.input_dir / "carrier_initial_inventory.csv").exists():
            missing.append("carrier_initial_inventory.csv")
        return {
            "resultDir": str(self.result_dir),
            "inputDir": str(self.input_dir),
            "ok": not missing,
            "missing": missing,
        }

    # ------------------------------------------------------------- 결과 파일

    @property
    def summary(self) -> dict:
        def load() -> dict:
            path = self.result_dir / "SUMMARY.json"
            if not path.exists():
                raise ResultFilesMissingError(path)
            return json.loads(path.read_text(encoding="utf-8"))

        return self._cached("summary", load)

    @property
    def inventory_timeline(self) -> pd.DataFrame:
        def load() -> pd.DataFrame:
            df = self._result_csv("CARRIER_INVENTORY_TIMELINE.csv").copy()
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df["date"] = df["timestamp"].dt.strftime("%Y-%m-%d")
            return df

        return self._cached("timeline", load)

    @property
    def inventory_impact(self) -> pd.DataFrame:
        return self._result_csv("INVENTORY_IMPACT_SUMMARY.csv")

    @property
    def service_need(self) -> pd.DataFrame:
        def load() -> pd.DataFrame:
            df = self._result_csv("SERVICE_NEED_RESULT.csv").copy()
            df["due_time"] = pd.to_datetime(df["due_time"])
            return df

        return self._cached("service_need", load)

    @property
    def train_plan(self) -> pd.DataFrame:
        return self._result_csv("KORAIL_TRAIN_PLAN.csv")

    @property
    def stop_work_plan(self) -> pd.DataFrame:
        return self._result_csv("STOP_WORK_PLAN.csv")

    @property
    def carrier_service_summary(self) -> pd.DataFrame:
        return self._result_csv("CARRIER_SERVICE_SUMMARY.csv")

    # ------------------------------------------------- KORAIL 운영자 관점 소스
    #
    # 아래 파일들은 전 선사 물량을 담고 있다.
    # KORAIL Control Tower 에서만 사용하고 선사 화면에는 노출하지 않는다.

    @property
    def train_operation_summary(self) -> pd.DataFrame:
        return self._result_csv("FINAL_TRAIN_OPERATION_SUMMARY.csv")

    @property
    def carrier_allocation(self) -> pd.DataFrame:
        return self._result_csv("CARRIER_ALLOCATION.csv")

    @property
    def segment_load(self) -> pd.DataFrame:
        return self._result_csv("SEGMENT_LOAD.csv")

    @property
    def all_recommendations(self) -> pd.DataFrame:
        """전 선사 추천. KORAIL 관점 집계에만 사용한다."""
        return self._result_csv("CARRIER_RECOMMENDATIONS.csv")

    @property
    def truck_comparison(self) -> pd.DataFrame:
        """MILP 산출물이 아닌 트럭 비교 입력 (data/ 폴더).

        철도 측 값과 충돌하면 MILP 결과가 우선한다.
        """

        def load() -> pd.DataFrame:
            path = (
                Path(__file__).resolve().parents[2]
                / "data"
                / "TRUCK_COMPARISON_BY_RECOMMENDATION.csv"
            )
            if not path.exists():
                return pd.DataFrame()
            return _read_csv(path)

        return self._cached("truck_comparison", load)

    @property
    def initial_inventory(self) -> pd.DataFrame:
        return self._input_csv("carrier_initial_inventory.csv")

    def recommendations(self, carrier_id: str) -> pd.DataFrame:
        """선사별 추천 파일. 파일이 없으면 빈 DataFrame 을 돌려준다.

        추천이 0건인 것과 결과 파일이 통째로 없는 것은 UI 에서 구분해야 하지만,
        선사별 추천 파일은 추천이 없으면 생성되지 않을 수 있으므로 여기서는
        빈 결과로 취급한다. (필수 파일 누락은 health() 로 판정)
        """

        def load() -> pd.DataFrame:
            path = self.result_dir / f"CARRIER_RECOMMENDATIONS_{carrier_id}.csv"
            if not path.exists():
                return pd.DataFrame()
            df = _read_csv(path)
            return df[df["carrier_id"] == carrier_id].copy() if len(df) else df

        return self._cached(f"rec:{carrier_id}", load)

    def explanation_context(self, carrier_id: str) -> pd.DataFrame:
        """챗봇 근거 데이터. 다른 carrier context 파일과 절대 섞지 않는다."""

        def load() -> pd.DataFrame:
            path = (
                self.result_dir
                / f"RECOMMENDATION_EXPLANATION_CONTEXT_{carrier_id}.csv"
            )
            if not path.exists():
                return pd.DataFrame()
            df = _read_csv(path)
            return df[df["carrier_id"] == carrier_id].copy() if len(df) else df

        return self._cached(f"explain:{carrier_id}", load)

    # ---------------------------------------------------------- carrier 격리

    def carrier_timeline(self, carrier_id: str) -> pd.DataFrame:
        """항상 이 함수를 통해서만 timeline 에 접근한다."""
        df = self.inventory_timeline
        return df[df["carrier_id"] == carrier_id]

    def known_carriers(self) -> list[str]:
        """dev mode selector 전용. 실제 선사 화면에서는 사용하지 않는다."""
        return sorted(self.inventory_timeline["carrier_id"].unique().tolist())


store = ResultStore(config.RESULT_DIR, config.INPUT_DIR)
