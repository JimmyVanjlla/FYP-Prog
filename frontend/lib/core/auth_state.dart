import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'api_client.dart';
import 'jwt.dart';
import 'push_service.dart';

/// The 7 staff roles (Ch1 §1.5.2 / Ch4 §4.1) — mirrors the backend's
/// app/models/roles.py::Role. Kept as plain string constants (not a Dart
/// enum) so a role value round-trips through JSON/JWT without a mapping
/// table to keep in sync.
class Roles {
  static const owner = 'Restaurant Owner';
  static const manager = 'Restaurant Manager';
  static const kitchenStaff = 'Kitchen Staff';
  static const inventoryStaff = 'Inventory Staff';
  static const shiftSupervisor = 'Shift Supervisor';
  static const procurementOfficer = 'Procurement Officer';
  static const deliveryStaff = 'Delivery/Logistics Staff';

  static const all = [
    owner,
    manager,
    kitchenStaff,
    inventoryStaff,
    shiftSupervisor,
    procurementOfficer,
    deliveryStaff,
  ];

  const Roles._();
}

/// App-wide auth/session state. The JWT is the single source of truth for
/// role — there is no separate role selector anywhere in the UI (Ch4
/// §4.4.1 auth principle), it's decoded out of the token FastAPI issued.
class AuthState extends ChangeNotifier {
  static const _tokenStorageKey = 'access_token';

  final ApiClient api;
  final FlutterSecureStorage _storage;
  final PushService _push;

  String? _token;
  String? _role;
  bool _restoring = true;

  /// The signed-in person's name, for the menu header. Loaded after sign-in
  /// and whenever the profile is saved; null until then, and the menu simply
  /// shows the role.
  String? displayName;

  /// Shown on the login screen after a session ends on its own (the token
  /// expired), so the person knows why they were sent back.
  String? notice;

  AuthState({ApiClient? api, FlutterSecureStorage? storage, PushService? push})
    : api = api ?? ApiClient(),
      _storage = storage ?? const FlutterSecureStorage(),
      _push = push ?? PushService() {
    this.api.onUnauthorized = _sessionExpired;
  }

  static const _expiredNotice = 'Your session has expired. Please log in again.';

  bool get isAuthenticated => _token != null;
  String? get role => _role;
  bool get isRestoring => _restoring;
  // Only used to build the report-download URL (see
  // ApiClient.reportDownloadUrl) for the system browser, which can't send
  // an Authorization header itself — never logged or displayed.
  String? get token => _token;

  /// Called once at app startup to resume a session without asking the
  /// user to log in again every time they reopen the app.
  Future<void> restoreSession() async {
    final stored = await _storage.read(key: _tokenStorageKey);
    if (stored != null && isJwtExpired(stored)) {
      // Tokens last 24 hours; one saved yesterday is useless, and keeping it
      // would open the app on a screen that can only fail.
      await _storage.delete(key: _tokenStorageKey);
      notice = _expiredNotice;
    } else if (stored != null) {
      _applyToken(stored);
      unawaited(_push.register(api));
      unawaited(loadProfile());
    }
    _restoring = false;
    notifyListeners();
  }

  /// The backend rejected our token mid-session. Drop it and go back to login.
  /// (No push unregister: that call needs a valid token, which is the problem.)
  void _sessionExpired() {
    if (_token == null) return; // several requests can fail together
    unawaited(_storage.delete(key: _tokenStorageKey));
    _token = null;
    _role = null;
    displayName = null;
    api.setToken(null);
    notice = _expiredNotice;
    notifyListeners();
  }

  Future<void> loadProfile() async {
    try {
      final me = await api.getJson('/users/me');
      final name = me is Map ? me['name'] : null;
      if (name is String && name != displayName) {
        displayName = name;
        notifyListeners();
      }
    } catch (_) {
      // The header falls back to the role; not worth bothering the person.
    }
  }

  Future<void> login({required String email, required String password}) async {
    final result = await api.login(email: email, password: password);
    final token = result['access_token'] as String;
    await _storage.write(key: _tokenStorageKey, value: token);
    notice = null;
    _applyToken(token);
    unawaited(_push.register(api));
    unawaited(loadProfile());
    notifyListeners();
  }

  // There is no self-registration in the app: a Restaurant Manager or Owner
  // creates every account from the Staff screen (POST /users).

  Future<void> logout() async {
    // While the token is still valid, so the backend stops pushing this
    // person's alerts to this phone.
    await _push.unregister(api);
    await _storage.delete(key: _tokenStorageKey);
    _token = null;
    _role = null;
    displayName = null;
    api.setToken(null);
    notifyListeners();
  }

  void _applyToken(String token) {
    _token = token;
    api.setToken(token);
    _role = decodeJwtPayload(token)['role'] as String?;
  }
}
