#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""컨테이너 트럭 OD 거리·시간·최저 운임 계산기.

사용자가 출발지, 도착지, 20FT/40FT 수량만 입력하면 NAVER Maps의 실시간
도로 경로를 조회하고, 2026 운임표와 다음 규정을 적용해 견적을 반환한다.

* 기본: 거리별 왕복운임
* 수도권 화주공장 ↔ 부산신항/광양항(의왕ICD 경유): 기점별 편도운임
* 의왕ICD ↔ 부산신항/신광양항 공컨테이너 포지셔닝: 왕복운임의 50%
* 20FT: 가능한 두 컨테이너마다 단가의 180% (2개/대 COMBINE), 잔여 1개는 단품 운임

NAVER Maps API 키는 코드에 넣지 않고 NAVER_MAPS_CLIENT_ID,
NAVER_MAPS_CLIENT_SECRET 환경변수에서 읽는다.

``--batch-weeks``를 사용하면 상위 결과 폴더의 W01/W02 추천 결과를 읽어
추천별 트럭 단일운송-철도운송 비교 CSV 3종을 생성한다.
"""

from __future__ import annotations

import argparse
import csv
import getpass
import heapq
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

import requests


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_RESULTS_ROOT = SCRIPT_DIR.parent
DEFAULT_BATCH_OUTPUT_ROOT = SCRIPT_DIR / "outputs"

# mode_selection_rev1.ipynb에서 실제 연결을 검증한 Maps API Gateway 경로와 맞춘다.
GEOCODE_API_URL = "https://maps.apigw.ntruss.com/map-geocode/v2/geocode"
DIRECTIONS_API_URL = "https://maps.apigw.ntruss.com/map-direction/v1/driving"

RATE_TYPES: dict[str, str] = {
    "안전위탁운임": "안전위탁운임",
    "운수사업자 간 운임": "운수사업자간운임",
    "안전운송운임": "안전운송운임",
}
RATE_TYPE_ORDER = tuple(RATE_TYPES)
COMBINE_20FT_MULTIPLIER = Decimal("1.80")

# 사용자 제공 산식. MJ → TJ 변환을 위해 1,000,000으로 나눈다.
TRUCK_FUEL_EFFICIENCY_KM_PER_L = Decimal("3")
RAIL_DIESEL_CONSUMPTION_L_PER_KM = Decimal("3.21")
DIESEL_HEATING_VALUE_MJ_PER_L = Decimal("35.2")
DIESEL_CO2_EMISSION_FACTOR_KG_PER_TJ = Decimal("73200")
MJ_PER_TJ = Decimal("1000000")
RAIL_EMPTY_RATE_PER_CONTAINER_KM = {
    20: Decimal("516") * Decimal("0.74"),
    40: Decimal("800") * Decimal("0.74"),
}
RAIL_HANDLING_COST_PER_CONTAINER_KRW = {
    20: 16_000,
    40: 20_000,
}


@dataclass(frozen=True)
class Hub:
    code: str
    name: str
    address: str
    is_port: bool = False


HUBS: dict[str, Hub] = {
    "UIWANG": Hub("UIWANG", "의왕ICD", "경기 의왕시 오봉로 168"),
    "BUGANG": Hub(
        "BUGANG", "부강화물역 CY", "세종 연동면 연청로 745-86 컨테이너화물조작장"
    ),
    "YAKMOK": Hub("YAKMOK", "약목역 CY", "경북 칠곡군 약목면 칠곡대로 635"),
    "BUSAN": Hub("BUSAN", "부산신항(북철송장역)", "부산 강서구 신항남로 330", True),
    "DONGSAN": Hub("DONGSAN", "동산역 CY", "전북 전주시 덕진구 고랑동 716-1"),
    "GWANGYANG": Hub("GWANGYANG", "신광양항", "전남 광양시 항만대로 755", True),
}

# 사용자 입력에서 허용하는 거점 별칭. 공백·괄호·하이픈은 무시해서 비교한다.
HUB_ALIASES: dict[str, str] = {
    "의왕icd": "UIWANG",
    "의왕icd오봉역": "UIWANG",
    "의왕": "UIWANG",
    "오봉역": "UIWANG",
    "오봉": "UIWANG",
    "부강화물역": "BUGANG",
    "부강": "BUGANG",
    "부강화물역cy": "BUGANG",
    "부강화물역간이역": "BUGANG",
    "약목역": "YAKMOK",
    "약목역cy": "YAKMOK",
    "약목": "YAKMOK",
    "부산신항": "BUSAN",
    "부산신항북철송장역": "BUSAN",
    "부산": "BUSAN",
    "동산역": "DONGSAN",
    "동산역cy": "DONGSAN",
    "동산역간이역": "DONGSAN",
    "동산": "DONGSAN",
    "신광양항": "GWANGYANG",
    "신광양": "GWANGYANG",
    "광양": "GWANGYANG",
    "광양항": "GWANGYANG",
}
# 기점별 편도 운임표의 노선명은 입력 거점명과 다르므로 명시적으로 연결한다.
PORT_TO_ONE_WAY_ROUTE = {
    "BUSAN": "부산신항↔의왕ICD",
    "GWANGYANG": "광양항↔의왕ICD",
}


class HttpClient(Protocol):
    def get(self, url: str, **kwargs: Any) -> Any:
        """requests.Session.get과 호환되는 최소 인터페이스."""


def _compact(text: str) -> str:
    """주소/거점명 비교용으로 의미 없는 기호를 제거한다."""
    return re.sub(r"[\s\-_,·()（）]", "", str(text)).lower()


for _hub in HUBS.values():
    HUB_ALIASES[_compact(_hub.address)] = _hub.code
    HUB_ALIASES[_compact(_hub.code)] = _hub.code
    HUB_ALIASES[_compact(_hub.name)] = _hub.code


def _admin_compact(text: str) -> str:
    """강원도와 강원특별자치도를 같은 행정구역으로 취급한다."""
    return _compact(text).replace("강원도", "강원특별자치도")


def _as_decimal(value: Any, column: str) -> Decimal:
    try:
        return Decimal(str(value).replace(",", "").strip())
    except Exception as error:  # csv 데이터 오류를 명확히 알려 주기 위해 보존한다.
        raise ValueError(f"운임표의 {column} 값이 숫자가 아닙니다: {value!r}") from error


def _round_half_up_krw(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _round_to_nearest_hundred_krw(value: Decimal) -> int:
    """철도 운임의 '100원 미만 반올림'을 컨테이너 1개 운임에 적용한다."""
    return int(value.quantize(Decimal("1E2"), rounding=ROUND_HALF_UP))


def _diesel_co2_kg(fuel_liters: Decimal) -> float:
    return float(
        fuel_liters
        * DIESEL_HEATING_VALUE_MJ_PER_L
        * DIESEL_CO2_EMISSION_FACTOR_KG_PER_TJ
        / MJ_PER_TJ
    )


def _truck_co2_kg(distance_km: float, vehicle_count: int) -> float:
    """트럭 대수와 실제 NAVER 도로거리를 반영한 총 CO₂ 배출량."""
    fuel_liters = Decimal(str(distance_km)) * vehicle_count / TRUCK_FUEL_EFFICIENCY_KM_PER_L
    return _diesel_co2_kg(fuel_liters)


def _rail_co2_kg(distance_km: float) -> float:
    """철도 서비스 1회 운행의 CO₂ 배출량.

    제공된 3.21 L/km는 열차 단위 계수이므로, 컨테이너 수량으로 중복 곱하지 않는다.
    """
    fuel_liters = Decimal(str(distance_km)) * RAIL_DIESEL_CONSUMPTION_L_PER_KM
    return _diesel_co2_kg(fuel_liters)


def _tariff_distance_km(distance_km: float) -> int:
    """실거리의 소수 첫째 자리에서 반올림한 km를 운임표 구간으로 쓴다."""
    return max(1, int(Decimal(str(distance_km)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)))


def _container_size_ft(value: str) -> int:
    """AXIS 추천 파일의 20FT/40FT 값을 검증해 숫자 규격으로 변환한다."""
    try:
        size = int(str(value).upper().replace("FT", "").strip())
    except ValueError as error:
        raise ValueError(f"지원하지 않는 컨테이너 규격입니다: {value!r}") from error
    if size not in {20, 40}:
        raise ValueError(f"컨테이너 규격은 20FT 또는 40FT여야 합니다: {value!r}")
    return size


@dataclass(frozen=True)
class Endpoint:
    input_value: str
    display_name: str
    route_address: str
    hub: Hub | None

    @property
    def is_address(self) -> bool:
        return self.hub is None


@dataclass(frozen=True)
class RoadMetric:
    distance_km: float
    duration_minutes: float
    source: str


@dataclass(frozen=True)
class RoundTripRateRow:
    distance_km: int
    rates: Mapping[str, Mapping[int, Decimal]]


@dataclass(frozen=True)
class OneWayRateRow:
    route_name: str
    sido: str
    sigungu: str
    eupmyeondong: str
    distance_km: int
    rates: Mapping[str, Mapping[int, Decimal]]


@dataclass(frozen=True)
class FareCandidate:
    rate_type: str
    total_cost_krw: int
    fare_20ft_per_container_krw: Decimal | None
    fare_40ft_per_container_krw: Decimal | None
    truck_count_20ft: int
    truck_count_40ft: int
    combine_20ft_pair_count: int
    combine_20ft_applied: bool


@dataclass(frozen=True)
class QuoteResult:
    origin: str
    destination: str
    resolved_origin: str
    resolved_destination: str
    road: RoadMetric
    fare_policy: str
    fare_source: str
    tariff_distance_km: int
    location_match: str | None
    count_20ft: int
    count_40ft: int
    selected: FareCandidate
    alternatives: tuple[FareCandidate, ...]

    def as_dict(self) -> dict[str, Any]:
        """CLI와 웹/서비스 레이어에서 그대로 직렬화할 수 있는 결과."""
        result = asdict(self)
        result["road"] = {
            **result["road"],
            "distance_km": round(self.road.distance_km, 3),
            "duration_minutes": round(self.road.duration_minutes, 1),
        }
        for candidate in [result["selected"], *result["alternatives"]]:
            for key in ("fare_20ft_per_container_krw", "fare_40ft_per_container_krw"):
                if candidate[key] is not None:
                    candidate[key] = float(candidate[key])
        return result


class NaverMapsClient:
    """NAVER Geocoding + Directions 5 API로 실제 도로 OD를 구한다."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        vehicle_type: int = 5,
        route_option: str = "traoptimal",
        session: HttpClient | None = None,
    ) -> None:
        if not client_id or not client_secret:
            raise EnvironmentError(
                "NAVER Maps API 키가 없습니다. NAVER_MAPS_CLIENT_ID와 "
                "NAVER_MAPS_CLIENT_SECRET 환경변수를 설정하세요."
            )
        for label, value in (("NAVER_MAPS_CLIENT_ID", client_id), ("NAVER_MAPS_CLIENT_SECRET", client_secret)):
            try:
                value.encode("ascii")
            except UnicodeEncodeError as error:
                raise ValueError(
                    f"{label}에 한글 또는 특수 문구가 들어 있습니다. "
                    "'네이버_API_Key_ID' 같은 예시 문구가 아니라 NAVER Cloud 콘솔의 "
                    "Maps Application에서 발급된 실제 Client ID/Client Secret을 그대로 넣으세요."
                ) from error
        if vehicle_type not in {1, 2, 3, 4, 5, 6}:
            raise ValueError("vehicle_type은 NAVER Maps 차종 코드 1~6 중 하나여야 합니다.")
        self.headers = {
            "x-ncp-apigw-api-key-id": client_id,
            "x-ncp-apigw-api-key": client_secret,
        }
        self.vehicle_type = vehicle_type
        self.route_option = route_option
        self.session = session or requests.Session()
        self._geocode_cache: dict[str, tuple[float, float]] = {}
        self._route_cache: dict[tuple[str, str], RoadMetric] = {}

    @classmethod
    def from_environment(cls, **kwargs: Any) -> "NaverMapsClient":
        """환경변수가 없으면 터미널에서 키를 묻는다.

        mode_selection_rev1.ipynb와 같은 방식이다. Secret은 getpass를 사용해
        화면·명령 기록에 표시하지 않는다.
        """
        client_id = os.getenv("NAVER_MAPS_CLIENT_ID", "").strip()
        client_secret = os.getenv("NAVER_MAPS_CLIENT_SECRET", "").strip()
        if not client_id:
            client_id = input("NAVER Maps Client ID: ").strip()
            if client_id:
                os.environ["NAVER_MAPS_CLIENT_ID"] = client_id
        if not client_secret:
            client_secret = getpass.getpass("NAVER Maps Client Secret: ").strip()
            if client_secret:
                os.environ["NAVER_MAPS_CLIENT_SECRET"] = client_secret
        return cls(client_id, client_secret, **kwargs)

    def geocode(self, address: str) -> tuple[float, float]:
        if address in self._geocode_cache:
            return self._geocode_cache[address]
        response = self.session.get(
            GEOCODE_API_URL,
            headers={**self.headers, "Accept": "application/json"},
            params={"query": address},
            timeout=20,
        )
        if not response.ok:
            self._raise_api_error("Geocoding", response)
        addresses = response.json().get("addresses", [])
        if not addresses:
            raise ValueError(f"NAVER 지도에서 주소를 찾지 못했습니다: {address}")
        point = (float(addresses[0]["x"]), float(addresses[0]["y"]))
        self._geocode_cache[address] = point
        return point

    def route(self, origin: str, destination: str) -> RoadMetric:
        cache_key = (origin, destination)
        if cache_key in self._route_cache:
            return self._route_cache[cache_key]
        start = self.geocode(origin)
        goal = self.geocode(destination)
        response = self.session.get(
            DIRECTIONS_API_URL,
            headers=self.headers,
            params={
                "start": f"{start[0]},{start[1]}",
                "goal": f"{goal[0]},{goal[1]}",
                "option": self.route_option,
                "cartype": self.vehicle_type,
                "fueltype": "diesel",
                "lang": "ko",
            },
            timeout=30,
        )
        if not response.ok:
            self._raise_api_error("Directions 5", response)
        body = response.json()
        routes = body.get("route", {}).get(self.route_option, [])
        if body.get("code") not in {0, "0"} or not routes:
            raise RuntimeError(f"NAVER 도로경로 결과가 없습니다: {body.get('message', body)}")
        summary = routes[0]["summary"]
        metric = RoadMetric(
            distance_km=float(summary["distance"]) / 1_000,
            duration_minutes=float(summary["duration"]) / 1_000 / 60,
            source=f"NAVER Maps Directions 5 / {self.route_option}",
        )
        self._route_cache[cache_key] = metric
        return metric

    @staticmethod
    def _raise_api_error(api_name: str, response: Any) -> None:
        """구독 누락(오류 210)을 실행자가 바로 해결할 수 있게 설명한다."""
        try:
            body = response.json()
            error = body.get("error", {})
            error_code = str(error.get("errorCode", ""))
        except Exception:
            error_code = ""
        if response.status_code == 401 and error_code == "210":
            raise RuntimeError(
                f"NAVER {api_name} API가 현재 키에 구독되지 않았습니다. "
                "NAVER Cloud 콘솔 > AI NAVER API > Application > 해당 Maps 앱 > 수정에서 "
                f"'{api_name}'를 선택해 저장한 뒤, 그 앱의 Client ID/Client Secret으로 다시 실행하세요."
            )
        raise RuntimeError(f"NAVER {api_name} 호출 실패 ({response.status_code}): {response.text}")


class TariffCatalog:
    """거리별 왕복 및 기점별 편도 운임 CSV를 검증해 메모리에 적재한다."""

    def __init__(self, roundtrip_rows: Mapping[int, RoundTripRateRow], one_way_rows: Iterable[OneWayRateRow]):
        self.roundtrip_rows = dict(roundtrip_rows)
        self.one_way_rows = tuple(one_way_rows)
        if not self.roundtrip_rows:
            raise ValueError("왕복 운임표에 데이터가 없습니다.")

    @classmethod
    def from_csv(cls, roundtrip_path: Path, one_way_path: Path | None = None) -> "TariffCatalog":
        roundtrip_rows = cls._load_roundtrip(roundtrip_path)
        one_way_rows = cls._load_one_way(one_way_path) if one_way_path else []
        return cls(roundtrip_rows, one_way_rows)

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        if not path.is_file():
            raise FileNotFoundError(f"운임표 파일을 찾지 못했습니다: {path}")
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            return list(csv.DictReader(file))

    @staticmethod
    def _rates(row: Mapping[str, str]) -> dict[str, dict[int, Decimal]]:
        result: dict[str, dict[int, Decimal]] = {}
        for rate_type, column_label in RATE_TYPES.items():
            result[rate_type] = {
                size: _as_decimal(row[f"{size}FT_{column_label}_원"], f"{size}FT_{column_label}_원")
                for size in (20, 40)
            }
        return result

    @classmethod
    def _load_roundtrip(cls, path: Path) -> dict[int, RoundTripRateRow]:
        rows: dict[int, RoundTripRateRow] = {}
        for row in cls._read_csv(path):
            try:
                distance = int(_as_decimal(row["구간거리_km"], "구간거리_km"))
            except KeyError as error:
                raise ValueError(f"{path.name}에 구간거리_km 열이 없습니다.") from error
            if distance in rows:
                raise ValueError(f"{path.name}에 중복 거리 구간({distance}km)이 있습니다.")
            rows[distance] = RoundTripRateRow(distance, cls._rates(row))
        return rows

    @classmethod
    def _load_one_way(cls, path: Path) -> list[OneWayRateRow]:
        rows: list[OneWayRateRow] = []
        required = {"기점_노선", "시도", "시군구", "읍면동", "구간거리_km"}
        for row in cls._read_csv(path):
            missing = required - set(row)
            if missing:
                raise ValueError(f"{path.name}에 필수 열이 없습니다: {', '.join(sorted(missing))}")
            rows.append(
                OneWayRateRow(
                    route_name=row["기점_노선"],
                    sido=row["시도"],
                    sigungu=row["시군구"],
                    eupmyeondong=row["읍면동"],
                    distance_km=int(_as_decimal(row["구간거리_km"], "구간거리_km")),
                    rates=cls._rates(row),
                )
            )
        return rows

    def roundtrip(self, distance_km: int) -> RoundTripRateRow:
        if distance_km not in self.roundtrip_rows:
            minimum, maximum = min(self.roundtrip_rows), max(self.roundtrip_rows)
            raise ValueError(
                f"운임 적용거리 {distance_km}km가 왕복 운임표 범위 {minimum}~{maximum}km를 벗어납니다."
            )
        return self.roundtrip_rows[distance_km]

    def match_one_way(
        self, route_name: str, address: str, road_distance_km: float
    ) -> tuple[OneWayRateRow, str] | None:
        """주소와 편도표 행을 매칭한다.

        읍면동까지 입력하면 그 행을 정확히 사용한다. 시군구까지만 있으면 실제
        NAVER OD 거리와 가장 가까운 행을 사용해, 임의의 최저 운임 행을 고르지 않는다.
        """
        address_key = _admin_compact(address)
        rows = [
            row
            for row in self.one_way_rows
            if row.route_name == route_name
            and _admin_compact(row.sido) in address_key
            and self._sigungu_matches(row.sigungu, address_key)
        ]
        if not rows:
            return None
        exact_dong_rows = [
            row for row in rows if row.eupmyeondong and _admin_compact(row.eupmyeondong) in address_key
        ]
        if exact_dong_rows:
            selected = min(exact_dong_rows, key=lambda row: abs(row.distance_km - road_distance_km))
            quality = "주소의 읍면동 정확 매칭"
        else:
            selected = min(rows, key=lambda row: (abs(row.distance_km - road_distance_km), row.eupmyeondong))
            quality = "시군구 입력: NAVER 도로거리와 가장 가까운 읍면동 행 선택"
        return selected, quality

    @staticmethod
    def _sigungu_matches(sigungu: str, address_key: str) -> bool:
        key = _admin_compact(sigungu)
        if key in address_key:
            return True
        # '안산시'처럼 구를 생략한 주소만 안산시 단원구·상록구를 모두 후보로 둔다.
        # 입력에 '단원구'가 있으면 '상록구' 행이 섞이지 않도록 한다.
        city_match = re.match(r"(.+?시)", sigungu)
        if not city_match:
            return False
        city_key = _admin_compact(city_match.group(1))
        remaining_address = address_key.split(city_key, 1)[-1] if city_key in address_key else ""
        has_district_after_city = bool(re.match(r"[가-힣]+구", remaining_address))
        return city_key in address_key and not has_district_after_city


@dataclass(frozen=True)
class RailService:
    """TRAIN_CANDIDATE.csv의 단일 철도 OD 후보."""

    train_id: str
    origin_hub: str
    destination_hub: str
    path: tuple[str, ...]
    distance_km: float
    duration_minutes: float


@dataclass(frozen=True)
class RailRoute:
    """직접 후보 또는 여러 후보를 연결해 만든 철도 경로."""

    origin_hub: str
    destination_hub: str
    path: tuple[str, ...]
    train_ids: tuple[str, ...]
    distance_km: float
    duration_minutes: float
    source: str
    uses_connected_od: bool


class TrainCatalog:
    """변경 가능한 TRAIN_CANDIDATE.csv에서 철도 OD 거리·시간을 읽는다.

    같은 OD에 시간표 후보가 여러 개면 운행시간이 가장 짧은 후보를 사용한다.
    직접 OD가 없으면 저장된 후보 OD를 연결해 가장 빠른 철도 경로를 찾는다.
    """

    REQUIRED_COLUMNS = {
        "train_id", "origin_terminal", "destination_terminal", "path",
        "origin_departure_time", "destination_arrival_time", "service_distance_km",
    }

    def __init__(self, services: Iterable[RailService], source_name: str) -> None:
        self.source_name = source_name
        grouped: dict[tuple[str, str], list[RailService]] = {}
        for service in services:
            grouped.setdefault((service.origin_hub, service.destination_hub), []).append(service)
        if not grouped:
            raise ValueError(f"{source_name}에 철도 운행 후보가 없습니다.")
        self._best_direct: dict[tuple[str, str], RailService] = {
            pair: min(candidates, key=lambda item: (item.duration_minutes, item.distance_km, item.train_id))
            for pair, candidates in grouped.items()
        }
        self._outgoing: dict[str, list[RailService]] = {}
        for service in self._best_direct.values():
            self._outgoing.setdefault(service.origin_hub, []).append(service)
        for services_for_hub in self._outgoing.values():
            services_for_hub.sort(key=lambda item: (item.destination_hub, item.duration_minutes, item.train_id))

    @classmethod
    def from_csv(cls, path: Path) -> "TrainCatalog":
        if not path.is_file():
            raise FileNotFoundError(f"TRAIN_CANDIDATE CSV를 찾지 못했습니다: {path}")
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            columns = set(reader.fieldnames or [])
            missing = cls.REQUIRED_COLUMNS - columns
            if missing:
                raise ValueError(
                    f"{path.name}에 철도 OD 계산 필수 열이 없습니다: {', '.join(sorted(missing))}"
                )
            services = [cls._service_from_row(row, path.name) for row in reader]
        return cls(services, path.name)

    @staticmethod
    def _terminal_to_hub(value: str, source_name: str) -> str:
        hub_code = HUB_ALIASES.get(_compact(value))
        if hub_code is None:
            raise ValueError(
                f"{source_name}의 철도 터미널 {value!r}를 6개 거점으로 해석하지 못했습니다. "
                "UIWANG/BUGANG/YAKMOK/BUSAN/DONGSAN/GWANGYANG 또는 대응 별칭을 사용하세요."
            )
        return hub_code

    @staticmethod
    def _parse_schedule_time(value: str, column: str, source_name: str) -> datetime:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError as error:
            try:
                return datetime.strptime(text, "%H:%M")
            except ValueError:
                raise ValueError(
                    f"{source_name}의 {column} 값이 ISO 날짜·시간 또는 HH:MM 형식이 아닙니다: {value!r}"
                ) from error

    @classmethod
    def _service_from_row(cls, row: Mapping[str, str], source_name: str) -> RailService:
        origin = cls._terminal_to_hub(row["origin_terminal"], source_name)
        destination = cls._terminal_to_hub(row["destination_terminal"], source_name)
        path_values = tuple(
            cls._terminal_to_hub(value, source_name)
            for value in str(row["path"]).split("|")
            if str(value).strip()
        )
        path = path_values or (origin, destination)
        if path[0] != origin or path[-1] != destination:
            raise ValueError(
                f"{source_name}의 {row['train_id']} path 첫·마지막 거점이 origin/destination과 일치하지 않습니다."
            )
        departure = cls._parse_schedule_time(row["origin_departure_time"], "origin_departure_time", source_name)
        arrival = cls._parse_schedule_time(row["destination_arrival_time"], "destination_arrival_time", source_name)
        duration_minutes = (arrival - departure).total_seconds() / 60
        if duration_minutes <= 0 and departure.date() == arrival.date():
            duration_minutes += 24 * 60
        if duration_minutes <= 0:
            raise ValueError(
                f"{source_name}의 {row['train_id']} 도착시각이 출발시각보다 빠릅니다."
            )
        distance_km = float(_as_decimal(row["service_distance_km"], "service_distance_km"))
        if distance_km <= 0:
            raise ValueError(f"{source_name}의 {row['train_id']} service_distance_km는 0보다 커야 합니다.")
        return RailService(
            train_id=str(row["train_id"]),
            origin_hub=origin,
            destination_hub=destination,
            path=path,
            distance_km=distance_km,
            duration_minutes=duration_minutes,
        )

    def route(self, origin_hub: str, destination_hub: str) -> RailRoute:
        """OD의 직접 후보를 우선 사용하고, 없을 때만 철도 후보 OD를 연결한다."""
        if origin_hub == destination_hub:
            return RailRoute(
                origin_hub, destination_hub, (origin_hub,), (), 0.0, 0.0,
                f"{self.source_name}: 동일 거점으로 철도 구간 없음", False,
            )
        direct = self._best_direct.get((origin_hub, destination_hub))
        if direct:
            return RailRoute(
                origin_hub=origin_hub,
                destination_hub=destination_hub,
                path=direct.path,
                train_ids=(direct.train_id,),
                distance_km=direct.distance_km,
                duration_minutes=direct.duration_minutes,
                source=f"{self.source_name}: {direct.train_id}",
                uses_connected_od=False,
            )
        return self._connected_route(origin_hub, destination_hub)

    def _connected_route(self, origin_hub: str, destination_hub: str) -> RailRoute:
        """직접 OD가 없을 때 운행시간 기준 최단 경로를 Dijkstra로 찾는다."""
        queue: list[tuple[float, float, int, str, tuple[str, ...], tuple[RailService, ...]]] = []
        sequence = 0
        heapq.heappush(queue, (0.0, 0.0, sequence, origin_hub, (origin_hub,), ()))
        best: dict[str, tuple[float, float]] = {origin_hub: (0.0, 0.0)}
        while queue:
            duration, distance, _, current, hubs, services = heapq.heappop(queue)
            if (duration, distance) != best.get(current):
                continue
            if current == destination_hub:
                path = tuple(hub for service in services for hub in service.path[:-1]) + (destination_hub,)
                return RailRoute(
                    origin_hub=origin_hub,
                    destination_hub=destination_hub,
                    path=path,
                    train_ids=tuple(service.train_id for service in services),
                    distance_km=distance,
                    duration_minutes=duration,
                    source=f"{self.source_name}: 직접 OD 부재로 {len(services)}개 철도 OD 연결",
                    uses_connected_od=True,
                )
            for service in self._outgoing.get(current, []):
                candidate = (duration + service.duration_minutes, distance + service.distance_km)
                if candidate < best.get(service.destination_hub, (float("inf"), float("inf"))):
                    best[service.destination_hub] = candidate
                    sequence += 1
                    heapq.heappush(
                        queue,
                        (
                            candidate[0], candidate[1], sequence, service.destination_hub,
                            hubs + (service.destination_hub,), services + (service,),
                        ),
                    )
        raise ValueError(
            f"{self.source_name}에서 철도 경로를 찾지 못했습니다: {origin_hub} → {destination_hub}"
        )


@dataclass(frozen=True)
class TransportLeg:
    mode: str
    origin: str
    destination: str
    path: str
    distance_km: float
    duration_minutes: float
    cost_krw: int
    co2_kg: float
    source: str
    rate_type: str | None = None
    vehicle_count: int | None = None
    fare_policy: str | None = None
    train_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TransportPlan:
    name: str
    total_distance_km: float
    total_duration_minutes: float
    total_cost_krw: int
    total_co2_kg: float
    legs: tuple[TransportLeg, ...]


@dataclass(frozen=True)
class ComparisonDifference:
    """복합운송 - 트럭 단일운송. 음수면 복합운송이 더 낮다는 뜻이다."""

    cost_krw: int
    duration_minutes: float
    co2_kg: float


@dataclass(frozen=True)
class TransportComparisonResult:
    origin: str
    destination: str
    count_20ft: int
    count_40ft: int
    direct_truck: TransportPlan
    truck_rail_intermodal: TransportPlan
    intermodal_minus_direct: ComparisonDifference
    carbon_method: str

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for plan_name in ("direct_truck", "truck_rail_intermodal"):
            plan = result[plan_name]
            plan["total_distance_km"] = round(plan["total_distance_km"], 3)
            plan["total_duration_minutes"] = round(plan["total_duration_minutes"], 1)
            plan["total_co2_kg"] = round(plan["total_co2_kg"], 3)
            for leg in plan["legs"]:
                leg["distance_km"] = round(leg["distance_km"], 3)
                leg["duration_minutes"] = round(leg["duration_minutes"], 1)
                leg["co2_kg"] = round(leg["co2_kg"], 3)
        result["intermodal_minus_direct"]["duration_minutes"] = round(
            result["intermodal_minus_direct"]["duration_minutes"], 1
        )
        result["intermodal_minus_direct"]["co2_kg"] = round(
            result["intermodal_minus_direct"]["co2_kg"], 3
        )
        return result


class TruckTransportCalculator:
    """규정 적용 순서를 고정한 단일 OD 견적 서비스."""

    def __init__(self, tariffs: TariffCatalog, router: Any) -> None:
        self.tariffs = tariffs
        self.router = router

    @staticmethod
    def resolve_endpoint(value: str) -> Endpoint:
        key = _compact(value)
        hub_code = HUB_ALIASES.get(key)
        if hub_code:
            hub = HUBS[hub_code]
            return Endpoint(value, hub.name, hub.address, hub)
        if not str(value).strip():
            raise ValueError("출발지와 도착지는 비어 있을 수 없습니다.")
        return Endpoint(value, value.strip(), value.strip(), None)

    def calculate(
        self,
        origin: str,
        destination: str,
        *,
        count_20ft: int = 0,
        count_40ft: int = 0,
    ) -> QuoteResult:
        self._validate_counts(count_20ft, count_40ft)
        origin_endpoint = self.resolve_endpoint(origin)
        destination_endpoint = self.resolve_endpoint(destination)
        return self._quote_for_endpoints(
            origin_endpoint, destination_endpoint, count_20ft=count_20ft, count_40ft=count_40ft
        )

    def calculate_comparison(
        self,
        origin: str,
        destination: str,
        *,
        count_20ft: int,
        count_40ft: int,
        train_catalog: TrainCatalog,
    ) -> TransportComparisonResult:
        """트럭 단일운송과 가장 가까운 CY를 이용한 트럭-철도 복합운송을 비교한다."""
        self._validate_counts(count_20ft, count_40ft)
        origin_endpoint = self.resolve_endpoint(origin)
        destination_endpoint = self.resolve_endpoint(destination)
        direct_quote = self._quote_for_endpoints(
            origin_endpoint, destination_endpoint, count_20ft=count_20ft, count_40ft=count_40ft
        )
        direct_plan = self._plan("트럭 단일운송", (self._truck_leg(direct_quote),))

        rail_origin, origin_access_road = self._nearest_rail_hub(origin_endpoint, address_is_origin=True)
        rail_destination, destination_access_road = self._nearest_rail_hub(
            destination_endpoint, address_is_origin=False
        )
        intermodal_legs: list[TransportLeg] = []
        if origin_access_road is not None:
            origin_access_quote = self._quote_for_endpoints(
                origin_endpoint,
                rail_origin,
                count_20ft=count_20ft,
                count_40ft=count_40ft,
                road=origin_access_road,
            )
            intermodal_legs.append(self._truck_leg(origin_access_quote))

        rail_route = train_catalog.route(rail_origin.hub.code, rail_destination.hub.code)
        if rail_route.distance_km > 0:
            intermodal_legs.append(self._rail_leg(rail_route, count_20ft, count_40ft))

        if destination_access_road is not None:
            destination_access_quote = self._quote_for_endpoints(
                rail_destination,
                destination_endpoint,
                count_20ft=count_20ft,
                count_40ft=count_40ft,
                road=destination_access_road,
            )
            intermodal_legs.append(self._truck_leg(destination_access_quote))

        intermodal_plan = self._plan("트럭-철도 복합운송", tuple(intermodal_legs))
        return TransportComparisonResult(
            origin=origin,
            destination=destination,
            count_20ft=count_20ft,
            count_40ft=count_40ft,
            direct_truck=direct_plan,
            truck_rail_intermodal=intermodal_plan,
            intermodal_minus_direct=ComparisonDifference(
                cost_krw=intermodal_plan.total_cost_krw - direct_plan.total_cost_krw,
                duration_minutes=intermodal_plan.total_duration_minutes - direct_plan.total_duration_minutes,
                co2_kg=intermodal_plan.total_co2_kg - direct_plan.total_co2_kg,
            ),
            carbon_method=(
                "트럭: (NAVER 도로거리 × 투입 차량대수 ÷ 3km/L) × 35.2MJ/L × "
                "73,200kgCO2/TJ ÷ 1,000,000; 철도: (철도거리 × 3.21L/km) × "
                "35.2MJ/L × 73,200kgCO2/TJ ÷ 1,000,000 (철도 서비스 1회 기준)"
            ),
        )

    def _quote_for_endpoints(
        self,
        origin_endpoint: Endpoint,
        destination_endpoint: Endpoint,
        *,
        count_20ft: int,
        count_40ft: int,
        road: RoadMetric | None = None,
    ) -> QuoteResult:
        """해석이 끝난 두 endpoint에 같은 트럭 운임 규칙을 적용한다."""
        road = road or self.router.route(origin_endpoint.route_address, destination_endpoint.route_address)
        tariff_row, policy, source, location_match = self._select_tariff(
            origin_endpoint, destination_endpoint, road.distance_km
        )
        candidates = tuple(
            self._cost_by_rate_type(
                rate_type,
                tariff_row.rates[rate_type],
                count_20ft,
                count_40ft,
            )
            for rate_type in RATE_TYPE_ORDER
        )
        selected = min(candidates, key=lambda item: (item.total_cost_krw, RATE_TYPE_ORDER.index(item.rate_type)))
        return QuoteResult(
            origin=origin_endpoint.input_value,
            destination=destination_endpoint.input_value,
            resolved_origin=origin_endpoint.route_address,
            resolved_destination=destination_endpoint.route_address,
            road=road,
            fare_policy=policy,
            fare_source=source,
            tariff_distance_km=tariff_row.distance_km,
            location_match=location_match,
            count_20ft=count_20ft,
            count_40ft=count_40ft,
            selected=selected,
            alternatives=candidates,
        )

    @staticmethod
    def _hub_endpoint(hub: Hub) -> Endpoint:
        return Endpoint(hub.name, hub.name, hub.address, hub)

    def _nearest_rail_hub(
        self, endpoint: Endpoint, *, address_is_origin: bool
    ) -> tuple[Endpoint, RoadMetric | None]:
        """주소는 NAVER 도로거리 최솟값의 CY에 연결하고, 이미 거점이면 그대로 둔다."""
        if endpoint.hub is not None:
            return endpoint, None
        candidates: list[tuple[RoadMetric, Endpoint]] = []
        for hub in HUBS.values():
            hub_endpoint = self._hub_endpoint(hub)
            if address_is_origin:
                road = self.router.route(endpoint.route_address, hub_endpoint.route_address)
            else:
                road = self.router.route(hub_endpoint.route_address, endpoint.route_address)
            candidates.append((road, hub_endpoint))
        road, hub_endpoint = min(
            candidates, key=lambda item: (item[0].distance_km, item[0].duration_minutes, item[1].hub.code)
        )
        return hub_endpoint, road

    @staticmethod
    def _truck_leg(quote: QuoteResult) -> TransportLeg:
        vehicle_count = quote.selected.truck_count_20ft + quote.selected.truck_count_40ft
        return TransportLeg(
            mode="truck",
            origin=quote.origin,
            destination=quote.destination,
            path=f"{quote.resolved_origin} → {quote.resolved_destination}",
            distance_km=quote.road.distance_km,
            duration_minutes=quote.road.duration_minutes,
            cost_krw=quote.selected.total_cost_krw,
            co2_kg=_truck_co2_kg(quote.road.distance_km, vehicle_count),
            source=quote.fare_source,
            rate_type=quote.selected.rate_type,
            vehicle_count=vehicle_count,
            fare_policy=quote.fare_policy,
        )

    @staticmethod
    def _rail_leg(rail_route: RailRoute, count_20ft: int, count_40ft: int) -> TransportLeg:
        fare_20ft = _round_to_nearest_hundred_krw(
            RAIL_EMPTY_RATE_PER_CONTAINER_KM[20] * Decimal(str(rail_route.distance_km))
        )
        fare_40ft = _round_to_nearest_hundred_krw(
            RAIL_EMPTY_RATE_PER_CONTAINER_KM[40] * Decimal(str(rail_route.distance_km))
        )
        distance_fare = fare_20ft * count_20ft + fare_40ft * count_40ft
        handling_cost = (
            RAIL_HANDLING_COST_PER_CONTAINER_KRW[20] * count_20ft
            + RAIL_HANDLING_COST_PER_CONTAINER_KRW[40] * count_40ft
        )
        cost = distance_fare + handling_cost
        path_names = " → ".join(HUBS[hub_code].name for hub_code in rail_route.path)
        return TransportLeg(
            mode="rail",
            origin=HUBS[rail_route.origin_hub].name,
            destination=HUBS[rail_route.destination_hub].name,
            path=path_names,
            distance_km=rail_route.distance_km,
            duration_minutes=rail_route.duration_minutes,
            cost_krw=cost,
            co2_kg=_rail_co2_kg(rail_route.distance_km),
            source=rail_route.source,
            fare_policy=(
                "공컨테이너 철도운임: 20FT 516×0.74원/컨테이너-km, "
                "40FT 800×0.74원/컨테이너-km; 컨테이너 1개 운임별 100원 미만 반올림; "
                "상하차비: 20FT 16,000원/개, 40FT 20,000원/개"
            ),
            train_ids=rail_route.train_ids,
        )

    @staticmethod
    def _plan(name: str, legs: tuple[TransportLeg, ...]) -> TransportPlan:
        return TransportPlan(
            name=name,
            total_distance_km=sum(leg.distance_km for leg in legs),
            total_duration_minutes=sum(leg.duration_minutes for leg in legs),
            total_cost_krw=sum(leg.cost_krw for leg in legs),
            total_co2_kg=sum(leg.co2_kg for leg in legs),
            legs=legs,
        )

    @staticmethod
    def _validate_counts(count_20ft: int, count_40ft: int) -> None:
        if count_20ft < 0 or count_40ft < 0:
            raise ValueError("컨테이너 수량은 0 이상이어야 합니다.")
        if count_20ft + count_40ft == 0:
            raise ValueError("20FT 또는 40FT 컨테이너를 적어도 1개 입력하세요.")

    def _select_tariff(
        self, origin: Endpoint, destination: Endpoint, road_distance_km: float
    ) -> tuple[RoundTripRateRow | OneWayRateRow, str, str, str | None]:
        hub_codes = {endpoint.hub.code for endpoint in (origin, destination) if endpoint.hub}
        port_endpoint = next(
            (endpoint for endpoint in (origin, destination) if endpoint.hub and endpoint.hub.is_port), None
        )

        # 포지셔닝은 편도표보다 우선한다. 의왕ICD와 항만 사이 공컨테이너 공급은
        # 거리별 왕복운임의 50%라는 독립 규정을 그대로 적용한다.
        if "UIWANG" in hub_codes and port_endpoint and len(hub_codes) == 2:
            distance = _tariff_distance_km(road_distance_km)
            base = self.tariffs.roundtrip(distance)
            half_rates = {
                rate_type: {size: amount * Decimal("0.5") for size, amount in size_rates.items()}
                for rate_type, size_rates in base.rates.items()
            }
            return (
                RoundTripRateRow(base.distance_km, half_rates),
                "포지셔닝: 의왕ICD ↔ 항만 공컨테이너 공급운송, 거리별 왕복운임의 50% 적용",
                "수출입컨테이너_거리별_안전운임_2026_왕복.csv",
                None,
            )

        # 편도표에는 '항만 ↔ 의왕ICD' 경유 노선별 수도권 화주공장 행이 들어 있다.
        # 한쪽이 해당 항만, 반대쪽이 주소일 때만 예외 규정을 적용한다.
        if port_endpoint:
            address_endpoint = destination if port_endpoint is origin else origin
            route_name = PORT_TO_ONE_WAY_ROUTE.get(port_endpoint.hub.code)
            if route_name and address_endpoint.is_address:
                matched = self.tariffs.match_one_way(route_name, address_endpoint.input_value, road_distance_km)
                if matched:
                    row, match_quality = matched
                    return (
                        row,
                        "수도권 화주공장 작업 + 의왕ICD 경유: 기점별 편도운임 적용",
                        "(별첨)_수출입_컨테이너_품목_기점별_운임(편도)_통합.csv",
                        f"{row.sido} {row.sigungu} {row.eupmyeondong} / {match_quality}",
                    )

        distance = _tariff_distance_km(road_distance_km)
        return (
            self.tariffs.roundtrip(distance),
            "기본: 거리별 왕복운임 적용",
            "수출입컨테이너_거리별_안전운임_2026_왕복.csv",
            None,
        )

    @staticmethod
    def _cost_by_rate_type(
        rate_type: str,
        rates: Mapping[int, Decimal],
        count_20ft: int,
        count_40ft: int,
    ) -> FareCandidate:
        # 20FT는 짝수 전체에만 COMBINE을 적용하는 것이 아니라, 가능한 모든 2개
        # 묶음에 적용한다. 예: 5개 = 2개/대 COMBINE 2대 + 1개/대 일반운임 1대.
        combine_20ft_pair_count, remaining_20ft_count = divmod(count_20ft, 2)
        combine_20ft_applied = combine_20ft_pair_count > 0
        truck_count_20ft = combine_20ft_pair_count + remaining_20ft_count
        cost_20ft = (
            rates[20] * COMBINE_20FT_MULTIPLIER * combine_20ft_pair_count
            + rates[20] * remaining_20ft_count
        )
        truck_count_40ft = count_40ft
        cost_40ft = rates[40] * count_40ft
        return FareCandidate(
            rate_type=rate_type,
            total_cost_krw=_round_half_up_krw(cost_20ft + cost_40ft),
            fare_20ft_per_container_krw=rates[20] if count_20ft else None,
            fare_40ft_per_container_krw=rates[40] if count_40ft else None,
            truck_count_20ft=truck_count_20ft,
            truck_count_40ft=truck_count_40ft,
            combine_20ft_pair_count=combine_20ft_pair_count,
            combine_20ft_applied=combine_20ft_applied,
        )


RECOMMENDATION_REQUIRED_COLUMNS = {
    "recommendation_id", "carrier_id", "container_size", "quantity_boxes", "quantity_teu",
    "origin_hub", "origin_name", "destination_hub", "destination_name", "train_id",
    "tariff_distance_km", "estimated_rail_charge_krw",
}
STOP_PLAN_REQUIRED_COLUMNS = {
    "train_id", "stop_sequence", "hub", "actual_load_start_time", "actual_available_time",
}
SEGMENT_LOAD_REQUIRED_COLUMNS = {
    "train_id", "segment_sequence", "from_hub", "to_hub", "capacity_teu", "physical_distance_km",
}
TRAIN_PLAN_REQUIRED_COLUMNS = {"train_id", "capacity_teu"}
TIMELINE_REQUIRED_COLUMNS = {
    "carrier_id", "timestamp", "hub_code", "container_size", "baseline_inventory",
    "post_rail_inventory", "baseline_unmet_demand", "post_rail_unmet_demand",
}
IMPACT_REQUIRED_COLUMNS = {
    "carrier_id", "hub_code", "container_size", "baseline_stockout_boxes",
    "post_rail_stockout_boxes", "stockout_reduction_boxes",
}

COMPARISON_COLUMNS = [
    "recommendation_id", "carrier_id", "origin_hub", "origin_name", "destination_hub",
    "destination_name", "container_size", "quantity_boxes", "quantity_teu", "train_id",
    "road_distance_km", "road_duration_minutes", "truck_tariff_distance_km",
    "truck_vehicle_count", "truck_per_vehicle_fare_krw", "truck_rate_type",
    "truck_capacity_rule", "truck_standard_min_cost_krw", "truck_combine_min_cost_krw",
    "truck_fare_candidate_count", "truck_combine_eligibility", "truck_combine_applied",
    "truck_combine_pair_count", "rail_tariff_distance_km", "rail_physical_distance_km",
    "rail_model_charge_krw", "rail_distance_fare_krw", "rail_handling_cost_krw", "rail_cost_krw",
    "truck_cost_krw", "cost_difference_krw", "cost_saving_rate", "rail_process_start_time", "rail_available_time",
    "rail_end_to_end_hours", "truck_origin_loading_hours", "truck_destination_unloading_hours",
    "truck_end_to_end_hours", "time_difference_hours", "rail_total_train_co2_kg",
    "rail_max_capacity_teu", "rail_co2_allocation_ratio", "rail_co2_kg", "truck_co2_kg",
    "co2_difference_kg", "co2_reduction_rate", "truck_fare_policy", "truck_fare_source",
    "truck_distance_source", "rail_co2_parameter_source", "time_boundary",
]

INVENTORY_CONTEXT_COLUMNS = [
    "recommendation_id", "carrier_id", "origin_hub", "destination_hub", "container_size",
    "rail_available_time", "inventory_context_status",
    "destination_baseline_inventory_at_rail_available",
    "destination_post_rail_inventory_at_rail_available",
    "destination_baseline_unmet_demand_at_rail_available",
    "destination_post_rail_unmet_demand_at_rail_available",
    "destination_baseline_stockout_boxes", "destination_post_rail_stockout_boxes",
    "destination_stockout_reduction_boxes",
]

ROAD_CACHE_COLUMNS = [
    "origin_hub", "destination_hub", "road_distance_km", "road_duration_minutes", "distance_source",
]


def _read_csv_rows(path: Path, required_columns: set[str]) -> list[dict[str, str]]:
    """CSV 스키마를 먼저 검증해 변경된 W01/W02 결과의 오류를 명확히 알린다."""
    if not path.is_file():
        raise FileNotFoundError(f"필수 입력 CSV를 찾지 못했습니다: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        missing = required_columns - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path.name}에 필수 열이 없습니다: {', '.join(sorted(missing))}")
        return list(reader)


def _write_csv_rows(path: Path, fieldnames: list[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _as_float(value: Any, label: str) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError as error:
        raise ValueError(f"{label} 값이 숫자가 아닙니다: {value!r}") from error


def _as_positive_int(value: Any, label: str) -> int:
    number = _as_float(value, label)
    if not number.is_integer() or number <= 0:
        raise ValueError(f"{label}은 0보다 큰 정수여야 합니다: {value!r}")
    return int(number)


def _parse_datetime(value: str, label: str) -> datetime:
    try:
        return datetime.fromisoformat(str(value).strip())
    except ValueError as error:
        raise ValueError(f"{label}은 ISO 날짜·시간 형식이어야 합니다: {value!r}") from error


def _format_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M")


def _hub_endpoint(hub_code: str) -> Endpoint:
    try:
        hub = HUBS[hub_code]
    except KeyError as error:
        raise ValueError(f"지원하지 않는 거점 코드입니다: {hub_code}") from error
    return Endpoint(hub.name, hub.name, hub.address, hub)


def _load_road_cache(path: Path) -> dict[tuple[str, str], RoadMetric]:
    if not path.is_file():
        return {}
    rows = _read_csv_rows(path, set(ROAD_CACHE_COLUMNS) - {"distance_source"})
    cache: dict[tuple[str, str], RoadMetric] = {}
    for row in rows:
        key = (row["origin_hub"], row["destination_hub"])
        if key in cache:
            raise ValueError(f"{path.name}에 중복 도로 OD가 있습니다: {key[0]} → {key[1]}")
        cache[key] = RoadMetric(
            distance_km=_as_float(row["road_distance_km"], "road_distance_km"),
            duration_minutes=_as_float(row["road_duration_minutes"], "road_duration_minutes"),
            source=row.get("distance_source") or f"도로 경로 캐시: {path.name}",
        )
    return cache


def _road_cache_rows(cache: Mapping[tuple[str, str], RoadMetric], keys: Iterable[tuple[str, str]]) -> list[dict[str, Any]]:
    return [
        {
            "origin_hub": origin_hub,
            "destination_hub": destination_hub,
            "road_distance_km": cache[(origin_hub, destination_hub)].distance_km,
            "road_duration_minutes": cache[(origin_hub, destination_hub)].duration_minutes,
            "distance_source": cache[(origin_hub, destination_hub)].source,
        }
        for origin_hub, destination_hub in sorted(set(keys))
    ]


class _BatchRoadRouter:
    """W01/W02의 동일 거점 OD는 한 번만 NAVER API를 호출하고 캐시한다."""

    def __init__(self, cache: dict[tuple[str, str], RoadMetric], vehicle_type: int) -> None:
        self.cache = cache
        self.vehicle_type = vehicle_type
        self.client: NaverMapsClient | None = None
        self.used_keys: set[tuple[str, str]] = set()

    def metric(self, origin_hub: str, destination_hub: str) -> RoadMetric:
        key = (origin_hub, destination_hub)
        self.used_keys.add(key)
        if key not in self.cache:
            if self.client is None:
                self.client = NaverMapsClient.from_environment(vehicle_type=self.vehicle_type)
            self.cache[key] = self.client.route(
                _hub_endpoint(origin_hub).route_address,
                _hub_endpoint(destination_hub).route_address,
            )
        return self.cache[key]


def _load_week_inputs(week_dir: Path) -> dict[str, list[dict[str, str]]]:
    """W01/W02 폴더의 추천·운행·재고 파일을 읽고 최소 스키마를 검증한다."""
    return {
        "recommendations": _read_csv_rows(
            week_dir / "CARRIER_RECOMMENDATIONS.csv", RECOMMENDATION_REQUIRED_COLUMNS
        ),
        "stop_plan": _read_csv_rows(week_dir / "STOP_WORK_PLAN.csv", STOP_PLAN_REQUIRED_COLUMNS),
        "segment_load": _read_csv_rows(week_dir / "SEGMENT_LOAD.csv", SEGMENT_LOAD_REQUIRED_COLUMNS),
        "train_plan": _read_csv_rows(week_dir / "KORAIL_TRAIN_PLAN.csv", TRAIN_PLAN_REQUIRED_COLUMNS),
        "timeline": _read_csv_rows(week_dir / "CARRIER_INVENTORY_TIMELINE.csv", TIMELINE_REQUIRED_COLUMNS),
        "impact": _read_csv_rows(week_dir / "INVENTORY_IMPACT_SUMMARY.csv", IMPACT_REQUIRED_COLUMNS),
    }


def _stop_index(stop_rows: Iterable[Mapping[str, str]]) -> dict[tuple[str, str], Mapping[str, str]]:
    index: dict[tuple[str, str], Mapping[str, str]] = {}
    for row in stop_rows:
        key = (row["train_id"], row["hub"])
        if key in index:
            raise ValueError(f"STOP_WORK_PLAN에 중복 열차·거점이 있습니다: {key[0]} / {key[1]}")
        index[key] = row
    return index


def _segments_by_train(segment_rows: Iterable[Mapping[str, str]]) -> dict[str, list[Mapping[str, str]]]:
    grouped: dict[str, list[Mapping[str, str]]] = {}
    for row in segment_rows:
        grouped.setdefault(row["train_id"], []).append(row)
    for train_id, rows in grouped.items():
        rows.sort(key=lambda item: _as_positive_int(item["segment_sequence"], f"{train_id}.segment_sequence"))
    return grouped


def _capacity_by_train(
    train_rows: Iterable[Mapping[str, str]], segment_rows: Iterable[Mapping[str, str]]
) -> dict[str, float]:
    """최대 화차 길이는 KORAIL capacity_teu를 우선, 없으면 segment capacity_teu를 사용한다."""
    capacity: dict[str, float] = {}
    for row in train_rows:
        train_id = row["train_id"]
        value = _as_float(row["capacity_teu"], f"{train_id}.capacity_teu")
        if value <= 0:
            raise ValueError(f"{train_id}.capacity_teu는 0보다 커야 합니다.")
        if train_id in capacity and capacity[train_id] != value:
            raise ValueError(f"KORAIL_TRAIN_PLAN의 {train_id} capacity_teu가 일관되지 않습니다.")
        capacity[train_id] = value
    fallback: dict[str, set[float]] = {}
    for row in segment_rows:
        fallback.setdefault(row["train_id"], set()).add(
            _as_float(row["capacity_teu"], f"{row['train_id']}.capacity_teu")
        )
    for train_id, values in fallback.items():
        if train_id not in capacity:
            if len(values) != 1:
                raise ValueError(f"SEGMENT_LOAD의 {train_id} capacity_teu가 일관되지 않습니다.")
            capacity[train_id] = next(iter(values))
    return capacity


def _rail_journey(
    recommendation: Mapping[str, str],
    stops: Mapping[tuple[str, str], Mapping[str, str]],
    segments: Mapping[str, list[Mapping[str, str]]],
) -> tuple[datetime, datetime, float]:
    """추천 OD가 실제로 탑승한 열차 구간의 작업 시작·사용가능 시각·물리거리를 계산한다."""
    prefix = str(recommendation["recommendation_id"])
    train_id = recommendation["train_id"]
    try:
        origin_stop = stops[(train_id, recommendation["origin_hub"])]
        destination_stop = stops[(train_id, recommendation["destination_hub"])]
    except KeyError as error:
        raise ValueError(f"{prefix}: STOP_WORK_PLAN에서 추천 OD의 열차 정차 정보를 찾지 못했습니다.") from error
    origin_sequence = _as_positive_int(origin_stop["stop_sequence"], f"{prefix}.origin stop_sequence")
    destination_sequence = _as_positive_int(destination_stop["stop_sequence"], f"{prefix}.destination stop_sequence")
    if origin_sequence >= destination_sequence:
        raise ValueError(f"{prefix}: 열차 정차 순서가 origin → destination 방향과 일치하지 않습니다.")
    route_segments = [
        row for row in segments.get(train_id, [])
        if origin_sequence <= _as_positive_int(row["segment_sequence"], f"{prefix}.segment_sequence") < destination_sequence
    ]
    if len(route_segments) != destination_sequence - origin_sequence:
        raise ValueError(f"{prefix}: SEGMENT_LOAD의 OD 구간이 STOP_WORK_PLAN과 일치하지 않습니다.")
    physical_distance = sum(_as_float(row["physical_distance_km"], f"{prefix}.physical_distance_km") for row in route_segments)
    load_start = _parse_datetime(origin_stop["actual_load_start_time"], f"{prefix}.actual_load_start_time")
    available = _parse_datetime(destination_stop["actual_available_time"], f"{prefix}.actual_available_time")
    if available < load_start:
        raise ValueError(f"{prefix}: rail_available_time이 rail_process_start_time보다 빠릅니다.")
    return load_start, available, physical_distance


def _combine_eligibility(container_size: str, quantity_boxes: int) -> str:
    if _container_size_ft(container_size) == 20 and quantity_boxes >= 2:
        pair_count, remainder = divmod(quantity_boxes, 2)
        if remainder:
            return (
                f"ELIGIBLE: 20FT {pair_count}쌍은 2개/대 COMBINE, "
                "잔여 1개는 1개/대 일반운임 적용"
            )
        return f"ELIGIBLE: 20FT {pair_count}쌍에 2개/대 COMBINE 운임 적용"
    if _container_size_ft(container_size) == 20:
        return "INELIGIBLE: 20FT 1개는 2개/대 COMBINE 대상 아님"
    return "INELIGIBLE: COMBINE은 20FT 컨테이너에만 적용"


def _rail_fare_for_recommendation(recommendation: Mapping[str, str]) -> tuple[int, int]:
    """거리운임과 철도 상하차비를 분리해 현재 철도 운임 규칙으로 재계산한다."""
    size = _container_size_ft(recommendation["container_size"])
    boxes = _as_positive_int(recommendation["quantity_boxes"], f"{recommendation['recommendation_id']}.quantity_boxes")
    tariff_distance = _as_float(recommendation["tariff_distance_km"], f"{recommendation['recommendation_id']}.tariff_distance_km")
    if tariff_distance <= 0:
        raise ValueError(f"{recommendation['recommendation_id']}.tariff_distance_km는 0보다 커야 합니다.")
    per_container = _round_to_nearest_hundred_krw(
        RAIL_EMPTY_RATE_PER_CONTAINER_KM[size] * Decimal(str(tariff_distance))
    )
    return per_container * boxes, RAIL_HANDLING_COST_PER_CONTAINER_KRW[size] * boxes


def _truck_quote_for_recommendation(
    calculator: TruckTransportCalculator,
    recommendation: Mapping[str, str],
    road: RoadMetric,
) -> QuoteResult:
    size = _container_size_ft(recommendation["container_size"])
    boxes = _as_positive_int(recommendation["quantity_boxes"], f"{recommendation['recommendation_id']}.quantity_boxes")
    origin = _hub_endpoint(recommendation["origin_hub"])
    destination = _hub_endpoint(recommendation["destination_hub"])
    return calculator._quote_for_endpoints(
        origin,
        destination,
        count_20ft=boxes if size == 20 else 0,
        count_40ft=boxes if size == 40 else 0,
        road=road,
    )


def _comparison_rows_for_week(
    inputs: Mapping[str, list[dict[str, str]]],
    calculator: TruckTransportCalculator,
    road_router: _BatchRoadRouter,
) -> list[dict[str, Any]]:
    recommendations = inputs["recommendations"]
    identifiers = [row["recommendation_id"] for row in recommendations]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("CARRIER_RECOMMENDATIONS.csv의 recommendation_id가 unique하지 않습니다.")
    stops = _stop_index(inputs["stop_plan"])
    segments = _segments_by_train(inputs["segment_load"])
    capacities = _capacity_by_train(inputs["train_plan"], inputs["segment_load"])
    rows: list[dict[str, Any]] = []
    for recommendation in recommendations:
        recommendation_id = recommendation["recommendation_id"]
        origin_hub, destination_hub = recommendation["origin_hub"], recommendation["destination_hub"]
        if origin_hub not in HUBS or destination_hub not in HUBS:
            raise ValueError(f"{recommendation_id}: 지원하지 않는 추천 거점 OD입니다: {origin_hub} → {destination_hub}")
        boxes = _as_positive_int(recommendation["quantity_boxes"], f"{recommendation_id}.quantity_boxes")
        teu = _as_float(recommendation["quantity_teu"], f"{recommendation_id}.quantity_teu")
        if teu <= 0:
            raise ValueError(f"{recommendation_id}.quantity_teu는 0보다 커야 합니다.")
        road = road_router.metric(origin_hub, destination_hub)
        truck_quote = _truck_quote_for_recommendation(calculator, recommendation, road)
        size = _container_size_ft(recommendation["container_size"])
        standard_costs = [
            _round_half_up_krw(
                (candidate.fare_20ft_per_container_krw * boxes)
                if size == 20
                else (candidate.fare_40ft_per_container_krw * boxes)
            )
            for candidate in truck_quote.alternatives
        ]
        combine_costs = [candidate.total_cost_krw for candidate in truck_quote.alternatives if candidate.combine_20ft_applied]
        selected = truck_quote.selected
        rail_start, rail_available, rail_physical_distance = _rail_journey(recommendation, stops, segments)
        rail_distance_fare, rail_handling_cost = _rail_fare_for_recommendation(recommendation)
        rail_cost = rail_distance_fare + rail_handling_cost
        try:
            max_capacity_teu = capacities[recommendation["train_id"]]
        except KeyError as error:
            raise ValueError(f"{recommendation_id}: {recommendation['train_id']}의 최대 화차 길이(TEU)를 찾지 못했습니다.") from error
        allocation_ratio = teu / max_capacity_teu
        if allocation_ratio > 1 + 1e-9:
            raise ValueError(
                f"{recommendation_id}: 운송량 {teu}TEU가 열차 최대 화차 길이 {max_capacity_teu}TEU를 초과합니다."
            )
        rail_total_co2 = _rail_co2_kg(rail_physical_distance)
        rail_co2 = rail_total_co2 * allocation_ratio
        vehicle_count = selected.truck_count_20ft + selected.truck_count_40ft
        truck_co2 = _truck_co2_kg(road.distance_km, vehicle_count)
        truck_hours = road.duration_minutes / 60 + 3.0
        rail_hours = (rail_available - rail_start).total_seconds() / 3_600
        rows.append({
            "recommendation_id": recommendation_id,
            "carrier_id": recommendation["carrier_id"],
            "origin_hub": origin_hub,
            "origin_name": recommendation["origin_name"],
            "destination_hub": destination_hub,
            "destination_name": recommendation["destination_name"],
            "container_size": recommendation["container_size"],
            "quantity_boxes": boxes,
            "quantity_teu": teu,
            "train_id": recommendation["train_id"],
            "road_distance_km": road.distance_km,
            "road_duration_minutes": road.duration_minutes,
            "truck_tariff_distance_km": truck_quote.tariff_distance_km,
            "truck_vehicle_count": vehicle_count,
            # 20FT가 COMBINE 운임과 단품 운임을 함께 쓰는 경우에는 차량당 평균 운임을 기록한다.
            "truck_per_vehicle_fare_krw": selected.total_cost_krw / vehicle_count,
            "truck_rate_type": selected.rate_type,
            "truck_capacity_rule": (
                f"20FT 2개/대 COMBINE {selected.combine_20ft_pair_count}대 + "
                f"20FT 1개/대 {selected.truck_count_20ft - selected.combine_20ft_pair_count}대"
                if size == 20 and selected.combine_20ft_applied and selected.truck_count_20ft != selected.combine_20ft_pair_count
                else "20FT 2개/대 COMBINE"
                if size == 20 and selected.combine_20ft_applied
                else "20FT 1개/대, 40FT 1개/대"
            ),
            "truck_standard_min_cost_krw": min(standard_costs),
            "truck_combine_min_cost_krw": min(combine_costs) if combine_costs else "",
            "truck_fare_candidate_count": len(truck_quote.alternatives),
            "truck_combine_eligibility": _combine_eligibility(recommendation["container_size"], boxes),
            "truck_combine_applied": selected.combine_20ft_applied,
            "truck_combine_pair_count": selected.combine_20ft_pair_count,
            "rail_tariff_distance_km": _as_float(recommendation["tariff_distance_km"], f"{recommendation_id}.tariff_distance_km"),
            "rail_physical_distance_km": rail_physical_distance,
            "rail_model_charge_krw": _as_float(recommendation["estimated_rail_charge_krw"], f"{recommendation_id}.estimated_rail_charge_krw"),
            "rail_distance_fare_krw": rail_distance_fare,
            "rail_handling_cost_krw": rail_handling_cost,
            "rail_cost_krw": rail_cost,
            "truck_cost_krw": selected.total_cost_krw,
            "cost_difference_krw": selected.total_cost_krw - rail_cost,
            "cost_saving_rate": (selected.total_cost_krw - rail_cost) / selected.total_cost_krw if selected.total_cost_krw else "",
            "rail_process_start_time": _format_datetime(rail_start),
            "rail_available_time": _format_datetime(rail_available),
            "rail_end_to_end_hours": rail_hours,
            "truck_origin_loading_hours": 1.5,
            "truck_destination_unloading_hours": 1.5,
            "truck_end_to_end_hours": truck_hours,
            "time_difference_hours": truck_hours - rail_hours,
            "rail_total_train_co2_kg": rail_total_co2,
            "rail_max_capacity_teu": max_capacity_teu,
            "rail_co2_allocation_ratio": allocation_ratio,
            "rail_co2_kg": rail_co2,
            "truck_co2_kg": truck_co2,
            "co2_difference_kg": truck_co2 - rail_co2,
            "co2_reduction_rate": (truck_co2 - rail_co2) / truck_co2 if truck_co2 else "",
            "truck_fare_policy": truck_quote.fare_policy,
            "truck_fare_source": truck_quote.fare_source,
            "truck_distance_source": road.source,
            "rail_co2_parameter_source": (
                "철도 총배출량 = 추천 OD 물리거리 × 3.21L/km × 35.2MJ/L × 73,200kgCO2/TJ ÷ 1,000,000; "
                "배분 = 총배출량 × (recommendation quantity_teu / KORAIL_TRAIN_PLAN capacity_teu)"
            ),
            "time_boundary": "Rail: STOP_WORK_PLAN actual_load_start_time → actual_available_time; Truck: NAVER road duration + origin/destination each 1.5h",
        })
    return rows


def _inventory_context_rows(
    comparison_rows: Iterable[Mapping[str, Any]],
    timeline_rows: Iterable[Mapping[str, str]],
    impact_rows: Iterable[Mapping[str, str]],
) -> list[dict[str, Any]]:
    timeline: dict[tuple[str, str, str, str], Mapping[str, str]] = {}
    for row in timeline_rows:
        key = (row["carrier_id"], _format_datetime(_parse_datetime(row["timestamp"], "timeline.timestamp")), row["hub_code"], row["container_size"])
        if key in timeline:
            raise ValueError(f"CARRIER_INVENTORY_TIMELINE.csv에 중복 키가 있습니다: {key}")
        timeline[key] = row
    impact: dict[tuple[str, str, str], Mapping[str, str]] = {}
    for row in impact_rows:
        key = (row["carrier_id"], row["hub_code"], row["container_size"])
        if key in impact:
            raise ValueError(f"INVENTORY_IMPACT_SUMMARY.csv에 중복 키가 있습니다: {key}")
        impact[key] = row
    context_rows: list[dict[str, Any]] = []
    for comparison in comparison_rows:
        timeline_key = (
            str(comparison["carrier_id"]), str(comparison["rail_available_time"]),
            str(comparison["destination_hub"]), str(comparison["container_size"]),
        )
        timeline_value = timeline.get(timeline_key)
        impact_value = impact.get((timeline_key[0], timeline_key[2], timeline_key[3]))
        row: dict[str, Any] = {
            "recommendation_id": comparison["recommendation_id"],
            "carrier_id": comparison["carrier_id"],
            "origin_hub": comparison["origin_hub"],
            "destination_hub": comparison["destination_hub"],
            "container_size": comparison["container_size"],
            "rail_available_time": comparison["rail_available_time"],
            "inventory_context_status": "AVAILABLE" if timeline_value else "TIMELINE_NOT_FOUND",
            "destination_baseline_inventory_at_rail_available": timeline_value["baseline_inventory"] if timeline_value else "",
            "destination_post_rail_inventory_at_rail_available": timeline_value["post_rail_inventory"] if timeline_value else "",
            "destination_baseline_unmet_demand_at_rail_available": timeline_value["baseline_unmet_demand"] if timeline_value else "",
            "destination_post_rail_unmet_demand_at_rail_available": timeline_value["post_rail_unmet_demand"] if timeline_value else "",
            "destination_baseline_stockout_boxes": impact_value["baseline_stockout_boxes"] if impact_value else "",
            "destination_post_rail_stockout_boxes": impact_value["post_rail_stockout_boxes"] if impact_value else "",
            "destination_stockout_reduction_boxes": impact_value["stockout_reduction_boxes"] if impact_value else "",
        }
        context_rows.append(row)
    return context_rows


def _discover_week_dirs(results_root: Path) -> list[Path]:
    candidates = sorted(
        directory for directory in results_root.glob("W??_*")
        if directory.is_dir() and (directory / "CARRIER_RECOMMENDATIONS.csv").is_file()
    )
    if not candidates:
        raise FileNotFoundError(
            f"{results_root}에서 W01/W02 결과 폴더를 찾지 못했습니다. "
            "CARRIER_RECOMMENDATIONS.csv가 있는 W??_* 폴더가 필요합니다."
        )
    return candidates


def _default_rate_csv(pattern: str, label: str) -> Path:
    """계산기와 같은 폴더에 둔 운임표를 하나만 자동 선택한다."""
    candidates = sorted(SCRIPT_DIR.glob(pattern))
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise FileNotFoundError(
            f"{label}를 찾지 못했습니다. --roundtrip-rate-csv 또는 --oneway-rate-csv로 경로를 지정하세요."
        )
    raise ValueError(f"{label}가 여러 개입니다. 명령어에서 명시적으로 경로를 지정하세요: {candidates}")


def run_weekly_recommendation_batch(
    week_dirs: Iterable[Path],
    tariffs: TariffCatalog,
    output_root: Path,
    *,
    vehicle_type: int = 5,
) -> list[tuple[Path, Path, Path]]:
    """W01/W02의 추천별 트럭 대비 결과와 재고 컨텍스트·도로 캐시를 각각 만든다."""
    week_dirs = list(week_dirs)
    cache: dict[tuple[str, str], RoadMetric] = {}
    for week_dir in week_dirs:
        cache.update(_load_road_cache(output_root / week_dir.name / "ROAD_ROUTE_CACHE.csv"))
    road_router = _BatchRoadRouter(cache, vehicle_type)
    calculator = TruckTransportCalculator(tariffs, road_router)
    output_paths: list[tuple[Path, Path, Path]] = []
    for week_dir in week_dirs:
        inputs = _load_week_inputs(week_dir)
        road_router.used_keys.clear()
        comparison_rows = _comparison_rows_for_week(inputs, calculator, road_router)
        if len(comparison_rows) != len(inputs["recommendations"]):
            raise ValueError(f"{week_dir.name}: 추천 건수와 비교 결과 건수가 일치하지 않습니다.")
        context_rows = _inventory_context_rows(comparison_rows, inputs["timeline"], inputs["impact"])
        week_output_dir = output_root / week_dir.name
        comparison_path = week_output_dir / "TRUCK_COMPARISON_BY_RECOMMENDATION.csv"
        context_path = week_output_dir / "RECOMMENDATION_INVENTORY_CONTEXT.csv"
        cache_path = week_output_dir / "ROAD_ROUTE_CACHE.csv"
        _write_csv_rows(comparison_path, COMPARISON_COLUMNS, comparison_rows)
        _write_csv_rows(context_path, INVENTORY_CONTEXT_COLUMNS, context_rows)
        _write_csv_rows(cache_path, ROAD_CACHE_COLUMNS, _road_cache_rows(cache, road_router.used_keys))
        output_paths.append((comparison_path, context_path, cache_path))
    return output_paths


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", help="출발지 주소 또는 6개 지정 거점명")
    parser.add_argument("--destination", help="도착지 주소 또는 6개 지정 거점명")
    parser.add_argument("--20ft", "--count-20ft", dest="count_20ft", type=int, default=0, help="20FT 수량")
    parser.add_argument("--40ft", "--count-40ft", dest="count_40ft", type=int, default=0, help="40FT 수량")
    parser.add_argument("--roundtrip-rate-csv", type=Path, help="거리별 왕복 운임 CSV")
    parser.add_argument("--oneway-rate-csv", type=Path, help="기점별 편도 운임 CSV")
    parser.add_argument(
        "--train-candidate-csv", type=Path,
        help="지정 시 TRAIN_CANDIDATE.csv를 이용해 트럭 단일운송과 트럭-철도 복합운송을 비교",
    )
    parser.add_argument(
        "--vehicle-type", type=int, choices=range(1, 7), default=5,
        help="NAVER Directions 차종 코드 (기본값: 5, 4축 이상 특수 화물차)",
    )
    parser.add_argument("--output", type=Path, help="결과 JSON 저장 경로 (생략 시 표준출력)")
    parser.add_argument(
        "--batch-weeks", action="store_true",
        help="W01/W02 추천 결과를 읽어 추천별 비교 CSV 3종을 생성",
    )
    parser.add_argument(
        "--results-root", type=Path, default=DEFAULT_RESULTS_ROOT,
        help="W01/W02 폴더가 있는 상위 결과 폴더 (기본값: 계산기 상위 폴더)",
    )
    parser.add_argument(
        "--batch-week-dir", type=Path, action="append",
        help="처리할 W 폴더. 여러 번 지정 가능; 생략 시 --results-root 아래 W01/W02 자동 탐색",
    )
    parser.add_argument(
        "--batch-output-root", type=Path, default=DEFAULT_BATCH_OUTPUT_ROOT,
        help="배치 CSV 저장 상위 폴더 (기본값: mode_comparison/outputs)",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)
    roundtrip_rate_csv = args.roundtrip_rate_csv
    oneway_rate_csv = args.oneway_rate_csv
    if args.batch_weeks:
        roundtrip_rate_csv = roundtrip_rate_csv or _default_rate_csv(
            "수출입컨테이너_거리별_안전운임_2026_왕복.csv", "거리별 왕복 운임 CSV"
        )
        oneway_rate_csv = oneway_rate_csv or _default_rate_csv(
            "(별첨)_수출입_컨테이너_품목_기점별_운임(편도)_통합.csv", "기점별 편도 운임 CSV"
        )
        week_dirs = args.batch_week_dir or _discover_week_dirs(args.results_root)
        tariffs = TariffCatalog.from_csv(roundtrip_rate_csv, oneway_rate_csv)
        output_paths = run_weekly_recommendation_batch(
            week_dirs, tariffs, args.batch_output_root, vehicle_type=args.vehicle_type
        )
        print("추천별 비교 CSV를 저장했습니다:")
        for comparison_path, context_path, cache_path in output_paths:
            print(f"- {comparison_path}")
            print(f"- {context_path}")
            print(f"- {cache_path}")
        return 0

    if not args.origin or not args.destination:
        raise ValueError("단일 견적에는 --origin과 --destination이 필요합니다.")
    if not roundtrip_rate_csv:
        raise ValueError("단일 견적에는 --roundtrip-rate-csv가 필요합니다.")

    tariffs = TariffCatalog.from_csv(roundtrip_rate_csv, oneway_rate_csv)
    router = NaverMapsClient.from_environment(vehicle_type=args.vehicle_type)
    calculator = TruckTransportCalculator(tariffs, router)
    if args.train_candidate_csv:
        result = calculator.calculate_comparison(
            args.origin,
            args.destination,
            count_20ft=args.count_20ft,
            count_40ft=args.count_40ft,
            train_catalog=TrainCatalog.from_csv(args.train_candidate_csv),
        ).as_dict()
    else:
        result = calculator.calculate(
            args.origin,
            args.destination,
            count_20ft=args.count_20ft,
            count_40ft=args.count_40ft,
        ).as_dict()
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(f"결과를 저장했습니다: {args.output}")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
