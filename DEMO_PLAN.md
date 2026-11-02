# System preview: 20-minute plan

Live system: https://fyp-prog.onrender.com (API), shown through the Android app on the emulator.
Every demo account shares the seed password (see `backend/scripts/seed_dev_data.py`); the logins are
`manager@test.com`, `kitchen@test.com`, `inventory@test.com`, `supervisor@test.com`,
`procurement@test.com`, `delivery@test.com`.

## Before you start (the 30 minutes before)

| When | Do this | Why |
|---|---|---|
| 30 min before | Close Firefox/Chrome tabs and other heavy programs. Start the emulator from its saved snapshot (Device Manager, the Pixel 9 Pro XL, normal start, not Cold Boot). | The laptop has about 2.5 GB free; a cold-booted emulator froze once during rehearsal. |
| 20 min before | Open https://fyp-prog.onrender.com/health in a browser. | The free server sleeps after about 15 idle minutes and takes about 50 seconds to wake. |
| 10 min before | Open the app and log in as Manager. Click through a couple of screens. | Any request keeps the server awake and warms each screen. |
| 3 min before | Open `/health` again, then leave the app on the login screen. | The server must not be asleep when you begin. |
| Always | Keep a terminal open in `backend/` with the venv active for the push step. | See beat 7. |

If the app shows a spinner for more than a minute, the server is waking up: wait, then pull down to refresh.

## Run of show

Times are a guide. Beats 1 to 6 are the core; beat 7 is the showpiece; if you run short, cut beat 5.

| # | Min | Role and screen | What to do and say |
|---|---|---|---|
| 1 | 0:00 to 1:30 | (talk) | One sentence on the problem (food waste from over-preparation, Malaysia). One sentence on the answer: Prophet forecasts demand per dish per meal period, and that single forecast drives prep, staffing and purchasing for six roles in one app. Mention it is deployed and live, Android. |
| 2 | 1:30 to 5:00 | **Manager**: Needs attention | Budget bar. Open the pending purchase order: line items, "remaining budget after approval" beside Approve and Reject. Approve it. Then the portion review (Curry Laksa, Roti Telur): leftover rate over threshold, suggested smaller portion. Say: this closes the feedback loop from leftovers back into the recipe. |
| 3 | 3:30 to 5:00 | **Manager**: Forecasts | Start on the forecast list (3 Nov onward), pick a dish, show the weekend uplift. Open the **Accuracy** tab (see "Talking points" below before you do). |
| 4 | 5:00 to 8:00 | **Kitchen**: Prep | Today, Lunch. The recommendation comes from the forecast. Change one quantity a lot: the "reason" box appears. Confirm. Open Leftovers: the end-of-service form. |
| 5 | 8:00 to 10:30 | **Shift Supervisor**: Schedules | New shift schedule for today. The recommended headcount appears per station (about 4 and 4). Assign staff: the "below recommendation" flag clears as you add. Publish. Say: staffing is driven by the same forecast. |
| 6 | 10:30 to 14:00 | **Procurement, then Delivery, then Inventory** | Procurement: the "Recommended to buy" list (18 items, driven by the forecast), then Deliveries: a delivery for purchase order #3 (Coffee Powder, Milo Powder, Tea Leaves, RM 740) is already scheduled for 3 Nov. Log in as **Delivery**, open it, and type a received quantity that does not match: the row turns red and a discrepancy is recorded. Log in as **Inventory**, verify the delivery into stock (the three low-stock items go up). Say: three roles, one chain, each step confirmed by a different person. |
| 7 | 14:00 to 16:30 | **Push notification** | Log in as Kitchen on the emulator, press Home so the app is in the background. In the terminal run the command below. Within seconds the "Prep update" notification appears. Say: sent by the live server through Firebase Cloud Messaging. |
| 8 | 16:30 to 18:00 | **Manager**: Reports | Open the weekly report, show the three sections (forecast accuracy, waste, budget), open the PDF. |
| 9 | 18:00 to 20:00 | (talk) | The evaluation (below). Then questions. |

The push command (beat 7), from `backend/` with the venv active:

```bash
python scripts/demo_push.py --base-url https://fyp-prog.onrender.com
```

It confirms one Lunch recommendation for today as Kitchen at 1.8 times the recommended quantity. If it says there is nothing
unconfirmed, open the Kitchen Prep screen once (it creates the recommendations) and run it again, or add `--period Dinner`.

## Showing notifications (three ways, easiest first)

1. **In-app inbox, no setup (about 1 minute).** Every role has a bell icon at the top right. In beat 2, when the Manager approves
   purchase order #1, the system records "Purchase order #1 was approved" for the Procurement Officer. Later, log in as
   `procurement@test.com` and tap the bell: it is waiting there. This shows notifications are tied to roles and to events.
2. **Prep updates for the kitchen.** Confirming a prep quantity that differs a lot from the recommendation (beat 4) sends a
   "Prep update" to every Kitchen Staff account. Log in as another kitchen account (or the same one) and open the bell.
3. **A real push to the phone (beat 7).** Log in as Kitchen on the emulator, press the Home button so the app is in the
   background, then run the push command from `backend/`. A notification appears in the phone's notification bar within seconds.
   A push is **not** drawn while the app is open on screen, which is why the app must be in the background.

Other things that raise notifications, if asked: a high-demand forecast (Kitchen), low stock and near-expiry stock (Inventory),
a published shift schedule (the staff on it), purchase orders approved or rejected (Procurement), and a scheduled job that
fails after its retries (Manager and Owner).

## If you are asked to create a staff account

Log in as `manager@test.com` (or `owner@test.com`), open the menu at the top left, choose **Staff**, then **Add staff account**.
Only a Manager or Owner can do this. There is no self-registration: the login screen says so, and on the live server the
registration endpoint is closed after the first account. Use a throwaway name, because the account stays in the database.

## The evaluation, in 90 seconds (beat 9)

Say this, in this order:

1. "I measured the forecasting model against simple methods a manager could use without a model: same as last week, and a four-week average."
2. "The first version, using the settings in my Chapter 4 algorithm, was far worse than a plain average: 59% error against 14%."
3. "The cause was forcing yearly seasonality on with only weeks of history. I fixed it; error is now 14%, close to the 12.5% that is the best possible on this data."
4. "Limits: this is simulated order data, so it shows the method works, not what it saves a real restaurant. With real data and a real restaurant over several weeks I could also measure waste reduction, which I cannot claim yet."

Full figures: `FORECAST_EVALUATION.md`.

## How the app is navigated

Every role uses the same menu: the three-line button at the top left opens a drawer listing that role's screens. The bell
(notifications) and the logout icon are at the top right.

## Suppliers: what deactivating does

A deactivated supplier cannot receive new purchase orders, and their prices stop counting towards dish margins and waste costs
(an ingredient only they price then shows as costing 0). **Reactivate** restores all of that. Do not deactivate a supplier during
the demo: Fresh Farm Poultry & Seafood supplies PO #1, and Kedai Runcit Supplies supplies PO #3.

## Talking points for things that may look odd

- **Accuracy tab shows about 28% error.** Those are the forecasts for 29 Oct to 1 Nov, produced by the first version of the model before the fix. Say so. It is the evidence behind the evaluation story, and it improves as new days are scored.
- **Forecasts for 2 Nov show strange numbers** (for example 0 portions for one dish). Same reason; they are the old model's output for a day that was already in the past when the fix went in. Scroll to 3 Nov onward.
- **Android only.** The target is "mobile"; iOS needs a Mac to build and is documented as untested.
- **Scheduled jobs.** Daily training, stock consumption and the weekly report are built and tested but a background worker is not paid for on the free hosting, so they were triggered by hand for this preview.
- **First load is slow.** The free hosting tier sleeps when idle.

## Things not to do during the demo

- Do not press **Retrain forecasts now**. It takes 40 to 50 seconds on the free server and nothing needs it; the forecasts for 3 to 9 Nov are already trained.
- Do not run the push command twice in a row for the same screen without checking; each run uses up a recommendation.
- Do not log out and in repeatedly on the emulator; each login is slow on the free server.

## State the database was left in (2 Nov, night)

- Order history 2 Sep to 2 Nov; forecasts stored for 3 to 9 Nov (trained with the fixed model).
- Purchase order #1 (RM 530) pending approval, for the Manager to approve in beat 2; two portion reviews pending.
- Purchase order #3 (RM 740: Coffee Powder, Milo Powder, Tea Leaves) approved, with its delivery scheduled for 3 Nov and waiting for Delivery staff to confirm receipt (beat 6).
- Weekly report for 27 Oct to 2 Nov generated; one older report.
- Supervisor has one rehearsal schedule (4 Nov, Lunch) and none for 3 Nov.
- Kitchen: one prep recommendation already confirmed for 31 Oct; 2 Nov and 3 Nov recommendations get created when the Prep screen opens.

If you need the data back in this shape: `scripts/extend_demo_orders.py` (history), then Manager, Forecasts, Retrain.
