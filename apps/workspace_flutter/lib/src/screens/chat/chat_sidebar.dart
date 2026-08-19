import 'dart:async';

import 'package:flutter/material.dart';

import '../../app_scope.dart';
import '../../controllers/app_controller.dart';
import '../../localization/app_strings.dart';
import '../../models/models.dart';
import '../../theme/geem_theme.dart';
import '../../widgets/geem_avatar.dart';
import '../../widgets/geem_gradient_button.dart';
import '../profile/profile_screen.dart';

class ChatSidebar extends StatelessWidget {
  const ChatSidebar({this.onNavigate, super.key});

  final VoidCallback? onNavigate;

  @override
  Widget build(BuildContext context) {
    final controller = AppScope.of(context);
    final strings = context.strings;
    return SafeArea(
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 12),
            child: Row(
              children: [
                const GeemAvatar(size: 36),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    strings.text('appName'),
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
              ],
            ),
          ),
          const Divider(),
          Padding(
            padding: const EdgeInsets.all(14),
            child: GeemGradientButton(
              label: strings.text('newChat'),
              icon: Icons.add_comment_outlined,
              height: 42,
              borderRadius: 24,
              onPressed: () {
                controller.newChat();
                onNavigate?.call();
              },
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: _WorkspaceSwitcher(
              controller: controller,
              onNavigate: onNavigate,
            ),
          ),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            child: Divider(),
          ),
          Expanded(
            child: controller.workspaceLoading
                ? const _SidebarLoading()
                : ListView(
                    padding: const EdgeInsets.fromLTRB(9, 0, 9, 12),
                    children: [
                      if (controller.favoriteConversations.isNotEmpty)
                        _ConversationSection(
                          title: strings.text('favorites'),
                          conversations: controller.favoriteConversations,
                          onNavigate: onNavigate,
                        ),
                      if (controller.pinnedConversations
                          .where((item) => !item.isFavorite)
                          .isNotEmpty)
                        _ConversationSection(
                          title: strings.text('pinned'),
                          conversations: controller.pinnedConversations
                              .where((item) => !item.isFavorite)
                              .toList(growable: false),
                          onNavigate: onNavigate,
                        ),
                      _ConversationSection(
                        title: strings.text('recent'),
                        conversations: controller.recentConversations
                            .where((item) => !item.isFavorite)
                            .toList(growable: false),
                        emptyLabel: strings.text('noConversations'),
                        onNavigate: onNavigate,
                      ),
                    ],
                  ),
          ),
          const Divider(),
          _SidebarFooter(controller: controller),
        ],
      ),
    );
  }
}

class _WorkspaceSwitcher extends StatelessWidget {
  const _WorkspaceSwitcher({required this.controller, this.onNavigate});

  final AppController controller;
  final VoidCallback? onNavigate;

  @override
  Widget build(BuildContext context) {
    final current = controller.currentWorkspace;
    final strings = context.strings;
    return PopupMenuButton<String>(
      enabled: controller.workspaces.isNotEmpty,
      onSelected: (workspaceId) {
        controller.selectWorkspace(workspaceId);
        onNavigate?.call();
      },
      tooltip: strings.text('workspaces'),
      position: PopupMenuPosition.under,
      itemBuilder: (context) => controller.workspaces
          .map(
            (workspace) => PopupMenuItem<String>(
              value: workspace.id,
              child: Row(
                children: [
                  Icon(
                    workspace.id == current?.id
                        ? Icons.check_circle_rounded
                        : Icons.business_outlined,
                    size: 18,
                    color: workspace.id == current?.id
                        ? Theme.of(context).colorScheme.primary
                        : Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          workspace.name,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        Text(
                          workspace.role.name,
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
                ],
              ),
            ),
          )
          .toList(growable: false),
      child: Container(
        height: 48,
        padding: const EdgeInsets.symmetric(horizontal: 12),
        decoration: BoxDecoration(
          color: context.geemTokens.muted,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: context.geemTokens.border),
        ),
        child: Row(
          children: [
            const Icon(Icons.business_outlined, size: 19),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                current?.name ?? strings.text('workspace'),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontWeight: FontWeight.w500,
                  fontSize: 13,
                ),
              ),
            ),
            const Icon(Icons.unfold_more_rounded, size: 18),
          ],
        ),
      ),
    );
  }
}

class _ConversationSection extends StatelessWidget {
  const _ConversationSection({
    required this.title,
    required this.conversations,
    this.emptyLabel,
    this.onNavigate,
  });

  final String title;
  final List<Conversation> conversations;
  final String? emptyLabel;
  final VoidCallback? onNavigate;

  @override
  Widget build(BuildContext context) {
    if (conversations.isEmpty && emptyLabel == null) {
      return const SizedBox.shrink();
    }
    return Padding(
      padding: const EdgeInsets.only(bottom: 15),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(9, 0, 9, 5),
            child: Text(
              title.toUpperCase(),
              style: Theme.of(context).textTheme.labelSmall?.copyWith(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
                fontWeight: FontWeight.w600,
                letterSpacing: context.strings.isArabic ? 0 : 0.8,
                fontSize: 10.5,
              ),
            ),
          ),
          if (conversations.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 7),
              child: Text(
                emptyLabel!,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
              ),
            )
          else
            for (final conversation in conversations)
              _ConversationRow(
                conversation: conversation,
                onNavigate: onNavigate,
              ),
        ],
      ),
    );
  }
}

class _ConversationRow extends StatelessWidget {
  const _ConversationRow({required this.conversation, this.onNavigate});

  final Conversation conversation;
  final VoidCallback? onNavigate;

  @override
  Widget build(BuildContext context) {
    final controller = AppScope.of(context);
    final selected = controller.activeConversation?.id == conversation.id;
    final title = conversation.title?.trim().isNotEmpty == true
        ? conversation.title!.trim()
        : context.strings.text('untitled');
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 1),
      child: Material(
        color: selected
            ? Theme.of(context).colorScheme.primary.withValues(alpha: 0.1)
            : Colors.transparent,
        borderRadius: BorderRadius.circular(8),
        child: InkWell(
          onTap: () {
            controller.openConversation(conversation.id);
            onNavigate?.call();
          },
          borderRadius: BorderRadius.circular(8),
          child: Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(10, 7, 3, 7),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 12.5,
                      fontWeight: FontWeight.w500,
                      color: selected
                          ? Theme.of(context).colorScheme.primary
                          : null,
                    ),
                  ),
                ),
                if (conversation.isFavorite)
                  const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 3),
                    child: Icon(
                      Icons.star_rounded,
                      color: GeemColors.amber,
                      size: 16,
                    ),
                  ),
                _ConversationMenu(conversation: conversation),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

enum _ConversationAction { favorite, pin, rename, delete }

class _ConversationMenu extends StatelessWidget {
  const _ConversationMenu({required this.conversation});

  final Conversation conversation;

  @override
  Widget build(BuildContext context) {
    final strings = context.strings;
    final controller = AppScope.of(context, listen: false);
    return PopupMenuButton<_ConversationAction>(
      tooltip: strings.text('conversationActions'),
      padding: EdgeInsets.zero,
      iconSize: 18,
      onSelected: (action) async {
        switch (action) {
          case _ConversationAction.favorite:
            await controller.toggleFavorite(conversation);
          case _ConversationAction.pin:
            await controller.togglePinned(conversation);
          case _ConversationAction.rename:
            if (context.mounted) await _showRenameDialog(context, conversation);
          case _ConversationAction.delete:
            if (context.mounted) await _showDeleteDialog(context, conversation);
        }
      },
      itemBuilder: (context) => [
        PopupMenuItem(
          value: _ConversationAction.favorite,
          child: _MenuLabel(
            icon: conversation.isFavorite
                ? Icons.star_rounded
                : Icons.star_border_rounded,
            label: strings.text(
              conversation.isFavorite ? 'removeFavorite' : 'addFavorite',
            ),
            color: conversation.isFavorite ? GeemColors.amber : null,
          ),
        ),
        PopupMenuItem(
          value: _ConversationAction.pin,
          child: _MenuLabel(
            icon: conversation.isPinned
                ? Icons.push_pin_rounded
                : Icons.push_pin_outlined,
            label: strings.text(conversation.isPinned ? 'unpin' : 'pin'),
          ),
        ),
        PopupMenuItem(
          value: _ConversationAction.rename,
          child: _MenuLabel(
            icon: Icons.edit_outlined,
            label: strings.text('rename'),
          ),
        ),
        PopupMenuItem(
          value: _ConversationAction.delete,
          child: _MenuLabel(
            icon: Icons.delete_outline_rounded,
            label: strings.text('delete'),
            color: Theme.of(context).colorScheme.error,
          ),
        ),
      ],
      icon: Icon(
        Icons.more_horiz_rounded,
        color: Theme.of(context).colorScheme.onSurfaceVariant,
      ),
    );
  }
}

class _MenuLabel extends StatelessWidget {
  const _MenuLabel({required this.icon, required this.label, this.color});

  final IconData icon;
  final String label;
  final Color? color;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Icon(icon, size: 18, color: color),
      const SizedBox(width: 10),
      Text(label, style: TextStyle(color: color)),
    ],
  );
}

class _SidebarFooter extends StatelessWidget {
  const _SidebarFooter({required this.controller});

  final AppController controller;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.all(8),
    child: Row(
      children: [
        Expanded(
          child: Tooltip(
            message: context.strings.text('profile'),
            child: Semantics(
              button: true,
              label: context.strings.text('profile'),
              child: InkWell(
                key: const Key('sidebar-profile-button'),
                onTap: () => unawaited(openProfileScreen(context)),
                borderRadius: BorderRadius.circular(12),
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 4,
                    vertical: 5,
                  ),
                  child: Row(
                    children: [
                      CircleAvatar(
                        radius: 18,
                        backgroundColor: Theme.of(
                          context,
                        ).colorScheme.primary.withValues(alpha: 0.12),
                        foregroundColor: Theme.of(context).colorScheme.primary,
                        child: Text(
                          controller.userInitials,
                          style: const TextStyle(
                            fontWeight: FontWeight.w700,
                            fontSize: 11,
                          ),
                        ),
                      ),
                      const SizedBox(width: 9),
                      Expanded(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              controller.user?.email ?? '',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            if (controller.currentWorkspace != null)
                              Text(
                                controller.currentWorkspace!.name,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: Theme.of(context).textTheme.labelSmall
                                    ?.copyWith(
                                      color: Theme.of(
                                        context,
                                      ).colorScheme.onSurfaceVariant,
                                      fontSize: 10.5,
                                    ),
                              ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
        IconButton(
          key: const Key('sidebar-language-button'),
          onPressed: controller.toggleLocale,
          tooltip: context.strings.text('language'),
          icon: const Icon(Icons.language_rounded, size: 19),
        ),
      ],
    ),
  );
}

class _SidebarLoading extends StatelessWidget {
  const _SidebarLoading();

  @override
  Widget build(BuildContext context) => ListView.builder(
    padding: const EdgeInsets.symmetric(horizontal: 16),
    itemCount: 6,
    itemBuilder: (context, index) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 7),
      child: FractionallySizedBox(
        widthFactor: index.isEven ? 0.86 : 0.68,
        alignment: AlignmentDirectional.centerStart,
        child: Container(
          height: 12,
          decoration: BoxDecoration(
            color: context.geemTokens.muted,
            borderRadius: BorderRadius.circular(5),
          ),
        ),
      ),
    ),
  );
}

Future<void> _showRenameDialog(
  BuildContext context,
  Conversation conversation,
) async {
  final controller = AppScope.of(context, listen: false);
  final strings = context.strings;
  final input = TextEditingController(text: conversation.title ?? '');
  final result = await showDialog<String>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(strings.text('renameChat')),
      content: TextField(controller: input, autofocus: true, maxLength: 160),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: Text(strings.text('cancel')),
        ),
        FilledButton(
          onPressed: () => Navigator.pop(context, input.text),
          child: Text(strings.text('save')),
        ),
      ],
    ),
  );
  input.dispose();
  if (result?.trim().isNotEmpty == true) {
    await controller.renameConversation(conversation, result!);
  }
}

Future<void> _showDeleteDialog(
  BuildContext context,
  Conversation conversation,
) async {
  final controller = AppScope.of(context, listen: false);
  final strings = context.strings;
  final confirmed = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      icon: Icon(
        Icons.delete_outline_rounded,
        color: Theme.of(context).colorScheme.error,
      ),
      title: Text(strings.text('deleteChat')),
      content: Text(strings.text('deleteChatBody')),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context, false),
          child: Text(strings.text('cancel')),
        ),
        FilledButton(
          style: FilledButton.styleFrom(
            backgroundColor: Theme.of(context).colorScheme.error,
          ),
          onPressed: () => Navigator.pop(context, true),
          child: Text(strings.text('delete')),
        ),
      ],
    ),
  );
  if (confirmed == true) await controller.deleteConversation(conversation);
}
