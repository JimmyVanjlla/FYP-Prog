// Smoke test: an unauthenticated app boot lands on the login screen, with
// no role selector present (Ch4 §4.4.1 — role comes from the JWT, never a
// login-time choice).
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage_platform_interface/flutter_secure_storage_platform_interface.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:restaurant_ops/core/auth_state.dart';
import 'package:restaurant_ops/core/theme.dart';
import 'package:restaurant_ops/features/auth/login_screen.dart';

/// In-memory fake so the test never touches a real platform secure-storage
/// channel (there isn't one available under `flutter test`).
class _FakeSecureStorage extends FlutterSecureStoragePlatform {
  final _data = <String, String>{};

  @override
  Future<String?> read({required String key, required Map<String, String> options}) async =>
      _data[key];

  @override
  Future<void> write({
    required String key,
    required String value,
    required Map<String, String> options,
  }) async {
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
  Future<Map<String, String>> readAll({required Map<String, String> options}) async =>
      Map.of(_data);

  @override
  Future<void> deleteAll({required Map<String, String> options}) async {
    _data.clear();
  }
}

void main() {
  testWidgets('Unauthenticated app shows the login screen, no role selector', (tester) async {
    FlutterSecureStoragePlatform.instance = _FakeSecureStorage();

    await tester.pumpWidget(
      ChangeNotifierProvider(
        create: (_) => AuthState()..restoreSession(),
        child: MaterialApp(theme: buildAppTheme(), home: const LoginScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Restaurant Ops'), findsOneWidget);
    expect(find.widgetWithText(TextFormField, 'Email'), findsOneWidget);
    expect(find.widgetWithText(TextFormField, 'Password'), findsOneWidget);
    expect(find.byType(DropdownButtonFormField<String>), findsNothing);
  });
}
