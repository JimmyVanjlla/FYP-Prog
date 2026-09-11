/// Mirrors the backend's PortionRecommendationOut schema
/// (app/schemas/feedback.py).
class PortionRecommendation {
  final int recommendationId;
  final int menuItemId;
  final String leftoverRate;
  final String suggestedPortionSize;
  final String status;

  PortionRecommendation({
    required this.recommendationId,
    required this.menuItemId,
    required this.leftoverRate,
    required this.suggestedPortionSize,
    required this.status,
  });

  factory PortionRecommendation.fromJson(Map<String, dynamic> json) {
    return PortionRecommendation(
      recommendationId: json['recommendation_id'] as int,
      menuItemId: json['menu_item_id'] as int,
      leftoverRate: json['leftover_rate'].toString(),
      suggestedPortionSize: json['suggested_portion_size'].toString(),
      status: json['status'] as String,
    );
  }
}
