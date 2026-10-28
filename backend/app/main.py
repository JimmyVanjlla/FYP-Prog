from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging_config import configure_logging, get_logger
from app.routers import (
    auth,
    config,
    delivery,
    feedback,
    forecasting,
    inventory,
    kitchen,
    menu,
    procurement,
    reporting,
    staffing,
    users,
    waste,
)

app = FastAPI(
    title="AI-Based Restaurant Resource Management and Order Demand Prediction System",
    description=(
        "Backend API. Sprint 1: Module 1 (User & Access Management), Module 2 "
        "(Menu & Recipe Management). Sprint 2: Module 3 (Inventory Management), "
        "Module 4 (Demand Forecasting), Module 5 (Kitchen Operations). Sprint 3: "
        "Module 6 (Waste Management), Module 7 (Portion & Forecast Feedback), "
        "Module 8 (Staff Scheduling). Sprint 4: Module 9 (Procurement & Supplier "
        "Management), Module 10 (Delivery Management). Sprint 5: Module 11 "
        "(Reporting & Analytics). Interactive docs at /docs (FastAPI's "
        "automatic OpenAPI generation — see Ch4 NFR-Maintainability)."
    ),
    version="0.5.0",
)

configure_logging()
logger = get_logger(__name__)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    # Empty by default (see Settings.cors_allowed_origins) — the Flutter
    # mobile app isn't affected either way; a web target sets
    # CORS_ALLOWED_ORIGINS explicitly rather than inheriting an open policy.
    allow_origins=_settings.cors_allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Previously an unhandled exception in a route just became a bare 500
    with the traceback visible only in whatever terminal happened to be
    running uvicorn at the time — nothing was captured anywhere once that
    scrollback was gone. This logs the full exception server-side (via the
    centralized logging setup above) before returning a generic message,
    so the client never sees internal details it shouldn't."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred."},
    )


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(menu.router)
app.include_router(inventory.router)
app.include_router(forecasting.router)
app.include_router(kitchen.router)
app.include_router(waste.router)
app.include_router(feedback.router)
app.include_router(staffing.router)
app.include_router(procurement.router)
app.include_router(delivery.router)
app.include_router(reporting.router)
app.include_router(config.router)


@app.get("/health", tags=["health"])
def health_check() -> dict:
    return {"status": "ok"}
