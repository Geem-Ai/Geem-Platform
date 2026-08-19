import 'package:flutter_secure_storage/flutter_secure_storage.dart';

abstract class CredentialStore {
  Future<String?> readRefreshToken();
  Future<void> writeRefreshToken(String token);
  Future<void> deleteRefreshToken();
  Future<String?> readWorkspaceId(String userId);
  Future<void> writeWorkspaceId(String userId, String workspaceId);
  Future<String?> readLocale();
  Future<void> writeLocale(String languageCode);
}

class DeviceCredentialStore implements CredentialStore {
  DeviceCredentialStore({FlutterSecureStorage? storage})
    : _storage = storage ?? FlutterSecureStorage();

  static const _refreshKey = 'geem.refresh-token';
  static const _localeKey = 'geem.locale';
  static const _workspacePrefix = 'geem.workspace.';

  final FlutterSecureStorage _storage;

  @override
  Future<String?> readRefreshToken() => _storage.read(key: _refreshKey);

  @override
  Future<void> writeRefreshToken(String token) =>
      _storage.write(key: _refreshKey, value: token);

  @override
  Future<void> deleteRefreshToken() => _storage.delete(key: _refreshKey);

  @override
  Future<String?> readWorkspaceId(String userId) =>
      _storage.read(key: '$_workspacePrefix$userId');

  @override
  Future<void> writeWorkspaceId(String userId, String workspaceId) =>
      _storage.write(key: '$_workspacePrefix$userId', value: workspaceId);

  @override
  Future<String?> readLocale() => _storage.read(key: _localeKey);

  @override
  Future<void> writeLocale(String languageCode) =>
      _storage.write(key: _localeKey, value: languageCode);
}
