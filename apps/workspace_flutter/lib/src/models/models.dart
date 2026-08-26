typedef JsonMap = Map<String, dynamic>;

DateTime? _dateTime(Object? value) {
  if (value is! String || value.isEmpty) return null;
  return DateTime.tryParse(value);
}

List<JsonMap> _jsonMapList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) => Map<String, dynamic>.from(item))
      .toList();
}

class GeemUser {
  const GeemUser({
    required this.id,
    required this.email,
    required this.status,
    required this.platformRole,
    this.emailVerifiedAt,
  });

  factory GeemUser.fromJson(JsonMap json) => GeemUser(
    id: json['id'] as String? ?? '',
    email: json['email'] as String? ?? '',
    status: json['status'] as String? ?? '',
    platformRole: json['platform_role'] as String? ?? '',
    emailVerifiedAt: _dateTime(json['email_verified_at']),
  );

  final String id;
  final String email;
  final String status;
  final String platformRole;
  final DateTime? emailVerifiedAt;
}

class RoleSummary {
  const RoleSummary({required this.name, this.systemKey, this.isOwner = false});

  factory RoleSummary.fromJson(JsonMap json) => RoleSummary(
    name: json['name'] as String? ?? '',
    systemKey: json['system_key'] as String?,
    isOwner: json['is_owner_role'] as bool? ?? false,
  );

  final String name;
  final String? systemKey;
  final bool isOwner;
}

class WorkspaceSummary {
  const WorkspaceSummary({
    required this.id,
    required this.name,
    required this.slug,
    required this.status,
    required this.role,
    required this.permissions,
  });

  factory WorkspaceSummary.fromJson(JsonMap json) => WorkspaceSummary(
    id: json['id'] as String? ?? '',
    name: json['name'] as String? ?? '',
    slug: json['slug'] as String? ?? '',
    status: json['status'] as String? ?? '',
    role: RoleSummary.fromJson(
      Map<String, dynamic>.from(json['role'] as Map? ?? const {}),
    ),
    permissions: (json['permissions'] as List? ?? const [])
        .whereType<String>()
        .toList(growable: false),
  );

  final String id;
  final String name;
  final String slug;
  final String status;
  final RoleSummary role;
  final List<String> permissions;

  bool get canChat => permissions.contains('chat.use');
}

class AuthTokens {
  const AuthTokens({
    required this.accessToken,
    required this.expiresAt,
    required this.user,
  });

  factory AuthTokens.fromJson(JsonMap json) => AuthTokens(
    accessToken: json['access_token'] as String? ?? '',
    expiresAt: _dateTime(json['expires_at']) ?? DateTime.now(),
    user: GeemUser.fromJson(
      Map<String, dynamic>.from(json['user'] as Map? ?? const {}),
    ),
  );

  final String accessToken;
  final DateTime expiresAt;
  final GeemUser user;
}

class MeResponse {
  const MeResponse({required this.user, required this.workspaces});

  factory MeResponse.fromJson(JsonMap json) => MeResponse(
    user: GeemUser.fromJson(
      Map<String, dynamic>.from(json['user'] as Map? ?? const {}),
    ),
    workspaces: _jsonMapList(
      json['workspaces'],
    ).map(WorkspaceSummary.fromJson).toList(growable: false),
  );

  final GeemUser user;
  final List<WorkspaceSummary> workspaces;
}

class Expert {
  const Expert({
    required this.id,
    required this.name,
    required this.status,
    required this.ownership,
    required this.knowledgeMode,
    this.description,
    this.iconUrl,
  });

  factory Expert.fromJson(JsonMap json) => Expert(
    id: json['id'] as String? ?? '',
    name: json['name'] as String? ?? '',
    description: json['description'] as String?,
    iconUrl: json['icon_url'] as String?,
    status: json['status'] as String? ?? '',
    ownership: json['ownership'] as String? ?? '',
    knowledgeMode: json['knowledge_mode'] as String? ?? 'rag',
  );

  final String id;
  final String name;
  final String? description;
  final String? iconUrl;
  final String status;
  final String ownership;
  final String knowledgeMode;

  bool get isAvailable => status == 'ready';
  bool get isGeemGeneral =>
      ownership == 'platform' && knowledgeMode == 'general';
}

class ConversationExpert {
  const ConversationExpert({
    required this.id,
    required this.name,
    required this.ownership,
    this.iconUrl,
  });

  factory ConversationExpert.fromJson(JsonMap json) => ConversationExpert(
    id: json['id'] as String? ?? '',
    name: json['name'] as String? ?? '',
    ownership: json['ownership'] as String? ?? '',
    iconUrl: json['icon_url'] as String?,
  );

  final String id;
  final String name;
  final String ownership;
  final String? iconUrl;
}

class MessagePreview {
  const MessagePreview({required this.content, required this.createdAt});

  factory MessagePreview.fromJson(JsonMap json) => MessagePreview(
    content: json['content'] as String? ?? '',
    createdAt: _dateTime(json['created_at']),
  );

  final String content;
  final DateTime? createdAt;
}

class Conversation {
  const Conversation({
    required this.id,
    required this.workspaceId,
    required this.expertId,
    required this.isPinned,
    required this.isFavorite,
    required this.updatedAt,
    this.title,
    this.expert,
    this.lastMessage,
  });

  factory Conversation.fromJson(JsonMap json) => Conversation(
    id: json['id'] as String? ?? '',
    workspaceId: json['workspace_id'] as String? ?? '',
    expertId: json['expert_id'] as String? ?? '',
    title: json['title'] as String?,
    isPinned: json['is_pinned'] as bool? ?? false,
    isFavorite: json['is_favorite'] as bool? ?? false,
    updatedAt: _dateTime(json['updated_at']) ?? DateTime.now(),
    expert: json['expert'] is Map
        ? ConversationExpert.fromJson(
            Map<String, dynamic>.from(json['expert'] as Map),
          )
        : null,
    lastMessage: json['last_message'] is Map
        ? MessagePreview.fromJson(
            Map<String, dynamic>.from(json['last_message'] as Map),
          )
        : null,
  );

  final String id;
  final String workspaceId;
  final String expertId;
  final String? title;
  final bool isPinned;
  final bool isFavorite;
  final DateTime updatedAt;
  final ConversationExpert? expert;
  final MessagePreview? lastMessage;

  Conversation copyWith({
    String? title,
    bool? isPinned,
    bool? isFavorite,
    DateTime? updatedAt,
  }) => Conversation(
    id: id,
    workspaceId: workspaceId,
    expertId: expertId,
    title: title ?? this.title,
    isPinned: isPinned ?? this.isPinned,
    isFavorite: isFavorite ?? this.isFavorite,
    updatedAt: updatedAt ?? this.updatedAt,
    expert: expert,
    lastMessage: lastMessage,
  );
}

class Citation {
  const Citation({
    this.kind = 'chunk',
    this.chunkId,
    this.documentId,
    this.documentTitle,
    this.page,
    this.snippet,
    this.toolCallId,
    this.connectionName,
    this.toolName,
    this.toolTitle,
  });

  factory Citation.fromJson(JsonMap json) => Citation(
    kind: json['kind'] as String? ?? 'chunk',
    chunkId: json['chunk_id'] as String?,
    documentId: json['document_id'] as String?,
    documentTitle: json['document_title'] as String?,
    page: (json['page'] as num?)?.toInt(),
    snippet: json['snippet'] as String?,
    toolCallId: json['tool_call_id'] as String?,
    connectionName:
        (json['connection_display_name'] as String?) ??
        (json['connection_name'] as String?),
    toolName: json['tool_name'] as String?,
    toolTitle: json['tool_title'] as String?,
  );

  final String kind;
  final String? chunkId;
  final String? documentId;
  final String? documentTitle;
  final int? page;
  final String? snippet;
  final String? toolCallId;
  final String? connectionName;
  final String? toolName;
  final String? toolTitle;

  bool get isTool => kind == 'tool';
}

class ToolActivity {
  const ToolActivity({
    required this.id,
    required this.toolName,
    required this.status,
    this.toolCallId,
    this.connectionName,
    this.errorCode,
  });

  factory ToolActivity.fromJson(JsonMap json) => ToolActivity(
    id: json['id'] as String? ?? '',
    toolCallId: json['tool_call_id'] as String?,
    connectionName:
        (json['connection_display_name'] as String?) ??
        (json['connection_name'] as String?),
    toolName: json['tool_name'] as String? ?? '',
    status: json['status'] as String? ?? '',
    errorCode: json['error_code'] as String?,
  );

  final String id;
  final String? toolCallId;
  final String? connectionName;
  final String toolName;
  final String status;
  final String? errorCode;

  ToolActivity copyWith({
    String? id,
    String? toolCallId,
    String? connectionName,
    String? toolName,
    String? status,
    String? errorCode,
  }) => ToolActivity(
    id: id ?? this.id,
    toolCallId: toolCallId ?? this.toolCallId,
    connectionName: connectionName ?? this.connectionName,
    toolName: toolName ?? this.toolName,
    status: status ?? this.status,
    errorCode: errorCode ?? this.errorCode,
  );
}

List<ToolActivity> _toolActivities(Object? value) {
  final activities = <ToolActivity>[];
  final indexByToolCall = <String, int>{};
  for (final json in _jsonMapList(value)) {
    final activity = ToolActivity.fromJson(json);
    final toolCallId = activity.toolCallId;
    if (toolCallId == null || toolCallId.isEmpty) {
      activities.add(activity);
      continue;
    }
    final existingIndex = indexByToolCall[toolCallId];
    if (existingIndex == null) {
      indexByToolCall[toolCallId] = activities.length;
      activities.add(activity);
      continue;
    }
    final existing = activities[existingIndex];
    if (existing.status == 'approval_required' &&
        activity.status != 'approval_required') {
      activities[existingIndex] = activity;
    }
  }
  return activities.toList(growable: false);
}

class ToolApproval {
  const ToolApproval({
    required this.id,
    required this.toolName,
    required this.status,
    this.toolCallId,
    this.connectionName,
    this.arguments,
    this.expiresAt,
  });

  factory ToolApproval.fromJson(JsonMap json) => ToolApproval(
    id: json['id'] as String? ?? '',
    toolCallId: json['tool_call_id'] as String?,
    connectionName:
        (json['connection_display_name'] as String?) ??
        (json['connection_name'] as String?),
    toolName: json['tool_name'] as String? ?? '',
    arguments: json['arguments'],
    status: json['status'] as String? ?? '',
    expiresAt: _dateTime(json['expires_at']),
  );

  final String id;
  final String? toolCallId;
  final String? connectionName;
  final String toolName;
  final Object? arguments;
  final String status;
  final DateTime? expiresAt;

  bool get blocksComposer =>
      status == 'pending' || status == 'approved' || status == 'executing';

  ToolApproval copyWith({String? status}) => ToolApproval(
    id: id,
    toolCallId: toolCallId,
    connectionName: connectionName,
    toolName: toolName,
    arguments: arguments,
    status: status ?? this.status,
    expiresAt: expiresAt,
  );
}

class MessageAttachment {
  const MessageAttachment({
    required this.id,
    required this.filename,
    required this.mimeType,
    required this.byteSize,
  });

  factory MessageAttachment.fromJson(JsonMap json) => MessageAttachment(
    id: json['id'] as String? ?? '',
    filename: json['filename'] as String? ?? '',
    mimeType: json['mime_type'] as String? ?? '',
    byteSize: (json['byte_size'] as num?)?.toInt() ?? 0,
  );

  final String id;
  final String filename;
  final String mimeType;
  final int byteSize;
}

class ChatMessage {
  const ChatMessage({
    required this.id,
    required this.conversationId,
    required this.role,
    required this.content,
    required this.status,
    required this.createdAt,
    this.citations = const [],
    this.attachments = const [],
    this.toolActivities = const [],
    this.toolApproval,
    this.errorMessage,
  });

  factory ChatMessage.fromJson(JsonMap json) => ChatMessage(
    id: json['id'] as String? ?? '',
    conversationId: json['conversation_id'] as String? ?? '',
    role: json['role'] as String? ?? '',
    content: json['content'] as String? ?? '',
    status: json['status'] as String? ?? 'completed',
    createdAt: _dateTime(json['created_at']) ?? DateTime.now(),
    citations: _jsonMapList(
      json['citations'],
    ).map(Citation.fromJson).toList(growable: false),
    attachments: _jsonMapList(
      json['attachments'],
    ).map(MessageAttachment.fromJson).toList(growable: false),
    toolActivities: _toolActivities(json['tool_activities']),
    toolApproval: json['tool_approval'] is Map
        ? ToolApproval.fromJson(
            Map<String, dynamic>.from(json['tool_approval'] as Map),
          )
        : null,
  );

  factory ChatMessage.optimistic({
    required String id,
    required String conversationId,
    required String role,
    required String content,
    required String status,
  }) => ChatMessage(
    id: id,
    conversationId: conversationId,
    role: role,
    content: content,
    status: status,
    createdAt: DateTime.now(),
  );

  final String id;
  final String conversationId;
  final String role;
  final String content;
  final String status;
  final DateTime createdAt;
  final List<Citation> citations;
  final List<MessageAttachment> attachments;
  final List<ToolActivity> toolActivities;
  final ToolApproval? toolApproval;
  final String? errorMessage;

  bool get isAssistant => role == 'assistant';
  bool get isFailed => status == 'failed' || status == 'cancelled';

  ChatMessage copyWith({
    String? id,
    String? content,
    String? status,
    List<Citation>? citations,
    List<ToolActivity>? toolActivities,
    ToolApproval? toolApproval,
    bool clearToolApproval = false,
    String? errorMessage,
    bool clearError = false,
  }) => ChatMessage(
    id: id ?? this.id,
    conversationId: conversationId,
    role: role,
    content: content ?? this.content,
    status: status ?? this.status,
    createdAt: createdAt,
    citations: citations ?? this.citations,
    attachments: attachments,
    toolActivities: toolActivities ?? this.toolActivities,
    toolApproval: clearToolApproval ? null : toolApproval ?? this.toolApproval,
    errorMessage: clearError ? null : errorMessage ?? this.errorMessage,
  );
}
