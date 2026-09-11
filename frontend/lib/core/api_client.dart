import 'dart:convert';

import 'package:http/http.dart' as http;

/// Thrown for any non-2xx response; [message] is the backend's `detail`
/// field when present (e.g. FR1.7's generic "Incorrect email or password.",
/// or a 403's "You do not have permission...").
class ApiException implements Exception {
  final int statusCode;
  final String message;

  ApiException(this.statusCode, this.message);

  @override
  String toString() => message;
}

/// Thin wrapper around the FastAPI backend. All data operations go through
/// authenticated REST calls here (Ch4 §4.1 — Flutter talks to the backend
/// over HTTPS, nothing else).
///
/// Base URL defaults to the Android emulator's alias for the host machine's
/// localhost; override via `--dart-define=API_BASE_URL=...` for a real
/// device, iOS simulator, or deployed backend.
class ApiClient {
  final String baseUrl;
  String? _token;

  ApiClient({String? baseUrl})
    : baseUrl =
          baseUrl ??
          const String.fromEnvironment(
            'API_BASE_URL',
            defaultValue: 'http://10.0.2.2:8000',
          );

  void setToken(String? token) => _token = token;

  Map<String, String> get _headers => {
    'Content-Type': 'application/json',
    if (_token != null) 'Authorization': 'Bearer $_token',
  };

  Uri _uri(String path) => Uri.parse('$baseUrl$path');

  dynamic _decode(http.Response resp) {
    if (resp.statusCode >= 200 && resp.statusCode < 300) {
      if (resp.body.isEmpty) return null;
      return jsonDecode(resp.body);
    }
    String message = 'Request failed (${resp.statusCode})';
    try {
      final body = jsonDecode(resp.body);
      if (body is Map && body['detail'] != null) {
        final detail = body['detail'];
        // FastAPI validation errors (422) come back as a list of
        // {loc, msg, type} objects rather than a plain string.
        message = detail is String ? detail : detail.toString();
      }
    } catch (_) {
      // Non-JSON error body — fall back to the generic message above.
    }
    throw ApiException(resp.statusCode, message);
  }

  Future<Map<String, dynamic>> register({
    required String name,
    required String email,
    required String password,
    required String role,
  }) async {
    final resp = await http.post(
      _uri('/auth/register'),
      headers: _headers,
      body: jsonEncode({
        'name': name,
        'email': email,
        'password': password,
        'role': role,
      }),
    );
    return _decode(resp) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> login({
    required String email,
    required String password,
  }) async {
    final resp = await http.post(
      _uri('/auth/login'),
      headers: _headers,
      body: jsonEncode({'email': email, 'password': password}),
    );
    return _decode(resp) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> currentUser() async {
    final resp = await http.get(_uri('/users/me'), headers: _headers);
    return _decode(resp) as Map<String, dynamic>;
  }

  Future<List<dynamic>> listMenuItems() async {
    final resp = await http.get(_uri('/menu-items'), headers: _headers);
    return _decode(resp) as List<dynamic>;
  }

  Future<Map<String, dynamic>> createMenuItem({
    required String name,
    String? description,
    required String price,
    required String category,
  }) async {
    final resp = await http.post(
      _uri('/menu-items'),
      headers: _headers,
      body: jsonEncode({
        'name': name,
        if (description != null && description.isNotEmpty)
          'description': description,
        'price': price,
        'category': category,
      }),
    );
    return _decode(resp) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> deactivateMenuItem(int menuItemId) async {
    final resp = await http.delete(
      _uri('/menu-items/$menuItemId'),
      headers: _headers,
    );
    return _decode(resp) as Map<String, dynamic>;
  }

  // --- Module 3: Inventory Management ---

  Future<List<dynamic>> listIngredients() async {
    final resp = await http.get(
      _uri('/inventory/ingredients'),
      headers: _headers,
    );
    return _decode(resp) as List<dynamic>;
  }

  Future<Map<String, dynamic>> createIngredient({
    required String name,
    required String unit,
    required String currentStock,
  }) async {
    final resp = await http.post(
      _uri('/inventory/ingredients'),
      headers: _headers,
      body: jsonEncode({
        'name': name,
        'unit': unit,
        'current_stock': currentStock,
      }),
    );
    return _decode(resp) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> recordStockAdjustment({
    required int ingredientId,
    required String adjustedQuantity,
    required String reasonCategory,
    String? note,
  }) async {
    final resp = await http.post(
      _uri('/inventory/stock-adjustments'),
      headers: _headers,
      body: jsonEncode({
        'ingredient_id': ingredientId,
        'adjusted_quantity': adjustedQuantity,
        'reason_category': reasonCategory,
        if (note != null && note.isNotEmpty) 'note': note,
      }),
    );
    return _decode(resp) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> createRestockingRequest({
    required int ingredientId,
    required String quantity,
    bool urgency = false,
  }) async {
    final resp = await http.post(
      _uri('/inventory/restocking-requests'),
      headers: _headers,
      body: jsonEncode({
        'ingredient_id': ingredientId,
        'quantity': quantity,
        'urgency': urgency,
      }),
    );
    return _decode(resp) as Map<String, dynamic>;
  }

  // --- Module 5: Kitchen Operations ---

  Future<Map<String, dynamic>> generatePrepRecommendation({
    required int menuItemId,
    required String mealPeriod,
    required String forecastDate,
  }) async {
    final resp = await http.post(
      _uri('/kitchen/prep-recommendations'),
      headers: _headers,
      body: jsonEncode({
        'menu_item_id': menuItemId,
        'meal_period': mealPeriod,
        'forecast_date': forecastDate,
      }),
    );
    return _decode(resp) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> confirmPrep({
    required int recommendationId,
    required String confirmedQuantity,
    String? deviationReason,
  }) async {
    final resp = await http.post(
      _uri('/kitchen/prep-recommendations/$recommendationId/confirm'),
      headers: _headers,
      body: jsonEncode({
        'confirmed_quantity': confirmedQuantity,
        if (deviationReason != null && deviationReason.isNotEmpty)
          'deviation_reason': deviationReason,
      }),
    );
    return _decode(resp) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> logLeftover({
    required int menuItemId,
    required String servicePeriodDate,
    required String preparedQuantity,
    required String leftoverQuantity,
    required String leftoverLevel,
  }) async {
    final resp = await http.post(
      _uri('/kitchen/leftover-logs'),
      headers: _headers,
      body: jsonEncode({
        'menu_item_id': menuItemId,
        'service_period_date': servicePeriodDate,
        'prepared_quantity': preparedQuantity,
        'leftover_quantity': leftoverQuantity,
        'leftover_level': leftoverLevel,
      }),
    );
    return _decode(resp) as Map<String, dynamic>;
  }
}
