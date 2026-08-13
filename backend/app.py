"""MOVE-AI 선사 UI 백엔드.

원칙 (핸드오프 §10):
  모든 응답은 current carrier 로 먼저 필터링한 뒤 집계한다.
  타 선사의 demand/supply/inventory/recommendation/allocation 은 절대 내려보내지 않는다.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from moveai import config
from moveai.chat.router import router as chat_router
from moveai.domain import CONTAINER_SIZES, HUBS
from moveai.result_store import ResultFilesMissingError
from moveai.weeks import registry
from moveai.selectors import inventory as inv
from moveai.selectors import optimization as opt
from moveai.selectors import overview as ov

app = FastAPI(
    title="MOVE-AI Carrier UI API",
    version="1.0.0",
    description="선사용 공컨테이너 의사결정지원 UI 백엔드 (read-only)",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(chat_router)


# --------------------------------------------------------------------- 공통

def _store(week: str | None):
    """주차별 결과 store. week 미지정이면 첫 주차로 떨어진다.

    W01/W02 는 독립된 결과이므로 주차 없이 전역 조회하지 않는다.
    """
    if week and not registry.exists(week):
        raise HTTPException(404, f"알 수 없는 주차입니다: {week}")
    return registry.store(week)


def _validate_size(size: str) -> str:
    if size not in CONTAINER_SIZES:
        raise HTTPException(400, f"알 수 없는 규격입니다: {size}")
    return size


def _validate_mode(mode: str) -> str:
    if mode not in ("baseline", "postRail"):
        raise HTTPException(400, f"알 수 없는 mode 입니다: {mode}")
    return mode


def _validate_carrier(carrier_id: str, week: str | None = None) -> str:
    """요청된 carrier 가 해당 주차 결과에 존재하는지 확인한다."""
    try:
        known = _store(week).known_carriers()
    except ResultFilesMissingError as exc:
        raise HTTPException(
            503,
            {
                "code": "RESULT_FILES_MISSING",
                "message": "최적화 결과 파일을 불러오지 못했습니다.",
                "path": str(exc.path),
            },
        )
    if carrier_id not in known:
        raise HTTPException(404, f"알 수 없는 선사입니다: {carrier_id}")
    return carrier_id


@app.exception_handler(ResultFilesMissingError)
def _missing_files_handler(_request, exc: ResultFilesMissingError):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=503,
        content={
            "detail": {
                "code": "RESULT_FILES_MISSING",
                "message": "최적화 결과 파일을 불러오지 못했습니다. 결과 디렉터리 설정을 확인해주세요.",
                "path": str(exc.path),
            }
        },
    )


# ----------------------------------------------------------------- meta/health

@app.get("/api/health")
def health(week: str | None = Query(None)) -> dict:
    return _store(week).health()


@app.post("/api/admin/reload")
def reload_results() -> dict:
    """MILP 재실행 후 결과를 다시 읽는다. 사용자 화면에는 노출하지 않는다."""
    registry.reload()
    return {"reloaded": True}


@app.get("/api/weeks")
def weeks() -> dict:
    """주차 manifest. 화면의 week selector 가 이것만 보고 그린다."""
    return {
        "weeks": [m.to_dict() for m in registry.all_meta()],
        "defaultWeekId": registry.default_week_id(),
    }


@app.get("/api/meta")
def meta(week: str | None = Query(None)) -> dict:
    store = _store(week)
    summary = store.summary
    dates = inv.horizon_dates(store)
    timeline = store.inventory_timeline

    candidate_source = summary.get("candidate_timetable_source")
    carrier_source = summary.get("carrier_data_source")

    return {
        "weekId": store.week_id,
        "weeks": [m.to_dict() for m in registry.all_meta()],
        "scenario": summary.get("scenario"),
        "horizonStart": timeline["timestamp"].min().isoformat(),
        "horizonEnd": timeline["timestamp"].max().isoformat(),
        "horizonDates": dates,
        "carrierDataSource": carrier_source,
        "candidateTimetableSource": candidate_source,
        # badge 는 실제 데이터로 교체되면 자동으로 사라진다 (§2)
        "isSyntheticCarrierData": carrier_source == "SYNTHETIC_CARRIER_LEVEL_DATA",
        "isPrototypeTimetable": candidate_source == "PROTOTYPE_SYNTHETIC",
        "allStagesProvenOptimal": bool(summary.get("all_stages_proven_optimal")),
        "carrierKorailViewConsistent": bool(
            summary.get("carrier_korail_view_consistent")
        ),
        "selectedTrainCount": summary.get("selected_train_count"),
        "recommendationCount": summary.get("recommendation_count"),
        "hubs": HUBS,
        "currentCarrierId": config.DEMO_CARRIER_ID,
        "devMode": config.DEV_MODE,
        # dev mode 에서만 carrier selector 를 노출한다 (§10)
        "availableCarriers": store.known_carriers() if config.DEV_MODE else [],
    }


# --------------------------------------------------------------------- carrier

@app.get("/api/carrier/{carrier_id}/overview")
def carrier_overview(carrier_id: str, week: str | None = Query(None)) -> dict:
    _validate_carrier(carrier_id, week)
    return ov.overview(_store(week), carrier_id)


@app.get("/api/carrier/{carrier_id}/inventory")
def carrier_inventory(
    carrier_id: str,
    size: str = Query("20FT"),
    mode: str = Query("baseline"),
    week: str | None = Query(None),
) -> dict:
    _validate_carrier(carrier_id, week)
    _validate_size(size)
    _validate_mode(mode)
    return inv.weekly_matrix(_store(week), carrier_id, size, mode)


@app.get("/api/carrier/{carrier_id}/inventory/{hub_code}/{size}/summary")
def carrier_inventory_summary(
    carrier_id: str,
    hub_code: str,
    size: str,
    mode: str = Query("baseline"),
    week: str | None = Query(None),
) -> dict:
    _validate_carrier(carrier_id, week)
    _validate_size(size)
    _validate_mode(mode)
    return inv.hub_summary(_store(week), carrier_id, hub_code, size, mode)


@app.get("/api/carrier/{carrier_id}/optimization")
def carrier_optimization(carrier_id: str, week: str | None = Query(None)) -> dict:
    _validate_carrier(carrier_id, week)
    store = _store(week)
    return {
        "weekId": store.week_id,
        "carrierId": carrier_id,
        "needs": opt.service_needs(store, carrier_id),
        "recommendations": opt.recommendations(store, carrier_id),
        "impacts": opt.inventory_impacts(store, carrier_id),
        "serviceSummary": opt.carrier_service_summary(store, carrier_id),
    }


@app.get("/api/carrier/{carrier_id}/optimization/recommendations/{recommendation_id}")
def carrier_recommendation_detail(
    carrier_id: str, recommendation_id: str, week: str | None = Query(None)
) -> dict:
    _validate_carrier(carrier_id, week)
    detail = opt.recommendation_detail(_store(week), carrier_id, recommendation_id)
    if detail is None:
        raise HTTPException(404, f"추천을 찾을 수 없습니다: {recommendation_id}")
    return detail
