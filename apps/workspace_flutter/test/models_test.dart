import 'package:flutter_test/flutter_test.dart';
import 'package:geem_workspace/src/models/models.dart';

void main() {
  test('conversation parses favorite and expert metadata', () {
    final conversation = Conversation.fromJson({
      'id': 'conversation-1',
      'workspace_id': 'workspace-1',
      'expert_id': 'expert-1',
      'title': 'Arabic policy',
      'is_pinned': true,
      'is_favorite': true,
      'updated_at': '2026-08-19T10:00:00Z',
      'expert': {
        'id': 'expert-1',
        'name': 'Geem General',
        'ownership': 'platform',
      },
    });

    expect(conversation.isFavorite, isTrue);
    expect(conversation.isPinned, isTrue);
    expect(conversation.expert?.name, 'Geem General');
  });

  test('workspace chat permission is derived from server permissions', () {
    final workspace = WorkspaceSummary.fromJson({
      'id': 'workspace-1',
      'name': 'Product',
      'slug': 'product',
      'status': 'active',
      'role': {'name': 'Member'},
      'permissions': ['chat.use', 'experts.view'],
    });

    expect(workspace.canChat, isTrue);
  });

  test('only backend-ready experts are available for chat', () {
    Expert expert(String status) => Expert.fromJson({
      'id': 'expert-1',
      'name': 'Geem General',
      'status': status,
      'ownership': 'platform',
      'knowledge_mode': 'general',
    });

    expect(expert('ready').isAvailable, isTrue);
    expect(expert('draft').isAvailable, isFalse);
    expect(expert('processing').isAvailable, isFalse);
  });

  test('message parses MCP tool citations, activity, and approval', () {
    final message = ChatMessage.fromJson({
      'id': 'message-1',
      'conversation_id': 'conversation-1',
      'role': 'assistant',
      'content': 'This tool call is awaiting your approval.',
      'status': 'pending',
      'created_at': '2026-08-26T12:00:00Z',
      'citations': [
        {
          'kind': 'tool',
          'connection_display_name': 'Customer CRM',
          'tool_name': 'update_customer',
        },
      ],
      'tool_activities': [
        {
          'id': 'invocation-1',
          'tool_call_id': 'call-1',
          'connection_name': 'Customer CRM',
          'tool_name': 'update_customer',
          'status': 'calling',
          'error_code': null,
        },
        {
          'id': 'approval-1',
          'tool_call_id': 'call-1',
          'connection_name': 'Customer CRM',
          'tool_name': 'update_customer',
          'status': 'approval_required',
        },
      ],
      'tool_approval': {
        'id': 'approval-1',
        'tool_call_id': 'call-1',
        'connection_name': 'Customer CRM',
        'tool_name': 'update_customer',
        'arguments': {'customer_id': 7, 'tier': 'gold'},
        'status': 'pending',
        'expires_at': '2026-08-26T12:05:00Z',
      },
    });

    final citation = message.citations.single;
    expect(citation.isTool, isTrue);
    expect(citation.connectionName, 'Customer CRM');
    expect(citation.toolName, 'update_customer');
    expect(citation.documentId, isNull);

    final activity = message.toolActivities.single;
    expect(activity.id, 'invocation-1');
    expect(activity.toolCallId, 'call-1');
    expect(activity.connectionName, 'Customer CRM');
    expect(activity.toolName, 'update_customer');
    expect(activity.status, 'calling');
    expect(activity.errorCode, isNull);

    final approval = message.toolApproval!;
    expect(approval.id, 'approval-1');
    expect(approval.toolCallId, 'call-1');
    expect(approval.connectionName, 'Customer CRM');
    expect(approval.toolName, 'update_customer');
    expect(approval.arguments, {'customer_id': 7, 'tier': 'gold'});
    expect(approval.status, 'pending');
    expect(approval.expiresAt, DateTime.parse('2026-08-26T12:05:00Z'));
    expect(approval.blocksComposer, isTrue);
  });
}
