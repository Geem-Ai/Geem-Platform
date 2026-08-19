import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geem_workspace/src/widgets/geem_thinking_typewriter.dart';

void main() {
  String visibleText(WidgetTester tester) {
    final finder = find.descendant(
      of: find.byType(GeemThinkingTypewriter),
      matching: find.byType(Text),
    );
    return tester.widget<Text>(finder).data ?? '';
  }

  Widget host(Widget child, {bool reducedMotion = false}) => MaterialApp(
    home: MediaQuery(
      data: MediaQueryData(disableAnimations: reducedMotion),
      child: Scaffold(body: Center(child: child)),
    ),
  );

  testWidgets('types, holds, deletes, and advances at the web cadence', (
    tester,
  ) async {
    await tester.pumpWidget(
      host(
        const GeemThinkingTypewriter(
          messages: ['Hi', 'Yo'],
          semanticsLabel: 'Geem is thinking…',
          shuffleMessages: false,
        ),
      ),
    );

    expect(visibleText(tester), isEmpty);

    await tester.pump(GeemThinkingTypewriter.typingDuration);
    expect(visibleText(tester), 'H');
    await tester.pump(GeemThinkingTypewriter.typingDuration);
    expect(visibleText(tester), 'Hi');

    await tester.pump(GeemThinkingTypewriter.holdDuration);
    expect(visibleText(tester), 'Hi');
    await tester.pump(GeemThinkingTypewriter.deleteDuration);
    expect(visibleText(tester), 'H');
    await tester.pump(GeemThinkingTypewriter.deleteDuration);
    expect(visibleText(tester), isEmpty);

    await tester.pump(GeemThinkingTypewriter.gapDuration);
    expect(visibleText(tester), isEmpty);
    await tester.pump(GeemThinkingTypewriter.typingDuration);
    expect(visibleText(tester), 'Y');
    await tester.pump(GeemThinkingTypewriter.typingDuration);
    expect(visibleText(tester), 'Yo');
  });

  testWidgets('reduced motion rotates complete messages without typing', (
    tester,
  ) async {
    await tester.pumpWidget(
      host(
        const GeemThinkingTypewriter(
          messages: ['Alpha', 'Beta'],
          semanticsLabel: 'Geem is thinking…',
          shuffleMessages: false,
        ),
        reducedMotion: true,
      ),
    );

    expect(visibleText(tester), 'Alpha');
    await tester.pump(GeemThinkingTypewriter.holdDuration);
    expect(visibleText(tester), 'Beta');
    await tester.pump(GeemThinkingTypewriter.holdDuration);
    expect(visibleText(tester), 'Alpha');
  });

  testWidgets('keeps one stable live-region label while text changes', (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    await tester.pumpWidget(
      host(
        const GeemThinkingTypewriter(
          messages: ['Thinking'],
          semanticsLabel: 'Geem is thinking…',
          shuffleMessages: false,
        ),
      ),
    );

    final status = find.bySemanticsLabel('Geem is thinking…');
    expect(status, findsOneWidget);
    expect(
      tester.getSemantics(status),
      matchesSemantics(label: 'Geem is thinking…', isLiveRegion: true),
    );

    await tester.pump(GeemThinkingTypewriter.typingDuration * 4);
    expect(find.bySemanticsLabel('Geem is thinking…'), findsOneWidget);
    semantics.dispose();
  });

  testWidgets('inactive state clears and stops the typewriter', (tester) async {
    Widget status(bool active) => host(
      GeemThinkingTypewriter(
        messages: const ['Thinking'],
        semanticsLabel: 'Geem is thinking…',
        active: active,
        shuffleMessages: false,
      ),
    );

    await tester.pumpWidget(status(true));
    await tester.pump(GeemThinkingTypewriter.typingDuration * 3);
    expect(visibleText(tester), 'Thi');

    await tester.pumpWidget(status(false));
    expect(find.byType(PulsingCursor), findsNothing);
    await tester.pump(const Duration(seconds: 3));
    expect(tester.takeException(), isNull);
  });

  testWidgets('cursor exposes reusable geometry and disposes its ticker', (
    tester,
  ) async {
    await tester.pumpWidget(
      host(
        const PulsingCursor(
          width: 8,
          height: 16,
          margin: EdgeInsetsDirectional.only(start: 4),
          color: Colors.blue,
        ),
      ),
    );

    expect(tester.getSize(find.byType(PulsingCursor)), const Size(12, 16));
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpWidget(host(const SizedBox.shrink()));
    await tester.pump(const Duration(seconds: 3));
    expect(tester.takeException(), isNull);
  });
}
