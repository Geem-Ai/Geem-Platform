import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../app_scope.dart';
import '../../controllers/app_controller.dart';
import '../../localization/app_strings.dart';
import '../../models/models.dart';
import '../../theme/geem_theme.dart';
import '../../widgets/geem_avatar.dart';

class ChatView extends StatelessWidget {
  const ChatView({super.key});

  @override
  Widget build(BuildContext context) {
    final controller = AppScope.of(context);
    if (controller.workspaces.isEmpty) {
      return const _NoWorkspaceState();
    }
    if (!controller.canUseCurrentWorkspace) {
      return const _ChatUnavailableState();
    }
    if (controller.activeConversation == null) {
      return const _ChatStarter();
    }
    return const _ConversationView();
  }
}

class _NoWorkspaceState extends StatelessWidget {
  const _NoWorkspaceState();

  @override
  Widget build(BuildContext context) {
    final strings = context.strings;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 440),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 72,
                height: 72,
                decoration: BoxDecoration(
                  color: Theme.of(
                    context,
                  ).colorScheme.primary.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(22),
                ),
                child: Icon(
                  Icons.business_outlined,
                  color: Theme.of(context).colorScheme.primary,
                  size: 32,
                ),
              ),
              const SizedBox(height: 22),
              Text(
                strings.text('noWorkspacesTitle'),
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 8),
              Text(
                strings.text('noWorkspacesBody'),
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: 22),
              OutlinedButton.icon(
                onPressed: AppScope.of(context, listen: false).logout,
                icon: const Icon(Icons.logout_rounded),
                label: Text(strings.text('logout')),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ChatUnavailableState extends StatelessWidget {
  const _ChatUnavailableState();

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(28),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.lock_outline_rounded,
            size: 40,
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
          const SizedBox(height: 14),
          Text(
            context.strings.text('chatUnavailable'),
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.titleMedium,
          ),
        ],
      ),
    ),
  );
}

class _ChatStarter extends StatelessWidget {
  const _ChatStarter();

  @override
  Widget build(BuildContext context) {
    final controller = AppScope.of(context);
    final strings = context.strings;
    return Column(
      children: [
        if (controller.errorCode != null) const _ChatErrorBanner(),
        Expanded(
          child: LayoutBuilder(
            builder: (context, constraints) => SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 30),
              child: ConstrainedBox(
                constraints: BoxConstraints(
                  minHeight: constraints.maxHeight - 60,
                ),
                child: Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 768),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const GeemAvatar(size: 96, heroTag: 'geem-chat-avatar'),
                        const SizedBox(height: 24),
                        Text(
                          strings.text('starterTitle'),
                          textAlign: TextAlign.center,
                          style: Theme.of(
                            context,
                          ).textTheme.headlineMedium?.copyWith(fontSize: 30),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          strings.text('starterSubtitle'),
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.bodyLarge
                              ?.copyWith(
                                color: Theme.of(
                                  context,
                                ).colorScheme.onSurfaceVariant,
                                fontSize: 17,
                              ),
                        ),
                        const SizedBox(height: 32),
                        const _ChatComposer(showExpertPicker: true),
                        const SizedBox(height: 22),
                        Text(
                          strings.text('starterDisclaimer'),
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.bodySmall
                              ?.copyWith(
                                color: Theme.of(
                                  context,
                                ).colorScheme.onSurfaceVariant,
                              ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _ConversationView extends StatelessWidget {
  const _ConversationView();

  @override
  Widget build(BuildContext context) {
    final controller = AppScope.of(context);
    return Column(
      children: [
        if (MediaQuery.sizeOf(context).width >= 1024) const _ChatToolbar(),
        if (controller.errorCode != null) const _ChatErrorBanner(),
        Expanded(
          child: controller.conversationLoading && controller.messages.isEmpty
              ? const Center(child: CircularProgressIndicator())
              : _MessageList(
                  key: ValueKey(controller.activeConversation!.id),
                  messages: controller.messages,
                  userInitials: controller.userInitials,
                  streaming: controller.streaming,
                  streamStage: controller.streamStage,
                ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 20),
          child: const Center(
            child: SizedBox(width: 768, child: _ChatComposer()),
          ),
        ),
      ],
    );
  }
}

class _ChatToolbar extends StatelessWidget {
  const _ChatToolbar();

  @override
  Widget build(BuildContext context) {
    final conversation = AppScope.of(context).activeConversation!;
    final title = conversation.title?.trim().isNotEmpty == true
        ? conversation.title!.trim()
        : context.strings.text('untitled');
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: context.geemTokens.border)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(
                    context,
                  ).textTheme.titleMedium?.copyWith(fontSize: 17),
                ),
                if (conversation.expert != null) ...[
                  const SizedBox(height: 3),
                  Row(
                    children: [
                      Text(
                        conversation.expert!.name,
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: Theme.of(context).colorScheme.onSurfaceVariant,
                        ),
                      ),
                      if (conversation.expert!.ownership == 'platform') ...[
                        const SizedBox(width: 6),
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 6,
                            vertical: 1,
                          ),
                          decoration: BoxDecoration(
                            color: Theme.of(
                              context,
                            ).colorScheme.primary.withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: Text(
                            'Geem',
                            style: TextStyle(
                              color: Theme.of(context).colorScheme.primary,
                              fontSize: 9.5,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),
                ],
              ],
            ),
          ),
          const GeemAvatar(size: 38),
        ],
      ),
    );
  }
}

class _ChatErrorBanner extends StatelessWidget {
  const _ChatErrorBanner();

  @override
  Widget build(BuildContext context) {
    final controller = AppScope.of(context);
    final scheme = Theme.of(context).colorScheme;
    return Container(
      width: double.infinity,
      color: scheme.errorContainer,
      padding: const EdgeInsetsDirectional.fromSTEB(18, 9, 8, 9),
      child: Row(
        children: [
          Icon(
            Icons.error_outline_rounded,
            size: 18,
            color: scheme.onErrorContainer,
          ),
          const SizedBox(width: 9),
          Expanded(
            child: Text(
              context.strings.error(
                controller.errorCode,
                controller.errorMessage,
              ),
              style: TextStyle(color: scheme.onErrorContainer, fontSize: 12.5),
            ),
          ),
          TextButton(
            onPressed: controller.workspaceLoading
                ? null
                : controller.reloadWorkspace,
            style: TextButton.styleFrom(
              foregroundColor: scheme.onErrorContainer,
              visualDensity: VisualDensity.compact,
            ),
            child: Text(context.strings.text('reload')),
          ),
          IconButton(
            onPressed: controller.clearFeedback,
            icon: Icon(
              Icons.close_rounded,
              color: scheme.onErrorContainer,
              size: 18,
            ),
            visualDensity: VisualDensity.compact,
          ),
        ],
      ),
    );
  }
}

class _MessageList extends StatefulWidget {
  const _MessageList({
    required this.messages,
    required this.userInitials,
    required this.streaming,
    required this.streamStage,
    super.key,
  });

  final List<ChatMessage> messages;
  final String userInitials;
  final bool streaming;
  final String? streamStage;

  @override
  State<_MessageList> createState() => _MessageListState();
}

class _MessageListState extends State<_MessageList> {
  final scrollController = ScrollController();
  bool stickToBottom = true;

  @override
  void initState() {
    super.initState();
    scrollController.addListener(_trackScrollPosition);
    _scrollAfterFrame(jump: true);
  }

  void _trackScrollPosition() {
    if (!scrollController.hasClients) return;
    final distance =
        scrollController.position.maxScrollExtent - scrollController.offset;
    final next = distance <= 96;
    if (next == stickToBottom) return;
    setState(() => stickToBottom = next);
  }

  @override
  void didUpdateWidget(covariant _MessageList oldWidget) {
    super.didUpdateWidget(oldWidget);
    final changed =
        oldWidget.messages.length != widget.messages.length ||
        (widget.messages.isNotEmpty &&
            oldWidget.messages.isNotEmpty &&
            oldWidget.messages.last.content.length !=
                widget.messages.last.content.length);
    if (changed && stickToBottom) _scrollAfterFrame();
  }

  void _scrollAfterFrame({bool jump = false}) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !scrollController.hasClients) return;
      final target = scrollController.position.maxScrollExtent;
      if (jump) {
        scrollController.jumpTo(target);
      } else {
        scrollController.animateTo(
          target,
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  void dispose() {
    scrollController.removeListener(_trackScrollPosition);
    scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Stack(
    children: [
      ListView.builder(
        controller: scrollController,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        itemCount: widget.messages.length,
        itemBuilder: (context, index) => _MessageRow(
          message: widget.messages[index],
          userInitials: widget.userInitials,
          streamStage: index == widget.messages.length - 1
              ? widget.streamStage
              : null,
        ),
      ),
      if (!stickToBottom)
        Positioned.directional(
          textDirection: Directionality.of(context),
          end: 16,
          bottom: 10,
          child: FloatingActionButton.small(
            heroTag: null,
            tooltip: context.strings.text('jumpToLatest'),
            onPressed: () {
              setState(() => stickToBottom = true);
              _scrollAfterFrame();
            },
            child: const Icon(Icons.keyboard_arrow_down_rounded),
          ),
        ),
    ],
  );
}

class _MessageRow extends StatelessWidget {
  const _MessageRow({
    required this.message,
    required this.userInitials,
    required this.streamStage,
  });

  final ChatMessage message;
  final String userInitials;
  final String? streamStage;

  @override
  Widget build(BuildContext context) {
    final isUser = message.role == 'user';
    final bubbleColor = isUser ? GeemColors.brand : context.geemTokens.muted;
    final foreground = isUser
        ? Colors.white
        : Theme.of(context).colorScheme.onSurface;
    final alignment = isUser ? MainAxisAlignment.end : MainAxisAlignment.start;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: alignment,
        children: [
          if (!isUser) ...[
            const GeemAvatar(size: 38),
            const SizedBox(width: 10),
          ],
          Flexible(
            child: ConstrainedBox(
              constraints: BoxConstraints(maxWidth: isUser ? 620 : 760),
              child: Column(
                crossAxisAlignment: isUser
                    ? CrossAxisAlignment.end
                    : CrossAxisAlignment.start,
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 16,
                      vertical: 13,
                    ),
                    decoration: BoxDecoration(
                      color: bubbleColor,
                      borderRadius: BorderRadiusDirectional.only(
                        topStart: const Radius.circular(16),
                        topEnd: const Radius.circular(16),
                        bottomStart: Radius.circular(isUser ? 16 : 4),
                        bottomEnd: Radius.circular(isUser ? 4 : 16),
                      ),
                    ),
                    child: _MessageBody(
                      message: message,
                      foreground: foreground,
                      streamStage: streamStage,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    _formatTime(message.createdAt),
                    style: Theme.of(context).textTheme.labelSmall?.copyWith(
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                      fontSize: 10,
                    ),
                  ),
                ],
              ),
            ),
          ),
          if (isUser) ...[
            const SizedBox(width: 10),
            CircleAvatar(
              radius: 19,
              backgroundColor: Theme.of(
                context,
              ).colorScheme.primary.withValues(alpha: 0.12),
              foregroundColor: Theme.of(context).colorScheme.primary,
              child: Text(
                userInitials,
                style: const TextStyle(
                  fontWeight: FontWeight.w700,
                  fontSize: 10.5,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _MessageBody extends StatelessWidget {
  const _MessageBody({
    required this.message,
    required this.foreground,
    required this.streamStage,
  });

  final ChatMessage message;
  final Color foreground;
  final String? streamStage;

  @override
  Widget build(BuildContext context) {
    final isWaiting = message.status == 'streaming' && message.content.isEmpty;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (isWaiting)
          _ThinkingStatus(stage: streamStage)
        else if (!message.isAssistant)
          SelectionArea(
            child: Text(
              message.content,
              style: TextStyle(color: foreground, fontSize: 14, height: 1.75),
            ),
          )
        else
          MarkdownBody(
            data: message.content,
            selectable: true,
            styleSheet: _markdownStyle(context, foreground),
            onTapLink: (_, href, _) => _openMarkdownLink(href),
            imageBuilder: (_, _, alt) => Text(
              alt ?? '',
              style: TextStyle(color: foreground, fontStyle: FontStyle.italic),
            ),
          ),
        if (message.status == 'streaming' && message.content.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 7),
            child: SizedBox(
              width: 14,
              child: LinearProgressIndicator(
                minHeight: 2,
                color: Theme.of(context).colorScheme.primary,
                backgroundColor: Colors.transparent,
              ),
            ),
          ),
        if (message.citations.isNotEmpty) ...[
          const SizedBox(height: 12),
          _CitationPanel(citations: message.citations),
        ],
        if (message.isFailed && message.isAssistant) ...[
          const SizedBox(height: 10),
          Text(
            message.errorMessage ?? context.strings.error('unknown'),
            style: TextStyle(
              color: Theme.of(context).colorScheme.error,
              fontSize: 12,
            ),
          ),
          const SizedBox(height: 4),
          TextButton.icon(
            onPressed: () =>
                AppScope.of(context, listen: false).retryMessage(message),
            style: TextButton.styleFrom(
              padding: EdgeInsets.zero,
              visualDensity: VisualDensity.compact,
            ),
            icon: const Icon(Icons.refresh_rounded, size: 16),
            label: Text(context.strings.text('retry')),
          ),
        ],
      ],
    );
  }
}

class _ThinkingStatus extends StatelessWidget {
  const _ThinkingStatus({required this.stage});

  final String? stage;

  @override
  Widget build(BuildContext context) {
    final key = switch (stage) {
      'retrieving' => 'retrieving',
      'retrying' => 'retrying',
      'generating' => 'generating',
      _ => 'thinking',
    };
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox.square(
          dimension: 14,
          child: CircularProgressIndicator(
            strokeWidth: 2,
            color: Theme.of(context).colorScheme.primary,
          ),
        ),
        const SizedBox(width: 9),
        Text(
          context.strings.text(key),
          style: TextStyle(
            color: Theme.of(context).colorScheme.onSurfaceVariant,
            fontSize: 12.5,
          ),
        ),
      ],
    );
  }
}

class _CitationPanel extends StatelessWidget {
  const _CitationPanel({required this.citations});

  final List<Citation> citations;

  @override
  Widget build(BuildContext context) => Theme(
    data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
    child: ExpansionTile(
      tilePadding: EdgeInsets.zero,
      childrenPadding: EdgeInsets.zero,
      dense: true,
      visualDensity: VisualDensity.compact,
      leading: const Icon(Icons.menu_book_outlined, size: 17),
      title: Text(
        '${context.strings.text('sources')} (${citations.length})',
        style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 12),
      ),
      children: [
        for (final citation in citations)
          Container(
            width: double.infinity,
            margin: const EdgeInsets.only(bottom: 7),
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: Theme.of(
                context,
              ).colorScheme.surface.withValues(alpha: 0.72),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: context.geemTokens.border),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  citation.documentTitle,
                  style: const TextStyle(
                    fontWeight: FontWeight.w600,
                    fontSize: 11.5,
                  ),
                ),
                if (citation.page > 0)
                  Text(
                    '${context.strings.text('page')} ${citation.page}',
                    style: Theme.of(context).textTheme.labelSmall,
                  ),
                if (citation.snippet.isNotEmpty) ...[
                  const SizedBox(height: 5),
                  Text(
                    citation.snippet,
                    style: const TextStyle(fontSize: 11, height: 1.5),
                  ),
                ],
              ],
            ),
          ),
      ],
    ),
  );
}

class _ChatComposer extends StatefulWidget {
  const _ChatComposer({this.showExpertPicker = false});

  final bool showExpertPicker;

  @override
  State<_ChatComposer> createState() => _ChatComposerState();
}

class _ChatComposerState extends State<_ChatComposer> {
  final input = TextEditingController();
  final focusNode = FocusNode();

  @override
  void dispose() {
    input.dispose();
    focusNode.dispose();
    super.dispose();
  }

  void send(AppController controller) {
    final value = input.text.trim();
    if (value.isEmpty || controller.chatBusy) return;
    if (widget.showExpertPicker && controller.selectedExpert == null) return;
    input.clear();
    setState(() {});
    unawaited(controller.sendMessage(value));
    focusNode.requestFocus();
  }

  @override
  Widget build(BuildContext context) {
    final controller = AppScope.of(context);
    final strings = context.strings;
    final selected = controller.selectedExpert;
    final canSend =
        input.text.trim().isNotEmpty &&
        !controller.chatBusy &&
        (!widget.showExpertPicker || selected != null);
    final placeholder = widget.showExpertPicker && selected != null
        ? strings.text('askHint').replaceAll('{{name}}', selected.name)
        : strings.text(
            widget.showExpertPicker ? 'expertRequired' : 'messageHint',
          );
    return Container(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: context.geemTokens.border),
        boxShadow: [
          BoxShadow(
            color: GeemColors.brand.withValues(alpha: 0.08),
            blurRadius: 26,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Column(
        children: [
          if (widget.showExpertPicker) ...[
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(14, 8, 8, 5),
              child: Row(
                children: [
                  Icon(
                    Icons.auto_awesome_rounded,
                    size: 18,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: DropdownButtonHideUnderline(
                      child: DropdownButton<String>(
                        isExpanded: true,
                        value: controller.selectedExpertId,
                        hint: Text(strings.text('selectExpert')),
                        borderRadius: BorderRadius.circular(14),
                        items: controller.experts
                            .where((expert) => expert.isAvailable)
                            .map(
                              (expert) => DropdownMenuItem(
                                value: expert.id,
                                child: Text(
                                  expert.name,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(
                                    fontSize: 13,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                              ),
                            )
                            .toList(growable: false),
                        onChanged: controller.chatBusy
                            ? null
                            : (value) {
                                if (value != null) {
                                  controller.selectExpert(value);
                                }
                              },
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const Divider(),
          ],
          Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(16, 9, 9, 9),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Expanded(
                  child: TextField(
                    controller: input,
                    focusNode: focusNode,
                    enabled: !controller.chatBusy,
                    minLines: 1,
                    maxLines: 6,
                    maxLength: 32000,
                    buildCounter:
                        (
                          _, {
                          required currentLength,
                          required isFocused,
                          maxLength,
                        }) => null,
                    textCapitalization: TextCapitalization.sentences,
                    onChanged: (_) => setState(() {}),
                    decoration: InputDecoration(
                      hintText: placeholder,
                      filled: false,
                      border: InputBorder.none,
                      enabledBorder: InputBorder.none,
                      focusedBorder: InputBorder.none,
                      contentPadding: const EdgeInsets.symmetric(vertical: 7),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                IconButton.filled(
                  onPressed: controller.streaming
                      ? controller.stopStreaming
                      : controller.sending
                      ? null
                      : canSend
                      ? () => send(controller)
                      : null,
                  tooltip: strings.text(
                    controller.streaming
                        ? 'stop'
                        : controller.sending
                        ? 'sendingMessage'
                        : 'send',
                  ),
                  icon: controller.sending
                      ? const SizedBox.square(
                          dimension: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : Icon(
                          controller.streaming
                              ? Icons.stop_rounded
                              : Icons.arrow_upward_rounded,
                          size: 20,
                        ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

String _formatTime(DateTime value) {
  final local = value.toLocal();
  final hour = local.hour.toString().padLeft(2, '0');
  final minute = local.minute.toString().padLeft(2, '0');
  final now = DateTime.now();
  if (now.year == local.year &&
      now.month == local.month &&
      now.day == local.day) {
    return '$hour:$minute';
  }
  return '${local.day}/${local.month} · $hour:$minute';
}

MarkdownStyleSheet _markdownStyle(BuildContext context, Color foreground) {
  final theme = Theme.of(context);
  final border = context.geemTokens.border;
  final body = TextStyle(color: foreground, fontSize: 14, height: 1.75);
  return MarkdownStyleSheet.fromTheme(theme).copyWith(
    p: body,
    a: body.copyWith(
      color: theme.colorScheme.primary,
      decoration: TextDecoration.underline,
      decorationColor: theme.colorScheme.primary,
    ),
    h1: body.copyWith(fontSize: 22, fontWeight: FontWeight.w700),
    h2: body.copyWith(fontSize: 19, fontWeight: FontWeight.w700),
    h3: body.copyWith(fontSize: 17, fontWeight: FontWeight.w600),
    h4: body.copyWith(fontSize: 15, fontWeight: FontWeight.w600),
    strong: body.copyWith(fontWeight: FontWeight.w700),
    em: body.copyWith(fontStyle: FontStyle.italic),
    listBullet: body,
    code: body.copyWith(
      fontFamily: 'monospace',
      fontSize: 12.5,
      backgroundColor: theme.colorScheme.surface.withValues(alpha: 0.7),
    ),
    blockSpacing: 10,
    tableColumnWidth: const IntrinsicColumnWidth(),
    tableScrollbarThumbVisibility: true,
    tableBorder: TableBorder.all(color: border),
    tableCellsPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
    blockquotePadding: EdgeInsetsDirectional.fromSTEB(
      12,
      8,
      10,
      8,
    ).resolve(Directionality.of(context)),
    blockquoteDecoration: BoxDecoration(
      color: theme.colorScheme.surface.withValues(alpha: 0.55),
      border: BorderDirectional(
        start: BorderSide(color: theme.colorScheme.primary, width: 3),
      ),
      borderRadius: BorderRadius.circular(8),
    ),
    codeblockPadding: const EdgeInsets.all(12),
    codeblockDecoration: BoxDecoration(
      color: theme.colorScheme.surface.withValues(alpha: 0.75),
      border: Border.all(color: border),
      borderRadius: BorderRadius.circular(10),
    ),
  );
}

Future<void> _openMarkdownLink(String? href) async {
  final uri = href == null ? null : Uri.tryParse(href);
  if (uri == null || (uri.scheme != 'https' && uri.scheme != 'http')) return;
  await launchUrl(uri, mode: LaunchMode.externalApplication);
}
