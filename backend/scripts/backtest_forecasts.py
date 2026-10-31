"""
Rolling-origin backtest of the demand-forecasting model (Chapter 1: forecast
accuracy "measured against the manual baseline").

For every (menu item, meal period) series the model is trained on the first
`--initial-days` days, asked to forecast the next `--horizon` days (exactly
what a daily training run does), scored against what actually happened, then
the window is extended by `--step` days and repeated. Nothing in the test
period is ever visible to the model that predicts it.

Compared against simple alternatives a manager could run without any model:
  - same weekday last week           ("same as last week")
  - average of the same weekday over the last 4 weeks
  - trailing 7-day average           (a flat "recent average")
and, when the data was produced by scripts/seed_dev_data.py, the generator's
true mean, which is the best any model could do on that data (a noise floor).

Prophet is configured exactly as app/services/forecasting.py does it
(weekly + yearly seasonality, point forecast only). The FR4.5 leftover
adjustment is not applied: it needs leftover logs and is a separate mechanism.

Usage (from backend/, venv active):
    python scripts/backtest_forecasts.py --save-snapshot ../evaluation/orders_snapshot.csv \
        --out-dir ../evaluation --oracle
    python scripts/backtest_forecasts.py --orders-csv ../evaluation/orders_snapshot.csv \
        --out-dir ../evaluation --oracle      # reproduce without the database
"""
import argparse
import logging
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PROPHET = "Prophet (deployed)"
PROPHET_WK = "Prophet weekly-only"
PROPHET_MULT = "Prophet weekly-only multiplicative"
PROPHET_STIFF = "Prophet weekly-only stiff trend"
# The first is what app/services/forecasting.py runs (and what Chapter 4's
# Algorithm 1 specifies). The rest are alternatives to measure it against;
# the last two are sensitivity checks, not candidates tuned on this data.
PROPHET_CONFIGS = {
    PROPHET: {"weekly_seasonality": True, "yearly_seasonality": True},
    PROPHET_WK: {"weekly_seasonality": True, "yearly_seasonality": False},
    PROPHET_MULT: {"weekly_seasonality": True, "yearly_seasonality": False, "seasonality_mode": "multiplicative"},
    PROPHET_STIFF: {"weekly_seasonality": True, "yearly_seasonality": False, "changepoint_prior_scale": 0.01},
}
SNAIVE = "Same weekday last week"
AVG4 = "Same weekday, 4-week average"
TRAIL7 = "Trailing 7-day average"
ORACLE = "Noise floor (true mean)"


def load_orders(args) -> tuple[pd.DataFrame, dict[int, str]]:
    if args.orders_csv:
        frame = pd.read_csv(args.orders_csv, parse_dates=["ds"])
        names = (
            frame.drop_duplicates("menu_item_id").set_index("menu_item_id")["item_name"].to_dict()
            if "item_name" in frame
            else {}
        )
        return frame, names

    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.menu import MenuItem
    from app.services.forecasting import _load_grouped_orders

    db = SessionLocal()
    try:
        grouped = _load_grouped_orders(db)
        names = {m.menu_item_id: m.name for m in db.scalars(select(MenuItem))}
    finally:
        db.close()
    grouped["item_name"] = grouped["menu_item_id"].map(names)
    if args.save_snapshot:
        path = Path(args.save_snapshot)
        path.parent.mkdir(parents=True, exist_ok=True)
        grouped.to_csv(path, index=False)
        print(f"saved order snapshot: {path} ({len(grouped)} rows)")
    return grouped, names


def prophet_forecast(train: pd.DataFrame, horizon: int, config: dict) -> np.ndarray:
    from prophet import Prophet

    model = Prophet(daily_seasonality=False, uncertainty_samples=0, **config)
    model.fit(train[["ds", "y"]])
    out = model.predict(model.make_future_dataframe(periods=horizon))
    return np.maximum(0.0, out["yhat"].to_numpy()[-horizon:])


def baseline_forecasts(series: pd.Series, test_dates: pd.DatetimeIndex) -> dict[str, np.ndarray]:
    """`series` is the training window only, indexed by date."""
    snaive, avg4 = [], []
    for d in test_dates:
        same_day = [series.get(d - pd.Timedelta(days=7 * k), np.nan) for k in range(1, 5)]
        snaive.append(same_day[0])
        avg4.append(np.nanmean(same_day))
    trail7 = float(series.iloc[-7:].mean())
    return {SNAIVE: np.array(snaive), AVG4: np.array(avg4), TRAIL7: np.full(len(test_dates), trail7)}


def oracle_means(frame: pd.DataFrame, names: dict[int, str]) -> pd.Series | None:
    """The generator's true mean for each row, or None if the data did not
    come from scripts/seed_dev_data.py."""
    try:
        from scripts import seed_dev_data as seed
    except Exception:
        return None
    demand = {name: avg for name, _c, _p, _r, avg in seed.MENU_ITEMS}
    share = {"Lunch": 0.55, "Dinner": 0.45}
    weeks = seed.WEEKS_OF_ORDER_HISTORY
    start = frame["ds"].min()
    if (frame["ds"].max() - start).days + 1 != weeks * 7:
        return None
    means = []
    for _, r in frame.iterrows():
        name = names.get(int(r["menu_item_id"]))
        if name not in demand or r["meal_period"] not in share:
            return None
        offset = (r["ds"] - start).days
        boost = 1.3 if r["ds"].weekday() >= 5 else 1.0
        trend = 1.0 + 0.15 * (offset / (weeks * 7))
        means.append(demand[name] * share[r["meal_period"]] * boost * trend)
    return pd.Series(means, index=frame.index)


def run_backtest(frame: pd.DataFrame, names: dict[int, str], args) -> pd.DataFrame:
    oracle = oracle_means(frame, names) if args.oracle else None
    if args.oracle and oracle is None:
        print("note: --oracle requested but the data does not match the seed generator; skipping it")
    if oracle is not None:
        frame = frame.assign(_oracle=oracle)

    rows = []
    groups = list(frame.groupby(["menu_item_id", "meal_period"]))
    for gi, ((item_id, period), grp) in enumerate(groups, start=1):
        grp = grp.sort_values("ds").reset_index(drop=True)
        series = grp.set_index("ds")["y"].asfreq("D")  # gaps become NaN, never silently zero
        n = len(series)
        cutoffs = range(args.initial_days, n - args.horizon + 1, args.step)
        for fold, cut in enumerate(cutoffs, start=1):
            train = series.iloc[:cut]
            test = series.iloc[cut : cut + args.horizon]
            train_df = train.dropna().reset_index()
            train_df.columns = ["ds", "y"]
            preds = {name: prophet_forecast(train_df, args.horizon, cfg) for name, cfg in PROPHET_CONFIGS.items()}
            preds.update(baseline_forecasts(train, test.index))
            if oracle is not None:
                o = grp.set_index("ds")["_oracle"].reindex(test.index).to_numpy()
                preds[ORACLE] = o
            for i, (d, actual) in enumerate(test.items()):
                if pd.isna(actual):
                    continue
                row = {
                    "menu_item_id": int(item_id),
                    "item": names.get(int(item_id), str(item_id)),
                    "meal_period": period,
                    "fold": fold,
                    "ds": d.date().isoformat(),
                    "horizon_day": i + 1,
                    "weekend": d.weekday() >= 5,
                    "actual": float(actual),
                }
                for model, p in preds.items():
                    row[model] = float(p[i])
                rows.append(row)
        print(f"  [{gi}/{len(groups)}] {names.get(int(item_id), item_id)} / {period}: {len(list(cutoffs))} folds", flush=True)
    return pd.DataFrame(rows)


def metrics(df: pd.DataFrame, model: str) -> dict[str, float]:
    ok = df[model].notna()
    a, p = df.loc[ok, "actual"].to_numpy(), df.loc[ok, model].to_numpy()
    e = p - a
    return {
        "WAPE %": 100 * np.abs(e).sum() / a.sum(),
        "MAE": np.abs(e).mean(),
        "MAPE %": 100 * (np.abs(e) / a).mean(),
        "Bias %": 100 * e.sum() / a.sum(),
        "Within 20 %": 100 * (np.abs(e) / a <= 0.2).mean(),
        "n": int(ok.sum()),
    }


def md_table(frame: pd.DataFrame, decimals: int = 1) -> str:
    cols = [frame.index.name or ""] + [str(c) for c in frame.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for idx, r in frame.iterrows():
        cells = [str(idx)] + [
            (f"{v:.{decimals}f}" if isinstance(v, (float, np.floating)) else str(v)) for v in r.tolist()
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def series_wape(df: pd.DataFrame, model: str) -> pd.Series:
    g = df.groupby(["menu_item_id", "meal_period"])
    return g.apply(lambda x: 100 * (x[model] - x["actual"]).abs().sum() / x["actual"].sum(), include_groups=False)


def bootstrap_diff(df: pd.DataFrame, a: str, b: str, draws: int = 4000, seed: int = 7) -> tuple[float, float, float]:
    """WAPE(a) - WAPE(b), resampling whole series (not single days, which are
    correlated within a series). Negative means `a` is better."""
    rng = np.random.default_rng(seed)
    keys = df.groupby(["menu_item_id", "meal_period"]).ngroup().to_numpy()
    n_series = keys.max() + 1
    err_a = np.bincount(keys, weights=(df[a] - df["actual"]).abs().to_numpy(), minlength=n_series)
    err_b = np.bincount(keys, weights=(df[b] - df["actual"]).abs().to_numpy(), minlength=n_series)
    act = np.bincount(keys, weights=df["actual"].to_numpy(), minlength=n_series)
    diffs = []
    for _ in range(draws):
        pick = rng.integers(0, n_series, n_series)
        diffs.append(100 * (err_a[pick].sum() - err_b[pick].sum()) / act[pick].sum())
    point = 100 * (err_a.sum() - err_b.sum()) / act.sum()
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return point, lo, hi


def build_report(df: pd.DataFrame, args) -> str:
    prophets = [PROPHET, PROPHET_WK, PROPHET_MULT, PROPHET_STIFF]
    models = [m for m in (*prophets, SNAIVE, AVG4, TRAIL7, ORACLE) if m in df.columns]
    out = []
    n_series = df.groupby(["menu_item_id", "meal_period"]).ngroups
    out.append(
        f"Series: {n_series}. Forecast folds per series: {df['fold'].max()}. "
        f"Scored predictions: {len(df)} per model. Training starts at {args.initial_days} days, "
        f"forecast horizon {args.horizon} days, window extended by {args.step} days per fold."
    )

    overall = pd.DataFrame({m: metrics(df, m) for m in models}).T
    overall.index.name = "Model"
    out.append("### Overall\n\n" + md_table(overall.drop(columns="n")))

    by_h = pd.DataFrame({m: df.groupby("horizon_day").apply(lambda x, m=m: metrics(x, m)["WAPE %"], include_groups=False) for m in models})
    by_h.index.name = "Days ahead (WAPE %)"
    out.append("### Error by how far ahead the forecast is\n\n" + md_table(by_h))

    by_w = pd.DataFrame(
        {m: df.groupby("weekend").apply(lambda x, m=m: metrics(x, m)["WAPE %"], include_groups=False) for m in models}
    )
    by_w.index = ["Weekday" if not i else "Weekend" for i in by_w.index]
    by_w.index.name = "Day type (WAPE %)"
    out.append("### Weekdays versus weekends\n\n" + md_table(by_w))

    by_f = pd.DataFrame({m: df.groupby("fold").apply(lambda x, m=m: metrics(x, m)["WAPE %"], include_groups=False) for m in models})
    by_f.index.name = "Fold (WAPE %)"
    out.append("### Stability across folds (a longer history is available in later folds)\n\n" + md_table(by_f))

    by_i = pd.DataFrame(
        {m: df.groupby("item").apply(lambda x, m=m: metrics(x, m)["WAPE %"], include_groups=False) for m in models}
    ).sort_values(PROPHET_WK)
    by_i.index.name = "Menu item (WAPE %)"
    out.append("### By menu item (Lunch and Dinner combined)\n\n" + md_table(by_i))

    sw = {m: series_wape(df, m) for m in models}
    wins = []
    for p in prophets:
        row = {"Model": p}
        for base in (SNAIVE, AVG4, TRAIL7):
            row[f"Better than '{base}'"] = f"{int((sw[p] < sw[base]).sum())} of {n_series}"
        wins.append(row)
    out.append("### Head to head, series by series\n\nNumber of series where the Prophet variant has lower error.\n\n" + md_table(pd.DataFrame(wins).set_index("Model")))

    ci = []
    for p in prophets:
        for base in (SNAIVE, AVG4, TRAIL7):
            point, lo, hi = bootstrap_diff(df, p, base)
            ci.append({"Comparison": f"{p} minus {base}", "WAPE difference (points)": point, "95% low": lo, "95% high": hi})
    out.append(
        "### How sure is the difference?\n\nWAPE of the Prophet variant minus WAPE of the baseline, in percentage points "
        "(negative means Prophet is better). The interval resamples whole series with replacement.\n\n"
        + md_table(pd.DataFrame(ci).set_index("Comparison"), 2)
    )
    return "\n\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--initial-days", type=int, default=28)
    ap.add_argument("--horizon", type=int, default=7)
    ap.add_argument("--step", type=int, default=7)
    ap.add_argument("--orders-csv", help="read orders from this snapshot instead of the database")
    ap.add_argument("--save-snapshot", help="write the orders used to this CSV (database mode)")
    ap.add_argument("--out-dir", default="../evaluation")
    ap.add_argument("--oracle", action="store_true", help="add the seed generator's true mean as a noise floor")
    args = ap.parse_args()

    logging.getLogger("cmdstanpy").setLevel(logging.ERROR)
    logging.getLogger("prophet").setLevel(logging.ERROR)

    from app.core.windows_toolchain import ensure_windows_cmdstan_toolchain

    ensure_windows_cmdstan_toolchain()

    frame, names = load_orders(args)
    print(f"loaded {len(frame)} daily rows, {frame.groupby(['menu_item_id', 'meal_period']).ngroups} series")
    df = run_backtest(frame, names, args)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "backtest_predictions.csv", index=False)
    report = build_report(df, args)
    (out_dir / "backtest_results.md").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"wrote {out_dir / 'backtest_predictions.csv'} and {out_dir / 'backtest_results.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
