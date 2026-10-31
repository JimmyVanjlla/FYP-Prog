# Multi-restaurant readiness: audit and migration plan

**Verdict: the report's claim holds.** Chapter 3 (Scalability) promises a schema
"designed to accommodate multi-restaurant deployments in future iterations
without requiring schema redesign". The schema was audited table by table on
31 Oct 2026. Nothing has to be redesigned: a second restaurant needs one new
table, a `restaurant_id` column on 9 of the 35 tables, and query scoping in the
service layer. The system is **not** multi-restaurant today, which is also what
the report scopes it to (Chapter 3: "initial single-restaurant context";
Chapter 4: "an individually developed Final Year Project rather than a
production-scale multi-tenant deployment").

## 1. What the audit looked at

All 35 tables in `Base.metadata` (the report's 33 entities plus `audit_logs` and
`device_tokens`), their foreign keys and unique constraints, then the code that
reads them (94 `select()` calls and 29 `db.get()` calls across services, routers
and tasks).

## 2. Which tables need a `restaurant_id`

A table only needs its own column if it cannot reach a restaurant through a
foreign-key chain.

**Seven root tables (no foreign keys at all):**
`users`, `menu_items`, `ingredients`, `suppliers`, `system_config`, `reports`,
`waste_reduction_trends`.

**Two more that look like children but are keyed by date, not by a parent:**
`budgets` (one budget per month) and `shift_schedules` (one schedule per date).
Both only point at a user, which would be a fragile way to find the restaurant,
so they get their own column.

**The other 26 inherit it** through the chain, with no change:

| Reaches a restaurant through | Tables |
|---|---|
| `menu_items` | `forecasts`, `orders`, `leftover_logs`, `portion_recommendations`, `prep_recommendations`, `recipe_ingredient_links`, and via `forecasts`: `forecast_accuracies`, `procurement_recommendations`, `staffing_recommendations`; via `prep_recommendations`: `prep_confirmations` |
| `ingredients` | `stock_batches`, `stock_adjustments`, `restocking_requests`, `waste_logs`, `supplier_pricing`, `purchase_order_items`, `delivery_items`, `delivery_discrepancies` |
| `suppliers` | `purchase_orders`, `supplier_discrepancies`, via `purchase_orders`: `deliveries` |
| `users` | `audit_logs`, `notifications`, `device_tokens` |
| `shift_schedules` | `shift_assignments`, `shift_closing_reports` |

## 3. Constraints that would have blocked it: none

| Constraint | Effect with two restaurants |
|---|---|
| `forecasts` unique on (menu_item_id, meal_period, forecast_date) | Fine: menu items already belong to one restaurant. |
| `deliveries.po_id`, `forecast_accuracies.forecast_id`, `shift_closing_reports.schedule_id`, `prep_confirmations.recommendation_id` unique | Fine: one-to-one with a parent that is already scoped. |
| `device_tokens.token` unique | Fine: a phone belongs to one user (re-registering moves it). |
| `users.email` unique | Keeps working (login is by email). It means one account belongs to one restaurant; staff who work at two would need two accounts, or a `user_restaurants` join table. A product decision, not a schema blocker. |
| No unique constraint on ingredient or menu-item names | Two restaurants can both have "Nasi Lemak". |

## 4. What is not a schema change but must change (the real work)

These are code assumptions of a single restaurant. Each is additive, but they
are most of the effort:

1. **Query scoping.** Every list and aggregate query (94 `select()` calls) must
   filter by the caller's restaurant.
2. **Lookups by id (29 `db.get()` calls).** `GET /purchase-orders/7` today
   returns PO 7 to any authorised user. With two restaurants it must also check
   PO 7 belongs to the caller's restaurant, or one restaurant could read
   another's data. This is the security-critical part.
3. **Singletons.** `system_config` is one row read by `get_or_create_config`
   (28 references); it becomes one row per restaurant. `Budget` lookups by month
   (4 sites) need the restaurant too.
4. **Role fan-out.** `notify(recipient_role=...)` messages every active user
   with a role (for example all Kitchen Staff). It must be limited to the
   restaurant the event happened in.
5. **Background jobs.** Training, consumption, expiry scans, waste rollups and
   the weekly report loop over everything today; each loops per restaurant.
6. **Report files.** `generated_reports/{period_end}_weekly_summary.pdf` is
   named by date only, so two restaurants' reports would overwrite each other;
   the name needs the restaurant id.
7. **Authentication.** The JWT carries a role; it would also carry the
   restaurant id, and the `get_current_user` dependency would expose it.

## 5. Migration plan (each step is shippable on its own)

1. Alembic migration: create `restaurants`; insert one row, "Default
   restaurant".
2. Add nullable `restaurant_id` to the 9 tables above; backfill every existing
   row with the default restaurant; then set it NOT NULL with a foreign key and
   an index. Existing data and behaviour are unchanged.
3. Put the restaurant id in the JWT and on the current-user dependency; add a
   small helper for "the caller's restaurant".
4. Scope the queries and `db.get()` lookups module by module, adding one
   cross-restaurant test per module ("restaurant B cannot read or change
   restaurant A's record").
5. Make `system_config`, budgets, background jobs, notifications and report
   file names per restaurant.
6. Add `POST /restaurants` and a way to provision the first Manager of a new
   restaurant (today the first-ever registration is the bootstrap).

## 6. Estimate and recommendation

About 9 columns, one migration, and roughly 120 query and lookup sites across
all 11 modules, plus a cross-restaurant test for each. That is several days of
work with real regression risk, and nothing in Chapters 1-4 requires it to be
demonstrated, so it is **deliberately left unbuilt**. Nothing built so far makes
it harder: the data model is already normalised around `menu_items`,
`ingredients`, `suppliers` and `users`, which is why so few tables need the
column.

For the report, this document is the evidence for the scalability claim; cite
sections 2 and 3.
