/// Mirrors the backend's MenuItemOut schema (app/schemas/menu.py).
class MenuItem {
  final int menuItemId;
  final String name;
  final String? description;
  final String price;
  final String category;
  final bool isActive;
  final double?
  profitMargin; // null until Sprint 2 wires real ingredient costing
  final bool isAvailable; // stubbed true until Sprint 2's stock check exists

  MenuItem({
    required this.menuItemId,
    required this.name,
    this.description,
    required this.price,
    required this.category,
    required this.isActive,
    this.profitMargin,
    required this.isAvailable,
  });

  factory MenuItem.fromJson(Map<String, dynamic> json) {
    return MenuItem(
      menuItemId: json['menu_item_id'] as int,
      name: json['name'] as String,
      description: json['description'] as String?,
      price: json['price'] as String,
      category: json['category'] as String,
      isActive: json['is_active'] as bool,
      profitMargin: json['profit_margin'] == null
          ? null
          : double.tryParse(json['profit_margin'].toString()),
      isAvailable: json['is_available'] as bool? ?? true,
    );
  }
}
