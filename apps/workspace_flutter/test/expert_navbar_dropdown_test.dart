import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geem_workspace/src/app_scope.dart';
import 'package:geem_workspace/src/controllers/app_controller.dart';
import 'package:geem_workspace/src/models/models.dart';
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

Expert _expert(String id, String name, {String status = 'ready'}) => Expert(
  id: id,
  name: name,
  status: status,
  ownership: 'workspace',
  knowledgeMode: 'rag',
);

Conversation _conversation({ConversationExpert? expert}) => Conversation(
  id: 'conversation-1',
  workspaceId: 'workspace-1',
  expertId: expert?.id ?? 'expert-1',
  title: 'Existing chat',
  isPinned: false,
  isFavorite: false,
  updatedAt: DateTime(2026),
  expert: expert,
);

void main() {
  late AppController controller;

  setUp(() {
    final credentials = _MemoryCredentialStore();
    controller = AppController(
      api: GeemApiClient(
        baseUrl: 'https://api.example.test',
        credentials: credentials,
      ),
      credentials: credentials,
      initialLocale: const Locale('en'),
    );
  });

  tearDown(() => controller.dispose());

  Future<void> pumpSelector(WidgetTester tester, {bool compact = false}) =>
      tester.pumpWidget(
        AppScope(
          controller: controller,
          child: MaterialApp(
            locale: const Locale('en'),
            theme: geemLightTheme(),
            home: Scaffold(
              body: Center(child: ExpertNavbarDropdown(compact: compact)),
            ),
          ),
        ),
      );

  testWidgets('compact dropdown lists and selects only ready experts', (
    tester,
  ) async {
    controller
      ..experts = [
        _expert('expert-1', 'Legal'),
        _expert('expert-2', 'Research'),
        _expert('expert-draft', 'Draft expert', status: 'draft'),
      ]
      ..selectedExpertId = 'expert-1';

    await pumpSelector(tester, compact: true);

    expect(find.byKey(ExpertNavbarDropdown.navbarKey), findsOneWidget);
    expect(
      tester.getSize(find.byKey(ExpertNavbarDropdown.navbarKey)).height,
      38,
    );

    await tester.tap(find.byType(DropdownButton<String>));
    await tester.pumpAndSettle();

    expect(find.text('Draft expert'), findsNothing);
    await tester.tap(find.text('Research').last);
    await tester.pumpAndSettle();

    expect(controller.selectedExpertId, 'expert-2');
  });

  testWidgets('dropdown is disabled while busy or without ready experts', (
    tester,
  ) async {
    controller
      ..experts = [_expert('expert-draft', 'Draft expert', status: 'draft')]
      ..selectedExpertId = 'expert-draft';

    await pumpSelector(tester);

    var dropdown = tester.widget<DropdownButton<String>>(
      find.byType(DropdownButton<String>),
    );
    expect(dropdown.value, isNull);
    expect(dropdown.onChanged, isNull);

    controller
      ..experts = [_expert('expert-1', 'Legal')]
      ..selectedExpertId = 'expert-1'
      ..sending = true;
    controller.notifyListeners();
    await tester.pump();

    dropdown = tester.widget<DropdownButton<String>>(
      find.byType(DropdownButton<String>),
    );
    expect(dropdown.value, 'expert-1');
    expect(dropdown.onChanged, isNull);
  });

  testWidgets('active conversation renders its expert read-only with a lock', (
    tester,
  ) async {
    controller
      ..experts = [_expert('expert-1', 'Different expert')]
      ..selectedExpertId = 'expert-1'
      ..activeConversation = _conversation(
        expert: const ConversationExpert(
          id: 'expert-1',
          name: 'Conversation expert',
          ownership: 'workspace',
        ),
      );

    await pumpSelector(tester);

    expect(find.byKey(ExpertNavbarDropdown.navbarKey), findsOneWidget);
    expect(find.text('Conversation expert'), findsOneWidget);
    expect(find.byIcon(Icons.lock_outline_rounded), findsOneWidget);
    expect(find.byType(DropdownButton<String>), findsNothing);
  });
}
