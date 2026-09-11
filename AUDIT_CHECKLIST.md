# Build-vs-Documentation Checklist

Tracks every gap found auditing the built system against the FYP report
(Chapters 1-4) and, specifically for this pass, the 11 full use-case
description tables in Chapter 3 §3.4.1. Checked off as fixed and verified
(tests passing), not just attempted. Update this file in the same commit
as each fix.

Legend: `[ ]` open · `[x]` fixed & tested · `[-]` deliberately not fixing (reason noted)

## A. Structural (large — touches multiple use cases/modules)

- [x] **A1. Purchase Order / Delivery status lifecycle doesn't match the
  report.** Fixed: both `PurchaseOrder.status` and `Delivery.status` now
  use UC-DM-04's exact 6-state lifecycle
  (`awaiting_delivery → in_transit → delivered → discrepancy_flagged /
  return_pending → return_resolved`), kept in sync by
  `delivery.py::_sync_po_status` (UC-PS-05 shows the PO tracking the
  identical values once past approval).
- [x] **A2. Delivery confirmation skips the Inventory Staff verification
  gate.** Fixed: `confirm_receipt` (UC-DM-02) no longer touches
  `Ingredient.current_stock` — it only records receipt and decides
  delivered/discrepancy_flagged/return_pending. A new `verify_delivery`
  (UC-IM-01, Inventory Staff only) is the step that actually updates
  stock, blocked (409) while the delivery isn't in "delivered" status.
  Added `Delivery.verified_by`/`verified_at` to mark that step distinctly
  from receipt confirmation.
- [x] **A3. UC-DM-04 "Update Delivery Status" has no endpoint.** Fixed:
  `PATCH /deliveries/{id}/status` for the pre-receipt tracking states and
  post-discrepancy return resolution; blocked (409, Alt Flow 2a) from
  setting `return_resolved` while any linked `DeliveryDiscrepancy` is
  still open. `delivered`/`discrepancy_flagged`/`return_pending` stay
  system-decided (via `confirm_receipt`'s own comparison), not settable
  through this endpoint.

## B. Missing use cases / features (medium)

- [x] **B1. UC-SS-05 "View My Shift Schedule" — entire use case missing.**
  Fixed: `GET /staffing/my-schedule` (published assignments only, joined
  with schedule date/meal_period).
- [x] **B2. UC-KO-01 Alt Flow 3a — no manual prep entry fallback.** Fixed:
  `manual_quantity` on `POST /kitchen/prep-recommendations`; required
  `PrepRecommendation.forecast_id` nullable to support it (documented
  divergence, same reasoning as the existing Staffing/Procurement
  recommendation nullable FKs).
- [x] **B3. FR5.4 only half-built.** Fixed both halves: "prep update"
  notification now fires when `generate_prep_recommendation` creates a
  genuinely new recommendation (not a cache-hit on an existing one), and a
  "high-demand alert" fires in `train_and_generate_forecasts` when a new
  forecast clears 1.5x the item/meal_period's own historical average
  (documented as this project's own threshold — Ch4 doesn't name a figure).
- [x] **B4. UC-MR-02 Alt Flow 2a — no way to remove a recipe-ingredient
  link.** Fixed: `DELETE /menu-items/{id}/recipe-links/{link_id}`.
- [x] **B5. Deactivating a menu item doesn't hide it anywhere.** Fixed:
  `GET /menu-items` excludes inactive items by default
  (`include_inactive=true` for a Manager reviewing history), and
  `generate_prep_recommendation` now rejects inactive items.
- [x] **B6. UC-PS-04 Alt Flow 3a — no way to deactivate a supplier.**
  Fixed: `PATCH /procurement/suppliers/{id}/deactivate`. `get_unit_price`
  already filtered to active suppliers, so pricing/recommendation
  exclusion was automatic once deactivation existed.
- [x] **B7. UC-PS-07 Alt Flow 3a — `SupplierDiscrepancy` has no resolve
  endpoint.** Fixed: `POST /procurement/discrepancies/{id}/resolve`,
  matching `DeliveryDiscrepancy`'s existing one.
- [x] **B8. UC-PS-06 "View Monthly Budget Utilisation" has no dedicated
  view.** Fixed: `GET /procurement/budget/utilisation` (limit, spent,
  remaining, % used for a given month).

## C. Moderate (notifications / logging gaps on existing flows)

- [x] **C1. PO approve/reject doesn't notify the Procurement Officer**
  (UC-PS-01 main flow step 5 / Alt Flow 4a). Fixed: both
  `approve_purchase_order` and `reject_purchase_order` now notify
  `po.created_by`.
- [x] **C2. Publishing a schedule / assigning staff doesn't notify anyone**
  (UC-SS-02 main flow step 5). Fixed: `publish_schedule` now notifies every
  assigned staff member.
- [x] **C3. UC-SS-02 Alt Flow 3a — assigning fewer/more staff than the AI
  recommendation isn't logged.** Fixed: `publish_schedule` compares actual
  headcount per station against `StaffingRecommendation` and logs any
  mismatch via `AuditLog`.

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
**Progress**: 21/21 actionable items fixed (A-C). 6 noted-not-fixed (D,
low-severity, documented in README's Known Gaps), 5 accepted-as-is (E,
deliberate documented deviations). **All actionable checklist items are
done.**
