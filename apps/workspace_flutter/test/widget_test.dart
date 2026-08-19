import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geem_workspace/src/app_scope.dart';
import 'package:geem_workspace/src/controllers/app_controller.dart';
import 'package:geem_workspace/src/screens/auth/auth_screen.dart';
import 'package:geem_workspace/src/services/credential_store.dart';
import 'package:geem_workspace/src/services/geem_api_client.dart';
import 'package:geem_workspace/src/theme/geem_theme.dart';

class _MemoryCredentialStore implements CredentialStore {
  String? refreshToken;
  String? locale;
  final workspaceIds = <String, String>{};

  @override
  Future<void> deleteRefreshToken() async => refreshToken = null;

  @override
  Future<String?> readLocale() async => locale;

  @override
  Future<String?> readRefreshToken() async => refreshToken;

  @override
  Future<String?> readWorkspaceId(String userId) async => workspaceIds[userId];

  @override
  Future<void> writeLocale(String languageCode) async => locale = languageCode;

  @override
  Future<void> writeRefreshToken(String token) async => refreshToken = token;

  @override
  Future<void> writeWorkspaceId(String userId, String workspaceId) async {
    workspaceIds[userId] = workspaceId;
  }
}

void main() {
  testWidgets('login screen exposes the requested auth actions', (
    tester,
  ) async {
    final credentials = _MemoryCredentialStore();
    final controller = AppController(
      api: GeemApiClient(
        baseUrl: 'https://api.example.test',
        credentials: credentials,
      ),
      credentials: credentials,
      initialLocale: const Locale('en'),
    )..sessionState = AppSessionState.unauthenticated;
    addTearDown(controller.dispose);

    await tester.pumpWidget(
      AppScope(
        controller: controller,
        child: MaterialApp(theme: geemLightTheme(), home: const AuthScreen()),
      ),
    );

    expect(find.text('Welcome back'), findsOneWidget);
    expect(find.text('Forgot password?'), findsOneWidget);
    expect(find.text('Sign in'), findsOneWidget);
    expect(find.byType(TextField), findsNWidgets(2));
  });

  testWidgets('reset deep-link token is not rendered on screen', (
    tester,
  ) async {
    final credentials = _MemoryCredentialStore();
    final controller =
        AppController(
            api: GeemApiClient(
              baseUrl: 'https://api.example.test',
              credentials: credentials,
            ),
            credentials: credentials,
            initialLocale: const Locale('en'),
          )
          ..sessionState = AppSessionState.unauthenticated
          ..authPage = AuthPage.resetPassword
          ..resetToken = 'secret-reset-token';
    addTearDown(controller.dispose);

    await tester.pumpWidget(
      AppScope(
        controller: controller,
        child: MaterialApp(theme: geemLightTheme(), home: const AuthScreen()),
      ),
    );

    expect(find.text('secret-reset-token'), findsNothing);
    expect(find.byType(TextField), findsNWidgets(2));
  });
}
