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
