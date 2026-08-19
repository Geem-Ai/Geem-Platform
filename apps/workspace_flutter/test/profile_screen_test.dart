import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geem_workspace/src/app_scope.dart';
import 'package:geem_workspace/src/controllers/app_controller.dart';
import 'package:geem_workspace/src/localization/app_strings.dart';
import 'package:geem_workspace/src/models/models.dart';
import 'package:geem_workspace/src/screens/profile/profile_screen.dart';
import 'package:geem_workspace/src/services/credential_store.dart';
import 'package:geem_workspace/src/services/geem_api_client.dart';
import 'package:geem_workspace/src/theme/geem_theme.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class _MemoryCredentialStore implements CredentialStore {
  String? refreshToken = 'refresh-token';
  String? locale;

  @override
  Future<void> deleteRefreshToken() async => refreshToken = null;

  @override
  Future<String?> readLocale() async => locale;

  @override
  Future<String?> readRefreshToken() async => refreshToken;

  @override
  Future<String?> readWorkspaceId(String userId) async => null;

  @override
  Future<void> writeLocale(String languageCode) async => locale = languageCode;

  @override
  Future<void> writeRefreshToken(String token) async => refreshToken = token;

  @override
  Future<void> writeWorkspaceId(String userId, String workspaceId) async {}
}

class _ProfileFixture {
  _ProfileFixture({this.logoutGate}) {
    credentials = _MemoryCredentialStore();
    api = GeemApiClient(
      baseUrl: 'https://api.example.test',
      credentials: credentials,
      client: MockClient((request) async {
        if (request.url.path == '/api/auth/logout') {
          logoutRequests += 1;
          final gate = logoutGate;
          if (gate != null) await gate.future;
          return http.Response('', 204);
        }
        return http.Response('{"code":"not_found"}', 404);
      }),
    );

    const workspace = WorkspaceSummary(
      id: 'workspace-1',
      name: 'Product',
      slug: 'product',
      status: 'active',
      role: RoleSummary(name: 'Member'),
      permissions: ['chat.use'],
    );
    controller =
        AppController(
            api: api,
            credentials: credentials,
            initialLocale: const Locale('en'),
          )
          ..sessionState = AppSessionState.authenticated
          ..user = const GeemUser(
            id: 'user-1',
            email: 'person@example.test',
            status: 'active',
            platformRole: 'user',
          )
          ..workspaces = const [workspace]
          ..currentWorkspace = workspace;
  }

  final Completer<void>? logoutGate;
  late final _MemoryCredentialStore credentials;
  late final GeemApiClient api;
  late final AppController controller;
  int logoutRequests = 0;

  void dispose() {
    controller.dispose();
    api.close();
  }
}

class _ProfileTestHost extends StatelessWidget {
  const _ProfileTestHost();

  static const openButtonKey = Key('open-profile');

  @override
  Widget build(BuildContext context) => Scaffold(
    body: const Center(child: Text('Chat root')),
    floatingActionButton: FloatingActionButton(
      key: openButtonKey,
      onPressed: () => Navigator.of(
        context,
      ).push(MaterialPageRoute<void>(builder: (_) => const ProfileScreen())),
      child: const Icon(Icons.person_outline_rounded),
    ),
  );
}

void main() {
  const strings = AppStrings('en');

  test('profile logout confirmation has Arabic copy', () {
    const arabic = AppStrings('ar');
    expect(arabic.text('profile'), 'الملف الشخصي');
    expect(arabic.text('logoutConfirmTitle'), 'تسجيل الخروج؟');
    expect(
      arabic.text('logoutConfirmBody'),
      'ستحتاج إلى تسجيل الدخول مرة أخرى للوصول إلى مساحة '
      'العمل هذه.',
    );
  });

  Future<void> pumpProfile(WidgetTester tester, _ProfileFixture fixture) async {
    await tester.binding.setSurfaceSize(const Size(800, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      AppScope(
        controller: fixture.controller,
        child: MaterialApp(
          locale: const Locale('en'),
          theme: geemLightTheme(),
          home: const _ProfileTestHost(),
        ),
      ),
    );
    await tester.tap(find.byKey(_ProfileTestHost.openButtonKey));
    await tester.pumpAndSettle();
  }

  testWidgets('opening profile never logs out the active session', (
    tester,
  ) async {
    final fixture = _ProfileFixture();
    addTearDown(fixture.dispose);

    await pumpProfile(tester, fixture);

    expect(find.byKey(ProfileScreen.screenKey), findsOneWidget);
    expect(find.text('person@example.test'), findsNWidgets(2));
    expect(find.text('Product'), findsOneWidget);
    expect(find.text('Member'), findsOneWidget);
    expect(find.byKey(ProfileScreen.logoutButtonKey), findsOneWidget);
    expect(fixture.logoutRequests, 0);
    expect(fixture.controller.sessionState, AppSessionState.authenticated);
  });

  testWidgets('cancelling logout keeps the profile and session active', (
    tester,
  ) async {
    final fixture = _ProfileFixture();
    addTearDown(fixture.dispose);
    await pumpProfile(tester, fixture);

    await tester.tap(find.byKey(ProfileScreen.logoutButtonKey));
    await tester.pumpAndSettle();

    expect(find.byType(AlertDialog), findsOneWidget);
    expect(find.text(strings.text('logoutConfirmTitle')), findsOneWidget);
    await tester.tap(find.widgetWithText(TextButton, strings.text('cancel')));
    await tester.pumpAndSettle();

    expect(find.byType(AlertDialog), findsNothing);
    expect(find.byKey(ProfileScreen.screenKey), findsOneWidget);
    expect(fixture.logoutRequests, 0);
    expect(fixture.controller.sessionState, AppSessionState.authenticated);
  });

  testWidgets('confirming logout shows progress and clears the profile route', (
    tester,
  ) async {
    final logoutGate = Completer<void>();
    final fixture = _ProfileFixture(logoutGate: logoutGate);
    addTearDown(fixture.dispose);
    await pumpProfile(tester, fixture);

    await tester.tap(find.byKey(ProfileScreen.logoutButtonKey));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(ProfileScreen.logoutConfirmButtonKey));
    await tester.pump();
    await tester.pump();

    expect(fixture.logoutRequests, 1);
    expect(find.text(strings.text('loggingOut')), findsWidgets);
    expect(find.byType(CircularProgressIndicator), findsWidgets);

    logoutGate.complete();
    await tester.pumpAndSettle();

    expect(find.text('Chat root'), findsOneWidget);
    expect(find.byKey(ProfileScreen.screenKey), findsNothing);
    expect(fixture.controller.sessionState, AppSessionState.unauthenticated);
  });
}
