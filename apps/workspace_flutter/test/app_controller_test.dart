import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geem_workspace/src/controllers/app_controller.dart';
import 'package:geem_workspace/src/services/credential_store.dart';
import 'package:geem_workspace/src/services/geem_api_client.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class _MemoryCredentialStore implements CredentialStore {
  String? refreshToken;

  @override
  Future<void> deleteRefreshToken() async => refreshToken = null;

  @override
  Future<String?> readLocale() async => null;

  @override
  Future<String?> readRefreshToken() async => refreshToken;

  @override
  Future<String?> readWorkspaceId(String userId) async => null;

  @override
  Future<void> writeLocale(String languageCode) async {}

  @override
  Future<void> writeRefreshToken(String token) async => refreshToken = token;

  @override
  Future<void> writeWorkspaceId(String userId, String workspaceId) async {}
}

void main() {
  test('auth links require a trusted scheme and host', () async {
    final credentials = _MemoryCredentialStore()..refreshToken = 'refresh-a';
    final controller = AppController(
      api: GeemApiClient(
        baseUrl: 'https://api.example.test',
        credentials: credentials,
      ),
      credentials: credentials,
      initialLocale: const Locale('en'),
    )..sessionState = AppSessionState.authenticated;
    addTearDown(controller.dispose);

    await controller.handleDeepLink(
      Uri.parse('geem://untrusted/reset-password?token=secret'),
    );
    expect(controller.sessionState, AppSessionState.authenticated);
    expect(controller.resetToken, isEmpty);
    expect(credentials.refreshToken, 'refresh-a');

    await controller.handleDeepLink(
      Uri.parse('geem://auth/reset-password?token=secret'),
    );
    expect(controller.sessionState, AppSessionState.unauthenticated);
    expect(controller.authPage, AuthPage.resetPassword);
    expect(controller.resetToken, 'secret');
    expect(credentials.refreshToken, isNull);
  });

  test('transient startup failure preserves the saved session', () async {
    final credentials = _MemoryCredentialStore()..refreshToken = 'refresh-a';
    final controller = AppController(
      api: GeemApiClient(
        baseUrl: 'https://api.example.test',
        credentials: credentials,
        client: MockClient((_) async => http.Response('Unavailable', 503)),
      ),
      credentials: credentials,
      initialLocale: const Locale('en'),
    );
    addTearDown(controller.dispose);

    await controller.initialize();

    expect(controller.sessionState, AppSessionState.unauthenticated);
    expect(controller.errorCode, 'server_error');
    expect(credentials.refreshToken, 'refresh-a');
  });

  test('terminal startup failure removes the saved session', () async {
    final credentials = _MemoryCredentialStore()..refreshToken = 'refresh-a';
    final controller = AppController(
      api: GeemApiClient(
        baseUrl: 'https://api.example.test',
        credentials: credentials,
        client: MockClient(
          (_) async => http.Response(
            '{"code":"session_revoked","message":"Revoked"}',
            401,
          ),
        ),
      ),
      credentials: credentials,
      initialLocale: const Locale('en'),
    );
    addTearDown(controller.dispose);

    await controller.initialize();

    expect(controller.sessionState, AppSessionState.unauthenticated);
    expect(credentials.refreshToken, isNull);
  });
}
