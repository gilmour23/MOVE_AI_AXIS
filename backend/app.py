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
from moveai.result_store import ResultFilesMissingError, store
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

def _validate_size(size: str) -> str:
    if size not in CONTAINER_SIZES:
        raise HTTPException(400, f"알 수 없는 규격입니다: {size}")
    return size


def _validate_mode(mode: str) -> str:
    if mode not in ("baseline", "postRail"):
        raise HTTPException(400, f"알 수 없는 mode 입니다: {mode}")
    return mode


def _validate_carrier(carrier_id: str) -> str:
    """요청된 carrier 가 결과에 존재하는지 확인한다."""
    try:
        known = store.known_carriers()
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
def health() -> dict:
    return store.health()


@app.post("/api/admin/reload")
def reload_results() -> dict:
    """MILP 재실행 후 결과를 다시 읽는다. 사용자 화면에는 노출하지 않는다."""
    store.reload()
    return {"reloaded": True}


@app.get("/api/meta")
def meta() -> dict:
    summary = store.summary
    dates = inv.horizon_dates(store)
    timeline = store.inventory_timeline

    candidate_source = summary.get("candidate_timetable_source")
    carrier_source = summary.get("carrier_data_source")

    return {
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
def carrier_overview(carrier_id: str) -> dict:
    _validate_carrier(carrier_id)
    return ov.overview(store, carrier_id)


@app.get("/api/carrier/{carrier_id}/inventory")
def carrier_inventory(
    carrier_id: str,
    size: str = Query("20FT"),
    mode: str = Query("baseline"),
) -> dict:
    _validate_carrier(carrier_id)
    _validate_size(size)
    _validate_mode(mode)
    return inv.weekly_matrix(store, carrier_id, size, mode)


@app.get("/api/carrier/{carrier_id}/inventory/{hub_code}/{size}/summary")
def carrier_inventory_summary(
    carrier_id: str,
    hub_code: str,
    size: str,
    mode: str = Query("baseline"),
) -> dict:
    _validate_carrier(carrier_id)
    _validate_size(size)
    _validate_mode(mode)
    return inv.hub_summary(store, carrier_id, hub_code, size, mode)


@app.get("/api/carrier/{carrier_id}/optimization")
def carrier_optimization(carrier_id: str) -> dict:
    _validate_carrier(carrier_id)
    return {
        "carrierId": carrier_id,
        "needs": opt.service_needs(store, carrier_id),
        "recommendations": opt.recommendations(store, carrier_id),
        "impacts": opt.inventory_impacts(store, carrier_id),
        "serviceSummary": opt.carrier_service_summary(store, carrier_id),
    }


@app.get("/api/carrier/{carrier_id}/optimization/recommendations/{recommendation_id}")
def carrier_recommendation_detail(carrier_id: str, recommendation_id: str) -> dict:
    _validate_carrier(carrier_id)
    detail = opt.recommendation_detail(store, carrier_id, recommendation_id)
    if detail is None:
        raise HTTPException(404, f"추천을 찾을 수 없습니다: {recommendation_id}")
    return detail


# --------------------------------------------------------- 프론트엔드 정적 서빙
#
# 배포 환경에서는 빌드된 프론트엔드를 같은 서버가 서빙해 URL 하나로 접속하게 한다.
# API 라우트를 모두 등록한 뒤에 마운트해야 /api 경로가 가려지지 않는다.
# 로컬 개발(Vite dev server)에서는 dist 가 없으므로 이 블록이 건너뛰어진다.

if config.STATIC_DIR.is_dir():
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    _INDEX = config.STATIC_DIR / "index.html"

    app.mount(
        "/assets",
        StaticFiles(directory=config.STATIC_DIR / "assets"),
        name="assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        """SPA 라우팅 지원.

        /inventory 같은 경로로 직접 들어오거나 새로고침해도 index.html 을 돌려준다.
        (BrowserRouter 를 쓰므로 이 fallback 이 없으면 404 가 난다)
        """
        candidate = (config.STATIC_DIR / full_path).resolve()
        if (
            full_path
            and candidate.is_file()
            and candidate.is_relative_to(config.STATIC_DIR)
        ):
            return FileResponse(candidate)
        return FileResponse(_INDEX)
