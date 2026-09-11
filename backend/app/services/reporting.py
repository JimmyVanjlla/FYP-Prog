"""
Module 11: Reporting & Analytics business logic. FR11.1-FR11.6.

PDF layout follows Ch4 §4.7.2's design principles precisely:
  01. Fixed white background (ReportLab's default — no theming).
  02. Single sans family (Helvetica, ReportLab's base font — no embedding).
  03. Color carries only data: blue/orange as the fixed predicted-vs-actual
      and leftover-vs-expiry pair; green reserved for "on track" only.
  04. Numbered sections mirror UC-RA-02's compile order: forecast accuracy,
      then waste cost & trends, then budget utilisation.
  05. Every figure is captioned with the FR/entity it's drawn from.
  06. Paginated — budget utilisation starts fresh on page 2.
"""
import os
from datetime import date, datetime, timezone
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.forecasting import Forecast, ForecastAccuracy
from app.models.procurement import Budget, PurchaseOrder
from app.models.report import Report
from app.models.waste import WasteLog
from app.services.config import get_or_create_config

# Ch4 §4.7.2 principle 03 — fixed categorical pair, reused everywhere.
COLOR_PREDICTED = colors.HexColor("#1565C0")  # blue
COLOR_ACTUAL = colors.HexColor("#EF6C00")  # orange
COLOR_ON_TRACK = colors.HexColor("#2E7D32")  # green — status only, never a series
COLOR_LEFTOVER = colors.HexColor("#1565C0")
COLOR_EXPIRY = colors.HexColor("#EF6C00")

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "generated_reports")


class NoDataForPeriodError(Exception):
    """FR11.6."""


def _forecast_accuracy_data(db: Session, period_start: date, period_end: date) -> list[dict]:
    rows = db.execute(
        select(Forecast, ForecastAccuracy)
        .join(ForecastAccuracy, ForecastAccuracy.forecast_id == Forecast.forecast_id)
        .where(Forecast.forecast_date >= period_start)
        .where(Forecast.forecast_date <= period_end)
        .order_by(Forecast.forecast_date)
    ).all()
    return [
        {
            "menu_item_id": f.menu_item_id,
            "meal_period": f.meal_period,
            "forecast_date": f.forecast_date,
            "predicted": f.predicted_quantity,
            "actual": a.actual_quantity,
            "error": a.accuracy_error,
        }
        for f, a in rows
    ]


def _waste_data(db: Session, period_start: date, period_end: date) -> dict:
    logs = db.scalars(
        select(WasteLog).where(WasteLog.logged_at >= period_start).where(WasteLog.logged_at <= period_end)
    ).all()
    leftover_cost = sum((l.waste_cost for l in logs if l.source_type == "leftover"), Decimal("0.00"))
    expiry_cost = sum((l.waste_cost for l in logs if l.source_type == "expiry"), Decimal("0.00"))
    return {"leftover_cost": leftover_cost, "expiry_cost": expiry_cost, "total_cost": leftover_cost + expiry_cost, "log_count": len(logs)}


def _budget_data(db: Session, period_start: date, period_end: date) -> dict:
    month_start = period_start.replace(day=1)
    budget = db.scalars(select(Budget).where(Budget.month == month_start)).first()
    limit = budget.budget_limit if budget else get_or_create_config(db).monthly_budget_limit

    spent_rows = db.scalars(
        select(PurchaseOrder.total_cost)
        .where(PurchaseOrder.created_at >= period_start)
        .where(PurchaseOrder.created_at <= period_end)
        .where(PurchaseOrder.status != "rejected")
    ).all()
    spent = sum(spent_rows, Decimal("0.00"))
    utilisation_pct = (spent / limit * 100) if limit else Decimal("0")
    return {"limit": limit, "spent": spent, "utilisation_pct": utilisation_pct}


def _has_any_data(forecast_data: list, waste_data: dict, budget_data: dict) -> bool:
    return bool(forecast_data) or waste_data["log_count"] > 0 or budget_data["spent"] > 0


def generate_weekly_report(db: Session, *, period_start: date, period_end: date) -> Report:
    """FR11.1 / FR11.3-FR11.6 — compiles and PDF-exports the weekly
    summary (UC-RA-02's forecast-accuracy -> waste -> budget order)."""
    forecast_data = _forecast_accuracy_data(db, period_start, period_end)
    waste_data = _waste_data(db, period_start, period_end)
    budget_data = _budget_data(db, period_start, period_end)

    if not _has_any_data(forecast_data, waste_data, budget_data):
        raise NoDataForPeriodError

    report = Report(type="weekly_summary", period_start=period_start, period_end=period_end, status="generated")
    db.add(report)
    db.flush()

    try:
        pdf_path = _render_pdf(report, forecast_data, waste_data, budget_data)
        report.pdf_path = pdf_path
    except Exception:
        # NFR4.1 — retried automatically up to 3 times by the Celery task
        # wrapper; here we just record that generation didn't complete.
        report.status = "failed"
        db.commit()
        raise

    db.commit()
    db.refresh(report)
    return report


def _render_pdf(report: Report, forecast_data: list[dict], waste_data: dict, budget_data: dict) -> str:
    os.makedirs(REPORTS_DIR, exist_ok=True)
    filename = f"{report.period_end.isoformat()}_weekly_summary.pdf"
    path = os.path.join(REPORTS_DIR, filename)

    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4
    margin = 2 * cm

    def header(title: str):
        c.setFont("Helvetica-Bold", 16)
        c.drawString(margin, height - margin, "Weekly Summary Report")
        c.setFont("Helvetica", 10)
        c.drawString(margin, height - margin - 18, f"{report.period_start} to {report.period_end}")
        c.setFont("Helvetica-Bold", 13)
        c.drawString(margin, height - margin - 50, title)
        c.setStrokeColor(colors.grey)
        c.line(margin, height - margin - 58, width - margin, height - margin - 58)

    # --- Page 1: Section 1 (Forecast Accuracy), Section 2 (Waste) --------
    header("1. Forecast Accuracy")
    y = height - margin - 80
    c.setFont("Helvetica", 9)
    if forecast_data:
        c.drawString(margin, y, "Item")
        c.setFillColor(COLOR_PREDICTED)
        c.drawString(margin + 6 * cm, y, "Predicted")
        c.setFillColor(COLOR_ACTUAL)
        c.drawString(margin + 9 * cm, y, "Actual")
        c.setFillColor(colors.black)
        c.drawString(margin + 12 * cm, y, "Error")
        y -= 14
        for row in forecast_data[:15]:  # cap rows per page — this is a summary, not a raw dump
            c.drawString(margin, y, f"#{row['menu_item_id']} ({row['meal_period']}, {row['forecast_date']})")
            c.setFillColor(COLOR_PREDICTED)
            c.drawString(margin + 6 * cm, y, str(row["predicted"]))
            c.setFillColor(COLOR_ACTUAL)
            c.drawString(margin + 9 * cm, y, str(row["actual"]))
            c.setFillColor(colors.black)
            c.drawString(margin + 12 * cm, y, f"{Decimal(row['error']) * 100:.1f}%")
            y -= 14
    else:
        c.drawString(margin, y, "No scored forecasts in this period.")
        y -= 14
    c.setFont("Helvetica-Oblique", 7)
    c.setFillColor(colors.grey)
    c.drawString(margin, y - 6, "Source: Forecast, ForecastAccuracy (FR4.4, FR11.3)")
    c.setFillColor(colors.black)

    y -= 40
    header_y_2 = y
    c.setFont("Helvetica-Bold", 13)
    c.drawString(margin, header_y_2, "2. Waste Cost & Trends")
    c.setStrokeColor(colors.grey)
    c.line(margin, header_y_2 - 8, width - margin, header_y_2 - 8)
    y = header_y_2 - 30

    bar_base_y = y - 60
    bar_max_width = 8 * cm
    max_cost = max(waste_data["leftover_cost"], waste_data["expiry_cost"], Decimal("1"))
    leftover_w = float(waste_data["leftover_cost"] / max_cost) * float(bar_max_width)
    expiry_w = float(waste_data["expiry_cost"] / max_cost) * float(bar_max_width)

    c.setFont("Helvetica", 10)
    c.setFillColor(COLOR_LEFTOVER)
    c.rect(margin, bar_base_y + 20, leftover_w, 14, fill=True, stroke=False)
    c.setFillColor(colors.black)
    c.drawString(margin, bar_base_y + 38, f"Leftover-sourced: RM {waste_data['leftover_cost']}")

    c.setFillColor(COLOR_EXPIRY)
    c.rect(margin, bar_base_y, expiry_w, 14, fill=True, stroke=False)
    c.setFillColor(colors.black)
    c.drawString(margin, bar_base_y - 4, f"Expiry-sourced: RM {waste_data['expiry_cost']}")

    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin, bar_base_y - 30, f"Total waste cost this period: RM {waste_data['total_cost']}")
    c.setFont("Helvetica-Oblique", 7)
    c.setFillColor(colors.grey)
    c.drawString(margin, bar_base_y - 46, "Source: WasteLog.source_type, WasteLog.waste_cost (FR6.1-FR6.3, FR11.4)")
    c.setFillColor(colors.black)

    c.setFont("Helvetica", 8)
    c.drawString(margin, 1.2 * cm, f"Generated {datetime.now(timezone.utc).isoformat()} — page 1 of 2")
    c.showPage()

    # --- Page 2: Section 3 (Budget Utilisation) ---------------------------
    header("3. Budget Utilisation")
    y = height - margin - 90
    c.setFont("Helvetica", 11)
    c.drawString(margin, y, f"Monthly budget limit: RM {budget_data['limit']}")
    y -= 18
    c.drawString(margin, y, f"Spent this period: RM {budget_data['spent']}")
    y -= 18

    utilisation = budget_data["utilisation_pct"]
    status_color = COLOR_ON_TRACK if utilisation <= 100 else colors.HexColor("#D32F2F")
    status_label = "On track" if utilisation <= 100 else "Over budget"
    c.setFillColor(status_color)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin, y, f"Utilisation: {utilisation:.1f}% — {status_label}")
    c.setFillColor(colors.black)
    y -= 30

    bar_w = 10 * cm
    filled_w = min(float(utilisation) / 100, 1.0) * float(bar_w)
    c.setStrokeColor(colors.grey)
    c.rect(margin, y, bar_w, 16, fill=False, stroke=True)
    c.setFillColor(status_color)
    c.rect(margin, y, filled_w, 16, fill=True, stroke=False)
    c.setFillColor(colors.black)

    c.setFont("Helvetica-Oblique", 7)
    c.setFillColor(colors.grey)
    c.drawString(margin, y - 20, "Source: Budget.budget_limit, PurchaseOrder.total_cost (FR9.4, FR11.5)")
    c.setFillColor(colors.black)

    c.setFont("Helvetica", 8)
    c.drawString(margin, 1.2 * cm, f"Generated {datetime.now(timezone.utc).isoformat()} — page 2 of 2")
    c.showPage()
    c.save()
    return path


def list_reports(db: Session) -> list[Report]:
    return list(db.scalars(select(Report).order_by(Report.generated_at.desc())))


def get_report(db: Session, report_id: int) -> Report | None:
    return db.get(Report, report_id)
