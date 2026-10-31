// Shared test scaffolding: an in-memory secure storage, a fake API that
// answers from a route table (and records what was sent), and a helper that
// pumps a screen logged in as a given role.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage_platform_interface/flutter_secure_storage_platform_interface.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:restaurant_ops/core/api_client.dart';
import 'package:restaurant_ops/core/auth_state.dart';
import 'package:restaurant_ops/core/theme.dart';

class FakeSecureStorage extends FlutterSecureStoragePlatform {
  final _data = <String, String>{};

  @override
  Future<String?> read({required String key, required Map<String, String> options}) async => _data[key];

  @override
  Future<void> write({required String key, required String value, required Map<String, String> options}) async {
    _data[key] = value;
  }

  @override
  Future<bool> containsKey({required String key, required Map<String, String> options}) async =>
      _data.containsKey(key);

  @override
  Future<void> delete({required String key, required Map<String, String> options}) async {
    _data.remove(key);
  }

  @override
  Future<Map<String, String>> readAll({required Map<String, String> options}) async => Map.of(_data);

  @override
  Future<void> deleteAll({required Map<String, String> options}) async {
    _data.clear();
  }
}

/// A JWT whose payload carries [role], enough for AuthState to route by.
String fakeToken(String role) {
  String enc(Object o) => base64Url.encode(utf8.encode(jsonEncode(o))).replaceAll('=', '');
  return '${enc({'alg': 'none'})}.${enc({'role': role, 'sub': '1'})}.sig';
}

class RecordedCall {
  final String method;
  final String path;
  final Object? body;

  RecordedCall(this.method, this.path, this.body);

  @override
  String toString() => '$method $path ${body ?? ''}';
}

typedef Handler = dynamic Function(Object? body, Map<String, dynamic>? query);

/// Answers requests from [routes], keyed "METHOD /path". Anything not
/// routed answers `[]` for a GET (an empty list) so a screen with nothing to
/// show still renders, and `{}` for writes.
class FakeApi extends ApiClient {
  final Map<String, Handler> routes;
  final List<RecordedCall> calls = [];

  /// The role the next login() hands back a token for.
  String loginRole = 'Restaurant Manager';

  FakeApi([Map<String, Handler>? routes]) : routes = routes ?? {}, super(baseUrl: 'http://fake');

  dynamic _answer(String method, String path, Object? body, Map<String, dynamic>? query) {
    calls.add(RecordedCall(method, path, body));
    final handler = routes['$method $path'];
    if (handler != null) return handler(body, query);
    return method == 'GET' ? <dynamic>[] : <String, dynamic>{};
  }

  @override
  Future<dynamic> getJson(String path, {Map<String, dynamic>? query}) async => _answer('GET', path, null, query);

  @override
  Future<dynamic> postJson(String path, [Object? body]) async => _answer('POST', path, body, null);

  @override
  Future<dynamic> patchJson(String path, Object? body) async => _answer('PATCH', path, body, null);

  @override
  Future<dynamic> putJson(String path, Object? body) async => _answer('PUT', path, body, null);

  @override
  Future<dynamic> deleteJson(String path) async => _answer('DELETE', path, null, null);

  // The typed wrappers the older screens still use.
  @override
  Future<List<dynamic>> listMenuItems() async => await getJson('/menu-items') as List<dynamic>;

  @override
  Future<List<dynamic>> listPurchaseOrders({String? status}) async =>
      await getJson('/procurement/purchase-orders', query: {'status_filter': status}) as List<dynamic>;

  @override
  Future<List<dynamic>> listPortionRecommendations({String? status}) async =>
      await getJson('/portion-feedback/recommendations', query: {'status_filter': status}) as List<dynamic>;

  @override
  Future<List<dynamic>> listWasteLogs() async => await getJson('/waste/logs') as List<dynamic>;

  @override
  Future<List<dynamic>> listWasteTrends() async => await getJson('/waste/trends') as List<dynamic>;

  @override
  Future<List<dynamic>> listReports() async => await getJson('/reports') as List<dynamic>;

  @override
  Future<List<dynamic>> listIngredients() async => await getJson('/inventory/ingredients') as List<dynamic>;

  @override
  Future<Map<String, dynamic>> login({required String email, required String password}) async =>
      {'access_token': fakeToken(loginRole)};

  @override
  Future<Map<String, dynamic>> confirmPrep({
    required int recommendationId,
    required String confirmedQuantity,
    String? deviationReason,
  }) async {
    final result = _answer('POST', '/kitchen/prep-recommendations/$recommendationId/confirm', {
      'confirmed_quantity': confirmedQuantity,
      'deviation_reason': ?deviationReason,
    }, null);
    return (result as Map).cast<String, dynamic>();
  }

  @override
  Future<Map<String, dynamic>> createRestockingRequest({
    required int ingredientId,
    required String quantity,
    bool urgency = false,
  }) async {
    final result = _answer('POST', '/inventory/restocking-requests', {
      'ingredient_id': ingredientId,
      'quantity': quantity,
      'urgency': urgency,
    }, null);
    return (result as Map).cast<String, dynamic>();
  }
}

/// A sensible default for the lookups most screens make.
Map<String, Handler> baseRoutes() => {
  'GET /config': (_, _) => {
    'config_id': 1,
    'default_low_stock_threshold': '10.000',
    'leftover_rate_threshold': '15.00',
    'prep_deviation_threshold': '10.00',
    'portions_per_staff_ratio': '30.00',
    'monthly_budget_limit': '8000.00',
    'near_expiry_window_days': 3,
    'delivery_deviation_threshold': '10.00',
    'stock_consumption_applied_through': null,
  },
  'GET /procurement/budget/utilisation': (_, _) => {
    'month': '2026-10-01',
    'budget_limit': '1000.00',
    'spent': '400.00',
    'remaining': '600.00',
    'utilisation_pct': '40.00',
  },
};

/// Pumps [screen] inside the app theme, logged in as [role], and settles.
Future<FakeApi> pumpAs(
  WidgetTester tester,
  String role,
  Widget screen, {
  Map<String, Handler> routes = const {},
  Size size = const Size(420, 900),
}) async {
  FlutterSecureStoragePlatform.instance = FakeSecureStorage();
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);

  final api = FakeApi({...baseRoutes(), ...routes})..loginRole = role;
  final auth = AuthState(api: api);
  await auth.login(email: 'test@restaurant.com', password: 'password123');

  await tester.pumpWidget(
    ChangeNotifierProvider<AuthState>.value(
      value: auth,
      child: MaterialApp(theme: buildAppTheme(), home: screen),
    ),
  );
  await tester.pumpAndSettle();
  return api;
}
