# Forecast accuracy evaluation

Chapter 1 says forecast accuracy "can be measured against the manual baseline
once the system is built". This is that measurement: a rolling-origin backtest
of the forecasting model against simple methods a manager could run by hand.

Run on 31 Oct 2026 with `backend/scripts/backtest_forecasts.py`. Every number
below is reproducible from `evaluation/orders_snapshot.csv` (see section 7).

## 1. Summary

1. **The model as first built, and as specified in Chapter 4 (Algorithm 1,
   line 8, `yearly_seasonality = TRUE`), performed badly on a restaurant with
   weeks of history:** 58.8% weighted error, against 14.3% for a plain
   four-week same-weekday average. It was worse than every simple method on
   all 24 series, and its error grew with the forecast horizon (21% one day
   ahead, 115% seven days ahead).
2. **The cause was the yearly seasonality setting.** It asks Prophet to learn a
   yearly cycle from 4 to 7 weeks of data. With it switched off, Prophet's
   error falls to **14.0%**, within 1.5 points of the best any method could
   achieve on this data (12.5%). **The app now uses Prophet's `auto` setting,
   which does exactly that at this history length (section 6).**
3. **With that fixed, Prophet is better than "same as last week" by 3.2
   points** (95% interval 2.3 to 4.0, so not chance) and better than a flat
   7-day average by 2.3 points, but **not distinguishable from the 4-week
   same-weekday average** (difference 0.3 points, interval -0.8 to +0.1).
4. **The data is simulated**, so this shows the method works, not how much
   money it saves a real restaurant (section 5).

## 2. Data and its limits

The only order history available is the seeded development data from
`scripts/seed_dev_data.py`: 24 series (12 menu items, Lunch and Dinner), 56
complete days each, 1,344 daily rows.

The generator is, for each day:

    mean = base demand x meal-period share x (1.3 on Sat/Sun) x (1 + 0.15 x day/56)
    quantity = round(Normal(mean, 0.15 x mean))

So the data has a weekend uplift, a gentle upward trend and random noise, and
nothing else: no holidays, promotions, weather, stock-outs or special events.
Because the true mean is known, the **noise floor** can be computed: even a
method that knew the true mean would be wrong by about 12.5% (WAPE), purely
from the random noise. That is the best score possible on this data and the
reference for everything below.

## 3. Method

- **Rolling origin.** For each series, train on the first 28 days, forecast the
  next 7, score against what happened, extend the training window by 7 days and
  repeat. That gives 4 folds per series and 672 scored predictions per method.
  This matches production: a daily run trains on history and forecasts 7 days.
  The model never sees the days it is scored on.
- **Prophet** is run in four configurations. The first is how
  `app/services/forecasting.py` was originally configured and how Chapter 4
  writes it (weekly and yearly seasonality forced on, point forecast only).
  The second turns the yearly term off. The other two are sensitivity checks.
  The FR4.5 leftover adjustment is not applied; it needs leftover logs and is
  a separate mechanism.
- **Manual-baseline stand-ins** (nothing is fitted):
  1. same weekday last week ("same as last week");
  2. average of the same weekday over the last 4 weeks;
  3. average of the last 7 days (a flat "recent average").
- **Metrics.**
  - WAPE: total absolute error divided by total actual demand. The headline
    figure, because it is not distorted by small days.
  - MAE: average error in portions.
  - MAPE: the average of |error| / actual, the same quantity the app stores
    per forecast as `accuracy_error`.
  - Bias: total (forecast - actual) divided by total actual; positive means
    over-forecasting, which is what produces leftovers.
  - Within 20%: share of days forecast to within 20% of actual.
- **Uncertainty.** Differences between methods are given with a 95% interval
  from resampling whole series with replacement (4,000 draws), because days
  within a series are not independent.

## 4. Results

### Overall

| Model | WAPE % | MAE | MAPE % | Bias % | Within 20% |
|---|---|---|---|---|---|
| Prophet, yearly forced on (as first built) | 58.8 | 10.6 | 61.0 | +16.2 | 28.9 |
| Prophet, weekly only (what `auto` gives; now deployed) | 14.0 | 2.5 | 14.5 | +0.2 | 74.7 |
| Same weekday last week | 17.2 | 3.1 | 17.4 | -1.7 | 67.6 |
| Same weekday, 4-week average | 14.3 | 2.6 | 14.3 | -4.5 | 76.0 |
| Trailing 7-day average | 16.3 | 2.9 | 16.6 | -1.7 | 68.8 |
| Noise floor (true mean) | 12.5 | 2.3 | 12.9 | 0.0 | 82.0 |

### Error by days ahead (WAPE %)

| Days ahead | Prophet yearly-on | Prophet weekly-only | Last week | 4-week avg | 7-day avg | Noise floor |
|---|---|---|---|---|---|---|
| 1 | 21.0 | 14.2 | 17.8 | 14.5 | 14.4 | 13.0 |
| 2 | 33.5 | 14.4 | 18.1 | 14.6 | 15.9 | 12.7 |
| 3 | 40.2 | 13.0 | 16.2 | 13.4 | 14.7 | 11.5 |
| 4 | 42.9 | 13.9 | 18.5 | 14.4 | 20.5 | 12.6 |
| 5 | 62.1 | 15.0 | 17.8 | 15.0 | 19.3 | 13.2 |
| 6 | 97.9 | 13.3 | 14.5 | 14.4 | 12.5 | 11.5 |
| 7 | 114.9 | 13.8 | 16.6 | 13.7 | 14.3 | 12.6 |

The yearly-on configuration gets steadily worse the further ahead it forecasts.
That pattern is the signature of a model extrapolating something it learned
from too little data. The weekly-only model is flat across the week.

### Is the difference real? (WAPE of Prophet minus WAPE of the baseline, points)

| Comparison | Difference | 95% interval |
|---|---|---|
| Yearly-on Prophet minus 4-week average | +44.5 | +37.8 to +50.7 |
| Weekly-only Prophet minus same weekday last week | -3.2 | -4.0 to -2.3 |
| Weekly-only Prophet minus trailing 7-day average | -2.3 | -3.0 to -1.6 |
| Weekly-only Prophet minus 4-week average | -0.3 | -0.8 to +0.1 |

Series by series, weekly-only Prophet beats last-week in 23 of 24 series, the
7-day average in 23 of 24, and the 4-week average in 16 of 24. The yearly-on
configuration beats none of them in any series.

### Stable across folds

Weekly-only Prophet scored 14.4, 13.2, 14.5 and 13.8% in the four folds, so
the result does not come from one lucky window.

### Sensitivity (not adopted)

Two further variants, a multiplicative weekend effect and a stiffer trend, both
scored 14.0 to 14.2%, no better than the plain weekly-only model. They are
reported only to show the conclusion does not depend on those choices. They
were not tuned and are not recommended, since tuning on simulated data would
only fit the simulator.

Full tables, including by menu item and weekday versus weekend:
`evaluation/backtest_results.md`.

## 5. What this does and does not show

**It shows:**
- The forecasting pipeline works end to end, and a weekly-seasonal Prophet
  model reaches close to the best achievable accuracy on this data.
- The yearly-seasonality setting in Chapter 4's Algorithm 1 is unsuitable for a
  restaurant with less than a year or two of history, and is badly so with weeks.
- On this data, a model that learns the weekly pattern beats "same as last week".

**It does not show:**
- **Real-world accuracy.** The data was generated by a simple rule that favours
  seasonal-average methods. Real demand has holidays, promotions, weather and
  outages, which is where a model like Prophet is expected to pull ahead of a
  plain average. This evaluation cannot show that; real order history could.
- **Waste reduction against a manual baseline.** Chapter 1 also promises that
  waste cost reduction can be measured. That needs a restaurant using the
  system for weeks and a record of waste before it. It cannot be measured from
  simulated data and should be stated as a limitation and future work.
- **That Prophet is the best possible model.** On this data a 4-week
  same-weekday average is statistically as good. The case for Prophet rests on
  real data and on the other things it offers (trend changes, holidays,
  missing days), not on this result.

**Suggested wording for the report:** "On simulated order data with a weekly
pattern, trend and 15% random noise, a rolling-origin backtest (28-day initial
window, 7-day horizon, 4 folds, 24 series) found Prophet's weighted absolute
percentage error to be 14.0%, against a noise floor of 12.5%, and better than a
same-day-last-week forecast (17.2%) with a 95% interval for the difference of
2.3 to 4.0 points. It could not be distinguished from a 4-week same-weekday
average (14.3%). Evaluation against real restaurant data is future work."

## 6. The change made

Chapter 4 Algorithm 1 and the first implementation both set
`yearly_seasonality = TRUE`. The measured effect was a model four times less
accurate than a naive average. `app/services/forecasting.py` now sets
`yearly_seasonality="auto"`, Prophet's own rule: the yearly term is switched on
only once there are two years of history (verified: weekly only at 56 and 400
days, weekly plus yearly at 800 days). That keeps the algorithm's intent,
capturing yearly patterns when the data can support them, without the failure.
At the history lengths in this evaluation it behaves exactly like weekly-only.

Two regression tests guard it (`tests/test_forecast_accuracy_regression.py`):
one trains on 35 noisy days with a known weekly pattern and requires the next
six days to be within 25% on average and 50% on the worst day (the old setting
gave 66% and 162%), and one checks the setting itself.

**The implementation now differs from the printed pseudocode, so Algorithm 1 in
the report should be updated to match**, line 8 reading
`Prophet( weekly_seasonality = TRUE, yearly_seasonality = AUTO, ... )` with a
note that AUTO enables it from two years of data, citing this evaluation. The
forecasts already stored were produced with the old setting; they are replaced
the next time training runs.

## 7. Reproducing this

From `backend/`, with the virtual environment active:

```bash
python scripts/backtest_forecasts.py --orders-csv ../evaluation/orders_snapshot.csv --out-dir ../evaluation --oracle
```

This needs no database. It takes a few minutes (96 model fits per Prophet
variant) and rewrites `evaluation/backtest_results.md` and
`evaluation/backtest_predictions.csv` (every individual prediction, for
checking any figure above). Drop `--orders-csv` to read the live database
instead, and add `--save-snapshot <path>` to keep the orders used.
