import 'package:flutter/widgets.dart';

import 'controllers/app_controller.dart';

class AppScope extends InheritedNotifier<AppController> {
  const AppScope({
    required AppController controller,
    required super.child,
    super.key,
  }) : super(notifier: controller);

  static AppController of(BuildContext context, {bool listen = true}) {
    if (!listen) {
      final element = context
          .getElementForInheritedWidgetOfExactType<AppScope>();
      final scope = element?.widget as AppScope?;
      assert(scope != null, 'AppScope is missing from the widget tree.');
      return scope!.notifier!;
    }
    final scope = context.dependOnInheritedWidgetOfExactType<AppScope>();
    assert(scope != null, 'AppScope is missing from the widget tree.');
    return scope!.notifier!;
  }
}
