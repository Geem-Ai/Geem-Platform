import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:geem_workspace/src/services/credential_store.dart';
import 'package:geem_workspace/src/services/geem_api_client.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class _MemoryCredentialStore implements CredentialStore {
  String? refreshToken;
  String? locale;
  final workspaceIds = <String, String>{};

  @override
  Future<void> deleteRefreshToken() async => refreshToken = null;

  @override
  Future<String?> readLocale() async => locale;

  @override
  Future<String?> readRefreshToken() async => refreshToken;

  @override
  Future<String?> readWorkspaceId(String userId) async => workspaceIds[userId];

  @override
  Future<void> writeLocale(String languageCode) async => locale = languageCode;

  @override
  Future<void> writeRefreshToken(String token) async => refreshToken = token;

  @override
  Future<void> writeWorkspaceId(String userId, String workspaceId) async {
    workspaceIds[userId] = workspaceId;
  }
}

http.Response _tokenResponse(
  String accessToken,
  String refreshToken,
) => http.Response(
  jsonEncode({
    'access_token': accessToken,
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
    'content-type': 'application/json',
    'set-cookie':
        'geem_refresh=$refreshToken; Path=/api/auth; HttpOnly; SameSite=Lax',
  },
);

void main() {
  test(
    'captures rotating refresh cookies and refreshes single-flight',
    () async {
      final credentials = _MemoryCredentialStore();
      var refreshCalls = 0;
      final client = MockClient((request) async {
        if (request.url.path == '/api/auth/login') {
          return _tokenResponse('access-a', 'refresh-a');
        }
        if (request.url.path == '/api/auth/refresh') {
          refreshCalls += 1;
          expect(jsonDecode(request.body), {'refresh_token': 'refresh-a'});
          await Future<void>.delayed(const Duration(milliseconds: 10));
          return _tokenResponse('access-b', 'refresh-b');
        }
        return http.Response('Not found', 404);
      });
      final api = GeemApiClient(
        baseUrl: 'https://api.example.test',
        credentials: credentials,
        client: client,
      );
      addTearDown(api.close);

      await api.login('member@example.com', 'password');
      expect(credentials.refreshToken, 'refresh-a');

      await Future.wait([api.refreshSession(), api.refreshSession()]);

      expect(refreshCalls, 1);
      expect(credentials.refreshToken, 'refresh-b');
    },
  );

  test(
    'retries a 401 with rotated auth and preserves workspace scope',
    () async {
      final credentials = _MemoryCredentialStore()..refreshToken = 'refresh-a';
      var listCalls = 0;
      final client = MockClient((request) async {
        if (request.url.path == '/api/auth/refresh') {
          return _tokenResponse('access-b', 'refresh-b');
        }
        if (request.url.path == '/api/conversations') {
          listCalls += 1;
          expect(request.headers['x-workspace-id'], 'workspace-1');
          if (listCalls == 1) return http.Response('Unauthorized', 401);
          expect(request.headers['authorization'], 'Bearer access-b');
          return http.Response('[]', 200);
        }
        return http.Response('Not found', 404);
      });
      final api = GeemApiClient(
        baseUrl: 'https://api.example.test',
        credentials: credentials,
        client: client,
      )..workspaceId = 'workspace-1';
      addTearDown(api.close);

      final conversations = await api.listConversations();

      expect(conversations, isEmpty);
      expect(listCalls, 2);
      expect(credentials.refreshToken, 'refresh-b');
    },
  );

  test('a late concurrent 401 reuses the rotated access token', () async {
    final credentials = _MemoryCredentialStore();
    final releaseLate401 = Completer<void>();
    var oldTokenCalls = 0;
    var refreshCalls = 0;
    final client = MockClient((request) async {
      if (request.url.path == '/api/auth/login') {
        return _tokenResponse('access-a', 'refresh-a');
      }
      if (request.url.path == '/api/auth/refresh') {
        refreshCalls += 1;
        return _tokenResponse('access-b', 'refresh-b');
      }
      if (request.url.path == '/api/conversations') {
        final authorization = request.headers['authorization'];
        if (authorization == 'Bearer access-a') {
          oldTokenCalls += 1;
          if (oldTokenCalls == 1) return http.Response('Unauthorized', 401);
          await releaseLate401.future;
          return http.Response('Unauthorized', 401);
        }
        if (authorization == 'Bearer access-b') {
          if (!releaseLate401.isCompleted) releaseLate401.complete();
          return http.Response('[]', 200);
        }
      }
      return http.Response('Not found', 404);
    });
    final api = GeemApiClient(
      baseUrl: 'https://api.example.test',
      credentials: credentials,
      client: client,
    )..workspaceId = 'workspace-1';
    addTearDown(api.close);
    await api.login('member@example.com', 'password');

    final results = await Future.wait([
      api.listConversations(),
      api.listConversations(),
    ]);

    expect(results, everyElement(isEmpty));
    expect(oldTokenCalls, 2);
    expect(refreshCalls, 1);
    expect(credentials.refreshToken, 'refresh-b');
  });

  test('logout waits for rotation and revokes the latest token', () async {
    final credentials = _MemoryCredentialStore();
    final refreshStarted = Completer<void>();
    final releaseRefresh = Completer<void>();
    String? logoutRefreshToken;
    final client = MockClient((request) async {
      if (request.url.path == '/api/auth/login') {
        return _tokenResponse('access-a', 'refresh-a');
      }
      if (request.url.path == '/api/auth/refresh') {
        refreshStarted.complete();
        await releaseRefresh.future;
        return _tokenResponse('access-b', 'refresh-b');
      }
      if (request.url.path == '/api/auth/logout') {
        logoutRefreshToken =
            (jsonDecode(request.body) as Map<String, dynamic>)['refresh_token']
                as String?;
        return http.Response('', 204);
      }
      return http.Response('Not found', 404);
    });
    final api = GeemApiClient(
      baseUrl: 'https://api.example.test',
      credentials: credentials,
      client: client,
    );
    addTearDown(api.close);
    await api.login('member@example.com', 'password');

    final refresh = api.refreshSession();
    await refreshStarted.future;
    final logout = api.logout();
    releaseRefresh.complete();
    await Future.wait<void>([refresh.then((_) {}), logout]);

    expect(logoutRefreshToken, 'refresh-b');
    expect(credentials.refreshToken, isNull);
  });
}
