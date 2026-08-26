import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geem_workspace/src/app_scope.dart';
import 'package:geem_workspace/src/controllers/app_controller.dart';
import 'package:geem_workspace/src/localization/app_strings.dart';
import 'package:geem_workspace/src/models/models.dart';
import 'package:geem_workspace/src/screens/chat/chat_view.dart';
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
    final conversation = Conversation(
      id: 'conversation-1',
      workspaceId: 'workspace-1',
      expertId: 'expert-1',
      title: 'Customer update',
      isPinned: false,
      isFavorite: false,
      updatedAt: DateTime(2026, 8, 26, 12),
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
          ..conversations = [conversation]
          ..activeConversation = conversation;
  });

  tearDown(() => controller.dispose());

  Future<void> pumpChat(
    WidgetTester tester, {
    Locale locale = const Locale('en'),
    ThemeData? theme,
    Size size = const Size(900, 1000),
    double textScale = 1,
  }) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = size;
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);
    await tester.pumpWidget(
      AppScope(
        controller: controller,
        child: MaterialApp(
          locale: locale,
          supportedLocales: const [Locale('ar'), Locale('en')],
          localizationsDelegates: const [
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          theme: theme ?? geemLightTheme(),
          builder: (context, child) => MediaQuery(
            data: MediaQuery.of(
              context,
            ).copyWith(textScaler: TextScaler.linear(textScale)),
            child: child!,
          ),
          home: const Scaffold(body: ChatView()),
        ),
      ),
    );
    await tester.pump();
  }

  testWidgets(
    'persisted MCP approval renders exact arguments and pauses composer',
    (tester) async {
      controller.messages = [
        ChatMessage.fromJson({
          'id': 'assistant-1',
          'conversation_id': 'conversation-1',
          'role': 'assistant',
          'content': 'This tool call is awaiting your approval.',
          'status': 'pending',
          'created_at': '2026-08-26T12:00:00Z',
          'citations': <Object?>[],
          'tool_activities': [
            {
              'id': 'activity-1',
              'tool_call_id': 'call-1',
              'connection_name': 'Shared CRM',
              'tool_name': 'update_customer',
              'status': 'approval_required',
            },
          ],
          'tool_approval': {
            'id': 'approval-1',
            'tool_call_id': 'call-1',
            'connection_name': 'Shared CRM',
            'tool_name': 'update_customer',
            'arguments': {'customer_id': 7, 'tier': 'gold'},
            'status': 'pending',
            'expires_at': '2026-08-26T12:05:00Z',
          },
        }),
      ];

      await pumpChat(tester);

      expect(
        find.byKey(const ValueKey('tool-activity-activity-1')),
        findsOneWidget,
      );
      expect(find.text('update_customer'), findsOneWidget);
      expect(find.text('Shared CRM'), findsOneWidget);
      expect(find.byKey(const Key('tool-approval-card')), findsOneWidget);
      expect(find.text('Approval required'), findsWidgets);
      expect(find.text('Shared CRM · update_customer'), findsOneWidget);

      final arguments = tester.widget<SelectableText>(
        find.descendant(
          of: find.byKey(const Key('tool-approval-arguments')),
          matching: find.byType(SelectableText),
        ),
      );
      expect(arguments.data, '{\n  "customer_id": 7,\n  "tier": "gold"\n}');
      expect(
        find.text(const AppStrings('en').text('toolApprovalDisclosure')),
        findsOneWidget,
      );
      expect(find.byKey(const Key('approve-tool-call')), findsOneWidget);
      expect(find.byKey(const Key('deny-tool-call')), findsOneWidget);

      final composer = find.byKey(const Key('chat-composer'));
      final field = tester.widget<TextField>(
        find.descendant(of: composer, matching: find.byType(TextField)),
      );
      expect(controller.hasPendingToolTurn, isTrue);
      expect(field.enabled, isFalse);
      expect(
        field.decoration?.hintText,
        const AppStrings('en').text('toolComposerPaused'),
      );
      expect(
        find.text(const AppStrings('en').text('toolComposerPaused')),
        findsWidgets,
      );
    },
  );

  testWidgets('persisted MCP tool citation renders tool metadata', (
    tester,
  ) async {
    controller.messages = [
      ChatMessage.fromJson({
        'id': 'assistant-2',
        'conversation_id': 'conversation-1',
        'role': 'assistant',
        'content': 'Customer found.',
        'status': 'completed',
        'created_at': '2026-08-26T12:00:00Z',
        'citations': [
          {
            'kind': 'tool',
            'connection_display_name': 'Shared CRM',
            'tool_name': 'find_customer',
          },
          {
            'kind': 'tool',
            'connection_display_name': 'Billing CRM',
            'tool_name': 'find_customer',
          },
        ],
        'tool_activities': [
          {
            'id': 'activity-2',
            'connection_name': 'Shared CRM',
            'tool_name': 'find_customer',
            'status': 'succeeded',
          },
        ],
      }),
    ];

    await pumpChat(tester);

    expect(
      find.byKey(const ValueKey('tool-activity-activity-2')),
      findsOneWidget,
    );
    expect(find.text('Completed'), findsOneWidget);
    expect(find.text('Sources (2)'), findsOneWidget);

    await tester.ensureVisible(find.byType(ExpansionTile));
    await tester.tap(find.byType(ExpansionTile));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey('tool-citation-Shared CRM-find_customer-0')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('tool-citation-Billing CRM-find_customer-1')),
      findsOneWidget,
    );
    expect(find.text('find_customer'), findsWidgets);
    expect(find.text('Shared CRM'), findsWidgets);
    expect(find.text('Billing CRM'), findsOneWidget);
    expect(find.text('Page 0'), findsNothing);
  });

  testWidgets('failed and unknown MCP activities show safe guidance', (
    tester,
  ) async {
    controller.messages = [
      ChatMessage(
        id: 'assistant-3',
        conversationId: 'conversation-1',
        role: 'assistant',
        content: 'I could not complete every external action.',
        status: 'completed',
        createdAt: DateTime(2026, 8, 26, 12),
        toolActivities: const [
          ToolActivity(
            id: 'activity-failed',
            connectionName: 'Shared CRM',
            toolName: 'find_customer',
            status: 'failed',
            errorCode: 'mcp_reauthorization_required',
          ),
          ToolActivity(
            id: 'activity-unknown',
            connectionName: 'Shared CRM',
            toolName: 'update_customer',
            status: 'outcome_unknown',
          ),
        ],
      ),
    ];

    await pumpChat(tester);

    expect(
      find.text(const AppStrings('en').error('mcp_reauthorization_required')),
      findsOneWidget,
    );
    expect(
      find.text(const AppStrings('en').text('toolOutcomeUnknown')),
      findsOneWidget,
    );
    expect(find.text('mcp_reauthorization_required'), findsNothing);
  });

  testWidgets('redacted pending arguments can be denied but not approved', (
    tester,
  ) async {
    controller.messages = [
      ChatMessage(
        id: 'assistant-redacted',
        conversationId: 'conversation-1',
        role: 'assistant',
        content: 'This tool call is awaiting your approval.',
        status: 'pending',
        createdAt: DateTime(2026, 8, 26, 12),
        toolApproval: const ToolApproval(
          id: 'approval-redacted',
          connectionName: 'Shared CRM',
          toolName: 'update_customer',
          status: 'pending',
        ),
      ),
    ];

    await pumpChat(tester);

    expect(
      find.text(const AppStrings('en').text('toolArgumentsUnavailable')),
      findsOneWidget,
    );
    expect(find.byKey(const Key('tool-approval-arguments')), findsNothing);
    expect(find.byKey(const Key('approve-tool-call')), findsNothing);
    expect(find.byKey(const Key('deny-tool-call')), findsOneWidget);
    expect(controller.hasPendingToolTurn, isTrue);
  });

  testWidgets('denied approval renders as terminal without stale actions', (
    tester,
  ) async {
    controller.messages = [
      ChatMessage(
        id: 'assistant-denied',
        conversationId: 'conversation-1',
        role: 'assistant',
        content: 'The tool request was denied.',
        status: 'failed',
        createdAt: DateTime(2026, 8, 26, 12),
        toolApproval: const ToolApproval(
          id: 'approval-denied',
          connectionName: 'Shared CRM',
          toolName: 'update_customer',
          status: 'denied',
        ),
      ),
    ];

    await pumpChat(tester);

    expect(find.text('Denied'), findsOneWidget);
    expect(find.byKey(const Key('tool-approval-arguments')), findsNothing);
    expect(find.byKey(const Key('approve-tool-call')), findsNothing);
    expect(find.byKey(const Key('deny-tool-call')), findsNothing);
    expect(controller.hasPendingToolTurn, isFalse);
  });

  testWidgets('executed approval renders as completed without stale actions', (
    tester,
  ) async {
    controller.messages = [
      ChatMessage(
        id: 'assistant-executed',
        conversationId: 'conversation-1',
        role: 'assistant',
        content: 'The customer was updated.',
        status: 'completed',
        createdAt: DateTime(2026, 8, 26, 12),
        toolApproval: const ToolApproval(
          id: 'approval-executed',
          connectionName: 'Shared CRM',
          toolName: 'update_customer',
          status: 'executed',
        ),
      ),
    ];

    await pumpChat(tester);

    expect(find.text('Completed'), findsOneWidget);
    expect(find.byKey(const Key('tool-approval-arguments')), findsNothing);
    expect(find.byKey(const Key('approve-tool-call')), findsNothing);
    expect(find.byKey(const Key('deny-tool-call')), findsNothing);
    expect(controller.hasPendingToolTurn, isFalse);
  });

  testWidgets('Arabic MCP status fits narrow high-text-scale layout', (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    controller.messages = [
      ChatMessage(
        id: 'assistant-arabic',
        conversationId: 'conversation-1',
        role: 'assistant',
        content: 'تعذر تأكيد النتيجة.',
        status: 'completed',
        createdAt: DateTime(2026, 8, 26, 12),
        toolActivities: const [
          ToolActivity(
            id: 'activity-arabic',
            connectionName: 'نظام إدارة علاقات العملاء المشترك',
            toolName: 'تحديث بيانات العميل في النظام الخارجي',
            status: 'outcome_unknown',
          ),
        ],
      ),
    ];

    await pumpChat(
      tester,
      locale: const Locale('ar'),
      size: const Size(320, 1000),
      textScale: 2,
    );

    expect(find.text('النتيجة غير معروفة'), findsOneWidget);
    expect(tester.takeException(), isNull);
    final node = tester.getSemantics(
      find.byKey(const ValueKey('tool-activity-activity-arabic')),
    );
    expect(node.flagsCollection.isLiveRegion, isTrue);
    semantics.dispose();
  });
}
