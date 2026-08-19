import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geem_workspace/src/app_scope.dart';
import 'package:geem_workspace/src/controllers/app_controller.dart';
import 'package:geem_workspace/src/models/models.dart';
import 'package:geem_workspace/src/screens/chat/chat_shell.dart';
import 'package:geem_workspace/src/screens/chat/expert_navbar_dropdown.dart';
import 'package:geem_workspace/src/services/credential_store.dart';
import 'package:geem_workspace/src/services/geem_api_client.dart';
import 'package:geem_workspace/src/theme/geem_theme.dart';

class _MemoryCredentialStore implements CredentialStore {
  @override
  Future<void> deleteRefreshToken() async {}

  @override
  Future<String?> readLocale() async => null;

  @override
  Future<String?> readRefreshToken() async => null;

  @override
  Future<String?> readWorkspaceId(String userId) async => null;

  @override
  Future<void> writeLocale(String languageCode) async {}

  @override
  Future<void> writeRefreshToken(String token) async {}

  @override
  Future<void> writeWorkspaceId(String userId, String workspaceId) async {}
}

void main() {
  late AppController controller;

  setUp(() {
    final credentials = _MemoryCredentialStore();
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
            api: GeemApiClient(
              baseUrl: 'https://api.example.test',
              credentials: credentials,
            ),
            credentials: credentials,
            initialLocale: const Locale('en'),
          )
          ..sessionState = AppSessionState.authenticated
          ..user = const GeemUser(
            id: 'user-1',
            email: 'person@example.test',
            status: 'active',
            platformRole: 'member',
          )
          ..workspaces = const [workspace]
          ..currentWorkspace = workspace
          ..experts = const [
            Expert(
              id: 'general',
              name: 'Geem General',
              status: 'ready',
              ownership: 'platform',
              knowledgeMode: 'general',
            ),
          ]
          ..selectedExpertId = 'general';
  });

  tearDown(() => controller.dispose());

  Future<void> pumpShell(WidgetTester tester, Size size) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = size;
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);
    await tester.pumpWidget(
      AppScope(
        controller: controller,
        child: MaterialApp(theme: geemLightTheme(), home: const ChatShell()),
      ),
    );
  }

  testWidgets('desktop new chat keeps expert dropdown in navbar only', (
    tester,
  ) async {
    await pumpShell(tester, const Size(1024, 768));

    final selector = find.byKey(ExpertNavbarDropdown.navbarKey);
    final composer = find.byKey(const Key('chat-composer'));
    expect(selector, findsOneWidget);
    expect(composer, findsOneWidget);
    expect(
      find.descendant(
        of: composer,
        matching: find.byType(DropdownButton<String>),
      ),
      findsNothing,
    );
  });

  testWidgets('mobile new chat places expert dropdown in app bar', (
    tester,
  ) async {
    await pumpShell(tester, const Size(320, 700));

    final selector = find.byKey(ExpertNavbarDropdown.navbarKey);
    expect(selector, findsOneWidget);
    expect(
      find.descendant(of: find.byType(AppBar), matching: selector),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: find.byKey(const Key('chat-composer')),
        matching: find.byType(DropdownButton<String>),
      ),
      findsNothing,
    );
  });
}
