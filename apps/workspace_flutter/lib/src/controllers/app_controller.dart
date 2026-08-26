import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';

import '../models/models.dart';
import '../services/api_exception.dart';
import '../services/credential_store.dart';
import '../services/geem_api_client.dart';
import '../services/sse_parser.dart';

enum AppSessionState { bootstrapping, unauthenticated, authenticated }

enum AuthPage { login, forgotPassword, checkEmail, verifyEmail, resetPassword }

class AppController extends ChangeNotifier {
  factory AppController({
    required GeemApiClient api,
    required CredentialStore credentials,
    Locale initialLocale = const Locale('ar'),
    @visibleForTesting List<Duration>? toolApprovalPollDelays,
  }) =>
      AppController._(api, credentials, initialLocale, toolApprovalPollDelays);

  AppController._(
    this._api,
    this._credentials,
    Locale initialLocale,
    List<Duration>? toolApprovalPollDelays,
  ) : _toolApprovalPollDelays =
          toolApprovalPollDelays == null || toolApprovalPollDelays.isEmpty
          ? _defaultToolApprovalPollDelays
          : List.unmodifiable(toolApprovalPollDelays),
      locale = initialLocale.languageCode == 'ar'
          ? const Locale('ar')
          : const Locale('en');

  static const _defaultToolApprovalPollDelays = [
    Duration(milliseconds: 1500),
    Duration(milliseconds: 2500),
    Duration(seconds: 4),
    Duration(seconds: 6),
    Duration(seconds: 10),
    Duration(seconds: 15),
    Duration(seconds: 30),
  ];

  final GeemApiClient _api;
  final CredentialStore _credentials;
  final List<Duration> _toolApprovalPollDelays;

  AppSessionState sessionState = AppSessionState.bootstrapping;
  AuthPage authPage = AuthPage.login;
  Locale locale;
  GeemUser? user;
  List<WorkspaceSummary> workspaces = const [];
  WorkspaceSummary? currentWorkspace;
  List<Expert> experts = const [];
  List<Conversation> conversations = const [];
  List<ChatMessage> messages = const [];
  Conversation? activeConversation;
  String? selectedExpertId;

  bool authBusy = false;
  bool workspaceLoading = false;
  bool conversationLoading = false;
  bool sending = false;
  bool streaming = false;
  bool forgotSubmitted = false;
  bool verificationResent = false;
  String pendingVerificationEmail = '';
  String resetToken = '';
  String? errorCode;
  String? errorMessage;
  String? noticeMessage;
  String? streamStage;
  String? decidingToolApprovalId;

  StreamSubscription<SseEvent>? _streamSubscription;
  Completer<void>? _streamCompleter;
  String? _streamAssistantId;
  String? _streamUserId;
  int _clientSequence = 0;
  int _streamGeneration = 0;
  int _contextGeneration = 0;
  int _streamToolSequence = 0;
  int _toolApprovalPollToken = 0;
  int? _toolApprovalPollContextGeneration;
  String? _toolApprovalPollConversationId;
  Timer? _toolApprovalPollTimer;
  Completer<void>? _toolApprovalPollDelayCompleter;
  bool _invalidatingSession = false;
  bool _disposed = false;

  List<Conversation> get favoriteConversations =>
      conversations.where((item) => item.isFavorite).toList(growable: false);

  List<Conversation> get pinnedConversations =>
      conversations.where((item) => item.isPinned).toList(growable: false);

  List<Conversation> get recentConversations =>
      conversations.where((item) => !item.isPinned).toList(growable: false);

  Expert? get selectedExpert {
    final id = selectedExpertId;
    if (id == null) return null;
    return experts.cast<Expert?>().firstWhere(
      (item) => item?.id == id,
      orElse: () => null,
    );
  }

  String get userInitials {
    final email = user?.email ?? '';
    final localPart = email.split('@').first;
    if (localPart.isEmpty) return 'U';
    final end = localPart.length < 2 ? localPart.length : 2;
    return localPart.substring(0, end).toUpperCase();
  }

  bool get canUseCurrentWorkspace => currentWorkspace?.canChat ?? false;
  bool get hasPendingToolTurn => messages.any(_messageHasPendingToolTurn);
  bool get toolApprovalBusy => decidingToolApprovalId != null;
  bool get chatBusy =>
      sending || streaming || toolApprovalBusy || hasPendingToolTurn;

  Future<void> initialize() async {
    try {
      final storedLocale = await _credentials.readLocale();
      if (storedLocale == 'ar' || storedLocale == 'en') {
        locale = Locale(storedLocale!);
        _notify();
      }
      await _api.refreshSession();
      await _loadIdentityAndWorkspace();
    } on ApiException catch (error) {
      if (error.isTerminalSession) {
        try {
          await _api.forgetSession();
        } catch (_) {
          // The app can still present login if secure storage is unavailable.
        }
      } else {
        _setError(error);
      }
      sessionState = AppSessionState.unauthenticated;
      authPage = AuthPage.login;
      _notify();
    } catch (error) {
      _setUnknownError(error);
      sessionState = AppSessionState.unauthenticated;
      authPage = AuthPage.login;
      _notify();
    }
  }

  Future<void> toggleLocale() async {
    locale = locale.languageCode == 'ar'
        ? const Locale('en')
        : const Locale('ar');
    _notify();
    await _credentials.writeLocale(locale.languageCode);
  }

  void showLogin() {
    _clearFeedback();
    forgotSubmitted = false;
    verificationResent = false;
    authPage = AuthPage.login;
    _notify();
  }

  void showForgotPassword() {
    _clearFeedback();
    forgotSubmitted = false;
    authPage = AuthPage.forgotPassword;
    _notify();
  }

  void showCheckEmail([String? email]) {
    _clearFeedback();
    verificationResent = false;
    if (email != null) pendingVerificationEmail = email.trim();
    authPage = AuthPage.checkEmail;
    _notify();
  }

  void showResetPassword([String? tokenOrLink]) {
    _clearFeedback();
    resetToken = tokenOrLink == null ? '' : tokenFromInput(tokenOrLink);
    authPage = AuthPage.resetPassword;
    _notify();
  }

  Future<void> login(String email, String password) async {
    if (authBusy) return;
    authBusy = true;
    _clearFeedback();
    _notify();
    try {
      await _api.login(email.trim(), password);
      await _loadIdentityAndWorkspace();
    } on ApiException catch (error) {
      if (error.code == 'email_not_verified') {
        pendingVerificationEmail = email.trim();
        authPage = AuthPage.checkEmail;
      } else {
        _setError(error);
      }
    } catch (error) {
      _setUnknownError(error);
    } finally {
      authBusy = false;
      _notify();
    }
  }

  Future<void> requestPasswordReset(String email) async {
    if (authBusy) return;
    authBusy = true;
    _clearFeedback();
    _notify();
    try {
      await _api.forgotPassword(email.trim());
      forgotSubmitted = true;
      pendingVerificationEmail = email.trim();
    } on ApiException catch (error) {
      _setError(error);
    } catch (error) {
      _setUnknownError(error);
    } finally {
      authBusy = false;
      _notify();
    }
  }

  Future<void> resendVerification(String email) async {
    if (authBusy) return;
    final normalized = email.trim();
    authBusy = true;
    verificationResent = false;
    _clearFeedback();
    _notify();
    try {
      await _api.resendVerification(normalized);
      pendingVerificationEmail = normalized;
      verificationResent = true;
    } on ApiException catch (error) {
      _setError(error);
    } catch (error) {
      _setUnknownError(error);
    } finally {
      authBusy = false;
      _notify();
    }
  }

  Future<void> verifyEmailFromInput(String tokenOrLink) async {
    final token = tokenFromInput(tokenOrLink);
    if (token.isEmpty) {
      errorCode = 'invalid_verification_token';
      errorMessage = 'The verification link is invalid.';
      _notify();
      return;
    }
    await _verifyEmail(token);
  }

  Future<void> _verifyEmail(String token) async {
    if (authBusy) return;
    await _prepareForExternalAuth();
    sessionState = AppSessionState.unauthenticated;
    authPage = AuthPage.verifyEmail;
    authBusy = true;
    _clearFeedback();
    _notify();
    try {
      await _api.verifyEmail(token);
      await _loadIdentityAndWorkspace();
    } on ApiException catch (error) {
      _setError(error);
    } catch (error) {
      _setUnknownError(error);
    } finally {
      authBusy = false;
      _notify();
    }
  }

  Future<void> completePasswordReset(
    String tokenOrLink,
    String password,
  ) async {
    if (authBusy) return;
    final token = tokenFromInput(
      tokenOrLink.isEmpty ? resetToken : tokenOrLink,
    );
    if (token.isEmpty) {
      errorCode = 'invalid_reset_token';
      errorMessage = 'The password reset link is invalid.';
      _notify();
      return;
    }
    authBusy = true;
    _clearFeedback();
    _notify();
    try {
      await _api.resetPassword(token, password);
      resetToken = '';
      await _loadIdentityAndWorkspace();
    } on ApiException catch (error) {
      _setError(error);
    } catch (error) {
      _setUnknownError(error);
    } finally {
      authBusy = false;
      _notify();
    }
  }

  Future<void> handleDeepLink(Uri uri) async {
    if (!_isTrustedAuthLink(uri)) return;
    final path = uri.path.toLowerCase();
    final token = uri.queryParameters['token']?.trim() ?? '';
    if (path == '/verify-email' && token.isNotEmpty) {
      await _verifyEmail(token);
      return;
    }
    if (path == '/reset-password' && token.isNotEmpty) {
      await _prepareForExternalAuth();
      sessionState = AppSessionState.unauthenticated;
      authPage = AuthPage.resetPassword;
      resetToken = token;
      _clearFeedback();
      _notify();
    }
  }

  bool _isTrustedAuthLink(Uri uri) {
    final scheme = uri.scheme.toLowerCase();
    final host = uri.host.toLowerCase();
    if (scheme == 'geem') return host == 'auth';
    return scheme == 'https' &&
        (host == 'hub.geem.ai' || host == 'app-uat.geem.ai');
  }

  Future<void> _prepareForExternalAuth() async {
    await stopStreaming();
    await _api.forgetSession();
    _contextGeneration += 1;
    _clearIdentityAndWorkspace();
  }

  String tokenFromInput(String value) {
    final trimmed = value.trim();
    final uri = Uri.tryParse(trimmed);
    final token = uri?.queryParameters['token'];
    return token?.trim().isNotEmpty == true ? token!.trim() : trimmed;
  }

  Future<void> _loadIdentityAndWorkspace() async {
    final me = await _api.getMe();
    await stopStreaming();
    _contextGeneration += 1;
    final identityGeneration = _contextGeneration;
    _clearIdentityAndWorkspace();
    user = me.user;
    workspaces = me.workspaces;
    _clearFeedback();

    final savedId = await _credentials.readWorkspaceId(me.user.id);
    if (identityGeneration != _contextGeneration) return;
    WorkspaceSummary? selected;
    if (savedId != null) {
      selected = _workspaceById(savedId);
    }
    selected ??= workspaces.cast<WorkspaceSummary?>().firstWhere(
      (item) => item?.canChat == true,
      orElse: () => workspaces.isEmpty ? null : workspaces.first,
    );

    currentWorkspace = selected;
    _api.workspaceId = selected?.id;

    if (selected != null) {
      await _credentials.writeWorkspaceId(me.user.id, selected.id);
      if (identityGeneration != _contextGeneration) return;
      await _loadWorkspaceData();
    } else {
      experts = const [];
      conversations = const [];
      activeConversation = null;
      messages = const [];
    }
    if (identityGeneration != _contextGeneration || user?.id != me.user.id) {
      return;
    }
    sessionState = AppSessionState.authenticated;
    authPage = AuthPage.login;
    _notify();
  }

  Future<void> selectWorkspace(String workspaceId) async {
    final next = _workspaceById(workspaceId);
    if (next == null || next.id == currentWorkspace?.id) return;
    await stopStreaming();
    _contextGeneration += 1;
    final generation = _contextGeneration;
    currentWorkspace = next;
    _api.workspaceId = next.id;
    activeConversation = null;
    messages = const [];
    experts = const [];
    conversations = const [];
    selectedExpertId = null;
    sending = false;
    _clearFeedback();
    _notify();
    final currentUser = user;
    if (currentUser != null) {
      await _credentials.writeWorkspaceId(currentUser.id, next.id);
    }
    if (!_isCurrentContext(generation, next.id)) return;
    await _loadWorkspaceData();
  }

  Future<void> _loadWorkspaceData() async {
    final workspace = currentWorkspace;
    final generation = _contextGeneration;
    if (workspace == null || !workspace.canChat) {
      experts = const [];
      conversations = const [];
      selectedExpertId = null;
      _notify();
      return;
    }

    workspaceLoading = true;
    _clearFeedback();
    _notify();
    var loadedExperts = <Expert>[];
    var loadedConversations = <Conversation>[];
    try {
      await Future.wait<void>([
        _api.listExperts().then((value) => loadedExperts = value),
        _api.listConversations().then((value) => loadedConversations = value),
      ]);
      if (!_isCurrentContext(generation, workspace.id)) return;
      experts = loadedExperts;
      conversations = loadedConversations;
      _ensureSelectedExpert();
    } on ApiException catch (error) {
      if (_isCurrentContext(generation, workspace.id)) _setError(error);
    } catch (error) {
      if (_isCurrentContext(generation, workspace.id)) {
        _setUnknownError(error);
      }
    } finally {
      if (_isCurrentContext(generation, workspace.id)) {
        workspaceLoading = false;
        _notify();
      }
    }
  }

  Future<void> reloadWorkspace() async {
    if (workspaceLoading) return;
    await _loadWorkspaceData();
  }

  void selectExpert(String expertId) {
    if (activeConversation != null || chatBusy) return;
    if (!experts.any((item) => item.id == expertId && item.isAvailable)) {
      return;
    }
    selectedExpertId = expertId;
    _notify();
  }

  Future<void> newChat() async {
    await stopStreaming();
    _contextGeneration += 1;
    activeConversation = null;
    messages = const [];
    conversationLoading = false;
    sending = false;
    _clearFeedback();
    _ensureSelectedExpert();
    _notify();
  }

  Future<void> openConversation(String conversationId) async {
    if (activeConversation?.id == conversationId && messages.isNotEmpty) {
      _startToolApprovalPolling();
      return;
    }
    await stopStreaming();
    final conversation = conversations.cast<Conversation?>().firstWhere(
      (item) => item?.id == conversationId,
      orElse: () => null,
    );
    if (conversation == null ||
        conversation.workspaceId != currentWorkspace?.id) {
      return;
    }
    final generation = ++_contextGeneration;
    final workspaceId = currentWorkspace!.id;
    activeConversation = conversation;
    messages = const [];
    conversationLoading = true;
    _clearFeedback();
    _notify();
    try {
      final loaded = await _api.listMessages(conversationId);
      if (_isCurrentContext(generation, workspaceId) &&
          activeConversation?.id == conversationId) {
        messages = loaded;
        _startToolApprovalPolling();
      }
    } on ApiException catch (error) {
      if (_isCurrentContext(generation, workspaceId)) _setError(error);
    } catch (error) {
      if (_isCurrentContext(generation, workspaceId)) {
        _setUnknownError(error);
      }
    } finally {
      if (_isCurrentContext(generation, workspaceId)) {
        conversationLoading = false;
        _notify();
      }
    }
  }

  Future<void> toggleFavorite(Conversation conversation) async {
    final workspaceId = currentWorkspace?.id;
    if (workspaceId == null || conversation.workspaceId != workspaceId) return;
    final generation = _contextGeneration;
    final optimistic = conversation.copyWith(
      isFavorite: !conversation.isFavorite,
      updatedAt: DateTime.now(),
    );
    _replaceConversation(optimistic);
    _notify();
    try {
      final updated = await _api.updateConversation(
        conversation.id,
        isFavorite: !conversation.isFavorite,
      );
      if (_isCurrentContext(generation, workspaceId)) {
        _replaceConversation(updated, insertIfMissing: false);
      }
    } on ApiException catch (error) {
      if (_isCurrentContext(generation, workspaceId)) {
        _replaceConversation(conversation, insertIfMissing: false);
        _setError(error);
      }
    } catch (error) {
      if (_isCurrentContext(generation, workspaceId)) {
        _replaceConversation(conversation, insertIfMissing: false);
        _setUnknownError(error);
      }
    }
    if (_isCurrentContext(generation, workspaceId)) _notify();
  }

  Future<void> togglePinned(Conversation conversation) async {
    final workspaceId = currentWorkspace?.id;
    if (workspaceId == null || conversation.workspaceId != workspaceId) return;
    final generation = _contextGeneration;
    final optimistic = conversation.copyWith(
      isPinned: !conversation.isPinned,
      updatedAt: DateTime.now(),
    );
    _replaceConversation(optimistic);
    _notify();
    try {
      final updated = await _api.updateConversation(
        conversation.id,
        isPinned: !conversation.isPinned,
      );
      if (_isCurrentContext(generation, workspaceId)) {
        _replaceConversation(updated, insertIfMissing: false);
      }
    } on ApiException catch (error) {
      if (_isCurrentContext(generation, workspaceId)) {
        _replaceConversation(conversation, insertIfMissing: false);
        _setError(error);
      }
    } catch (error) {
      if (_isCurrentContext(generation, workspaceId)) {
        _replaceConversation(conversation, insertIfMissing: false);
        _setUnknownError(error);
      }
    }
    if (_isCurrentContext(generation, workspaceId)) _notify();
  }

  Future<void> renameConversation(
    Conversation conversation,
    String title,
  ) async {
    final normalized = title.trim();
    final workspaceId = currentWorkspace?.id;
    if (normalized.isEmpty ||
        workspaceId == null ||
        conversation.workspaceId != workspaceId) {
      return;
    }
    final generation = _contextGeneration;
    try {
      final updated = await _api.updateConversation(
        conversation.id,
        title: normalized,
      );
      if (_isCurrentContext(generation, workspaceId)) {
        _replaceConversation(updated, insertIfMissing: false);
      }
    } on ApiException catch (error) {
      if (_isCurrentContext(generation, workspaceId)) _setError(error);
    } catch (error) {
      if (_isCurrentContext(generation, workspaceId)) {
        _setUnknownError(error);
      }
    }
    if (_isCurrentContext(generation, workspaceId)) _notify();
  }

  Future<void> deleteConversation(Conversation conversation) async {
    final workspaceId = currentWorkspace?.id;
    if (workspaceId == null || conversation.workspaceId != workspaceId) return;
    final generation = _contextGeneration;
    try {
      await _api.deleteConversation(conversation.id);
      if (!_isCurrentContext(generation, workspaceId)) return;
      conversations = conversations
          .where((item) => item.id != conversation.id)
          .toList(growable: false);
      if (activeConversation?.id == conversation.id) {
        activeConversation = null;
        messages = const [];
      }
    } on ApiException catch (error) {
      if (_isCurrentContext(generation, workspaceId)) _setError(error);
    } catch (error) {
      if (_isCurrentContext(generation, workspaceId)) {
        _setUnknownError(error);
      }
    }
    if (_isCurrentContext(generation, workspaceId)) _notify();
  }

  Future<void> sendMessage(String content) async {
    final normalized = content.trim();
    final workspaceId = currentWorkspace?.id;
    if (normalized.isEmpty ||
        chatBusy ||
        !canUseCurrentWorkspace ||
        workspaceId == null) {
      return;
    }
    final newChatExpert = activeConversation == null ? selectedExpert : null;
    if (activeConversation == null && newChatExpert?.isAvailable != true) {
      errorCode = 'expert_required';
      _notify();
      return;
    }
    final generation = _contextGeneration;
    sending = true;
    _clearFeedback();
    _notify();

    var conversation = activeConversation;
    final wasUntitled = conversation?.title?.trim().isEmpty ?? true;
    try {
      if (conversation == null) {
        final expertId = newChatExpert!.id;
        conversation = await _api.createConversation(expertId);
        if (!_isCurrentContext(generation, workspaceId)) return;
        final provisional = conversation.copyWith(
          title: _provisionalTitle(normalized),
        );
        activeConversation = provisional;
        conversations = [
          provisional,
          ...conversations.where((item) => item.id != provisional.id),
        ];
      }
      if (!_isCurrentContext(generation, workspaceId)) return;

      final userClientId = _clientId('user');
      final assistantClientId = _clientId('assistant');
      messages = [
        ...messages,
        ChatMessage.optimistic(
          id: userClientId,
          conversationId: conversation.id,
          role: 'user',
          content: normalized,
          status: 'pending',
        ),
        ChatMessage.optimistic(
          id: assistantClientId,
          conversationId: conversation.id,
          role: 'assistant',
          content: '',
          status: 'streaming',
        ),
      ];
      _notify();

      await _runStream(
        _api.streamMessage(conversation.id, normalized),
        userMessageId: userClientId,
        assistantMessageId: assistantClientId,
      );

      if (!_isCurrentContext(generation, workspaceId)) return;
      await _refreshConversationList();
      if (wasUntitled) unawaited(_pollForTitle(conversation.id));
    } on ApiException catch (error) {
      if (_isCurrentContext(generation, workspaceId)) {
        _setError(error);
        _markCurrentAssistantFailed(error.message);
      }
    } catch (error) {
      if (_isCurrentContext(generation, workspaceId)) {
        _setUnknownError(error);
        _markCurrentAssistantFailed(error.toString());
      }
    } finally {
      if (_isCurrentContext(generation, workspaceId)) {
        sending = false;
        streaming = false;
        streamStage = null;
        _notify();
      }
    }
  }

  Future<void> retryMessage(ChatMessage message) async {
    final conversation = activeConversation;
    final workspaceId = currentWorkspace?.id;
    if (conversation == null ||
        workspaceId == null ||
        streaming ||
        sending ||
        toolApprovalBusy ||
        hasPendingToolTurn ||
        !message.isAssistant ||
        message.id.startsWith('client-')) {
      return;
    }
    final generation = _contextGeneration;
    _replaceMessage(
      message.id,
      message.copyWith(
        content: '',
        status: 'streaming',
        citations: const [],
        toolActivities: const [],
        clearToolApproval: true,
        clearError: true,
      ),
    );
    _notify();
    try {
      await _runStream(
        _api.retryMessage(conversation.id, message.id),
        userMessageId: '',
        assistantMessageId: message.id,
      );
      if (!_isCurrentContext(generation, workspaceId)) return;
      await _refreshConversationList();
    } on ApiException catch (error) {
      if (_isCurrentContext(generation, workspaceId)) {
        _setError(error);
        _markCurrentAssistantFailed(error.message);
      }
    } catch (error) {
      if (_isCurrentContext(generation, workspaceId)) {
        _setUnknownError(error);
        _markCurrentAssistantFailed(error.toString());
      }
    } finally {
      if (_isCurrentContext(generation, workspaceId)) {
        streaming = false;
        streamStage = null;
        _notify();
      }
    }
  }

  Future<void> decideToolApproval(ChatMessage message, String decision) async {
    final conversation = activeConversation;
    final workspaceId = currentWorkspace?.id;
    final approval = message.toolApproval;
    if (conversation == null ||
        workspaceId == null ||
        approval == null ||
        approval.status != 'pending' ||
        toolApprovalBusy ||
        (decision != 'approve' && decision != 'deny') ||
        message.conversationId != conversation.id) {
      return;
    }

    final generation = _contextGeneration;
    decidingToolApprovalId = approval.id;
    _clearFeedback();
    _replaceMessage(
      message.id,
      message.copyWith(
        toolApproval: approval.copyWith(
          status: decision == 'approve' ? 'approved' : 'denied',
        ),
      ),
    );
    _notify();
    try {
      final status = await _api.decideToolApproval(
        conversation.id,
        approval.id,
        decision,
      );
      if (!_isCurrentConversation(generation, workspaceId, conversation.id)) {
        return;
      }
      _updateToolApprovalStatus(message.id, approval.id, status);
      await _refreshActiveMessages(
        generation: generation,
        workspaceId: workspaceId,
        conversationId: conversation.id,
      );
      if (_isCurrentConversation(generation, workspaceId, conversation.id)) {
        _startToolApprovalPolling();
      }
    } on ApiException catch (error) {
      if (_isCurrentConversation(generation, workspaceId, conversation.id)) {
        _updateToolApprovalStatus(message.id, approval.id, approval.status);
        _setError(error);
      }
    } catch (error) {
      if (_isCurrentConversation(generation, workspaceId, conversation.id)) {
        _updateToolApprovalStatus(message.id, approval.id, approval.status);
        _setUnknownError(error);
      }
    } finally {
      if (decidingToolApprovalId == approval.id) {
        decidingToolApprovalId = null;
      }
      _notify();
    }
  }

  Future<void> _runStream(
    Stream<SseEvent> events, {
    required String userMessageId,
    required String assistantMessageId,
  }) async {
    await stopStreaming();
    final generation = ++_streamGeneration;
    streaming = true;
    streamStage = 'generating';
    _streamUserId = userMessageId;
    _streamAssistantId = assistantMessageId;
    final completer = Completer<void>();
    var terminalReceived = false;
    _streamCompleter = completer;
    _notify();

    _streamSubscription = events.listen(
      (event) {
        if (generation != _streamGeneration) return;
        terminalReceived = _handleStreamEvent(event) || terminalReceived;
      },
      onError: (Object error, StackTrace stackTrace) {
        if (generation != _streamGeneration) return;
        terminalReceived = true;
        final apiError = error is ApiException ? error : null;
        _markCurrentAssistantFailed(
          apiError?.message ?? error.toString(),
          toolErrorCode: apiError?.code ?? 'network',
        );
        if (apiError != null) _setError(apiError);
        if (!completer.isCompleted) completer.complete();
        _notify();
      },
      onDone: () {
        if (generation == _streamGeneration && !terminalReceived) {
          const message = 'The response stream ended before completion.';
          errorCode = 'network';
          errorMessage = message;
          _markCurrentAssistantFailed(message, toolErrorCode: 'network');
          _notify();
        }
        if (!completer.isCompleted) completer.complete();
      },
      cancelOnError: false,
    );

    await completer.future;
    if (generation != _streamGeneration) return;
    _streamSubscription = null;
    _streamCompleter = null;
    streaming = false;
    streamStage = null;
    _startToolApprovalPolling();
    _notify();
  }

  bool _handleStreamEvent(SseEvent event) {
    final data = event.dataMap;
    var terminal = false;
    switch (event.event) {
      case 'message_start':
        final userId = data['user_message_id'] as String?;
        final assistantId = data['assistant_message_id'] as String?;
        if (userId != null && _streamUserId?.isNotEmpty == true) {
          _replaceMessageId(_streamUserId!, userId, status: 'completed');
          _streamUserId = userId;
        }
        if (assistantId != null && _streamAssistantId != null) {
          _replaceMessageId(
            _streamAssistantId!,
            assistantId,
            status: 'streaming',
          );
          _streamAssistantId = assistantId;
        }
        break;
      case 'token':
      case 'message':
        _appendAssistantText(_streamText(event.data));
        break;
      case 'replace':
        _setAssistantText(_streamText(event.data));
        break;
      case 'status':
        streamStage = data['stage'] as String? ?? streamStage;
        break;
      case 'tool_call':
        _recordToolCall(data);
        streamStage = 'using_tools';
        break;
      case 'tool_result':
        _recordToolResult(data);
        streamStage = 'using_tools';
        break;
      case 'tool_approval_required':
        terminal = true;
        final assistantId = data['assistant_message_id'] as String?;
        if (assistantId != null &&
            _streamAssistantId != null &&
            assistantId != _streamAssistantId) {
          _replaceMessageId(
            _streamAssistantId!,
            assistantId,
            status: 'pending',
          );
          _streamAssistantId = assistantId;
        }
        _recordToolApproval(data);
        streamStage = 'approval_required';
        break;
      case 'title':
        final title = data['title'] as String?;
        if (title != null &&
            title.trim().isNotEmpty &&
            activeConversation != null) {
          final updated = activeConversation!.copyWith(title: title.trim());
          _replaceConversation(updated);
        }
        break;
      case 'final':
      case 'message_complete':
        terminal = true;
        final answer = data['answer'] as String?;
        if (answer != null) _setAssistantText(answer);
        final citations = _citationsFrom(data['citations']);
        final assistantId = data['assistant_message_id'] as String?;
        if (assistantId != null &&
            _streamAssistantId != null &&
            assistantId != _streamAssistantId) {
          _replaceMessageId(
            _streamAssistantId!,
            assistantId,
            status: 'completed',
          );
          _streamAssistantId = assistantId;
        }
        _patchCurrentAssistant(
          status: data['status'] as String? ?? 'completed',
          citations: citations,
          clearError: true,
        );
        break;
      case 'error':
        terminal = true;
        final message = data['message'] as String? ?? 'Generation failed.';
        final eventErrorCode =
            (data['error'] as String?) ??
            (data['code'] as String?) ??
            'generation_failed';
        errorCode = eventErrorCode;
        errorMessage = message;
        _markCurrentAssistantFailed(message, toolErrorCode: eventErrorCode);
        break;
      default:
        break;
    }
    _notify();
    return terminal;
  }

  String _streamText(Object? data) {
    if (data is String) return data;
    if (data is Map) {
      final map = Map<String, dynamic>.from(data);
      return (map['text'] as String?) ??
          (map['token'] as String?) ??
          (map['content'] as String?) ??
          '';
    }
    return '';
  }

  List<Citation> _citationsFrom(Object? value) {
    if (value is! List) return const [];
    return value
        .whereType<Map>()
        .map((item) => Citation.fromJson(Map<String, dynamic>.from(item)))
        .toList(growable: false);
  }

  void _recordToolCall(JsonMap data) {
    final toolName = data['tool_name'] as String? ?? 'Tool';
    final connectionName = _toolConnectionName(data);
    final toolCallId = _toolEventId(data);
    _mutateCurrentAssistantActivities((current) {
      if (toolCallId != null) {
        final index = current.indexWhere(
          (item) => item.id == toolCallId || item.toolCallId == toolCallId,
        );
        if (index >= 0) {
          current[index] = current[index].copyWith(
            id: toolCallId,
            toolCallId: toolCallId,
            connectionName: connectionName,
            toolName: toolName,
            status: 'calling',
          );
          return current;
        }
      }
      current.add(
        ToolActivity(
          id: toolCallId ?? 'stream-tool-${_streamToolSequence++}',
          toolCallId: toolCallId,
          connectionName: connectionName,
          toolName: toolName,
          status: 'calling',
        ),
      );
      return current;
    });
  }

  void _recordToolResult(JsonMap data) {
    final toolName = data['tool_name'] as String? ?? 'Tool';
    final connectionName = _toolConnectionName(data);
    final toolCallId = _toolEventId(data);
    final rawStatus = data['outcome_unknown'] == true
        ? 'outcome_unknown'
        : data['status'] as String?;
    final status = switch (rawStatus) {
      'completed' || 'success' || 'succeeded' => 'succeeded',
      'outcome_unknown' => 'outcome_unknown',
      _ => 'failed',
    };
    _mutateCurrentAssistantActivities((current) {
      var index = toolCallId == null
          ? -1
          : current.indexWhere(
              (item) => item.id == toolCallId || item.toolCallId == toolCallId,
            );
      if (index < 0) {
        index = current.lastIndexWhere(
          (item) =>
              item.status == 'calling' &&
              (connectionName == null || item.connectionName == connectionName),
        );
      }
      if (index >= 0) {
        current[index] = current[index].copyWith(
          id: toolCallId,
          toolCallId: toolCallId,
          connectionName: connectionName,
          toolName: toolName,
          status: status,
          errorCode: data['error_code'] as String?,
        );
      } else {
        current.add(
          ToolActivity(
            id: toolCallId ?? 'stream-tool-${_streamToolSequence++}',
            toolCallId: toolCallId,
            connectionName: connectionName,
            toolName: toolName,
            status: status,
            errorCode: data['error_code'] as String?,
          ),
        );
      }
      return current;
    });
  }

  void _recordToolApproval(JsonMap data) {
    final approvalId =
        (data['approval_id'] as String?) ??
        (data['id'] as String?) ??
        'approval-${_streamToolSequence++}';
    final toolCallId = _toolEventId(data);
    final toolName = data['tool_name'] as String? ?? 'Tool';
    final connectionName = _toolConnectionName(data);
    _mutateCurrentAssistantActivities((current) {
      var index = toolCallId == null
          ? -1
          : current.indexWhere(
              (item) => item.id == toolCallId || item.toolCallId == toolCallId,
            );
      if (index < 0) {
        index = current.lastIndexWhere(
          (item) =>
              item.status == 'calling' &&
              (connectionName == null || item.connectionName == connectionName),
        );
      }
      final activity = ToolActivity(
        id: toolCallId ?? approvalId,
        toolCallId: toolCallId,
        connectionName: connectionName,
        toolName: toolName,
        status: 'approval_required',
      );
      if (index >= 0) {
        current[index] = activity;
      } else {
        current.add(activity);
      }
      return current;
    });
    _patchCurrentAssistant(
      status: data['status'] as String? ?? 'pending',
      toolApproval: ToolApproval(
        id: approvalId,
        toolCallId: toolCallId,
        connectionName: connectionName,
        toolName: toolName,
        arguments: data['arguments'],
        status: 'pending',
        expiresAt: DateTime.tryParse(data['expires_at'] as String? ?? ''),
      ),
      clearError: true,
    );
  }

  String? _toolEventId(JsonMap data) =>
      (data['tool_call_id'] as String?) ?? (data['id'] as String?);

  String? _toolConnectionName(JsonMap data) =>
      (data['connection_display_name'] as String?) ??
      (data['connection_name'] as String?);

  void _mutateCurrentAssistantActivities(
    List<ToolActivity> Function(List<ToolActivity>) mutate,
  ) {
    final assistantId = _streamAssistantId;
    if (assistantId == null) return;
    messages = messages
        .map(
          (item) => item.id == assistantId
              ? item.copyWith(
                  toolActivities: mutate(
                    item.toolActivities.toList(growable: true),
                  ),
                )
              : item,
        )
        .toList(growable: false);
  }

  Future<void> stopStreaming() async {
    final subscription = _streamSubscription;
    if (subscription == null) return;
    _streamGeneration += 1;
    await subscription.cancel();
    _streamSubscription = null;
    final completer = _streamCompleter;
    if (completer != null && !completer.isCompleted) {
      completer.complete();
    }
    _streamCompleter = null;
    _resolveCallingToolActivities(status: 'cancelled');
    _patchCurrentAssistant(status: 'cancelled');
    streaming = false;
    streamStage = null;
    _notify();
  }

  Future<void> _refreshConversationList() async {
    final workspaceId = currentWorkspace?.id;
    if (workspaceId == null) return;
    try {
      final loaded = await _api.listConversations();
      if (currentWorkspace?.id != workspaceId) return;
      conversations = loaded;
      final activeId = activeConversation?.id;
      if (activeId != null) {
        final refreshed = loaded.cast<Conversation?>().firstWhere(
          (item) => item?.id == activeId,
          orElse: () => activeConversation,
        );
        activeConversation = refreshed;
      }
      _notify();
    } on ApiException catch (error) {
      if (error.isTerminalSession) _setError(error);
      // The streamed answer is already usable; a later manual reload can retry.
    } catch (_) {
      // The streamed answer is already usable; a later manual reload can retry.
    }
  }

  Future<void> _refreshActiveMessages({
    required int generation,
    required String workspaceId,
    required String conversationId,
  }) async {
    try {
      final loaded = await _api.listMessages(conversationId);
      if (!_isCurrentConversation(generation, workspaceId, conversationId)) {
        return;
      }
      messages = loaded;
      _notify();
    } on ApiException catch (error) {
      if (error.isTerminalSession &&
          _isCurrentConversation(generation, workspaceId, conversationId)) {
        _setError(error);
      }
    } catch (_) {
      // Approval refresh is best effort; scheduled polls can retry.
    }
  }

  Future<void> _pollToolApprovalOutcome({
    required int generation,
    required String workspaceId,
    required String conversationId,
    required int pollToken,
  }) async {
    var attempt = 0;
    while (hasPendingToolTurn) {
      final delay =
          _toolApprovalPollDelays[attempt.clamp(
            0,
            _toolApprovalPollDelays.length - 1,
          )];
      await _waitForToolApprovalPoll(delay);
      if (pollToken != _toolApprovalPollToken ||
          !_isCurrentConversation(generation, workspaceId, conversationId)) {
        return;
      }
      await _refreshActiveMessages(
        generation: generation,
        workspaceId: workspaceId,
        conversationId: conversationId,
      );
      if (pollToken != _toolApprovalPollToken || !hasPendingToolTurn) return;
      attempt += 1;
    }
  }

  void _startToolApprovalPolling() {
    final conversation = activeConversation;
    final workspaceId = currentWorkspace?.id;
    if (conversation == null || workspaceId == null || !hasPendingToolTurn) {
      return;
    }
    if (_toolApprovalPollContextGeneration == _contextGeneration &&
        _toolApprovalPollConversationId == conversation.id) {
      return;
    }
    _cancelToolApprovalPolling();
    final pollToken = _toolApprovalPollToken;
    _toolApprovalPollContextGeneration = _contextGeneration;
    _toolApprovalPollConversationId = conversation.id;
    unawaited(
      _pollToolApprovalOutcome(
        generation: _contextGeneration,
        workspaceId: workspaceId,
        conversationId: conversation.id,
        pollToken: pollToken,
      ).whenComplete(() {
        if (pollToken == _toolApprovalPollToken) {
          _toolApprovalPollContextGeneration = null;
          _toolApprovalPollConversationId = null;
        }
      }),
    );
  }

  Future<void> _waitForToolApprovalPoll(Duration delay) {
    final completer = Completer<void>();
    _toolApprovalPollDelayCompleter = completer;
    _toolApprovalPollTimer = Timer(delay, () {
      if (identical(_toolApprovalPollDelayCompleter, completer)) {
        _toolApprovalPollDelayCompleter = null;
        _toolApprovalPollTimer = null;
      }
      if (!completer.isCompleted) completer.complete();
    });
    return completer.future;
  }

  void _cancelToolApprovalPolling() {
    _toolApprovalPollToken += 1;
    _toolApprovalPollTimer?.cancel();
    _toolApprovalPollTimer = null;
    final completer = _toolApprovalPollDelayCompleter;
    _toolApprovalPollDelayCompleter = null;
    if (completer != null && !completer.isCompleted) completer.complete();
    _toolApprovalPollContextGeneration = null;
    _toolApprovalPollConversationId = null;
  }

  bool _messageHasPendingToolTurn(ChatMessage message) {
    if (message.toolApproval == null) return false;
    return message.status == 'pending' || message.status == 'streaming';
  }

  Future<void> _pollForTitle(String conversationId) async {
    final workspaceId = currentWorkspace?.id;
    final generation = _contextGeneration;
    if (workspaceId == null) return;
    for (final delay in const [
      Duration(milliseconds: 400),
      Duration(milliseconds: 900),
      Duration(milliseconds: 1600),
      Duration(milliseconds: 2800),
    ]) {
      await Future<void>.delayed(delay);
      if (!_isCurrentContext(generation, workspaceId) ||
          activeConversation?.id != conversationId) {
        return;
      }
      try {
        final conversation = await _api.getConversation(conversationId);
        if (!_isCurrentContext(generation, workspaceId) ||
            activeConversation?.id != conversationId) {
          return;
        }
        _replaceConversation(conversation);
        _notify();
        if (conversation.title?.trim().isNotEmpty == true) return;
      } on ApiException catch (error) {
        if (error.isTerminalSession) {
          _setError(error);
          return;
        }
        // Title polling is best effort.
      } catch (_) {
        // Title polling is best effort.
      }
    }
  }

  void _ensureSelectedExpert() {
    if (selectedExpertId != null &&
        experts.any(
          (item) => item.id == selectedExpertId && item.isAvailable,
        )) {
      return;
    }
    final available = experts
        .where((item) => item.isAvailable)
        .toList(growable: false);
    final general = available.cast<Expert?>().firstWhere(
      (item) => item?.isGeemGeneral == true,
      orElse: () => null,
    );
    selectedExpertId =
        general?.id ?? (available.isEmpty ? null : available.first.id);
  }

  WorkspaceSummary? _workspaceById(String id) => workspaces
      .cast<WorkspaceSummary?>()
      .firstWhere((item) => item?.id == id, orElse: () => null);

  bool _isCurrentContext(int generation, String workspaceId) =>
      !_disposed &&
      generation == _contextGeneration &&
      currentWorkspace?.id == workspaceId;

  bool _isCurrentConversation(
    int generation,
    String workspaceId,
    String conversationId,
  ) =>
      _isCurrentContext(generation, workspaceId) &&
      activeConversation?.id == conversationId;

  void _replaceConversation(
    Conversation conversation, {
    bool insertIfMissing = true,
  }) {
    var found = false;
    conversations = conversations
        .map((item) {
          if (item.id != conversation.id) return item;
          found = true;
          return conversation;
        })
        .toList(growable: true);
    if (!found) {
      if (!insertIfMissing) return;
      conversations.insert(0, conversation);
    }
    if (activeConversation?.id == conversation.id) {
      activeConversation = conversation;
    }
  }

  void _replaceMessage(String id, ChatMessage replacement) {
    messages = messages
        .map((item) => item.id == id ? replacement : item)
        .toList(growable: false);
  }

  void _updateToolApprovalStatus(
    String messageId,
    String approvalId,
    String status,
  ) {
    messages = messages
        .map((item) {
          final approval = item.toolApproval;
          if (item.id != messageId ||
              approval == null ||
              approval.id != approvalId) {
            return item;
          }
          return item.copyWith(toolApproval: approval.copyWith(status: status));
        })
        .toList(growable: false);
  }

  void _replaceMessageId(String oldId, String newId, {required String status}) {
    messages = messages
        .map(
          (item) => item.id == oldId
              ? item.copyWith(id: newId, status: status)
              : item,
        )
        .toList(growable: false);
  }

  void _appendAssistantText(String text) {
    if (text.isEmpty || _streamAssistantId == null) return;
    messages = messages
        .map(
          (item) => item.id == _streamAssistantId
              ? item.copyWith(
                  content: '${item.content}$text',
                  status: 'streaming',
                )
              : item,
        )
        .toList(growable: false);
  }

  void _setAssistantText(String text) {
    if (_streamAssistantId == null) return;
    messages = messages
        .map(
          (item) => item.id == _streamAssistantId
              ? item.copyWith(content: text, status: 'streaming')
              : item,
        )
        .toList(growable: false);
  }

  void _patchCurrentAssistant({
    String? status,
    List<Citation>? citations,
    List<ToolActivity>? toolActivities,
    ToolApproval? toolApproval,
    bool clearToolApproval = false,
    String? errorMessage,
    bool clearError = false,
  }) {
    if (_streamAssistantId == null) return;
    messages = messages
        .map(
          (item) => item.id == _streamAssistantId
              ? item.copyWith(
                  status: status,
                  citations: citations,
                  toolActivities: toolActivities,
                  toolApproval: toolApproval,
                  clearToolApproval: clearToolApproval,
                  errorMessage: errorMessage,
                  clearError: clearError,
                )
              : item,
        )
        .toList(growable: false);
  }

  void _markCurrentAssistantFailed(String message, {String? toolErrorCode}) {
    _resolveCallingToolActivities(
      status: toolErrorCode == 'mcp_tool_outcome_unknown'
          ? 'outcome_unknown'
          : 'failed',
      errorCode: toolErrorCode,
    );
    _patchCurrentAssistant(status: 'failed', errorMessage: message);
  }

  void _resolveCallingToolActivities({
    required String status,
    String? errorCode,
  }) {
    _mutateCurrentAssistantActivities((current) {
      for (var index = 0; index < current.length; index += 1) {
        final activity = current[index];
        if (activity.status != 'calling') continue;
        current[index] = activity.copyWith(
          status: status,
          errorCode: errorCode,
        );
      }
      return current;
    });
  }

  String _clientId(String role) =>
      'client-$role-${DateTime.now().microsecondsSinceEpoch}-${_clientSequence++}';

  String _provisionalTitle(String content) {
    final compact = content.replaceAll(RegExp(r'\s+'), ' ').trim();
    if (compact.length <= 56) return compact;
    return '${compact.substring(0, 55).trimRight()}…';
  }

  void _setError(ApiException error) {
    if (error.isTerminalSession) {
      _expireSession(error);
      return;
    }
    _setPlainError(error);
  }

  void _setPlainError(ApiException error) {
    errorCode = error.code;
    errorMessage = error.message;
  }

  void _expireSession(ApiException error) {
    if (_invalidatingSession) return;
    _invalidatingSession = true;
    _contextGeneration += 1;
    unawaited(stopStreaming());
    _clearIdentityAndWorkspace();
    sessionState = AppSessionState.unauthenticated;
    authPage = AuthPage.login;
    _setPlainError(error);
    _notify();
    unawaited(() async {
      try {
        await _api.forgetSession();
      } catch (_) {
        // Local state is already unauthenticated; retry cleanup on next launch.
      } finally {
        _invalidatingSession = false;
      }
    }());
  }

  void _setUnknownError(Object error) {
    errorCode = 'unknown';
    errorMessage = kDebugMode ? error.toString() : 'Something went wrong.';
  }

  void clearFeedback() {
    _clearFeedback();
    _notify();
  }

  void _clearFeedback() {
    errorCode = null;
    errorMessage = null;
    noticeMessage = null;
  }

  Future<void> logout() async {
    await stopStreaming();
    try {
      await _api.logout();
    } catch (_) {
      try {
        await _api.forgetSession();
      } catch (_) {
        // Always clear the in-memory UI even if secure storage is unavailable.
      }
    }
    _contextGeneration += 1;
    _clearIdentityAndWorkspace();
    sessionState = AppSessionState.unauthenticated;
    authPage = AuthPage.login;
    _clearFeedback();
    _notify();
  }

  void _clearIdentityAndWorkspace() {
    user = null;
    workspaces = const [];
    currentWorkspace = null;
    experts = const [];
    conversations = const [];
    activeConversation = null;
    messages = const [];
    selectedExpertId = null;
    workspaceLoading = false;
    conversationLoading = false;
    sending = false;
    streaming = false;
    decidingToolApprovalId = null;
    _cancelToolApprovalPolling();
    _streamAssistantId = null;
    _streamUserId = null;
    streamStage = null;
    _api.workspaceId = null;
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _cancelToolApprovalPolling();
    unawaited(_streamSubscription?.cancel());
    _api.close();
    super.dispose();
  }
}
