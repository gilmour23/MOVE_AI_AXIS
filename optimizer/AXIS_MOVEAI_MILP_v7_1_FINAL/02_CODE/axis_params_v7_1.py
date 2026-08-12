"""
AXIS v7 — Reference Parameter Loader  (지시서 Phase 5-2)

`03_INPUT_DATA/AXIS_rail_OD_parameters_v1.xlsx` 에서 철도 파라미터를 읽는다.
xlsx 가 없으면 하드코딩 fallback 을 쓰되, 어느 값이 어디서 왔는지 항상 기록한다.

거리 개념 분리 (지시서 Phase 5-1)
---------------------------------
두 거리는 의미가 다르므로 이름부터 분리한다.

  physical_distance_km  열차가 실제로 주행하는 거리.
                        각 정차역의 인입선을 포함한다.
                        Train-km / Wagon-km / TEU-km / 구간 적재율에 사용.

  tariff_distance_km    코레일 영업거리. 운임 계산에만 사용.
                        통과만 하는 역의 인입선은 포함하지 않는다.

두 값이 다른 이유 (실측 확인)
  의왕 출발 OD 8건에서 physical - tariff = 정확히 5.8 km.
    의왕→부강 111.8 = 의왕인입 + 경부선(의왕~부강) + 부강인입
    부강→약목 152.6 = 부강인입 + 경부선(부강~약목)
    의왕→약목 258.6 = 의왕인입 + 경부선(의왕~약목)
    => 111.8 + 152.6 - 258.6 = 5.8 = 2 x 부강인입선(2.9km)
  즉 부강 CY 에 정차하는 열차는 인입선을 진입·진출 2회 주행하지만,
  통과 OD 의 영업거리에는 인입선이 포함되지 않는다.
  **오류가 아니라 서로 다른 물리량이다.**

  다만 약목·동산 인입선은 원자료 재구성에서 0 으로 처리되어 있어
  거점 간 일관성이 완전하지는 않다 (KNOWN_LIMITATION 으로 기록).

출처
  코레일 화물운임      https://info.korail.com/info/contents.do?key=873
  코레일 50량 시험운행 https://info.korail.com/info/selectBbsNttView.do?bbsNo=199&key=911&nttNo=16264
  철도거리표(공공데이터) https://www.data.go.kr/data/15137040/fileData.do
  2025 화물열차 시각표  https://www.data.go.kr/data/15042241/fileData.do
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

# xlsx OD_PARAMETER 는 철도 거점명(오봉)을 쓰고, 모델은 서비스 거점명(의왕ICD)을 쓴다.
HUB_BY_KO = {
    "오봉": "UIWANG", "의왕": "UIWANG", "의왕ICD": "UIWANG",
    "부강화물": "BUGANG", "부강": "BUGANG",
    "약목": "YAKMOK",
    "부산신항": "BUSAN",
    "동산": "DONGSAN",
    "신광양항": "GWANGYANG",
}

# ---------------------------------------------------------------- fallback
# xlsx 를 읽지 못할 때만 사용. 값은 REFERENCE_PARAMS 시트와 동일하다.
FALLBACK = {
    "laden_rate_20ft": (516.0, "KRW/km/container", "OFFICIAL",
                        "https://info.korail.com/info/contents.do?key=873", "코레일 화물운임 20피트 영컨"),
    "laden_rate_40ft": (800.0, "KRW/km/container", "OFFICIAL",
                        "https://info.korail.com/info/contents.do?key=873", "코레일 화물운임 40피트 영컨"),
    "empty_discount_ratio": (0.74, "ratio", "OFFICIAL",
                             "https://info.korail.com/info/contents.do?key=873", "공컨 = 영컨운임의 74%"),
    "min_charge_distance": (100.0, "km", "OFFICIAL",
                            "https://info.korail.com/info/contents.do?key=873", "컨테이너 최저운임거리"),
    "benchmark_avg_speed": (68.379603, "km/h", "OFFICIAL_DERIVED",
                            "https://info.korail.com/info/selectBbsNttView.do?bbsNo=199&key=911&nttNo=16264",
                            "의왕~부산신항 402.3km / 5시간53분"),
    "container_loading_limit": (3.0, "h", "OFFICIAL",
                                "https://info.korail.com/info/contents.do?key=873",
                                "화물운송약관 컨테이너 적재제한시간"),
    "container_unloading_limit": (3.0, "h", "OFFICIAL",
                                  "https://info.korail.com/info/contents.do?key=873",
                                  "화물운송약관 컨테이너 하화제한시간"),
    "teu_per_wagon": (2.0, "TEU/wagon", "OFFICIAL_DERIVED",
                      "https://info.korail.com/info/selectBbsNttView.do?bbsNo=199&key=911&nttNo=16264",
                      "33량=66TEU, 50량=100TEU"),
    "base_max_wagons": (40.0, "wagons/train", "OFFICIAL_REFERENCE",
                        "https://info.korail.com/info/contents.do?key=870",
                        "2024-01 40량 컨테이너 화물열차 기본"),
    "literature_min_load_factor": (0.70, "ratio", "LITERATURE",
                                   "https://www.mdpi.com/2071-1050/14/8/4697",
                                   "Song et al. (2022) 50/60/70% 시나리오 중 상단"),
}

FALLBACK_TARIFF_KM = {
    ("UIWANG", "BUGANG"): 111.8, ("UIWANG", "YAKMOK"): 258.6, ("UIWANG", "BUSAN"): 402.3,
    ("BUGANG", "YAKMOK"): 152.6, ("BUGANG", "BUSAN"): 296.3, ("YAKMOK", "BUSAN"): 143.7,
    ("UIWANG", "DONGSAN"): 236.2, ("UIWANG", "GWANGYANG"): 384.8,
    ("BUGANG", "DONGSAN"): 130.2, ("BUGANG", "GWANGYANG"): 278.8,
    ("DONGSAN", "GWANGYANG"): 148.6,
}

# 열차가 실제 주행하는 인접 구간 거리 (인입선 포함).
PHYSICAL_SEGMENT_KM = {
    ("UIWANG", "BUGANG"): 111.8,
    ("BUGANG", "YAKMOK"): 152.6,
    ("YAKMOK", "BUSAN"): 143.7,
    ("BUGANG", "DONGSAN"): 130.2,
    ("DONGSAN", "GWANGYANG"): 148.6,
}


@dataclass
class RailParams:
    laden_rate: Dict[str, float]
    empty_discount_ratio: float
    min_charge_km: float
    avg_speed_kmph: float
    origin_loading_h: float
    intermediate_handling_h: float
    destination_unloading_h: float
    teu_per_wagon: float
    tariff_km: Dict[Tuple[str, str], float]
    physical_km: Dict[Tuple[str, str], float]
    provenance: list = field(default_factory=list)
    validation: list = field(default_factory=list)

    def empty_rate(self, size: str) -> float:
        """공컨 운임단가 (원/km/box)."""
        return self.laden_rate[size] * self.empty_discount_ratio

    def fare_per_box(self, origin: str, destination: str, size: str) -> float:
        km = max(self.tariff_km[(origin, destination)], self.min_charge_km)
        return km * self.empty_rate(size)


def _symmetric(d):
    out = {}
    for (a, b), v in d.items():
        out[(a, b)] = v
        out[(b, a)] = v
    return out


def load_rail_params(xlsx: Optional[Path] = None,
                     origin_loading_h: Optional[float] = None,
                     intermediate_handling_h: Optional[float] = None,
                     destination_unloading_h: Optional[float] = None) -> RailParams:
    prov = []
    vals = {}
    tariff = {}

    def record(name, value, unit, level, url, note, source):
        prov.append({"parameter": name, "value": value, "unit": unit,
                     "evidence_level": level, "source_url": url,
                     "note": note, "loaded_from": source})
        return value

    loaded = False
    if xlsx is not None and Path(xlsx).exists():
        try:
            import pandas as pd
            xf = pd.ExcelFile(xlsx)
            ref = xf.parse("REFERENCE_PARAMS")
            for r in ref.itertuples():
                vals[str(r.Parameter)] = (float(r.Value), str(r.Unit), str(r.Type),
                                          str(r.Source), str(r.Note))
            od = xf.parse("OD_PARAMETER")
            # 한글 거점명 -> 코드
            for r in od.itertuples():
                o = HUB_BY_KO.get(str(r.origin).strip())
                d = HUB_BY_KO.get(str(r.destination).strip())
                if o and d:
                    tariff[(o, d)] = float(r.rail_distance_km)
            loaded = bool(vals) and bool(tariff)
        except Exception as exc:  # noqa: BLE001
            prov.append({"parameter": "_xlsx_load_error", "value": str(exc)[:200],
                         "unit": "", "evidence_level": "", "source_url": "",
                         "note": "fell back to hard-coded values", "loaded_from": "ERROR"})

    src = "XLSX" if loaded else "FALLBACK_HARDCODED"

    def get(name):
        if name in vals:
            v, unit, level, url, note = vals[name]
            return record(name, v, unit, level, url, note, "XLSX")
        v, unit, level, url, note = FALLBACK[name]
        return record(name, v, unit, level, url, note, "FALLBACK_HARDCODED")

    laden = {"20FT": get("laden_rate_20ft"), "40FT": get("laden_rate_40ft")}
    ratio = get("empty_discount_ratio")
    min_km = get("min_charge_distance")
    speed = get("benchmark_avg_speed")
    load_lim = get("container_loading_limit")
    unload_lim = get("container_unloading_limit")
    teu_wagon = get("teu_per_wagon")
    get("base_max_wagons")
    get("literature_min_load_factor")

    if not tariff:
        tariff = dict(FALLBACK_TARIFF_KM)
        prov.append({"parameter": "tariff_distance_km", "value": "FALLBACK",
                     "unit": "km", "evidence_level": "OFFICIAL_RECONSTRUCTED",
                     "source_url": "https://www.data.go.kr/data/15137040/fileData.do",
                     "note": "11 OD reconstructed from 철도거리표",
                     "loaded_from": "FALLBACK_HARDCODED"})
    else:
        prov.append({"parameter": "tariff_distance_km", "value": f"{len(tariff)} OD",
                     "unit": "km", "evidence_level": "OFFICIAL_RECONSTRUCTED",
                     "source_url": "https://www.data.go.kr/data/15137040/fileData.do",
                     "note": "OD_PARAMETER!rail_distance_km", "loaded_from": "XLSX"})

    tariff = _symmetric(tariff)
    physical = _symmetric(PHYSICAL_SEGMENT_KM)
    prov.append({"parameter": "physical_distance_km", "value": f"{len(physical)} segments",
                 "unit": "km", "evidence_level": "OFFICIAL_RECONSTRUCTED",
                 "source_url": "https://www.data.go.kr/data/15137040/fileData.do",
                 "note": "adjacent segments incl. terminal 인입선 at each stop",
                 "loaded_from": "HARDCODED_FROM_XLSX_NETWORK_BASIS"})

    p = RailParams(
        laden_rate=laden, empty_discount_ratio=ratio, min_charge_km=min_km,
        avg_speed_kmph=speed,
        origin_loading_h=load_lim if origin_loading_h is None else origin_loading_h,
        intermediate_handling_h=(unload_lim if intermediate_handling_h is None
                                 else intermediate_handling_h),
        destination_unloading_h=(unload_lim if destination_unloading_h is None
                                 else destination_unloading_h),
        teu_per_wagon=teu_wagon, tariff_km=tariff, physical_km=physical, provenance=prov)
    p.validation = validate_params(p)
    return p


def validate_params(p: RailParams) -> list:
    """
    지시서 Phase 5-1 runtime validation.

    두 거리를 같은 값으로 강제하지 않는다. 의미가 다르기 때문이다.
    대신 차이를 전부 계산해 기록하고, 설명되지 않는 큰 차이가 있으면 실패시킨다.
    """
    from itertools import combinations
    checks = []

    def add(name, ok, detail=""):
        checks.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})

    add("laden_rate_positive", all(v > 0 for v in p.laden_rate.values()), p.laden_rate)
    add("empty_discount_in_range", 0 < p.empty_discount_ratio <= 1, p.empty_discount_ratio)
    add("min_charge_positive", p.min_charge_km > 0, p.min_charge_km)
    add("avg_speed_reasonable", 20 <= p.avg_speed_kmph <= 120, p.avg_speed_kmph)
    add("handling_times_nonnegative",
        min(p.origin_loading_h, p.intermediate_handling_h, p.destination_unloading_h) >= 0,
        (p.origin_loading_h, p.intermediate_handling_h, p.destination_unloading_h))

    # corridor 상의 모든 OD 가 tariff 표에 존재하는가
    corridors = [["UIWANG", "BUGANG", "YAKMOK", "BUSAN"],
                 ["UIWANG", "BUGANG", "DONGSAN", "GWANGYANG"]]
    missing_t, missing_p, deltas = [], [], []
    for seq in corridors:
        for i in range(len(seq) - 1):
            for j in range(i + 1, len(seq)):
                o, d = seq[i], seq[j]
                if (o, d) not in p.tariff_km:
                    missing_t.append((o, d))
                    continue
                phys = 0.0
                ok = True
                for k in range(i, j):
                    seg = (seq[k], seq[k + 1])
                    if seg not in p.physical_km:
                        missing_p.append(seg)
                        ok = False
                        break
                    phys += p.physical_km[seg]
                if ok:
                    deltas.append({"origin": o, "destination": d,
                                   "physical_distance_km": round(phys, 1),
                                   "tariff_distance_km": p.tariff_km[(o, d)],
                                   "delta_km": round(phys - p.tariff_km[(o, d)], 2),
                                   "passes_through_bugang":
                                       "BUGANG" in seq[i + 1:j]})
    add("all_corridor_od_have_tariff_distance", not missing_t, missing_t)
    add("all_corridor_segments_have_physical_distance", not missing_p, missing_p)

    # delta 는 부강 인입선 왕복(5.8km)으로만 설명되어야 한다
    unexplained = [d for d in deltas
                   if abs(d["delta_km"]) > 0.01
                   and not (d["passes_through_bugang"] and abs(d["delta_km"] - 5.8) < 0.01)]
    add("distance_delta_fully_explained", not unexplained,
        f"unexplained={unexplained}" if unexplained else
        "all deltas are 0 or 5.8km (BUGANG 인입선 왕복 2 x 2.9km)")

    add("tariff_distance_symmetric",
        all(p.tariff_km.get((b, a)) == v for (a, b), v in p.tariff_km.items()), "")
    return checks + [{"check": "_deltas", "pass": True, "detail": deltas}]


def provenance_rows(p: RailParams) -> list:
    return [r for r in p.provenance]
