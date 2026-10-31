Series: 24. Forecast folds per series: 4. Scored predictions: 672 per model. Training starts at 28 days, forecast horizon 7 days, window extended by 7 days per fold.

### Overall

| Model | WAPE % | MAE | MAPE % | Bias % | Within 20 % |
|---|---|---|---|---|---|
| Prophet (deployed) | 58.8 | 10.6 | 61.0 | 16.2 | 28.9 |
| Prophet weekly-only | 14.0 | 2.5 | 14.5 | 0.2 | 74.7 |
| Prophet weekly-only multiplicative | 14.2 | 2.6 | 14.6 | 0.3 | 74.0 |
| Prophet weekly-only stiff trend | 14.0 | 2.5 | 14.5 | 0.2 | 74.7 |
| Same weekday last week | 17.2 | 3.1 | 17.4 | -1.7 | 67.6 |
| Same weekday, 4-week average | 14.3 | 2.6 | 14.3 | -4.5 | 76.0 |
| Trailing 7-day average | 16.3 | 2.9 | 16.6 | -1.7 | 68.8 |
| Noise floor (true mean) | 12.5 | 2.3 | 12.9 | -0.0 | 82.0 |

### Error by how far ahead the forecast is

| Days ahead (WAPE %) | Prophet (deployed) | Prophet weekly-only | Prophet weekly-only multiplicative | Prophet weekly-only stiff trend | Same weekday last week | Same weekday, 4-week average | Trailing 7-day average | Noise floor (true mean) |
|---|---|---|---|---|---|---|---|---|
| 1 | 21.0 | 14.2 | 14.1 | 14.3 | 17.8 | 14.5 | 14.4 | 13.0 |
| 2 | 33.5 | 14.4 | 14.4 | 14.4 | 18.1 | 14.6 | 15.9 | 12.7 |
| 3 | 40.2 | 13.0 | 13.0 | 13.0 | 16.2 | 13.4 | 14.7 | 11.5 |
| 4 | 42.9 | 13.9 | 14.4 | 13.9 | 18.5 | 14.4 | 20.5 | 12.6 |
| 5 | 62.1 | 15.0 | 15.8 | 15.0 | 17.8 | 15.0 | 19.3 | 13.2 |
| 6 | 97.9 | 13.3 | 13.3 | 13.3 | 14.5 | 14.4 | 12.5 | 11.5 |
| 7 | 114.9 | 13.8 | 13.8 | 13.8 | 16.6 | 13.7 | 14.3 | 12.6 |

### Weekdays versus weekends

| Day type (WAPE %) | Prophet (deployed) | Prophet weekly-only | Prophet weekly-only multiplicative | Prophet weekly-only stiff trend | Same weekday last week | Same weekday, 4-week average | Trailing 7-day average | Noise floor (true mean) |
|---|---|---|---|---|---|---|---|---|
| Weekday | 62.1 | 13.7 | 13.7 | 13.8 | 16.6 | 14.1 | 14.4 | 12.3 |
| Weekend | 52.4 | 14.5 | 15.1 | 14.4 | 18.2 | 14.7 | 19.9 | 12.9 |

### Stability across folds (a longer history is available in later folds)

| Fold (WAPE %) | Prophet (deployed) | Prophet weekly-only | Prophet weekly-only multiplicative | Prophet weekly-only stiff trend | Same weekday last week | Same weekday, 4-week average | Trailing 7-day average | Noise floor (true mean) |
|---|---|---|---|---|---|---|---|---|
| 1 | 68.1 | 14.4 | 14.5 | 14.4 | 16.9 | 14.4 | 16.7 | 13.3 |
| 2 | 58.0 | 13.2 | 13.3 | 13.2 | 16.7 | 13.9 | 16.9 | 11.9 |
| 3 | 45.4 | 14.5 | 14.9 | 14.5 | 17.6 | 15.0 | 16.0 | 12.5 |
| 4 | 63.9 | 13.8 | 14.1 | 13.9 | 17.5 | 14.1 | 15.5 | 12.2 |

### By menu item (Lunch and Dinner combined)

| Menu item (WAPE %) | Prophet (deployed) | Prophet weekly-only | Prophet weekly-only multiplicative | Prophet weekly-only stiff trend | Same weekday last week | Same weekday, 4-week average | Trailing 7-day average | Noise floor (true mean) |
|---|---|---|---|---|---|---|---|---|
| Satay Ayam (5 sticks) | 54.3 | 11.3 | 11.2 | 11.4 | 15.2 | 11.7 | 15.9 | 10.6 |
| Mee Goreng Mamak | 67.4 | 11.7 | 11.9 | 11.8 | 13.8 | 11.5 | 13.0 | 10.1 |
| Kopi O | 61.3 | 12.4 | 12.5 | 12.4 | 17.5 | 13.1 | 15.7 | 10.7 |
| Teh Tarik | 51.5 | 12.8 | 13.0 | 12.8 | 17.1 | 13.8 | 16.4 | 12.9 |
| Char Kuey Teow | 53.0 | 13.1 | 13.5 | 13.1 | 16.6 | 12.6 | 17.4 | 11.5 |
| Roti Telur | 62.0 | 13.1 | 13.3 | 13.2 | 17.1 | 12.7 | 16.7 | 12.1 |
| Milo Ais | 34.7 | 13.5 | 13.4 | 13.5 | 18.1 | 13.4 | 15.7 | 12.7 |
| Nasi Lemak | 53.0 | 14.0 | 14.6 | 14.0 | 17.0 | 15.2 | 15.7 | 12.3 |
| Nasi Goreng Kampung | 60.4 | 14.1 | 14.4 | 14.1 | 15.9 | 14.6 | 15.8 | 12.3 |
| Roti Canai | 61.5 | 14.8 | 15.0 | 14.7 | 16.0 | 15.3 | 16.5 | 12.4 |
| Curry Laksa | 68.0 | 16.9 | 16.9 | 16.9 | 19.0 | 17.8 | 17.5 | 14.3 |
| Chicken Rice | 85.3 | 18.8 | 18.8 | 18.8 | 21.4 | 18.3 | 18.3 | 16.0 |

### Head to head, series by series

Number of series where the Prophet variant has lower error.

| Model | Better than 'Same weekday last week' | Better than 'Same weekday, 4-week average' | Better than 'Trailing 7-day average' |
|---|---|---|---|
| Prophet (deployed) | 0 of 24 | 0 of 24 | 0 of 24 |
| Prophet weekly-only | 23 of 24 | 16 of 24 | 23 of 24 |
| Prophet weekly-only multiplicative | 23 of 24 | 12 of 24 | 22 of 24 |
| Prophet weekly-only stiff trend | 23 of 24 | 16 of 24 | 23 of 24 |

### How sure is the difference?

WAPE of the Prophet variant minus WAPE of the baseline, in percentage points (negative means Prophet is better). The interval resamples whole series with replacement.

| Comparison | WAPE difference (points) | 95% low | 95% high |
|---|---|---|---|
| Prophet (deployed) minus Same weekday last week | 41.61 | 34.93 | 47.83 |
| Prophet (deployed) minus Same weekday, 4-week average | 44.45 | 37.77 | 50.69 |
| Prophet (deployed) minus Trailing 7-day average | 42.51 | 35.46 | 49.13 |
| Prophet weekly-only minus Same weekday last week | -3.18 | -3.97 | -2.31 |
| Prophet weekly-only minus Same weekday, 4-week average | -0.34 | -0.77 | 0.13 |
| Prophet weekly-only minus Trailing 7-day average | -2.27 | -3.00 | -1.55 |
| Prophet weekly-only multiplicative minus Same weekday last week | -2.98 | -3.81 | -2.10 |
| Prophet weekly-only multiplicative minus Same weekday, 4-week average | -0.15 | -0.59 | 0.31 |
| Prophet weekly-only multiplicative minus Trailing 7-day average | -2.08 | -2.82 | -1.35 |
| Prophet weekly-only stiff trend minus Same weekday last week | -3.17 | -3.97 | -2.30 |
| Prophet weekly-only stiff trend minus Same weekday, 4-week average | -0.33 | -0.76 | 0.13 |
| Prophet weekly-only stiff trend minus Trailing 7-day average | -2.27 | -2.99 | -1.54 |
