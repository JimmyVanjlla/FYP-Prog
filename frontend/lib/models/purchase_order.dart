/// Mirrors the backend's PurchaseOrderOut schema
/// (app/schemas/procurement.py).
class PurchaseOrder {
  final int poId;
  final int supplierId;
  final String status;
  final String totalCost;
  final bool exceedsBudget;

  PurchaseOrder({
    required this.poId,
    required this.supplierId,
    required this.status,
    required this.totalCost,
    required this.exceedsBudget,
  });

  factory PurchaseOrder.fromJson(Map<String, dynamic> json) {
    return PurchaseOrder(
      poId: json['po_id'] as int,
      supplierId: json['supplier_id'] as int,
      status: json['status'] as String,
      totalCost: json['total_cost'].toString(),
      exceedsBudget: json['exceeds_budget'] as bool? ?? false,
    );
  }
}
