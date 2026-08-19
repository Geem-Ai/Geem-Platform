class ApiException implements Exception {
  const ApiException(this.message, {required this.status, required this.code});

  final String message;
  final int status;
  final String code;

  bool get isTerminalSession =>
      status == 401 &&
      (code == 'unauthorized' ||
          code == 'session_expired' ||
          code == 'session_revoked');

  @override
  String toString() => 'ApiException($status, $code): $message';
}
