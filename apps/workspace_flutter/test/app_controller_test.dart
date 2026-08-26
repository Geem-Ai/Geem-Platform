import 'dart:async';
import 'dart:convert';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geem_workspace/src/controllers/app_controller.dart';
import 'package:geem_workspace/src/models/models.dart';
import 'package:geem_workspace/src/services/api_exception.dart';
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

class _StreamingClient extends http.BaseClient {
  _StreamingClient(this.body);

  final Stream<List<int>> body;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async =>
      http.StreamedResponse(
        body,
        200,
        headers: const {'content-type': 'text/event-stream'},
      );
}

http.Response _tokenResponse() => http.Response(
  jsonEncode({
    'access_token': 'access-a',
    'expires_at': '2030-01-01T00:00:00Z',
    'user': {
      'id': 'user-1',
      'email': 'member@example.com',
      'status': 'active',
      'platform_role': 'user',
    },
  }),
  200,
  headers: {
    'set-cookie':
        'geem_refresh=refresh-a; Path=/api/auth; HttpOnly; SameSite=Lax',
  },
);

WorkspaceSummary _workspace() => const WorkspaceSummary(
  id: 'workspace-1',
  name: 'Product',
  slug: 'product',
  status: 'active',
  role: RoleSummary(name: 'Member'),
  permissions: ['chat.use'],
);

Conversation _conversation() => Conversation(
  id: 'conversation-1',
  workspaceId: 'workspace-1',
  expertId: 'expert-1',
  title: 'Existing chat',
  isPinned: false,
  isFavorite: false,
  updatedAt: DateTime(2026),
);

Map<String, Object?> _conversationJson() => {
  'id': 'conversation-1',
  'workspace_id': 'workspace-1',
  'expert_id': 'expert-1',
  'title': 'Existing chat',
  'is_pinned': false,
  'is_favorite': false,
  'updated_at': '2026-08-26T12:00:00Z',
};

Map<String, Object?> _toolMessageJson({
  required String approvalStatus,
  required String messageStatus,
}) => {
  'id': 'assistant-1',
  'conversation_id': 'conversation-1',
  'role': 'assistant',
  'content': messageStatus == 'completed'
      ? 'Customer updated.'
      : 'This tool call is awaiting your approval.',
  'status': messageStatus,
  'citations': [],
  'tool_approval': {
    'id': 'approval-1',
    'tool_call_id': 'call-1',
    'connection_name': 'CRM',
    'tool_name': 'update_customer',
    'arguments': {'customer_id': 7},
    'status': approvalStatus,
    'expires_at': '2026-08-26T12:05:00Z',
  },
  'created_at': '2026-08-26T12:00:00Z',
};

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

  test('expert selection accepts only ready experts on an idle new chat', () {
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
          ..experts = const [
            Expert(
              id: 'general',
              name: 'Geem General',
              status: 'ready',
              ownership: 'platform',
              knowledgeMode: 'general',
            ),
            Expert(
              id: 'research',
              name: 'Research',
              status: 'ready',
              ownership: 'workspace',
              knowledgeMode: 'rag',
            ),
            Expert(
              id: 'draft',
              name: 'Draft',
              status: 'draft',
              ownership: 'workspace',
              knowledgeMode: 'rag',
            ),
          ];
    addTearDown(controller.dispose);

    controller.selectedExpertId = 'general';
    controller.selectExpert('draft');
    expect(controller.selectedExpertId, 'general');

    controller.selectExpert('research');
    expect(controller.selectedExpertId, 'research');

    controller.sending = true;
    controller.selectExpert('general');
    expect(controller.selectedExpertId, 'research');

    controller.sending = false;
    controller.activeConversation = Conversation(
      id: 'conversation-1',
      workspaceId: 'workspace-1',
      expertId: 'research',
      title: 'Existing chat',
      isPinned: false,
      isFavorite: false,
      updatedAt: DateTime(2026),
    );
    controller.selectExpert('general');
    expect(controller.selectedExpertId, 'research');
  });

  test('new chat replaces a stale expert with Geem General', () async {
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
          ..experts = const [
            Expert(
              id: 'draft',
              name: 'Draft',
              status: 'draft',
              ownership: 'workspace',
              knowledgeMode: 'rag',
            ),
            Expert(
              id: 'general',
              name: 'Geem General',
              status: 'ready',
              ownership: 'platform',
              knowledgeMode: 'general',
            ),
          ]
          ..selectedExpertId = 'draft';
    addTearDown(controller.dispose);

    await controller.newChat();

    expect(controller.selectedExpertId, 'general');
  });

  test('tool approval event is terminal and reconciles a no-id tool call', () async {
    final credentials = _MemoryCredentialStore();
    final regularClient = MockClient((request) async {
      if (request.url.path == '/api/auth/login') return _tokenResponse();
      if (request.url.path == '/api/conversations') {
        return http.Response(jsonEncode([_conversationJson()]), 200);
      }
      return http.Response('Not found', 404);
    });
    final streamClient = MockClient((request) async {
      expect(
        request.url.path,
        '/api/conversations/conversation-1/messages/stream',
      );
      expect(request.headers['x-workspace-id'], 'workspace-1');
      return http.Response(
        'event: message_start\n'
        'data: {"user_message_id":"user-1","assistant_message_id":"assistant-1"}\n\n'
        'event: tool_call\n'
        'data: {"connection_name":"CRM","tool_name":"Update customer","status":"dispatching"}\n\n'
        'event: tool_approval_required\n'
        'data: {"approval_id":"approval-1","tool_call_id":"call-1","connection_name":"CRM","tool_name":"update_customer","arguments":{"customer_id":7,"tier":"gold"},"assistant_message_id":"assistant-1","status":"pending"}\n\n',
        200,
        headers: {'content-type': 'text/event-stream'},
      );
    });
    final api = GeemApiClient(
      baseUrl: 'https://api.example.test',
      credentials: credentials,
      client: regularClient,
      streamClientFactory: () => streamClient,
    )..workspaceId = 'workspace-1';
    await api.login('member@example.com', 'password');
    final conversation = _conversation();
    final controller =
        AppController(
            api: api,
            credentials: credentials,
            initialLocale: const Locale('en'),
          )
          ..sessionState = AppSessionState.authenticated
          ..currentWorkspace = _workspace()
          ..activeConversation = conversation
          ..conversations = [conversation];
    addTearDown(controller.dispose);

    await controller.sendMessage('Update the customer');

    final assistant = controller.messages.singleWhere(
      (message) => message.isAssistant,
    );
    expect(controller.errorCode, isNull);
    expect(assistant.status, 'pending');
    expect(assistant.toolActivities, hasLength(1));
    expect(assistant.toolActivities.single.id, 'call-1');
    expect(assistant.toolActivities.single.status, 'approval_required');
    expect(assistant.toolApproval?.id, 'approval-1');
    expect(assistant.toolApproval?.arguments, {
      'customer_id': 7,
      'tier': 'gold',
    });
    expect(controller.hasPendingToolTurn, isTrue);
  });

  test('tool result completes no-id activity and keeps its citation', () async {
    final credentials = _MemoryCredentialStore();
    final regularClient = MockClient((request) async {
      if (request.url.path == '/api/auth/login') return _tokenResponse();
      if (request.url.path == '/api/conversations') {
        return http.Response(jsonEncode([_conversationJson()]), 200);
      }
      return http.Response('Not found', 404);
    });
    final streamClient = MockClient((_) async {
      return http.Response(
        'event: message_start\n'
        'data: {"user_message_id":"user-1","assistant_message_id":"assistant-1"}\n\n'
        'event: tool_call\n'
        'data: {"connection_name":"CRM","tool_name":"Find customer","status":"dispatching"}\n\n'
        'event: tool_result\n'
        'data: {"connection_name":"CRM","tool_name":"Find customer","status":"completed"}\n\n'
        'event: replace\n'
        'data: {"text":"Customer found."}\n\n'
        'event: final\n'
        'data: {"answer":"Customer found.","assistant_message_id":"assistant-1","status":"completed","citations":[{"kind":"tool","connection_display_name":"CRM","tool_name":"find_customer"}]}\n\n',
        200,
        headers: {'content-type': 'text/event-stream'},
      );
    });
    final api = GeemApiClient(
      baseUrl: 'https://api.example.test',
      credentials: credentials,
      client: regularClient,
      streamClientFactory: () => streamClient,
    )..workspaceId = 'workspace-1';
    await api.login('member@example.com', 'password');
    final conversation = _conversation();
    final controller =
        AppController(
            api: api,
            credentials: credentials,
            initialLocale: const Locale('en'),
          )
          ..sessionState = AppSessionState.authenticated
          ..currentWorkspace = _workspace()
          ..activeConversation = conversation
          ..conversations = [conversation];
    addTearDown(controller.dispose);

    await controller.sendMessage('Find the customer');

    final assistant = controller.messages.singleWhere(
      (message) => message.isAssistant,
    );
    expect(assistant.content, 'Customer found.');
    expect(assistant.status, 'completed');
    expect(assistant.toolActivities, hasLength(1));
    expect(assistant.toolActivities.single.status, 'succeeded');
    expect(assistant.toolActivities.single.connectionName, 'CRM');
    expect(assistant.citations.single.isTool, isTrue);
    expect(assistant.citations.single.toolName, 'find_customer');
    expect(controller.hasPendingToolTurn, isFalse);
  });

  test('MCP SSE error resolves a calling activity as outcome unknown', () async {
    final credentials = _MemoryCredentialStore();
    final regularClient = MockClient((request) async {
      if (request.url.path == '/api/auth/login') return _tokenResponse();
      if (request.url.path == '/api/conversations') {
        return http.Response(jsonEncode([_conversationJson()]), 200);
      }
      return http.Response('Not found', 404);
    });
    final streamClient = MockClient(
      (_) async => http.Response(
        'event: message_start\n'
        'data: {"user_message_id":"user-1","assistant_message_id":"assistant-1"}\n\n'
        'event: tool_call\n'
        'data: {"connection_name":"CRM","tool_name":"Update customer"}\n\n'
        'event: error\n'
        'data: {"error":"mcp_tool_outcome_unknown","message":"The outcome could not be confirmed."}\n\n',
        200,
        headers: {'content-type': 'text/event-stream'},
      ),
    );
    final api = GeemApiClient(
      baseUrl: 'https://api.example.test',
      credentials: credentials,
      client: regularClient,
      streamClientFactory: () => streamClient,
    )..workspaceId = 'workspace-1';
    await api.login('member@example.com', 'password');
    final conversation = _conversation();
    final controller =
        AppController(
            api: api,
            credentials: credentials,
            initialLocale: const Locale('en'),
          )
          ..sessionState = AppSessionState.authenticated
          ..currentWorkspace = _workspace()
          ..activeConversation = conversation
          ..conversations = [conversation];
    addTearDown(controller.dispose);

    await controller.sendMessage('Update the customer');

    final assistant = controller.messages.singleWhere(
      (message) => message.isAssistant,
    );
    expect(assistant.status, 'failed');
    expect(assistant.toolActivities.single.status, 'outcome_unknown');
    expect(
      assistant.toolActivities.single.errorCode,
      'mcp_tool_outcome_unknown',
    );
    expect(controller.errorCode, 'mcp_tool_outcome_unknown');
  });

  test(
    'MCP transport error resolves a calling activity without jargon',
    () async {
      final credentials = _MemoryCredentialStore();
      final regularClient = MockClient((request) async {
        if (request.url.path == '/api/auth/login') return _tokenResponse();
        if (request.url.path == '/api/conversations') {
          return http.Response(jsonEncode([_conversationJson()]), 200);
        }
        return http.Response('Not found', 404);
      });
      Stream<List<int>> failingStream() async* {
        yield utf8.encode(
          'event: message_start\n'
          'data: {"user_message_id":"user-1","assistant_message_id":"assistant-1"}\n\n'
          'event: tool_call\n'
          'data: {"connection_name":"CRM","tool_name":"Update customer"}\n\n',
        );
        throw const ApiException(
          'Reconnect the MCP server.',
          status: 403,
          code: 'mcp_reauthorization_required',
        );
      }

      final api = GeemApiClient(
        baseUrl: 'https://api.example.test',
        credentials: credentials,
        client: regularClient,
        streamClientFactory: () => _StreamingClient(failingStream()),
      )..workspaceId = 'workspace-1';
      await api.login('member@example.com', 'password');
      final conversation = _conversation();
      final controller =
          AppController(
              api: api,
              credentials: credentials,
              initialLocale: const Locale('en'),
            )
            ..sessionState = AppSessionState.authenticated
            ..currentWorkspace = _workspace()
            ..activeConversation = conversation
            ..conversations = [conversation];
      addTearDown(controller.dispose);

      await controller.sendMessage('Update the customer');

      final assistant = controller.messages.singleWhere(
        (message) => message.isAssistant,
      );
      expect(assistant.status, 'failed');
      expect(assistant.errorMessage, 'Reconnect the MCP server.');
      expect(assistant.errorMessage, isNot(contains('ApiException(')));
      expect(assistant.toolActivities.single.status, 'failed');
      expect(
        assistant.toolActivities.single.errorCode,
        'mcp_reauthorization_required',
      );
    },
  );

  test('denying a tool approval refreshes history and unblocks chat', () async {
    final credentials = _MemoryCredentialStore();
    var approvalCalls = 0;
    final client = MockClient((request) async {
      if (request.url.path == '/api/auth/login') return _tokenResponse();
      if (request.url.path.endsWith('/tool-approvals/approval-1')) {
        approvalCalls += 1;
        expect(jsonDecode(request.body), {'decision': 'deny'});
        return http.Response('{"id":"approval-1","status":"denied"}', 200);
      }
      if (request.url.path.endsWith('/messages')) {
        return http.Response(
          jsonEncode([
            {
              'id': 'assistant-1',
              'conversation_id': 'conversation-1',
              'role': 'assistant',
              'content': 'This tool request was not approved.',
              'status': 'failed',
              'citations': [],
              'tool_approval': {
                'id': 'approval-1',
                'tool_call_id': 'call-1',
                'connection_name': 'CRM',
                'tool_name': 'update_customer',
                'arguments': {'customer_id': 7},
                'status': 'denied',
              },
              'created_at': '2026-08-26T12:00:00Z',
            },
          ]),
          200,
        );
      }
      return http.Response('Not found', 404);
    });
    final api = GeemApiClient(
      baseUrl: 'https://api.example.test',
      credentials: credentials,
      client: client,
    )..workspaceId = 'workspace-1';
    await api.login('member@example.com', 'password');
    final conversation = _conversation();
    final pending = ChatMessage(
      id: 'assistant-1',
      conversationId: conversation.id,
      role: 'assistant',
      content: 'This tool call is awaiting your approval.',
      status: 'pending',
      createdAt: DateTime(2026),
      toolApproval: const ToolApproval(
        id: 'approval-1',
        toolCallId: 'call-1',
        connectionName: 'CRM',
        toolName: 'update_customer',
        arguments: {'customer_id': 7},
        status: 'pending',
      ),
    );
    final controller =
        AppController(
            api: api,
            credentials: credentials,
            initialLocale: const Locale('en'),
          )
          ..sessionState = AppSessionState.authenticated
          ..currentWorkspace = _workspace()
          ..activeConversation = conversation
          ..conversations = [conversation]
          ..messages = [pending];
    addTearDown(controller.dispose);
    expect(controller.chatBusy, isTrue);

    await controller.decideToolApproval(pending, 'deny');

    expect(approvalCalls, 1);
    expect(controller.messages.single.toolApproval?.status, 'denied');
    expect(controller.hasPendingToolTurn, isFalse);
    expect(controller.chatBusy, isFalse);
  });

  test('executed approval blocks until its assistant message is terminal', () {
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
          ..messages = [
            ChatMessage(
              id: 'assistant-1',
              conversationId: 'conversation-1',
              role: 'assistant',
              content: 'This tool call is awaiting your approval.',
              status: 'pending',
              createdAt: DateTime(2026),
              toolApproval: const ToolApproval(
                id: 'approval-1',
                toolName: 'update_customer',
                status: 'executed',
              ),
            ),
          ];
    addTearDown(controller.dispose);

    expect(controller.hasPendingToolTurn, isTrue);
    expect(controller.chatBusy, isTrue);

    controller.messages = [
      controller.messages.single.copyWith(status: 'completed'),
    ];

    expect(controller.hasPendingToolTurn, isFalse);
    expect(controller.chatBusy, isFalse);
  });

  test(
    'history polling continues through executed until assistant completes',
    () async {
      final credentials = _MemoryCredentialStore();
      final finalFetched = Completer<void>();
      var messageCalls = 0;
      final client = MockClient((request) async {
        if (request.url.path == '/api/auth/login') return _tokenResponse();
        if (request.url.path.endsWith('/messages')) {
          messageCalls += 1;
          final payload = switch (messageCalls) {
            1 => _toolMessageJson(
              approvalStatus: 'pending',
              messageStatus: 'pending',
            ),
            2 => _toolMessageJson(
              approvalStatus: 'approved',
              messageStatus: 'pending',
            ),
            3 => _toolMessageJson(
              approvalStatus: 'executed',
              messageStatus: 'pending',
            ),
            _ => _toolMessageJson(
              approvalStatus: 'executed',
              messageStatus: 'completed',
            ),
          };
          if (messageCalls >= 4 && !finalFetched.isCompleted) {
            finalFetched.complete();
          }
          return http.Response(jsonEncode([payload]), 200);
        }
        return http.Response('Not found', 404);
      });
      final api = GeemApiClient(
        baseUrl: 'https://api.example.test',
        credentials: credentials,
        client: client,
      )..workspaceId = 'workspace-1';
      await api.login('member@example.com', 'password');
      final conversation = _conversation();
      final controller =
          AppController(
              api: api,
              credentials: credentials,
              initialLocale: const Locale('en'),
              toolApprovalPollDelays: const [Duration.zero],
            )
            ..sessionState = AppSessionState.authenticated
            ..currentWorkspace = _workspace()
            ..conversations = [conversation];
      addTearDown(controller.dispose);

      await controller.openConversation(conversation.id);
      await finalFetched.future.timeout(const Duration(seconds: 1));
      await Future<void>.delayed(Duration.zero);

      expect(messageCalls, 4);
      expect(controller.messages.single.status, 'completed');
      expect(controller.messages.single.toolApproval?.status, 'executed');
      expect(controller.hasPendingToolTurn, isFalse);
      expect(controller.chatBusy, isFalse);
    },
  );
}
