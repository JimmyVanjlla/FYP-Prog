from fastapi import FastAPI

from app.routers import auth, menu, users

app = FastAPI(
    title="AI-Based Restaurant Resource Management and Order Demand Prediction System",
    description=(
        "Backend API. Sprint 1 scope: Module 1 (User & Access Management) "
        "and Module 2 (Menu & Recipe Management). Interactive docs at /docs "
        "(FastAPI's automatic OpenAPI generation — see Ch4 NFR-Maintainability)."
    ),
    version="0.1.0",
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(menu.router)


@app.get("/health", tags=["health"])
def health_check() -> dict:
    return {"status": "ok"}
