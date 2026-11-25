"""
Module 11: Reporting & Analytics business logic. FR11.1-FR11.6.

PDF layout follows Ch4 §4.7.2's design principles precisely:
  01. Fixed white background (ReportLab's default — no theming).
  02. Single sans family (Helvetica, ReportLab's base font — no embedding).
  03. Color carries only data: blue/orange as the fixed predicted-vs-actual
      and leftover-vs-expiry pair; green reserved for "on track" only.
  04. Numbered sections mirror UC-RA-02's compile order: forecast accuracy,
      then waste cost & trends, then budget utilisation.
  05. Every figure is captioned with where it comes from (the FR it serves).
  06. Paginated — budget utilisation starts fresh on page 2.
"""
import os
from datetime import date, datetime, timezone
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.dates import end_of_day
from app.models.forecasting import Forecast, ForecastAccuracy
from app.models.kitchen import LeftoverLog
from app.models.menu import MenuItem
from app.models.procurement import Budget, PurchaseOrder
from app.models.report import Report
from app.models.staffing import ShiftAssignment, ShiftSchedule
from app.models.user import User
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
        select(Forecast, ForecastAccuracy, MenuItem.name)
        .join(ForecastAccuracy, ForecastAccuracy.forecast_id == Forecast.forecast_id)
        .join(MenuItem, MenuItem.menu_item_id == Forecast.menu_item_id)
        .where(Forecast.forecast_date >= period_start)
        .where(Forecast.forecast_date <= period_end)
        .order_by(Forecast.forecast_date)
    ).all()
    return [
        {
            "menu_item_id": f.menu_item_id,
            "menu_item_name": name,
            "meal_period": f.meal_period,
            "forecast_date": f.forecast_date,
            "predicted": f.predicted_quantity,
            "actual": a.actual_quantity,
            "error": a.accuracy_error,
        }
        for f, a, name in rows
    ]


def _waste_data(db: Session, period_start: date, period_end: date) -> dict:
    logs = db.scalars(
        select(WasteLog)
        .where(WasteLog.logged_at >= period_start)
        .where(WasteLog.logged_at <= end_of_day(period_end))
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
        .where(PurchaseOrder.created_at <= end_of_day(period_end))
        .where(PurchaseOrder.status != "rejected")
    ).all()
    spent = sum(spent_rows, Decimal("0.00"))
    utilisation_pct = (spent / limit * 100) if limit else Decimal("0")
    return {"limit": limit, "spent": spent, "utilisation_pct": utilisation_pct}


def _leftover_data(db: Session, period_start: date, period_end: date) -> dict:
    """The % leftover calculation for the period: per dish, what was prepared, what
    was served (prepared minus leftover) and what was left, from the leftover logs
    the kitchen's orders produce (leftover = confirmed prep - portions served)."""
    rows = db.execute(
        select(
            MenuItem.name,
            func.sum(LeftoverLog.prepared_quantity),
            func.sum(LeftoverLog.leftover_quantity),
        )
        .join(MenuItem, MenuItem.menu_item_id == LeftoverLog.menu_item_id)
        .where(LeftoverLog.service_period_date >= period_start)
        .where(LeftoverLog.service_period_date <= period_end)
        .group_by(MenuItem.name)
    ).all()
    dishes = []
    for name, prepared, leftover in rows:
        prepared, leftover = float(prepared or 0), float(leftover or 0)
        dishes.append(
            {
                "menu_item_name": name,
                "prepared": prepared,
                "served": prepared - leftover,
                "leftover": leftover,
                "leftover_percent": (leftover / prepared * 100) if prepared else 0.0,
            }
        )
    dishes.sort(key=lambda d: (-d["leftover_percent"], d["menu_item_name"]))
    prepared = sum(d["prepared"] for d in dishes)
    leftover = sum(d["leftover"] for d in dishes)
    return {
        "prepared": prepared,
        "served": prepared - leftover,
        "leftover": leftover,
        "leftover_percent": (leftover / prepared * 100) if prepared else 0.0,
        "dishes": dishes,
    }


_MEAL_ORDER = {"Breakfast": 0, "Lunch": 1, "Dinner": 2}


def _staffing_data(db: Session, period_start: date, period_end: date) -> list[dict]:
    """Who was assigned to which duty: every published shift in the period, with
    the people on it and their station."""
    schedules = db.scalars(
        select(ShiftSchedule)
        .where(ShiftSchedule.date >= period_start)
        .where(ShiftSchedule.date <= period_end)
        .where(ShiftSchedule.status == "published")
    ).all()
    schedules.sort(key=lambda s: (s.date, _MEAL_ORDER.get(s.meal_period, 9)))
    shifts = []
    for schedule in schedules:
        staff = db.execute(
            select(User.name, ShiftAssignment.station, ShiftAssignment.attendance_status)
            .join(User, User.user_id == ShiftAssignment.staff_id)
            .where(ShiftAssignment.schedule_id == schedule.schedule_id)
            .order_by(User.name)
        ).all()
        shifts.append(
            {
                "date": schedule.date,
                "meal_period": schedule.meal_period,
                "staff": [{"name": n, "station": st, "attendance": att} for n, st, att in staff],
            }
        )
    return shifts


def _report_extras(db: Session, period_start: date, period_end: date) -> dict:
    return {
        "leftover": _leftover_data(db, period_start, period_end),
        "staffing": _staffing_data(db, period_start, period_end),
    }


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
        pdf_path = _render_pdf(report, forecast_data, waste_data, budget_data, _report_extras(db, report.period_start, report.period_end))
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


def report_summary(db: Session, report: Report) -> dict:
    """UC-RA-01 main flow step 4 — "displays the report summary in-app": the
    same three sections the PDF holds (forecast accuracy, waste, budget),
    as data, so the app can show it without handing off to a PDF viewer."""
    forecast_data = _forecast_accuracy_data(db, report.period_start, report.period_end)
    waste_data = _waste_data(db, report.period_start, report.period_end)
    budget_data = _budget_data(db, report.period_start, report.period_end)
    errors = [float(row["error"]) for row in forecast_data]
    return {
        "report_id": report.report_id,
        "type": report.type,
        "status": report.status,
        "period_start": report.period_start,
        "period_end": report.period_end,
        "generated_at": report.generated_at,
        "forecast_accuracy": {
            "scored_forecasts": len(forecast_data),
            "mean_error": (sum(errors) / len(errors)) if errors else None,
            "rows": forecast_data,
        },
        "waste": waste_data,
        "budget": budget_data,
        **_report_extras(db, report.period_start, report.period_end),
    }


def regenerate_report(db: Session, report: Report) -> Report:
    """UC-RA-01 Alt Flow 4a — a report whose PDF generation failed can be
    regenerated in place (same row, same period) instead of the Manager
    having to create a second report for it."""
    forecast_data = _forecast_accuracy_data(db, report.period_start, report.period_end)
    waste_data = _waste_data(db, report.period_start, report.period_end)
    budget_data = _budget_data(db, report.period_start, report.period_end)
    if not _has_any_data(forecast_data, waste_data, budget_data):
        raise NoDataForPeriodError

    try:
        report.pdf_path = _render_pdf(report, forecast_data, waste_data, budget_data, _report_extras(db, report.period_start, report.period_end))
        report.status = "generated"
        report.generated_at = datetime.now(timezone.utc)
    except Exception:
        report.status = "failed"
        db.commit()
        raise
    db.commit()
    db.refresh(report)
    return report


def ensure_pdf(db: Session, report: Report) -> str | None:
    """FR11.2 — path of the report's PDF, re-rendering it from the database
    when the file isn't on this machine's disk. The API and the Celery worker
    run as separate containers with separate, ephemeral disks, so a PDF the
    worker wrote on Monday (or one written before the API last restarted)
    isn't there to serve. None when there is nothing to render (generation
    failed, or the period no longer has data)."""
    if report.status == "failed" or not report.pdf_path:
        return None
    if os.path.exists(report.pdf_path):
        return report.pdf_path

    forecast_data = _forecast_accuracy_data(db, report.period_start, report.period_end)
    waste_data = _waste_data(db, report.period_start, report.period_end)
    budget_data = _budget_data(db, report.period_start, report.period_end)
    if not _has_any_data(forecast_data, waste_data, budget_data):
        return None

    report.pdf_path = _render_pdf(report, forecast_data, waste_data, budget_data, _report_extras(db, report.period_start, report.period_end))
    db.commit()
    return report.pdf_path


def _fmt_day(d: date) -> str:
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b %Y')}"


def _fmt_stamp(dt: datetime) -> str:
    return f"{dt.day} {dt.strftime('%b %Y, %H:%M')} UTC"


def _by_dish(forecast_data: list[dict]) -> list[dict]:
    """One row per dish: portions predicted and sold over the period (Lunch
    and Dinner together) and the average forecast error, furthest off first."""
    grouped: dict[int, dict] = {}
    for row in forecast_data:
        g = grouped.setdefault(
            row["menu_item_id"],
            {"name": row.get("menu_item_name") or f"Menu item #{row['menu_item_id']}", "predicted": 0.0, "actual": 0.0, "errors": []},
        )
        g["predicted"] += float(row["predicted"])
        g["actual"] += float(row["actual"])
        g["errors"].append(float(row["error"]))
    dishes = [
        {"name": g["name"], "predicted": g["predicted"], "actual": g["actual"], "error": sum(g["errors"]) / len(g["errors"])}
        for g in grouped.values()
    ]
    return sorted(dishes, key=lambda d: d["error"], reverse=True)


def _render_pdf(
    report: Report, forecast_data: list[dict], waste_data: dict, budget_data: dict, extras: dict | None = None
) -> str:
    os.makedirs(REPORTS_DIR, exist_ok=True)
    filename = f"{report.period_end.isoformat()}_weekly_summary.pdf"
    path = os.path.join(REPORTS_DIR, filename)

    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4
    margin = 2 * cm
    content_w = width - 2 * margin
    generated = _fmt_stamp(datetime.now(timezone.utc))
    grey = colors.HexColor("#6B7280")
    panel = colors.HexColor("#F3F4F6")
    rule = colors.HexColor("#D1D5DB")
    black = colors.black
    page_count = 3
    extras = extras or {"leftover": None, "staffing": []}

    errors = [float(r["error"]) for r in forecast_data]
    mean_error = sum(errors) / len(errors) if errors else None
    utilisation = budget_data["utilisation_pct"]
    over_budget = utilisation > 100
    status_color = colors.HexColor("#D32F2F") if over_budget else COLOR_ON_TRACK
    status_label = "Over budget" if over_budget else "On track"

    def title_block(y_top: float) -> float:
        c.setFillColor(black)
        c.setFont("Helvetica-Bold", 20)
        c.drawString(margin, y_top, "Weekly Summary Report")
        c.setFont("Helvetica", 11)
        c.setFillColor(grey)
        c.drawString(margin, y_top - 18, f"{_fmt_day(report.period_start)}  to  {_fmt_day(report.period_end)}")
        c.setFillColor(black)
        c.setStrokeColor(rule)
        c.setLineWidth(1)
        c.line(margin, y_top - 30, width - margin, y_top - 30)
        return y_top - 30

    def section(y: float, label: str) -> float:
        c.setFillColor(black)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(margin, y, label)
        c.setStrokeColor(rule)
        c.line(margin, y - 7, width - margin, y - 7)
        return y - 26

    def caption(y: float, text: str) -> float:
        c.setFont("Helvetica-Oblique", 8)
        c.setFillColor(grey)
        for line in simpleSplit(text, "Helvetica-Oblique", 8, content_w):
            c.drawString(margin, y, line)
            y -= 11
        c.setFillColor(black)
        return y

    def footer(page: int):
        c.setStrokeColor(rule)
        c.line(margin, 1.7 * cm, width - margin, 1.7 * cm)
        c.setFont("Helvetica", 8)
        c.setFillColor(grey)
        c.drawString(margin, 1.2 * cm, f"Restaurant Ops  |  Weekly Summary Report  |  Generated {generated}")
        c.drawRightString(width - margin, 1.2 * cm, f"Page {page} of {page_count}")
        c.setFillColor(black)

    # --- Page 1: summary, Section 1 (Forecast Accuracy), Section 2 (Waste) ---
    y = title_block(height - margin)

    # Key figures, so the reader gets the point before the detail.
    gap = 0.4 * cm
    box_w = (content_w - 2 * gap) / 3
    box_h = 1.9 * cm
    box_y = y - 18 - box_h
    kpis = [
        ("Average forecast error", "n/a" if mean_error is None else f"{mean_error * 100:.1f}%"),
        ("Waste cost", f"RM {waste_data['total_cost']:.2f}"),
        ("Budget used", f"{utilisation:.1f}%"),
    ]
    for i, (label, value) in enumerate(kpis):
        x = margin + i * (box_w + gap)
        c.setFillColor(panel)
        c.roundRect(x, box_y, box_w, box_h, 6, fill=True, stroke=False)
        c.setFillColor(grey)
        c.setFont("Helvetica", 9)
        c.drawString(x + 0.4 * cm, box_y + box_h - 0.65 * cm, label)
        c.setFillColor(black)
        c.setFont("Helvetica-Bold", 17)
        c.drawString(x + 0.4 * cm, box_y + 0.5 * cm, value)
    y = box_y - 32

    y = section(y, "1. Forecast Accuracy")
    dishes = _by_dish(forecast_data)
    if dishes:
        col_pred = margin + 8.2 * cm
        col_act = margin + 11.2 * cm
        col_err = width - margin
        row_h = 15
        c.setFillColor(panel)
        c.rect(margin, y - 4, content_w, row_h, fill=True, stroke=False)
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(black)
        c.drawString(margin + 4, y, "Dish (Lunch and Dinner)")
        c.setFillColor(COLOR_PREDICTED)
        c.drawRightString(col_pred, y, "Predicted")
        c.setFillColor(COLOR_ACTUAL)
        c.drawRightString(col_act, y, "Actual")
        c.setFillColor(black)
        c.drawRightString(col_err - 4, y, "Avg error")
        y -= row_h
        c.setFont("Helvetica", 9)
        for d in dishes[:14]:  # a summary, not a raw dump
            c.drawString(margin + 4, y, d["name"])
            c.setFillColor(COLOR_PREDICTED)
            c.drawRightString(col_pred, y, f"{d['predicted']:.0f}")
            c.setFillColor(COLOR_ACTUAL)
            c.drawRightString(col_act, y, f"{d['actual']:.0f}")
            c.setFillColor(black)
            c.drawRightString(col_err - 4, y, f"{d['error'] * 100:.1f}%")
            c.setStrokeColor(rule)
            c.setLineWidth(0.4)
            c.line(margin, y - 4, width - margin, y - 4)
            y -= row_h
        y = caption(
            y - 2,
            "Portions summed over the period; furthest-off dishes first. Error is the average of |predicted - actual| / actual. "
            "Source: forecast accuracy records (FR4.4, FR11.3).",
        )
    else:
        c.setFont("Helvetica", 10)
        c.drawString(margin, y, "No forecasts were scored in this period.")
        y -= 16

    y -= 22
    y = section(y, "2. Waste Cost & Trends")
    leftover = waste_data["leftover_cost"]
    expiry = waste_data["expiry_cost"]
    total = leftover + expiry
    c.setFont("Helvetica", 10)
    if waste_data["log_count"] == 0:
        c.drawString(margin, y, "No waste was recorded in this period.")
        y -= 16
    else:
        bar_w = content_w
        left_w = float(leftover / total) * bar_w if total else 0
        c.setFillColor(COLOR_LEFTOVER)
        c.rect(margin, y - 6, left_w, 14, fill=True, stroke=False)
        c.setFillColor(COLOR_EXPIRY)
        c.rect(margin + left_w, y - 6, bar_w - left_w, 14, fill=True, stroke=False)
        y -= 28
        for color, label, value in ((COLOR_LEFTOVER, "Leftover-sourced", leftover), (COLOR_EXPIRY, "Expiry-sourced", expiry)):
            c.setFillColor(color)
            c.rect(margin, y - 1, 8, 8, fill=True, stroke=False)
            c.setFillColor(black)
            c.setFont("Helvetica", 10)
            c.drawString(margin + 14, y, label)
            c.drawRightString(margin + 8 * cm, y, f"RM {value:.2f}")
            y -= 15
        c.setFont("Helvetica-Bold", 11)
        c.drawString(margin, y - 4, f"Total waste cost this period: RM {total:.2f}  ({waste_data['log_count']} entries)")
        y -= 22
    caption(y, "Source: waste logs by origin, leftovers and expired stock (FR6.1-FR6.3, FR11.4).")
    footer(1)
    c.showPage()

    # --- Page 2: Section 3 (% Leftover) and Section 4 (Staff Assignment) -----
    y = title_block(height - margin)
    y = section(y - 28, "3. Leftover Calculation")
    left = extras["leftover"]
    c.setFont("Helvetica", 10)
    if not left or not left["dishes"]:
        c.drawString(margin, y, "No leftovers were recorded in this period.")
        y -= 16
    else:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(
            margin,
            y,
            f"{left['leftover_percent']:.1f}% of what was prepared was left over "
            f"({left['leftover']:.0f} of {left['prepared']:.0f} portions).",
        )
        y -= 20
        col_prep = margin + 8.4 * cm
        col_served = margin + 11.0 * cm
        col_left = margin + 13.6 * cm
        col_pct = width - margin
        row_h = 15
        c.setFillColor(panel)
        c.rect(margin, y - 4, content_w, row_h, fill=True, stroke=False)
        c.setFillColor(black)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(margin + 4, y, "Dish")
        c.drawRightString(col_prep, y, "Prepared")
        c.drawRightString(col_served, y, "Served")
        c.drawRightString(col_left, y, "Left over")
        c.drawRightString(col_pct - 4, y, "% left")
        y -= row_h
        c.setFont("Helvetica", 9)
        for d in left["dishes"][:12]:
            c.drawString(margin + 4, y, d["menu_item_name"])
            c.drawRightString(col_prep, y, f"{d['prepared']:.0f}")
            c.drawRightString(col_served, y, f"{d['served']:.0f}")
            c.drawRightString(col_left, y, f"{d['leftover']:.0f}")
            c.drawRightString(col_pct - 4, y, f"{d['leftover_percent']:.1f}%")
            c.setStrokeColor(rule)
            c.setLineWidth(0.4)
            c.line(margin, y - 4, width - margin, y - 4)
            y -= row_h
        y = caption(
            y - 2,
            "Leftover = confirmed prep minus the portions served (completed orders). Highest share left over first.",
        )

    y -= 24
    y = section(y, "4. Staff Assignment")
    shifts = extras["staffing"]
    if not shifts:
        c.setFont("Helvetica", 10)
        c.drawString(margin, y, "No shifts were published in this period.")
        y -= 16
    else:
        for shift in shifts[:14]:
            c.setFont("Helvetica-Bold", 9)
            c.drawString(margin + 4, y, f"{_fmt_day(shift['date'])}  {shift['meal_period']}")
            names = ", ".join(f"{p['name']} ({p['station']})" for p in shift["staff"]) or "no one assigned"
            c.setFont("Helvetica", 9)
            lines = simpleSplit(names, "Helvetica", 9, content_w - 5.2 * cm)
            for i, line in enumerate(lines):
                c.drawString(margin + 5.2 * cm, y, line)
                if i < len(lines) - 1:
                    y -= 11
            c.setStrokeColor(rule)
            c.setLineWidth(0.4)
            c.line(margin, y - 4, width - margin, y - 4)
            y -= 15
        if len(shifts) > 14:
            y = caption(y, f"and {len(shifts) - 14} more shifts this period.")
    caption(y, "Source: published shift schedules and their assignments (FR8.1-FR8.5).")
    footer(2)
    c.showPage()

    # --- Page 3: Section 5 (Budget Utilisation) ---------------------------
    y = title_block(height - margin)
    y = section(y - 28, "5. Budget Utilisation")
    spent = budget_data["spent"]
    limit = budget_data["limit"]
    rows = [
        ("Monthly budget limit", f"RM {limit:.2f}"),
        ("Ordered this period", f"RM {spent:.2f}"),
        ("Remaining of the monthly limit", f"RM {limit - spent:.2f}"),
    ]
    c.setFont("Helvetica", 11)
    for label, value in rows:
        c.setFillColor(black)
        c.drawString(margin + 4, y, label)
        c.drawRightString(margin + 9 * cm, y, value)
        c.setStrokeColor(rule)
        c.setLineWidth(0.4)
        c.line(margin, y - 6, margin + 9 * cm + 4, y - 6)
        y -= 20
    y -= 6
    c.setFillColor(status_color)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(margin + 4, y, f"Utilisation: {utilisation:.1f}%  -  {status_label}")
    y -= 24

    bar_w = content_w
    c.setStrokeColor(colors.grey)
    c.setLineWidth(0.8)
    c.rect(margin, y, bar_w, 16, fill=False, stroke=True)
    c.setFillColor(status_color)
    c.rect(margin, y, min(float(utilisation) / 100, 1.0) * bar_w, 16, fill=True, stroke=False)
    c.setFillColor(black)
    y -= 18
    y = caption(y, "Source: monthly budget and purchase orders raised in the period, excluding rejected ones (FR9.4, FR11.5).")

    y -= 30
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin, y, "About this report")
    y -= 18
    c.setFont("Helvetica", 9)
    c.setFillColor(grey)
    notes = [
        "Forecast accuracy compares what the system predicted with what was actually ordered, for days that have been scored.",
        "Waste cost values wasted ingredients at the supplier prices recorded in the system.",
        "The budget figure is the whole month's limit; the period's spend is not a monthly total.",
    ]
    for note in notes:
        for line in simpleSplit(note, "Helvetica", 9, content_w - 12):
            c.drawString(margin + 12, y, line)
            y -= 12
        y -= 4
    c.setFillColor(black)
    footer(3)
    c.showPage()
    c.save()
    return path


def list_reports(db: Session) -> list[Report]:
    return list(db.scalars(select(Report).order_by(Report.generated_at.desc())))


def get_report(db: Session, report_id: int) -> Report | None:
    return db.get(Report, report_id)
