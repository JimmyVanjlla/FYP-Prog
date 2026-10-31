// Small helpers for the loosely-typed JSON the feature screens work with.

typedef Json = Map<String, dynamic>;

List<Json> asJsonList(dynamic value) =>
    (value as List<dynamic>).map((e) => e as Json).toList();

Json asJson(dynamic value) => value as Json;

/// Numbers arrive from the API as strings (Decimal) or ints; screens only
/// ever need them as doubles for display and light arithmetic.
double asDouble(dynamic value, [double fallback = 0]) {
  if (value == null) return fallback;
  if (value is num) return value.toDouble();
  return double.tryParse(value.toString()) ?? fallback;
}

/// "12.500" -> "12.5", "6.50" -> "6.5", "3" -> "3" — trims the padding
/// Decimal columns carry.
String trimNum(dynamic value) {
  final d = asDouble(value);
  if (d == d.roundToDouble()) return d.toStringAsFixed(0);
  var s = d.toStringAsFixed(3);
  s = s.replaceFirst(RegExp(r'0+$'), '');
  return s.endsWith('.') ? s.substring(0, s.length - 1) : s;
}

String money(dynamic value) => 'RM ${asDouble(value).toStringAsFixed(2)}';
