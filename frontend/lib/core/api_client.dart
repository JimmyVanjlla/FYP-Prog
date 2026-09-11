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
      : baseUrl = baseUrl ??
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
      body: jsonEncode({'name': name, 'email': email, 'password': password, 'role': role}),
    );
    return _decode(resp) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> login({required String email, required String password}) async {
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
        if (description != null && description.isNotEmpty) 'description': description,
        'price': price,
        'category': category,
      }),
    );
    return _decode(resp) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> deactivateMenuItem(int menuItemId) async {
    final resp = await http.delete(_uri('/menu-items/$menuItemId'), headers: _headers);
    return _decode(resp) as Map<String, dynamic>;
  }
}
