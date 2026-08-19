import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';

import 'src/app.dart';
import 'src/controllers/app_controller.dart';
import 'src/services/credential_store.dart';
import 'src/services/geem_api_client.dart';

const _apiBaseUrl = String.fromEnvironment(
  'GEEM_API_URL',
  defaultValue: 'https://api.geem.ai',
);

void main() {
  WidgetsFlutterBinding.ensureInitialized();

  final credentials = DeviceCredentialStore();
  final api = GeemApiClient(baseUrl: _apiBaseUrl, credentials: credentials);
  final platformLocale = WidgetsBinding.instance.platformDispatcher.locale;
  final controller = AppController(
    api: api,
    credentials: credentials,
    initialLocale: platformLocale,
  );

  // Subscribe before runApp so a cold-start auth link cannot be missed. Queue
  // link handling behind session bootstrap to avoid racing refresh-token reads
  // with verification/reset token rotation.
  final appLinks = AppLinks();
  final initialization = controller.initialize();
  final linkSubscription = appLinks.uriLinkStream.listen(
    (uri) =>
        unawaited(initialization.then((_) => controller.handleDeepLink(uri))),
    onError: (_) {},
  );

  runApp(GeemApp(controller: controller, linkSubscription: linkSubscription));
}
