import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/models.dart';
import 'api_exception.dart';
import 'credential_store.dart';
import 'sse_parser.dart';

typedef HttpClientFactory = http.Client Function();

class GeemApiClient {
  factory GeemApiClient({
    required String baseUrl,
    required CredentialStore credentials,
    http.Client? client,
    HttpClientFactory? streamClientFactory,
  }) {
    final normalizedBaseUrl = baseUrl.replaceFirst(RegExp(r'/$'), '');
    final uri = Uri.tryParse(normalizedBaseUrl);
    if (uri == null || !uri.hasScheme || !uri.hasAuthority) {
      throw ArgumentError.value(
        baseUrl,
        'baseUrl',
        'Must be an absolute HTTP(S) URL.',
      );
    }
    return GeemApiClient._(
      normalizedBaseUrl,
      credentials,
      client ?? http.Client(),
      streamClientFactory ?? http.Client.new,
    );
  }

  GeemApiClient._(
    this._baseUrl,
    this._credentials,
    this._client,
    this._streamClientFactory,
  );

  final String _baseUrl;
  final CredentialStore _credentials;
  final http.Client _client;
  final HttpClientFactory _streamClientFactory;

  String? _accessToken;
  DateTime? _accessExpiresAt;
  String? workspaceId;
  Future<AuthTokens>? _refreshInFlight;
  Future<void> _tokenMutationTail = Future<void>.value();
  int _authEpoch = 0;
  bool _sessionEnding = false;

  String get baseUrl => _baseUrl;

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  Future<AuthTokens> login(String email, String password) async {
    final epoch = _authEpoch;
    final response = await _performRequest(
      'POST',
      '/api/auth/login',
      jsonBody: {'email': email, 'password': password},
      includeAuth: false,
      includeWorkspace: false,
    );
    _ensureSuccess(response);
    return _acceptTokenResponse(response, epoch: epoch);
  }

  Future<void> forgotPassword(String email) async {
    final response = await _performRequest(
      'POST',
      '/api/auth/forgot-password',
      jsonBody: {'email': email},
      includeAuth: false,
      includeWorkspace: false,
    );
    _ensureSuccess(response);
  }

  Future<void> resendVerification(String email) async {
    final response = await _performRequest(
      'POST',
      '/api/auth/resend-verification',
      jsonBody: {'email': email},
      includeAuth: false,
      includeWorkspace: false,
    );
    _ensureSuccess(response);
  }

  Future<AuthTokens> verifyEmail(String token) async {
    final epoch = _authEpoch;
    final response = await _performRequest(
      'POST',
      '/api/auth/verify-email',
      jsonBody: {'token': token},
      includeAuth: false,
      includeWorkspace: false,
    );
    _ensureSuccess(response);
    return _acceptTokenResponse(response, epoch: epoch);
  }

  Future<AuthTokens> resetPassword(String token, String password) async {
    final epoch = _authEpoch;
    final response = await _performRequest(
      'POST',
      '/api/auth/reset-password',
      jsonBody: {'token': token, 'password': password},
      includeAuth: false,
      includeWorkspace: false,
    );
    _ensureSuccess(response);
    return _acceptTokenResponse(response, epoch: epoch);
  }

  Future<AuthTokens> refreshSession() {
    if (_sessionEnding) {
      return Future<AuthTokens>.error(
        const ApiException(
          'The session is ending.',
          status: 401,
          code: 'session_revoked',
        ),
      );
    }
    final current = _refreshInFlight;
    if (current != null) return current;

    final epoch = _authEpoch;
    late Future<AuthTokens> future;
    future = (() async {
      try {
        return await _refreshNow(epoch);
      } finally {
        if (identical(_refreshInFlight, future)) _refreshInFlight = null;
      }
    })();
    _refreshInFlight = future;
    return future;
  }

  Future<AuthTokens> _refreshNow(int epoch) async {
    final refreshToken = await _credentials.readRefreshToken();
    if (refreshToken == null || refreshToken.isEmpty) {
      throw const ApiException(
        'No saved session.',
        status: 401,
        code: 'session_expired',
      );
    }
    final response = await _performRequest(
      'POST',
      '/api/auth/refresh',
      jsonBody: {'refresh_token': refreshToken},
      includeAuth: false,
      includeWorkspace: false,
    );
    _ensureSuccess(response);
    return _acceptTokenResponse(response, epoch: epoch);
  }

  Future<void> logout() async {
    final refresh = _refreshInFlight;
    if (refresh != null) {
      try {
        await refresh;
      } catch (_) {
        // Continue with local cleanup even when the in-flight refresh failed.
      }
    }
    _sessionEnding = true;
    try {
      final refreshToken = await _credentials.readRefreshToken();
      final response = await _performRequest(
        'POST',
        '/api/auth/logout',
        jsonBody: {'refresh_token': refreshToken},
        includeWorkspace: false,
      );
      _ensureSuccess(response);
    } finally {
      try {
        await forgetSession();
      } finally {
        _sessionEnding = false;
      }
    }
  }

  Future<void> forgetSession() async {
    _authEpoch += 1;
    _accessToken = null;
    _accessExpiresAt = null;
    workspaceId = null;
    await _serializeTokenMutation(_credentials.deleteRefreshToken);
  }

  Future<MeResponse> getMe() async {
    final json = await _requestJson(
      'GET',
      '/api/auth/me',
      includeWorkspace: false,
    );
    return MeResponse.fromJson(_asJsonMap(json));
  }

  Future<List<Expert>> listExperts() async {
    final json = await _requestJson('GET', '/api/experts');
    return _asJsonList(json).map(Expert.fromJson).toList(growable: false);
  }

  Future<List<Conversation>> listConversations({int limit = 100}) async {
    final json = await _requestJson(
      'GET',
      '/api/conversations?limit=$limit&offset=0',
    );
    return _asJsonList(json).map(Conversation.fromJson).toList(growable: false);
  }

  Future<Conversation> getConversation(String id) async {
    final safeId = Uri.encodeComponent(id);
    final json = await _requestJson('GET', '/api/conversations/$safeId');
    return Conversation.fromJson(_asJsonMap(json));
  }

  Future<Conversation> createConversation(String expertId) async {
    final json = await _requestJson(
      'POST',
      '/api/conversations',
      jsonBody: {'expert_id': expertId},
    );
    return Conversation.fromJson(_asJsonMap(json));
  }

  Future<Conversation> updateConversation(
    String id, {
    String? title,
    bool? isPinned,
    bool? isFavorite,
  }) async {
    final body = <String, Object?>{};
    if (title != null) body['title'] = title;
    if (isPinned != null) body['is_pinned'] = isPinned;
    if (isFavorite != null) body['is_favorite'] = isFavorite;
    final safeId = Uri.encodeComponent(id);
    final json = await _requestJson(
      'PATCH',
      '/api/conversations/$safeId',
      jsonBody: body,
    );
    return Conversation.fromJson(_asJsonMap(json));
  }

  Future<void> deleteConversation(String id) async {
    final safeId = Uri.encodeComponent(id);
    await _requestJson('DELETE', '/api/conversations/$safeId');
  }

  Future<List<ChatMessage>> listMessages(String conversationId) async {
    final safeId = Uri.encodeComponent(conversationId);
    final json = await _requestJson(
      'GET',
      '/api/conversations/$safeId/messages?limit=500&offset=0',
    );
    return _asJsonList(json).map(ChatMessage.fromJson).toList(growable: false);
  }

  Stream<SseEvent> streamMessage(String conversationId, String content) {
    final safeId = Uri.encodeComponent(conversationId);
    return _streamSse('/api/conversations/$safeId/messages/stream', {
      'content': content,
    });
  }

  Stream<SseEvent> retryMessage(
    String conversationId,
    String assistantMessageId,
  ) {
    final safeConversationId = Uri.encodeComponent(conversationId);
    final safeMessageId = Uri.encodeComponent(assistantMessageId);
    return _streamSse(
      '/api/conversations/$safeConversationId/messages/$safeMessageId/retry/stream',
      const {},
    );
  }

  Future<String> decideToolApproval(
    String conversationId,
    String approvalId,
    String decision,
  ) async {
    if (decision != 'approve' && decision != 'deny') {
      throw ArgumentError.value(
        decision,
        'decision',
        'Must be either approve or deny.',
      );
    }
    final safeConversationId = Uri.encodeComponent(conversationId);
    final safeApprovalId = Uri.encodeComponent(approvalId);
    final json = await _requestJson(
      'POST',
      '/api/conversations/$safeConversationId/tool-approvals/$safeApprovalId',
      jsonBody: {'decision': decision},
    );
    final payload = _asJsonMap(json);
    final status = payload['status'] as String?;
    if (status == null || status.isEmpty) {
      throw const ApiException(
        'The server returned an invalid approval response.',
        status: 0,
        code: 'invalid_response',
      );
    }
    return status;
  }

  Stream<SseEvent> _streamSse(String path, JsonMap body) async* {
    await _ensureFreshAccessToken();

    for (var attempt = 0; attempt < 2; attempt += 1) {
      final streamClient = _streamClientFactory();
      final tokenUsed = _accessToken;
      try {
        final request = http.Request('POST', _uri(path));
        request.headers.addAll(
          _headers(includeWorkspace: true, accessToken: tokenUsed),
        );
        request.headers['Accept'] = 'text/event-stream';
        request.headers['Content-Type'] = 'application/json';
        request.body = jsonEncode(body);

        final response = await streamClient.send(request);
        if (response.statusCode == 401 && attempt == 0) {
          final responseBody = await response.stream.bytesToString();
          final errorResponse = http.Response(
            responseBody,
            response.statusCode,
            headers: response.headers,
            reasonPhrase: response.reasonPhrase,
          );
          if (!_isSessionAuthFailure(errorResponse)) {
            throw _apiException(errorResponse);
          }
          if (tokenUsed == null || tokenUsed == _accessToken) {
            await refreshSession();
          }
          continue;
        }
        if (response.statusCode < 200 || response.statusCode >= 300) {
          final responseBody = await response.stream.bytesToString();
          throw _apiException(
            http.Response(
              responseBody,
              response.statusCode,
              headers: response.headers,
              reasonPhrase: response.reasonPhrase,
            ),
          );
        }

        final parser = SseParser();
        await for (final chunk in response.stream.transform(utf8.decoder)) {
          for (final event in parser.addChunk(chunk)) {
            yield event;
          }
        }
        for (final event in parser.close()) {
          yield event;
        }
        return;
      } finally {
        streamClient.close();
      }
    }
  }

  Future<void> _ensureFreshAccessToken() async {
    final expiresAt = _accessExpiresAt;
    if (_accessToken == null ||
        expiresAt == null ||
        expiresAt.isBefore(DateTime.now().add(const Duration(seconds: 30)))) {
      await refreshSession();
    }
  }

  Future<Object?> _requestJson(
    String method,
    String path, {
    JsonMap? jsonBody,
    bool includeWorkspace = true,
  }) async {
    var tokenUsed = _accessToken;
    var response = await _performRequest(
      method,
      path,
      jsonBody: jsonBody,
      includeWorkspace: includeWorkspace,
      accessToken: tokenUsed,
      pinAccessToken: true,
    );
    if (response.statusCode == 401 && _isSessionAuthFailure(response)) {
      if (tokenUsed == null || tokenUsed == _accessToken) {
        await refreshSession();
      }
      tokenUsed = _accessToken;
      response = await _performRequest(
        method,
        path,
        jsonBody: jsonBody,
        includeWorkspace: includeWorkspace,
        accessToken: tokenUsed,
        pinAccessToken: true,
      );
    }
    _ensureSuccess(response);
    if (response.statusCode == 204 || response.body.trim().isEmpty) return null;
    try {
      return jsonDecode(response.body);
    } on FormatException {
      throw ApiException(
        'The server returned an invalid response.',
        status: response.statusCode,
        code: 'invalid_response',
      );
    }
  }

  Future<http.Response> _performRequest(
    String method,
    String path, {
    JsonMap? jsonBody,
    bool includeAuth = true,
    bool includeWorkspace = true,
    String? accessToken,
    bool pinAccessToken = false,
  }) async {
    final request = http.Request(method, _uri(path));
    request.headers.addAll(
      _headers(
        includeAuth: includeAuth,
        includeWorkspace: includeWorkspace,
        accessToken: pinAccessToken ? accessToken : _accessToken,
      ),
    );
    if (jsonBody != null) {
      request.headers['Content-Type'] = 'application/json';
      request.body = jsonEncode(jsonBody);
    }
    try {
      final streamed = await _client.send(request);
      return await http.Response.fromStream(streamed);
    } on ApiException {
      rethrow;
    } catch (error) {
      throw ApiException(error.toString(), status: 0, code: 'network');
    }
  }

  Map<String, String> _headers({
    bool includeAuth = true,
    bool includeWorkspace = true,
    String? accessToken,
  }) {
    final headers = <String, String>{};
    final token = accessToken ?? _accessToken;
    if (includeAuth && token != null) {
      headers['Authorization'] = 'Bearer $token';
    }
    final id = workspaceId;
    if (includeWorkspace && id != null) {
      headers['X-Workspace-Id'] = id;
    }
    return headers;
  }

  Future<AuthTokens> _acceptTokenResponse(
    http.Response response, {
    required int epoch,
  }) async {
    final payload = _asJsonMap(_decodeBody(response));
    final tokens = AuthTokens.fromJson(payload);
    if (tokens.accessToken.isEmpty) {
      throw ApiException(
        'The server did not return an access token.',
        status: response.statusCode,
        code: 'invalid_response',
      );
    }
    final refreshToken = _refreshTokenFrom(response);
    var accepted = false;
    await _serializeTokenMutation(() async {
      if (epoch != _authEpoch) return;
      if (refreshToken != null) {
        await _credentials.writeRefreshToken(refreshToken);
      }
      if (epoch != _authEpoch) return;
      _accessToken = tokens.accessToken;
      _accessExpiresAt = tokens.expiresAt;
      accepted = true;
    });
    if (!accepted) {
      throw const ApiException(
        'The session changed while authentication was in progress.',
        status: 401,
        code: 'session_revoked',
      );
    }
    return tokens;
  }

  String? _refreshTokenFrom(http.Response response) {
    final setCookie = response.headers['set-cookie'];
    if (setCookie == null || setCookie.isEmpty) return null;
    final match = RegExp(
      r'(?:^|,\s*)geem_refresh=([^;,\s]+)',
      caseSensitive: false,
    ).firstMatch(setCookie);
    final token = match?.group(1);
    return token?.isNotEmpty == true ? token : null;
  }

  Future<void> _serializeTokenMutation(Future<void> Function() mutation) {
    final completer = Completer<void>();
    _tokenMutationTail = _tokenMutationTail.then((_) async {
      try {
        await mutation();
        completer.complete();
      } catch (error, stackTrace) {
        completer.completeError(error, stackTrace);
      }
    });
    return completer.future;
  }

  void _ensureSuccess(http.Response response) {
    if (response.statusCode >= 200 && response.statusCode < 300) return;
    throw _apiException(response);
  }

  ApiException _apiException(http.Response response) {
    JsonMap body = const {};
    try {
      final decoded = jsonDecode(response.body);
      if (decoded is Map) body = Map<String, dynamic>.from(decoded);
    } on FormatException {
      // Use HTTP fallback details below.
    }
    final code =
        (body['code'] as String?) ??
        (body['error'] as String?) ??
        _statusCode(response.statusCode);
    final rawDetail = body['detail'];
    final message =
        (body['message'] as String?) ??
        (rawDetail is String ? rawDetail : null) ??
        response.reasonPhrase ??
        'Request failed.';
    return ApiException(message, status: response.statusCode, code: code);
  }

  bool _isSessionAuthFailure(http.Response response) {
    if (response.statusCode != 401) return false;
    JsonMap body = const {};
    try {
      final decoded = jsonDecode(response.body);
      if (decoded is Map) body = Map<String, dynamic>.from(decoded);
    } on FormatException {
      return true;
    }
    final code = (body['code'] as String?) ?? (body['error'] as String?);
    if (code == null || code.isEmpty) return true;
    if (code == 'mcp_auth_required') return false;
    return true;
  }

  String _statusCode(int status) => switch (status) {
    400 => 'bad_request',
    401 => 'unauthorized',
    403 => 'forbidden',
    404 => 'not_found',
    409 => 'conflict',
    413 => 'payload_too_large',
    422 => 'validation',
    429 => 'rate_limited',
    _ when status >= 500 => 'server_error',
    _ => 'unknown',
  };

  Object? _decodeBody(http.Response response) {
    try {
      return jsonDecode(response.body);
    } on FormatException {
      throw ApiException(
        'The server returned an invalid response.',
        status: response.statusCode,
        code: 'invalid_response',
      );
    }
  }

  JsonMap _asJsonMap(Object? value) {
    if (value is Map) return Map<String, dynamic>.from(value);
    throw const ApiException(
      'Expected a JSON object.',
      status: 0,
      code: 'invalid_response',
    );
  }

  List<JsonMap> _asJsonList(Object? value) {
    if (value is! List) {
      throw const ApiException(
        'Expected a JSON list.',
        status: 0,
        code: 'invalid_response',
      );
    }
    return value
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList(growable: false);
  }

  void close() => _client.close();
}
