import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:url_launcher/url_launcher.dart';

import '../theme/geem_theme.dart';

/// Renders assistant replies with the same GitHub-flavoured Markdown treatment
/// used by Workspace Web. User messages intentionally remain plain text.
class GeemMarkdown extends StatelessWidget {
  const GeemMarkdown({required this.data, required this.foreground, super.key});

  final String data;
  final Color foreground;

  @override
  Widget build(BuildContext context) => MarkdownBody(
    data: data,
    selectable: true,
    styleSheet: geemMarkdownStyle(context, foreground),
    onTapLink: (_, href, _) {
      unawaited(openGeemMarkdownLink(href));
    },
    // Chat answers are text-only. Do not let Markdown load arbitrary remote
    // images; retain useful alt text instead.
    imageBuilder: (_, _, alt) => Text(
      alt ?? '',
      style: TextStyle(color: foreground, fontStyle: FontStyle.italic),
    ),
  );
}

MarkdownStyleSheet geemMarkdownStyle(BuildContext context, Color foreground) {
  final theme = Theme.of(context);
  final scheme = theme.colorScheme;
  final border = context.geemTokens.border;
  final subtleSurface = scheme.surface.withValues(
    alpha: theme.brightness == Brightness.dark ? 0.42 : 0.72,
  );
  final body = TextStyle(color: foreground, fontSize: 14, height: 2);
  final heading = body.copyWith(height: 1.4, fontWeight: FontWeight.w700);

  return MarkdownStyleSheet.fromTheme(theme).copyWith(
    p: body,
    pPadding: EdgeInsets.zero,
    a: body.copyWith(
      color: scheme.primary,
      decoration: TextDecoration.underline,
      decorationColor: scheme.primary,
    ),
    h1: heading.copyWith(fontSize: 22),
    h1Padding: const EdgeInsets.only(top: 8, bottom: 2),
    h2: heading.copyWith(fontSize: 19),
    h2Padding: const EdgeInsets.only(top: 8),
    h3: heading.copyWith(fontSize: 17, fontWeight: FontWeight.w600),
    h3Padding: const EdgeInsets.only(top: 5),
    h4: heading.copyWith(fontSize: 15, fontWeight: FontWeight.w600),
    h4Padding: const EdgeInsets.only(top: 4),
    h5: heading.copyWith(fontSize: 14, fontWeight: FontWeight.w600),
    h5Padding: const EdgeInsets.only(top: 3),
    h6: heading.copyWith(
      color: scheme.onSurfaceVariant,
      fontSize: 13,
      fontWeight: FontWeight.w600,
    ),
    h6Padding: const EdgeInsets.only(top: 3),
    strong: body.copyWith(fontWeight: FontWeight.w700),
    em: body.copyWith(fontStyle: FontStyle.italic),
    del: body.copyWith(decoration: TextDecoration.lineThrough),
    listBullet: body,
    listIndent: 24,
    listBulletPadding: const EdgeInsets.symmetric(horizontal: 3),
    checkbox: body.copyWith(color: scheme.primary),
    code: body.copyWith(
      fontFamily: 'monospace',
      fontSize: 12,
      height: 1.65,
      backgroundColor: subtleSurface,
    ),
    blockSpacing: 12,
    tableHead: body.copyWith(fontWeight: FontWeight.w700),
    tableBody: body.copyWith(fontSize: 13, height: 1.55),
    tableHeadAlign: TextAlign.start,
    tablePadding: const EdgeInsets.symmetric(vertical: 4),
    tableColumnWidth: const IntrinsicColumnWidth(),
    tableScrollbarThumbVisibility: true,
    tableBorder: TableBorder.all(color: border),
    tableCellsPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
    tableCellsDecoration: BoxDecoration(color: subtleSurface),
    tableHeadCellsDecoration: BoxDecoration(
      color: scheme.primary.withValues(alpha: 0.08),
    ),
    blockquote: body.copyWith(color: scheme.onSurfaceVariant),
    blockquotePadding: EdgeInsetsDirectional.fromSTEB(
      12,
      8,
      10,
      8,
    ).resolve(Directionality.of(context)),
    blockquoteDecoration: BoxDecoration(
      color: subtleSurface,
      border: BorderDirectional(
        start: BorderSide(color: scheme.primary, width: 3),
      ),
      borderRadius: BorderRadius.circular(8),
    ),
    codeblockPadding: const EdgeInsets.all(12),
    codeblockDecoration: BoxDecoration(
      color: subtleSurface,
      border: Border.all(color: border),
      borderRadius: BorderRadius.circular(10),
    ),
    horizontalRuleDecoration: BoxDecoration(
      border: Border(top: BorderSide(color: border)),
    ),
  );
}

bool isSafeGeemMarkdownLink(String? href) {
  final uri = href == null ? null : Uri.tryParse(href);
  return uri != null && (uri.scheme == 'https' || uri.scheme == 'http');
}

Future<void> openGeemMarkdownLink(String? href) async {
  if (!isSafeGeemMarkdownLink(href)) return;
  await launchUrl(Uri.parse(href!), mode: LaunchMode.externalApplication);
}
