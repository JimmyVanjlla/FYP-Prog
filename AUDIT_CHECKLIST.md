# Build-vs-Documentation Checklist

Tracks every gap found auditing the built system against the FYP report
(Chapters 1-4) and, specifically for this pass, the 11 full use-case
description tables in Chapter 3 §3.4.1. Checked off as fixed and verified
(tests passing), not just attempted. Update this file in the same commit
as each fix.

Legend: `[ ]` open · `[x]` fixed & tested · `[-]` deliberately not fixing (reason noted)

## A. Structural (large — touches multiple use cases/modules)

- [ ] **A1. Purchase Order / Delivery status lifecycle doesn't match the report.**
  Ch3 (UC-PS-05, UC-DM-04) specifies an 8-state lifecycle: `Pending
  Approval → Approved → Awaiting Delivery → In Transit → Delivered →
  Discrepancy Flagged / Return Pending → Return Resolved`. Built system has
  `PurchaseOrder.status` (pending_approval/approved/rejected) and
  `Delivery.status` (scheduled/received) — a flattened 2-3 state model with
  no `Delivery`-side discrepancy/return states at all.
- [ ] **A2. Delivery confirmation skips the Inventory Staff verification gate.**
  UC-IM-01 describes a *two-step* process: Delivery/Logistics Staff confirms
  physical receipt (UC-DM-02) *without* touching stock, then Inventory Staff
  separately verifies the recorded delivery against stock records before
  `Ingredient.current_stock` is actually updated (with a gate: if the PO is
  "Discrepancy Flagged" instead of "Delivered," route to discrepancy review
  first). Built system's `confirm_receipt` updates stock immediately,
  in one step, with no Inventory Staff gate at all.
- [ ] **A3. UC-DM-04 "Update Delivery Status" has no endpoint.** No way to
  manually progress a delivery through its lifecycle, and no guard
  preventing "Return Resolved" while a discrepancy is still open
  (Alt Flow 2a).

## B. Missing use cases / features (medium)

- [ ] **B1. UC-SS-05 "View My Shift Schedule" — entire use case missing.**
  No endpoint for a staff member to see their own shift assignments across
  schedules; only per-schedule listing exists (`GET
  /staffing/schedules/{id}/assignments`), which requires already knowing
  the schedule_id.
- [ ] **B2. UC-KO-01 Alt Flow 3a — no manual prep entry fallback.** When no
  forecast exists yet, `generate_prep_recommendation` just 404s.
  Documented behavior: fall through to manual prep quantity entry instead
  of a dead end.
- [ ] **B3. FR5.4 only half-built.** Only "prep deviation" notifications
  exist. Missing: notify Kitchen Staff when a *new forecast cycle updates*
  a prep recommendation (UC-KO-04 main flow step 1), and "high-demand
  alert" notifications for a forecasted demand spike (also named in FR5.4
  and UC-KO-04) were never built at all.
- [ ] **B4. UC-MR-02 Alt Flow 2a — no way to remove a recipe-ingredient
  link.** Only `POST` (add) exists; no `DELETE`.
- [ ] **B5. Deactivating a menu item doesn't hide it anywhere.** UC-MR-01
  Alt Flow 3a: deactivation should remove the item from active listings and
  prep recommendations. `GET /menu-items` returns all items regardless of
  `is_active`, and `generate_prep_recommendation` doesn't check it either.
- [ ] **B6. UC-PS-04 Alt Flow 3a — no way to deactivate a supplier.**
  `Supplier.is_active` exists; nothing ever sets it to `False`.
- [ ] **B7. UC-PS-07 Alt Flow 3a — `SupplierDiscrepancy` has no resolve
  endpoint.** `DeliveryDiscrepancy` has one; this is the inconsistent twin.
- [ ] **B8. UC-PS-06 "View Monthly Budget Utilisation" has no dedicated
  view.** Only the raw `Budget` list (from the earlier audit pass) and a
  boolean `exceeds_budget` flag on PO creation exist — no endpoint showing
  remaining budget / % utilised / breakdown by supplier or ingredient.

## C. Moderate (notifications / logging gaps on existing flows)

- [ ] **C1. PO approve/reject doesn't notify the Procurement Officer**
  (UC-PS-01 main flow step 5 / Alt Flow 4a).
- [ ] **C2. Publishing a schedule / assigning staff doesn't notify anyone**
  (UC-SS-02 main flow step 5).
- [ ] **C3. UC-SS-02 Alt Flow 3a — assigning fewer/more staff than the AI
  recommendation isn't logged** for later comparison against actual shift
  performance.

## D. Minor / cosmetic (already known from earlier audit passes)

- [ ] **D1.** Android `minSdkVersion` not pinned to 26 (report says
  "Android 8.0 and above"; current default of 24 is broader, not actually
  incompatible).
- [ ] **D2.** NFR-Performance targets (API <2s, Prophet <60s/100 items, PDF
  <30s) asserted, never load-tested.
- [ ] **D3.** FCM not wired to real credentials — notifications are
  honestly `queued_for_retry`, never actually delivered.
- [ ] **D4.** Flutter screens for Staff Scheduling, full Procurement
  (beyond the Manager's approval queue), and Delivery are not built —
  those modules are API-only via `/docs`.
- [ ] **D5.** No CI pipeline.
- [ ] **D6.** Not deployed to Railway/Render — runs locally against real
  Supabase/Redis Cloud.

## E. Documented, accepted deviations (not bugs — listed for completeness)

- [-] **E1.** `AuditLog` table added beyond Ch4's 33-entity dictionary, to
  actually satisfy FR1.5. Flagged to the user at the time; not objected to.
- [-] **E2.** `StaffingRecommendation.forecast_id` and
  `ProcurementRecommendation.forecast_id` are nullable, diverging from
  Ch4's dictionary (which shows both required) — both algorithms aggregate
  across *many* forecasts, not one, so a single required FK would misrepresent
  the relationship. See each model's docstring.
- [-] **E3.** No `"portion_adjusted"` tag column on `Order` (Ch4's
  pseudocode references one; the 33-entity dictionary has no such column).
  Superseded by the real FR4.5 fix (`_leftover_adjustment_factor`), which
  achieves the intended effect without a tag column.
- [-] **E4.** FR9.2's purchase-order-recommendation algorithm is this
  project's own heuristic — Ch4 §4.8 has no pseudocode for it (only 4
  algorithms are specified there).
- [-] **E5.** FR6.5's validation is indirect, via upstream `LeftoverLog`/
  `StockBatch` checks, since `WasteLog` itself has no direct user-facing
  create endpoint (it's always system-derived).

---
**Progress**: 0/21 actionable items fixed (A-C), 6 noted-not-fixed (D), 5
accepted-as-is (E).
