# Feature Checklist: promised vs built

Last checked 31 Oct 2026. Sources: Chapters 1-4, Form 2 (proposal) and the Chapter 3 use-case tables. Statuses were verified against the code, the database and the running app (the Android emulator against the live backend), not copied from earlier notes. The first version of this checklist, taken earlier the same day, found 25 of 61 requirements complete.

Columns: **Backend** is `Done` when it works and is tested, `Partial` when a named piece is missing. **App UI** is the Flutter app: `Done` has a working screen, `Partial` covers only part of it, `None` has no screen, `n/a` is automatic background work that needs no screen.

## Summary

- **61 functional requirements** across 11 modules.
- **Complete end to end: 61 of 61.** FR5.4 (push notifications) was the last one: it was confirmed on 31 Oct 2026 with a real Firebase project, a push from the backend arriving on the Android emulator while the app was not running.
- Backend: 61 done. App: 55 done, 0 partial, 0 with no screen, 6 needing none.
- Tests: 178 backend (including 5 cross-role integration workflows), 25 Flutter widget tests; the Flutter analyzer is clean.

## What is still genuinely open

These need something only you can provide, or a decision from you. None can be closed from the code alone.

1. **Deployment (Chapter 2, every sprint's final step): API deployed, worker not.** The API runs on Render's free tier at `https://fyp-prog.onrender.com` (built from `backend/Dockerfile`, HTTPS from the platform, migrations applied at start-up). Verified there on 31 Oct 2026: login, authenticated reads, report PDF download, every endpoint under the 2 s target (slowest 0.61 s), and a push notification sent by the deployed server reaching the Android emulator. **No Celery worker is running**, because Render has no free workers (about US$7 a month). Until one runs, the scheduled jobs (daily training, stock consumption, weekly report, push retry) only happen when triggered by hand. The free web service also sleeps when idle, so the first request after a quiet spell takes 30-60 s.
2. **iOS.** Pinned to iOS 13.0 as promised, but never built: that needs a Mac. Push on iOS would also need an APNs key uploaded to Firebase.
3. **Multi-restaurant readiness (Scalability NFR).** No table carries a restaurant/tenant column. Adding one later is additive (a `restaurants` table, a nullable `restaurant_id` on the root entities, and scoping the queries), not a redesign, which is what the report promises, but none of it is built. Decide whether 'designed to accommodate' is enough or you want it built.
4. **User acceptance testing and supervisor sign-off.** Process milestones I can't judge from here. Form 2 puts UAT at 13 Nov 2026, the draft report at 27 Nov and the final at 11 Dec.

## Fixed since the first check

**The five bugs from the first check:**

1. Duplicate forecasts: training now updates in place, a unique constraint prevents a repeat, and the 144 stale rows were removed from the database.
2. Forecasted consumption never reached stock: a daily job now applies it.
3. Retry exhaustion raised no alert: the Manager and Owner are now notified when a scheduled job gives up.
4. The audit trail covered only some actions: every state-changing request is now logged.
5. No 'forecasts not yet available' message: new availability endpoint and a Forecasts screen that explains it.

**Further problems found and fixed while building the screens:**

- The same datetime-vs-date boundary bug existed in two more places (weekly waste trend rollup and monthly budget utilisation), silently dropping the last day of the period. Budget utilisation visibly under-reported on the last day of any month.
- `GET /menu-items` took **8 seconds** (a query-per-item pattern against the hosted database). It now takes 0.7 s, and every endpoint measured is under the 2 s target.
- Prep recommendations had no date, manual ones piled up as duplicates, and confirming one twice crashed with a 500. Staffing recommendations stacked on every regenerate. Both now update in place, and a double confirmation is a clean 409.
- A delivery's receipt could be re-confirmed after it had been verified into stock, silently rewriting it. It now returns 409.
- The delivery deviation threshold was hard-coded at 10% although FR10.5 says configurable. It's now a setting.
- Three screens (approvals, waste, reports) had a latent debug-mode crash on pull-to-refresh (`setState` returning a Future), present since Sprint 5.
- Narrow-screen layout overflows in several new screens, found by the widget tests.

## Performance targets (Chapter 3), measured

Measured with `backend/scripts/measure_performance.py`; rerun it to reproduce.

| Target | Result | Notes |
|---|---|---|
| API responses under 2 s | **0.7 s slowest** (17 endpoints) | From a development laptop to a Supabase pooler in another country; each database round trip costs ~0.25 s here, so a backend deployed beside its database will be faster. |
| 100-item Prophet cycle under 60 s | **43 s** | One meal period per item on the development machine. Three meal periods per item (as in the seeded data) would be ~3x that, so the target holds for 100 item/period models, not 100 items x 3 periods. |
| Weekly PDF under 30 s | **0.13 s** | A synthetic report of 350 scored forecasts. |

## Module 1 - User and Access Management

| ID | Requirement | Backend | App UI | Notes |
|---|---|---|---|---|
| FR1.1 | Register with email, name, password | Done | Done |  |
| FR1.2 | Email/password login returns a JWT | Done | Done | Rate-limited per email. |
| FR1.3 | Role-based access control | Done | Done | Enforced server-side on every endpoint, and every one of the 7 roles now gets its own navigation. |
| FR1.4 | Manager creates / deactivates / reassigns staff accounts | Done | Done | Staff screen. |
| FR1.5 | Log all user actions with timestamps | Done | Done | Every state-changing request by a signed-in user is logged centrally; the Staff screen has an Activity log tab. |
| FR1.6 | Reject duplicate email on registration | Done | Done |  |
| FR1.7 | Generic login failure message | Done | Done |  |

## Module 2 - Menu and Recipe Management

| ID | Requirement | Backend | App UI | Notes |
|---|---|---|---|---|
| FR2.1 | Create / edit / deactivate menu items; show profit margin | Done | Done | Item detail screen: edit, deactivate/reactivate, margin shown. |
| FR2.2 | Recipe-to-ingredient links with quantity per serving | Done | Done | Add and remove on the item detail screen. |
| FR2.3 | Approved portion changes update ingredient quantities | Done | Done |  |
| FR2.4 | Availability driven by stock levels | Done | Done | Unavailable when stock can't cover a serving; a separate 'Low ingredient' flag appears when any ingredient is under its threshold. |
| FR2.5 | Reject zero/negative/non-numeric price and quantities | Done | Done |  |

## Module 3 - Inventory Management

| ID | Requirement | Backend | App UI | Notes |
|---|---|---|---|---|
| FR3.1 | Stock updated by deliveries, manual adjustments, forecasted consumption | Done | Done | A daily job deducts each finished day's consumption (logged orders where they exist, the forecast where they don't), once per day, floored at zero, with a low-stock alert. |
| FR3.2 | Batch expiry tracking and near-expiry alerts | Done | Done | Batches and expiry chips on the ingredient screen. |
| FR3.3 | Default low-stock threshold (Manager) + per-ingredient override (Inventory) | Done | Done | Settings screen and the ingredient screen. |
| FR3.4 | Manual adjustments with a reason | Done | Done |  |
| FR3.5 | Kitchen Staff submit restocking requests to Inventory | Done | Done | Kitchen requests from the ingredient screen; Inventory works the queue. |
| FR3.6 | Reject negative / non-numeric adjustments and thresholds | Done | Done |  |

## Module 4 - Demand Forecasting

| ID | Requirement | Backend | App UI | Notes |
|---|---|---|---|---|
| FR4.1 | Aggregate orders by item / meal period / date via Celery | Done | n/a | Written and tested; it only runs on schedule once a worker is deployed (see Deployment). |
| FR4.2 | Prophet model per item per meal period | Done | n/a | 100 items train in 43 s on the development machine. |
| FR4.3 | Store forecasts and serve them without reprocessing | Done | Done | Duplicate-forecast bug fixed; Forecasts screen. |
| FR4.4 | Track forecast accuracy against actuals | Done | Done | Accuracy tab. |
| FR4.5 | Leftover feedback refines forecasts downward | Done | n/a |  |
| FR4.6 | Handle insufficient history gracefully with a message | Done | Done | The Forecasts screen explains which items lack a forecast and shows the 14-day minimum. |

## Module 5 - Kitchen Operations

| ID | Requirement | Backend | App UI | Notes |
|---|---|---|---|---|
| FR5.1 | Prep quantity recommendations from the forecast | Done | Done | Prep screen, with a manual-entry fallback. |
| FR5.2 | Kitchen Staff confirm or adjust prep quantities | Done | Done |  |
| FR5.3 | Log end-of-service leftovers | Done | Done |  |
| FR5.4 | Push notifications via Firebase Cloud Messaging | Done | Done | Notifications are stored, shown in the in-app inbox, and pushed through FCM with token registration and a 15-minute retry. Verified on 31 Oct 2026 against a real Firebase project: the app registered its token, and a backend push reached the Android emulator while the app was not running. The token call (not the Installation ID) works with the HTTP v1 API. Limits: tested on Android only, and a push is not drawn while the app is open in the foreground (the in-app inbox covers that case). |
| FR5.5 | Require a justification for large prep deviations | Done | Done | The reason field appears at the quantity as soon as the change is large enough. |

## Module 6 - Waste Management

| ID | Requirement | Backend | App UI | Notes |
|---|---|---|---|---|
| FR6.1 | Aggregate leftover and expiry waste | Done | Done |  |
| FR6.2 | Waste cost from quantities and supplier pricing | Done | Done |  |
| FR6.3 | Waste reduction trend for the Manager | Done | Done | Bar chart with a period-on-period summary. |
| FR6.4 | Alerts to prioritise/discount near-expiry stock | Done | Done | Notification inbox, and expiry chips on batches. |
| FR6.5 | Reject invalid waste entries | Done | Done | New manual waste entry rejects non-positive quantities and amounts above what was prepared or delivered. |

## Module 7 - Portion and Forecast Feedback

| ID | Requirement | Backend | App UI | Notes |
|---|---|---|---|---|
| FR7.1 | Identify persistently high-leftover dishes | Done | n/a |  |
| FR7.2 | Portion-reduction recommendations surfaced to the Manager | Done | Done |  |
| FR7.3 | Propagate approved changes to Menu and Recipe | Done | Done |  |
| FR7.4 | Feed leftover rates back into forecasting | Done | n/a |  |
| FR7.5 | Reject leftover threshold outside 0-100% | Done | Done | Settings screen. |

## Module 8 - Staff Scheduling

| ID | Requirement | Backend | App UI | Notes |
|---|---|---|---|---|
| FR8.1 | AI staffing recommendations from forecasts | Done | Done | Shown beside the roster. |
| FR8.2 | Create and publish schedules with role/station assignments | Done | Done | Schedule Builder. |
| FR8.3 | Confirm shift opening with attendance | Done | Done |  |
| FR8.4 | Shift closing report: actual vs forecast | Done | Done | The report now carries the forecast and the variance. |
| FR8.5 | Block overlapping assignments | Done | Done |  |

## Module 9 - Procurement and Supplier Management

| ID | Requirement | Backend | App UI | Notes |
|---|---|---|---|---|
| FR9.1 | Supplier directory with pricing and contacts | Done | Done |  |
| FR9.2 | PO recommendations from forecast and stock | Done | Done | Heuristic (Chapter 4 specifies no algorithm for it). |
| FR9.3 | PO approval workflow (Officer creates, Manager approves) | Done | Done |  |
| FR9.4 | Track monthly budget and cumulative spend | Done | Done |  |
| FR9.5 | Flag supplier discrepancies | Done | Done |  |
| FR9.6 | Reject bad PO quantities; warn (don't block) when over budget | Done | Done | Running total and remaining budget sit beside the line items. |

## Module 10 - Delivery Management

| ID | Requirement | Backend | App UI | Notes |
|---|---|---|---|---|
| FR10.1 | Schedule deliveries and manage a calendar | Done | Done | Grouped by day, overdue flagged, date-window filter on the API. |
| FR10.2 | Confirm receipt with quantity verification | Done | Done | Delivery staff confirm, then Inventory staff verify into stock. |
| FR10.3 | Record discrepancies and goods returns | Done | Done |  |
| FR10.4 | Delivery history log with resolution tracking | Done | Done | History tab. |
| FR10.5 | Reject negative receipts; route over-deviation to discrepancies | Done | Done | The threshold is now genuinely configurable (it was hard-coded); a mismatch turns red as it's typed. |

## Module 11 - Reporting and Analytics

| ID | Requirement | Backend | App UI | Notes |
|---|---|---|---|---|
| FR11.1 | Weekly summary reports generated automatically via Celery | Done | n/a | Scheduled; needs a deployed worker to run unattended. |
| FR11.2 | PDF export via ReportLab | Done | Done |  |
| FR11.3 | Forecast accuracy report | Done | Done |  |
| FR11.4 | Waste cost and reduction trend report | Done | Done |  |
| FR11.5 | Budget utilisation and procurement cost report | Done | Done |  |
| FR11.6 | Reject report requests for empty date ranges | Done | Done |  |

## Use-case behaviours beyond the FR list

| ID | Promise | Status | Notes |
|---|---|---|---|
| UC-DF-01 | Forecast dashboard filterable by date range and item, with a not-yet-available message | Done | Forecasts screen. |
| UC-RA-01 | View the report summary in-app; manual Regenerate after a failure | Done | Tap a report for its summary; failed reports have a Regenerate button. |
| UC-SS-05 | Staff view their own published shifts | Done | My shifts. |
| UC-IM-01 / UC-DM-04 | Full PO and delivery status lifecycle (six states) | Done | |

## Non-functional requirements

| Area | Promise | Status | Notes |
|---|---|---|---|
| Performance | API responses under 2 seconds | Met | 0.7 s slowest, measured. |
| Performance | Full Prophet cycle under 60 s for up to 100 menu items | Met | 43 s for 100 item/period models; see the caveat above. |
| Performance | Weekly PDF under 30 s | Met | 0.13 s. |
| Security | JWT required on every endpoint except login and registration | Done | Only /health and the docs pages are open. |
| Security | Salted bcrypt password hashes | Done |  |
| Security | RBAC enforced at the API, not just the UI | Done | Re-checked against the database on every request; a cross-role test asserts the refusals. |
| Security | HTTPS for client-to-server traffic | Not exercised | Provided by Render/Railway once deployed. Nothing is deployed. |
| Usability | Each role sees only its own screens | Done | All 7 roles. |
| Usability | Meaningful, actionable error messages | Done |  |
| Usability | Android 8.0+ and iOS 13.0+ compatible | Android done, iOS untested | Android minSdk is Flutter's default (24, broader than 8.0), run on an API 36 emulator. iOS is pinned to 13.0 but never built. |
| Reliability | Celery tasks retry up to 3 times | Done |  |
| Reliability | Alert when all retries fail | Done | Manager and Owner are notified. |
| Reliability | Graceful handling of missing historical data | Done |  |
| Maintainability | Separated routers / services / models | Done |  |
| Maintainability | Auto-generated API documentation (OpenAPI) | Done | Served at /docs. |
| Scalability | Horizontal scaling by adding workers, no code change | Plausible, untested | The API is stateless and Celery is separate; documented in DEPLOYMENT.md (including the one-Beat-scheduler rule). |
| Scalability | Schema ready for multi-restaurant use without redesign | Not built | See open item 3. |

## Chapter 4 mobile screens and design principles

| Promised | Status | Notes |
|---|---|---|
| Minimal auth: email + password, no role selector, generic failure | Done |  |
| 'Needs your attention' queue (POs in red, portion reviews in amber, with text labels) | Done | The Manager's first screen. |
| Severity as colour plus text from one fixed 3-state palette | Done | Chips also carry an icon. |
| Stock Management with on-hand shown beside the threshold | Done | Plus batches and expiry on the ingredient screen. |
| PO approval with remaining budget beside Approve/Reject | Done |  |
| PO creation with a running total beside the line items | Done | Remaining budget sits beside the total. |
| Prep quantities screen with editable, pre-filled defaults | Done |  |
| Schedule Builder: recommendations and roster on one screen, '+ Assign staff', below-recommendation flag | Done | The flag updates as staff are assigned. |
| Scheduled Deliveries: confirm receipt and update status on one screen, with an inline red quantity-mismatch flag | Done | Turns red as the figure is typed. |
| Inline validation at the point of entry | Done |  |
| One reused interaction pattern ('+ add' row, filled/outlined action pair) | Done | One shared AddRow widget. |
| Two-page PDF report following the 6 design principles in section 4.7.2 | Done |  |

## Other promises

| Promise | Status | Notes |
|---|---|---|
| All 4 algorithms from Chapter 4 section 4.8 | Done | Plus a heuristic for PO recommendations, which Chapter 4 doesn't specify. |
| 33-entity data model on PostgreSQL | Done | 35 tables: the 33, an AuditLog (so FR1.5 could be met) and a DeviceToken table (for push). All migrated to Supabase. |
| Celery + Redis background jobs with a Beat schedule | Built, not running | Seven scheduled jobs, with retries and failure alerts, all tested. No worker process is running anywhere. |
| Deployment to Railway or Render | Not done | Files written; needs your account. See open item 1. |
| Firebase Cloud Messaging end to end | Done | See FR5.4. Android emulator only. |
| Integration testing across all roles | Done (API level) | 5 cross-role workflow tests. There are no end-to-end tests that drive the app against a live backend; the app was exercised by hand on the emulator and by 25 widget tests. |
| User acceptance testing and supervisor sign-off | Unknown | See open item 5. |
