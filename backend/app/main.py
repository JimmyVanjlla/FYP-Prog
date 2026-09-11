from fastapi import FastAPI

from app.routers import (
    auth,
    delivery,
    feedback,
    forecasting,
    inventory,
    kitchen,
    menu,
    procurement,
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
        "Management), Module 10 (Delivery Management). Interactive docs at /docs "
        "(FastAPI's automatic OpenAPI generation — see Ch4 NFR-Maintainability)."
    ),
    version="0.4.0",
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


@app.get("/health", tags=["health"])
def health_check() -> dict:
    return {"status": "ok"}
