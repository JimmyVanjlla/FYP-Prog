import 'dart:convert';

/// Minimal JWT payload decoder — no signature verification (the client
/// trusts the backend that issued the token over HTTPS; verification is the
/// backend's job on every request, per NFR-Security). Just enough to read
/// `role` back out so the UI can route without a second API call.
Map<String, dynamic> decodeJwtPayload(String token) {
  final parts = token.split('.');
  if (parts.length != 3) {
    throw const FormatException('Not a valid JWT');
  }
  final normalized = base64Url.normalize(parts[1]);
  final payload = utf8.decode(base64Url.decode(normalized));
  return jsonDecode(payload) as Map<String, dynamic>;
}

/// True when the token's `exp` claim (seconds since the epoch) has passed.
/// A token with no `exp`, or one that can't be read, is treated as not
/// expired: the backend is the authority and will answer 401 if it is.
bool isJwtExpired(String token, {DateTime? now}) {
  try {
    final exp = decodeJwtPayload(token)['exp'];
    if (exp is! num) return false;
    final expiry = DateTime.fromMillisecondsSinceEpoch(exp.toInt() * 1000, isUtc: true);
    return !(now ?? DateTime.now().toUtc()).isBefore(expiry);
  } catch (_) {
    return false;
  }
}
