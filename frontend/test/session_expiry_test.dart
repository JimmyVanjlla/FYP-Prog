// An expired login used to leave the app on "Could not validate credentials"
// with a Try again button that could never work. It should return to login.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_secure_storage_platform_interface/flutter_secure_storage_platform_interface.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';

import 'package:restaurant_ops/core/api_client.dart';
import 'package:restaurant_ops/core/auth_state.dart';
import 'package:restaurant_ops/core/jwt.dart';
import 'package:restaurant_ops/core/theme.dart';
import 'package:restaurant_ops/features/shared/auth/login_screen.dart';

import 'helpers.dart';

String tokenExpiring(DateTime at, {String role = 'Kitchen Staff'}) {
  String enc(Object o) => base64Url.encode(utf8.encode(jsonEncode(o))).replaceAll('=', '');
  final exp = at.toUtc().millisecondsSinceEpoch ~/ 1000;
  return '${enc({'alg': 'none'})}.${enc({'role': role, 'sub': '1', 'exp': exp})}.sig';
}

http.Client _answering(int status, Object body) =>
    MockClient((_) async => http.Response(jsonEncode(body), status, headers: {'content-type': 'application/json'}));

void main() {
  setUp(() => FlutterSecureStoragePlatform.instance = FakeSecureStorage());

  group('isJwtExpired', () {
    test('is true once exp has passed, false before it', () {
      final now = DateTime.utc(2026, 11, 3, 12);
      expect(isJwtExpired(tokenExpiring(DateTime.utc(2026, 11, 2)), now: now), isTrue);
      expect(isJwtExpired(tokenExpiring(DateTime.utc(2026, 11, 4)), now: now), isFalse);
    });

    test('leaves tokens it cannot judge to the backend', () {
      expect(isJwtExpired(fakeToken('Kitchen Staff')), isFalse); // no exp claim
      expect(isJwtExpired('not-a-jwt'), isFalse);
    });
  });

  group('AuthState', () {
    test('discards a saved token that has already expired and says why', () async {
      await const FlutterSecureStorage().write(
        key: 'access_token',
        value: tokenExpiring(DateTime.now().toUtc().subtract(const Duration(days: 2))),
      );
      final auth = AuthState(api: ApiClient(baseUrl: 'http://x'));

      await auth.restoreSession();

      expect(auth.isAuthenticated, isFalse);
      expect(auth.notice, contains('expired'));
      expect(await const FlutterSecureStorage().read(key: 'access_token'), isNull);
    });

    test('keeps a saved token that is still valid', () async {
      await const FlutterSecureStorage().write(
        key: 'access_token',
        value: tokenExpiring(DateTime.now().toUtc().add(const Duration(hours: 5))),
      );
      final auth = AuthState(api: ApiClient(baseUrl: 'http://x'));

      await auth.restoreSession();

      expect(auth.isAuthenticated, isTrue);
      expect(auth.role, 'Kitchen Staff');
      expect(auth.notice, isNull);
    });

    test('a 401 mid-session ends the session and tells the person', () async {
      await const FlutterSecureStorage().write(
        key: 'access_token',
        value: tokenExpiring(DateTime.now().toUtc().add(const Duration(hours: 1))),
      );
      final auth = AuthState(api: ApiClient(baseUrl: 'http://x'));
      await auth.restoreSession();
      expect(auth.isAuthenticated, isTrue);

      await http.runWithClient(
        () async {
          // Several screens load in parallel; all of them failing must be harmless.
          final results = await Future.wait([
            auth.api.getJson('/menu-items').then((_) => 'ok').catchError((_) => 'failed'),
            auth.api.getJson('/config').then((_) => 'ok').catchError((_) => 'failed'),
          ]);
          expect(results, ['failed', 'failed']);
        },
        () => _answering(401, {'detail': 'Could not validate credentials'}),
      );

      expect(auth.isAuthenticated, isFalse);
      expect(auth.notice, contains('expired'));
      expect(await const FlutterSecureStorage().read(key: 'access_token'), isNull);
    });

    test('a wrong password is not an expired session', () async {
      final auth = AuthState(api: ApiClient(baseUrl: 'http://x'));

      await http.runWithClient(
        () async {
          await expectLater(
            auth.login(email: 'a@b.com', password: 'wrong'),
            throwsA(isA<ApiException>()),
          );
        },
        () => _answering(401, {'detail': 'Incorrect email or password.'}),
      );

      expect(auth.notice, isNull);
    });
  });

  testWidgets('the login screen explains an expired session', (tester) async {
    final auth = AuthState(api: ApiClient(baseUrl: 'http://x'))..notice = 'Your session has expired. Please log in again.';
    await tester.pumpWidget(
      ChangeNotifierProvider<AuthState>.value(
        value: auth,
        child: MaterialApp(theme: buildAppTheme(), home: const LoginScreen()),
      ),
    );

    expect(find.text('Your session has expired. Please log in again.'), findsOneWidget);
  });
}
