/// Mirrors the backend's IngredientOut schema (app/schemas/inventory.py).
class Ingredient {
  final int ingredientId;
  final String name;
  final String unit;
  final String currentStock;
  final String? lowStockThreshold;
  final bool isLowStock;

  Ingredient({
    required this.ingredientId,
    required this.name,
    required this.unit,
    required this.currentStock,
    this.lowStockThreshold,
    required this.isLowStock,
  });

  factory Ingredient.fromJson(Map<String, dynamic> json) {
    return Ingredient(
      ingredientId: json['ingredient_id'] as int,
      name: json['name'] as String,
      unit: json['unit'] as String,
      currentStock: json['current_stock'] as String,
      lowStockThreshold: json['low_stock_threshold'] as String?,
      isLowStock: json['is_low_stock'] as bool? ?? false,
    );
  }
}
