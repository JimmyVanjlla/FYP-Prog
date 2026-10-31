import 'dart:async';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';

import 'api_client.dart';

/// FR5.4 — push notifications via Firebase Cloud Messaging.
///
/// The backend stores every notification and pushes it to the devices a user
/// has registered (see app/services/notifications.py); this is the phone's
/// half: get an FCM token, tell the backend about it after login, keep it
/// fresh, and withdraw it on logout so a signed-out phone stops getting that
/// person's alerts.
///
/// It stays completely inert until a Firebase project is supplied at build
/// time, because the credentials are the deployer's, not something that
/// belongs in source control:
///
///   flutter run \
///     --dart-define=FIREBASE_API_KEY=... \
///     --dart-define=FIREBASE_APP_ID=... \
///     --dart-define=FIREBASE_MESSAGING_SENDER_ID=... \
///     --dart-define=FIREBASE_PROJECT_ID=...
///
/// Without them the app works exactly as before, just without push; the
/// in-app notification inbox still shows everything.
class PushService {
  static const _apiKey = String.fromEnvironment('FIREBASE_API_KEY');
  static const _appId = String.fromEnvironment('FIREBASE_APP_ID');
  static const _senderId = String.fromEnvironment('FIREBASE_MESSAGING_SENDER_ID');
  static const _projectId = String.fromEnvironment('FIREBASE_PROJECT_ID');

  static bool get isConfigured =>
      _apiKey.isNotEmpty && _appId.isNotEmpty && _senderId.isNotEmpty && _projectId.isNotEmpty;

  String? _token;
  StreamSubscription<String>? _refreshSub;

  Future<bool> _ensureInitialised() async {
    if (!isConfigured) return false;
    if (Firebase.apps.isEmpty) {
      await Firebase.initializeApp(
        options: const FirebaseOptions(
          apiKey: _apiKey,
          appId: _appId,
          messagingSenderId: _senderId,
          projectId: _projectId,
        ),
      );
    }
    return true;
  }

  /// Registers this phone's token for the signed-in user. Never throws: a
  /// failure here (no Play services, notifications denied, offline) must not
  /// get in the way of logging in.
  Future<void> register(ApiClient api) async {
    try {
      if (!await _ensureInitialised()) return;
      final messaging = FirebaseMessaging.instance;
      await messaging.requestPermission();
      // firebase_messaging 17 deprecates getToken/onTokenRefresh in favour of
      // register()/onRegistered, which yield a Firebase Installation ID. The
      // backend sends by registration token (FCM HTTP v1 `message.token`), so
      // this keeps the long-established token API until sending by FID has
      // been confirmed against a real Firebase project.
      // ignore: deprecated_member_use
      final token = await messaging.getToken();
      if (token == null) return;
      _token = token;
      await _send(api, token);

      await _refreshSub?.cancel();
      // ignore: deprecated_member_use
      _refreshSub = messaging.onTokenRefresh.listen((fresh) {
        _token = fresh;
        unawaited(_send(api, fresh));
      });
    } catch (e) {
      debugPrint('Push registration skipped: $e');
    }
  }

  Future<void> _send(ApiClient api, String token) =>
      api.postJson('/notifications/devices', {'token': token, 'platform': defaultTargetPlatform.name});

  /// Withdraws this phone's token (call while the user is still signed in).
  Future<void> unregister(ApiClient api) async {
    await _refreshSub?.cancel();
    _refreshSub = null;
    final token = _token;
    if (token == null) return;
    try {
      await api.postJson('/notifications/devices/unregister', {'token': token});
    } catch (e) {
      debugPrint('Push unregister skipped: $e');
    }
    _token = null;
  }
}
