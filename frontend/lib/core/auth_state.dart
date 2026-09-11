import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'api_client.dart';
import 'jwt.dart';

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

  String? _token;
  String? _role;
  bool _restoring = true;

  AuthState({ApiClient? api, FlutterSecureStorage? storage})
    : api = api ?? ApiClient(),
      _storage = storage ?? const FlutterSecureStorage();

  bool get isAuthenticated => _token != null;
  String? get role => _role;
  bool get isRestoring => _restoring;

  /// Called once at app startup to resume a session without asking the
  /// user to log in again every time they reopen the app.
  Future<void> restoreSession() async {
    final stored = await _storage.read(key: _tokenStorageKey);
    if (stored != null) {
      _applyToken(stored);
    }
    _restoring = false;
    notifyListeners();
  }

  Future<void> login({required String email, required String password}) async {
    final result = await api.login(email: email, password: password);
    final token = result['access_token'] as String;
    await _storage.write(key: _tokenStorageKey, value: token);
    _applyToken(token);
    notifyListeners();
  }

  Future<void> register({
    required String name,
    required String email,
    required String password,
    required String role,
  }) async {
    await api.register(
      name: name,
      email: email,
      password: password,
      role: role,
    );
    // FR1.1 registration doesn't itself log the user in — mirrors the
    // backend, which issues no token from /auth/register.
  }

  Future<void> logout() async {
    await _storage.delete(key: _tokenStorageKey);
    _token = null;
    _role = null;
    api.setToken(null);
    notifyListeners();
  }

  void _applyToken(String token) {
    _token = token;
    api.setToken(token);
    _role = decodeJwtPayload(token)['role'] as String?;
  }
}
