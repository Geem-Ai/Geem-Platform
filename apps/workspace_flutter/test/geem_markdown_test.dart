import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geem_workspace/src/theme/geem_theme.dart';
import 'package:geem_workspace/src/widgets/geem_markdown.dart';

void main() {
  testWidgets('renders styled GitHub-flavoured Markdown', (tester) async {
    const markdown = '''
# Answer

This has **bold**, _emphasis_, ~~deleted text~~, and `inline code`.

- Item
- [x] Complete

> A useful quote

```dart
void main() {}
```

| Name | Value |
| --- | ---: |
| Geem | 1 |

---

[Open Geem](https://geem.ai)

![remote diagram](https://example.test/image.png)
''';

    await tester.pumpWidget(
      MaterialApp(
        theme: geemLightTheme(),
        home: const Scaffold(
          body: SingleChildScrollView(
            child: GeemMarkdown(data: markdown, foreground: Colors.black),
          ),
        ),
      ),
    );

    expect(find.byType(MarkdownBody), findsOneWidget);
    expect(find.text('Answer'), findsOneWidget);
    expect(find.text('Item'), findsOneWidget);
    expect(find.text('A useful quote'), findsOneWidget);
    expect(find.byType(Table), findsOneWidget);
    expect(find.byIcon(Icons.check_box), findsOneWidget);
    expect(find.text('remote diagram'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('updates partial Markdown as stream content grows', (
    tester,
  ) async {
    Widget app(String data) => MaterialApp(
      theme: geemLightTheme(),
      home: Scaffold(
        body: GeemMarkdown(data: data, foreground: Colors.black),
      ),
    );

    await tester.pumpWidget(app('## Stream'));
    expect(find.text('Stream'), findsOneWidget);

    await tester.pumpWidget(app('## Stream\n\n- First token\n- Second token'));
    expect(find.text('First token'), findsOneWidget);
    expect(find.text('Second token'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  test('allows only external HTTP(S) Markdown links', () {
    expect(isSafeGeemMarkdownLink('https://geem.ai/docs'), isTrue);
    expect(isSafeGeemMarkdownLink('http://localhost:8000/docs'), isTrue);
    expect(isSafeGeemMarkdownLink('javascript:alert(1)'), isFalse);
    expect(isSafeGeemMarkdownLink('file:///private/data'), isFalse);
    expect(isSafeGeemMarkdownLink(null), isFalse);
  });
}
