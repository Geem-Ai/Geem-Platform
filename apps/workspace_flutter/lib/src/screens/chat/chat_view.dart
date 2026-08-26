import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';

import '../../app_scope.dart';
import '../../controllers/app_controller.dart';
import '../../localization/app_strings.dart';
import '../../models/models.dart';
import '../../theme/geem_theme.dart';
import '../../widgets/geem_avatar.dart';
import '../../widgets/geem_markdown.dart';
import '../../widgets/geem_thinking_typewriter.dart';
import 'expert_navbar_dropdown.dart';

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
        if (MediaQuery.sizeOf(context).width >= 1024) const _ChatToolbar(),
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
                        const _ChatComposer(),
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
    final conversation = AppScope.of(context).activeConversation;
    final conversationTitle = conversation?.title?.trim();
    final title = conversation == null
        ? context.strings.text('newChat')
        : conversationTitle?.isNotEmpty == true
        ? conversationTitle!
        : context.strings.text('untitled');
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: context.geemTokens.border)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(
                context,
              ).textTheme.titleMedium?.copyWith(fontSize: 17),
            ),
          ),
          const SizedBox(width: 14),
          const ExpertNavbarDropdown(),
          const SizedBox(width: 12),
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
    super.key,
  });

  final List<ChatMessage> messages;
  final String userInitials;

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
    final oldLast = oldWidget.messages.isEmpty ? null : oldWidget.messages.last;
    final newLast = widget.messages.isEmpty ? null : widget.messages.last;
    final changed =
        oldWidget.messages.length != widget.messages.length ||
        oldLast?.content.length != newLast?.content.length ||
        oldLast?.citations.length != newLast?.citations.length ||
        _toolStateFingerprint(oldLast) != _toolStateFingerprint(newLast);
    if (changed && stickToBottom) _scrollAfterFrame();
  }

  String _toolStateFingerprint(ChatMessage? message) {
    if (message == null) return '';
    final activities = message.toolActivities
        .map((item) => '${item.id}:${item.status}')
        .join('|');
    return '$activities:${message.toolApproval?.status ?? ''}';
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
  const _MessageRow({required this.message, required this.userInitials});

  final ChatMessage message;
  final String userInitials;

  @override
  Widget build(BuildContext context) {
    final isUser = message.role == 'user';
    final bubbleColor = isUser
        ? GeemColors.brand
        : context.geemTokens.muted.withValues(alpha: 0.5);
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
                      horizontal: 20,
                      vertical: 16,
                    ),
                    decoration: BoxDecoration(
                      color: bubbleColor,
                      borderRadius: BorderRadiusDirectional.only(
                        topStart: const Radius.circular(16),
                        topEnd: const Radius.circular(16),
                        bottomStart: Radius.circular(isUser ? 16 : 4),
                        bottomEnd: Radius.circular(isUser ? 4 : 16),
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withValues(alpha: 0.045),
                          blurRadius: 5,
                          offset: const Offset(0, 1),
                        ),
                      ],
                    ),
                    child: _MessageBody(
                      message: message,
                      foreground: foreground,
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
  const _MessageBody({required this.message, required this.foreground});

  final ChatMessage message;
  final Color foreground;

  @override
  Widget build(BuildContext context) {
    final isWaiting = message.status == 'streaming' && message.content.isEmpty;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (message.toolActivities.isNotEmpty) ...[
          _ToolActivityList(activities: message.toolActivities),
          if (isWaiting || message.content.isNotEmpty)
            const SizedBox(height: 10),
        ],
        if (isWaiting)
          GeemThinkingTypewriter(
            messages: _thinkingMessages(context),
            semanticsLabel: context.strings.text('thinking'),
            style: TextStyle(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
              fontSize: 12.5,
            ),
          )
        else if (!message.isAssistant && message.content.isNotEmpty)
          SelectionArea(
            child: Text(
              message.content,
              style: TextStyle(color: foreground, fontSize: 14, height: 1.75),
            ),
          )
        else if (message.content.isNotEmpty)
          GeemMarkdown(data: message.content, foreground: foreground),
        if (message.status == 'streaming' && message.content.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Align(
              alignment: AlignmentDirectional.centerStart,
              child: PulsingCursor(
                width: 8,
                height: 16,
                margin: const EdgeInsetsDirectional.only(start: 4),
                color: foreground,
              ),
            ),
          ),
        if (message.status != 'streaming' && message.citations.isNotEmpty) ...[
          const SizedBox(height: 12),
          _CitationPanel(citations: message.citations),
        ],
        if (message.toolApproval != null) ...[
          const SizedBox(height: 12),
          _ToolApprovalCard(message: message),
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

class _ToolActivityList extends StatelessWidget {
  const _ToolActivityList({required this.activities});

  final List<ToolActivity> activities;

  @override
  Widget build(BuildContext context) => Column(
    key: const Key('tool-activity-list'),
    children: [
      for (final activity in activities) ...[
        _ToolActivityRow(activity: activity),
        if (activity != activities.last) const SizedBox(height: 7),
      ],
    ],
  );
}

class _ToolActivityRow extends StatelessWidget {
  const _ToolActivityRow({required this.activity});

  final ToolActivity activity;

  @override
  Widget build(BuildContext context) {
    final pending =
        activity.status == 'calling' || activity.status == 'approval_required';
    final failed =
        activity.status == 'failed' || activity.status == 'outcome_unknown';
    final succeeded = activity.status == 'succeeded';
    final cancelled = activity.status == 'cancelled';
    final brightness = Theme.of(context).brightness;
    final color = failed
        ? Theme.of(context).colorScheme.error
        : pending
        ? Theme.of(context).colorScheme.primary
        : !succeeded
        ? Theme.of(context).colorScheme.onSurfaceVariant
        : brightness == Brightness.dark
        ? Colors.green.shade300
        : Colors.green.shade800;
    return Semantics(
      container: true,
      liveRegion: true,
      child: Container(
        key: ValueKey('tool-activity-${activity.id}'),
        width: double.infinity,
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surface.withValues(alpha: 0.72),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: context.geemTokens.border),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (pending)
              SizedBox.square(
                dimension: 15,
                child: CircularProgressIndicator(
                  strokeWidth: 1.8,
                  color: color,
                ),
              )
            else
              Icon(
                failed
                    ? Icons.error_outline_rounded
                    : !succeeded
                    ? cancelled
                          ? Icons.cancel_outlined
                          : Icons.info_outline_rounded
                    : Icons.check_circle_outline_rounded,
                size: 16,
                color: color,
              ),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.build_outlined, size: 13),
                      const SizedBox(width: 5),
                      Expanded(
                        child: Text(
                          activity.toolName,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 11.5,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                      const SizedBox(width: 6),
                      Flexible(
                        child: Text(
                          _toolStatusLabel(context, activity.status),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          textAlign: TextAlign.end,
                          style: TextStyle(
                            color: color,
                            fontSize: 10.5,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ],
                  ),
                  if (activity.connectionName?.isNotEmpty == true) ...[
                    const SizedBox(height: 2),
                    Text(
                      activity.connectionName!,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.labelSmall,
                    ),
                  ],
                  if (activity.status == 'outcome_unknown') ...[
                    const SizedBox(height: 5),
                    Text(
                      context.strings.text('toolOutcomeUnknown'),
                      style: TextStyle(
                        color: Theme.of(context).colorScheme.error,
                        fontSize: 10.5,
                        height: 1.4,
                      ),
                    ),
                  ] else if (activity.status == 'failed' &&
                      activity.errorCode?.isNotEmpty == true) ...[
                    const SizedBox(height: 5),
                    Text(
                      context.strings.error(activity.errorCode),
                      style: TextStyle(
                        color: Theme.of(context).colorScheme.error,
                        fontSize: 10.5,
                        height: 1.4,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ToolApprovalCard extends StatelessWidget {
  const _ToolApprovalCard({required this.message});

  final ChatMessage message;

  @override
  Widget build(BuildContext context) {
    final approval = message.toolApproval!;
    final controller = AppScope.of(context);
    final actionable = approval.status == 'pending';
    final reviewAvailable =
        approval.arguments != null &&
        (actionable ||
            approval.status == 'approved' ||
            approval.status == 'executing');
    final busy = controller.decidingToolApprovalId == approval.id;
    return Semantics(
      container: true,
      liveRegion: true,
      child: Container(
        key: const Key('tool-approval-card'),
        width: double.infinity,
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: Colors.amber.withValues(alpha: 0.07),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: Colors.amber.withValues(alpha: 0.48)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(
                  Icons.shield_outlined,
                  size: 18,
                  color: Colors.amber.shade800,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        actionable
                            ? context.strings.text('toolApprovalRequired')
                            : _toolApprovalStatusLabel(
                                context,
                                approval.status,
                              ),
                        style: const TextStyle(
                          fontSize: 12.5,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      Text(
                        [
                          if (approval.connectionName?.isNotEmpty == true)
                            approval.connectionName!,
                          approval.toolName,
                        ].join(' · '),
                        style: Theme.of(context).textTheme.labelSmall,
                      ),
                    ],
                  ),
                ),
              ],
            ),
            if (reviewAvailable) ...[
              const SizedBox(height: 10),
              Text(
                context.strings.text('toolExactArguments'),
                style: const TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 4),
              Container(
                key: const Key('tool-approval-arguments'),
                width: double.infinity,
                constraints: const BoxConstraints(maxHeight: 208),
                padding: const EdgeInsets.all(9),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.surface,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: context.geemTokens.border),
                ),
                child: SingleChildScrollView(
                  child: Directionality(
                    textDirection: TextDirection.ltr,
                    child: SelectableText(
                      _prettyArguments(approval.arguments),
                      style: const TextStyle(
                        fontFamily: 'monospace',
                        fontSize: 10.5,
                        height: 1.45,
                      ),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 8),
              Text(
                context.strings.text('toolApprovalDisclosure'),
                style: Theme.of(
                  context,
                ).textTheme.labelSmall?.copyWith(height: 1.45),
              ),
            ],
            if (actionable && !reviewAvailable) ...[
              const SizedBox(height: 10),
              Text(
                context.strings.text('toolArgumentsUnavailable'),
                style: TextStyle(
                  color: Theme.of(context).colorScheme.error,
                  fontSize: 11,
                  height: 1.4,
                ),
              ),
            ],
            if (actionable) ...[
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  if (reviewAvailable)
                    FilledButton(
                      key: const Key('approve-tool-call'),
                      onPressed: busy
                          ? null
                          : () => unawaited(
                              controller.decideToolApproval(message, 'approve'),
                            ),
                      child: Text(context.strings.text('toolApproveOnce')),
                    ),
                  FilledButton.tonal(
                    key: const Key('deny-tool-call'),
                    onPressed: busy
                        ? null
                        : () => unawaited(
                            controller.decideToolApproval(message, 'deny'),
                          ),
                    style: FilledButton.styleFrom(
                      foregroundColor: Theme.of(context).colorScheme.error,
                    ),
                    child: Text(context.strings.text('toolDeny')),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _CitationPanel extends StatelessWidget {
  const _CitationPanel({required this.citations});

  final List<Citation> citations;

  @override
  Widget build(BuildContext context) => Theme(
    data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
    child: Material(
      color: Colors.transparent,
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
          for (final (index, citation) in citations.indexed)
            Container(
              key: ValueKey(
                citation.isTool
                    ? 'tool-citation-${citation.connectionName ?? 'unknown'}-${citation.toolCallId ?? citation.toolName ?? 'tool'}-$index'
                    : 'chunk-citation-${citation.chunkId ?? citation.documentId ?? 'source'}-$index',
              ),
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
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(
                        citation.isTool
                            ? Icons.build_outlined
                            : Icons.description_outlined,
                        size: 15,
                      ),
                      const SizedBox(width: 7),
                      Expanded(
                        child: Text(
                          citation.isTool
                              ? citation.toolTitle ??
                                    citation.toolName ??
                                    context.strings.text('tool')
                              : citation.documentTitle ??
                                    context.strings.text('source'),
                          style: const TextStyle(
                            fontWeight: FontWeight.w600,
                            fontSize: 11.5,
                          ),
                        ),
                      ),
                    ],
                  ),
                  if (citation.isTool &&
                      citation.connectionName?.isNotEmpty == true)
                    Padding(
                      padding: const EdgeInsetsDirectional.only(start: 22),
                      child: Text(
                        citation.connectionName!,
                        style: Theme.of(context).textTheme.labelSmall,
                      ),
                    ),
                  if (!citation.isTool && (citation.page ?? 0) > 0)
                    Text(
                      '${context.strings.text('page')} ${citation.page}',
                      style: Theme.of(context).textTheme.labelSmall,
                    ),
                  if (!citation.isTool &&
                      citation.snippet?.isNotEmpty == true) ...[
                    const SizedBox(height: 5),
                    Text(
                      citation.snippet!,
                      style: const TextStyle(fontSize: 11, height: 1.5),
                    ),
                  ],
                ],
              ),
            ),
        ],
      ),
    ),
  );
}

class _ChatComposer extends StatefulWidget {
  const _ChatComposer();

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
    if (controller.activeConversation == null &&
        controller.selectedExpert?.isAvailable != true) {
      return;
    }
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
    final isNewChat = controller.activeConversation == null;
    final toolTurnPending = controller.hasPendingToolTurn;
    final canSend =
        input.text.trim().isNotEmpty &&
        !controller.chatBusy &&
        (!isNewChat || selected?.isAvailable == true);
    final placeholder = toolTurnPending
        ? strings.text('toolComposerPaused')
        : isNewChat && selected?.isAvailable == true
        ? strings.text('askHint').replaceAll('{{name}}', selected!.name)
        : strings.text(isNewChat ? 'expertRequired' : 'messageHint');
    return Container(
      key: const Key('chat-composer'),
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
          if (toolTurnPending)
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(16, 10, 16, 0),
              child: Row(
                children: [
                  Icon(
                    Icons.pause_circle_outline_rounded,
                    size: 15,
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
                  const SizedBox(width: 7),
                  Expanded(
                    child: Text(
                      strings.text('toolComposerPaused'),
                      style: Theme.of(context).textTheme.labelSmall,
                    ),
                  ),
                ],
              ),
            ),
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

String _prettyArguments(Object? arguments) {
  try {
    return const JsonEncoder.withIndent('  ').convert(arguments ?? const {});
  } on JsonUnsupportedObjectError {
    return '{}';
  }
}

String _toolStatusLabel(BuildContext context, String status) =>
    switch (status) {
      'calling' => context.strings.text('toolStatusCalling'),
      'succeeded' => context.strings.text('toolStatusSucceeded'),
      'failed' => context.strings.text('toolStatusFailed'),
      'outcome_unknown' => context.strings.text('toolStatusOutcomeUnknown'),
      'approval_required' => context.strings.text('toolStatusApprovalRequired'),
      'cancelled' => context.strings.text('toolStatusCancelled'),
      _ => status,
    };

String _toolApprovalStatusLabel(BuildContext context, String status) =>
    switch (status) {
      'approved' => context.strings.text('toolApprovalApproved'),
      'denied' => context.strings.text('toolApprovalDenied'),
      'expired' => context.strings.text('toolApprovalExpired'),
      'executing' => context.strings.text('toolApprovalExecuting'),
      'executed' ||
      'completed' => context.strings.text('toolApprovalCompleted'),
      'outcome_unknown' => context.strings.text('toolStatusOutcomeUnknown'),
      _ => status,
    };

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

List<String> _thinkingMessages(BuildContext context) => [
  context.strings.text('thinking'),
  context.strings.text('thinkingCheckingSources'),
  context.strings.text('thinkingGatheringContext'),
  context.strings.text('thinkingReadingKnowledge'),
  context.strings.text('thinkingPreparingAnswer'),
  context.strings.text('thinkingLookingUp'),
];
