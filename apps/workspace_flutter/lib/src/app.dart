import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'app_scope.dart';
import 'controllers/app_controller.dart';
import 'screens/auth/auth_screen.dart';
import 'screens/chat/chat_shell.dart';
import 'theme/geem_theme.dart';
import 'widgets/geem_avatar.dart';

class GeemApp extends StatefulWidget {
  const GeemApp({
    required this.controller,
    required this.linkSubscription,
    super.key,
  });

  final AppController controller;
  final StreamSubscription<Uri> linkSubscription;

  @override
  State<GeemApp> createState() => _GeemAppState();
}

class _GeemAppState extends State<GeemApp> {
  @override
  void dispose() {
    unawaited(widget.linkSubscription.cancel());
    widget.controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AppScope(
    controller: widget.controller,
    child: AnimatedBuilder(
      animation: widget.controller,
      builder: (context, _) => MaterialApp(
        title: 'Geem',
        debugShowCheckedModeBanner: false,
        locale: widget.controller.locale,
        supportedLocales: const [Locale('ar'), Locale('en')],
        localizationsDelegates: const [
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        theme: geemLightTheme(),
        darkTheme: geemDarkTheme(),
        themeMode: ThemeMode.system,
        home: switch (widget.controller.sessionState) {
          AppSessionState.bootstrapping => const _BootstrapScreen(),
          AppSessionState.unauthenticated => const AuthScreen(),
          AppSessionState.authenticated => const ChatShell(),
        },
      ),
    ),
  );
}

class _BootstrapScreen extends StatelessWidget {
  const _BootstrapScreen();

  @override
  Widget build(BuildContext context) => Scaffold(
    body: Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const GeemAvatar(size: 72),
          const SizedBox(height: 22),
          SizedBox(
            width: 88,
            child: LinearProgressIndicator(
              minHeight: 3,
              borderRadius: BorderRadius.circular(4),
            ),
          ),
        ],
      ),
    ),
  );
}
