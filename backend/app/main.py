from fastapi import FastAPI

from app.routers import auth, forecasting, inventory, kitchen, menu, users

app = FastAPI(
    title="AI-Based Restaurant Resource Management and Order Demand Prediction System",
    description=(
        "Backend API. Sprint 1: Module 1 (User & Access Management), Module 2 "
        "(Menu & Recipe Management). Sprint 2: Module 3 (Inventory Management), "
        "Module 4 (Demand Forecasting), Module 5 (Kitchen Operations). "
        "Interactive docs at /docs (FastAPI's automatic OpenAPI generation — "
        "see Ch4 NFR-Maintainability)."
    ),
    version="0.2.0",
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(menu.router)
app.include_router(inventory.router)
app.include_router(forecasting.router)
app.include_router(kitchen.router)


@app.get("/health", tags=["health"])
def health_check() -> dict:
    return {"status": "ok"}
