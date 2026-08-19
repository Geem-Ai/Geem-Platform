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
}
