import 'package:flutter/material.dart';

import '../../app_scope.dart';
import '../../localization/app_strings.dart';
import '../../theme/geem_theme.dart';
import '../../widgets/geem_avatar.dart';
import 'chat_sidebar.dart';
import 'chat_view.dart';
import 'expert_navbar_dropdown.dart';

class ChatShell extends StatelessWidget {
  const ChatShell({super.key});

  @override
  Widget build(BuildContext context) {
    final desktop = MediaQuery.sizeOf(context).width >= 1024;
    return desktop ? const _DesktopChatShell() : const _MobileChatShell();
  }
}

class _DesktopChatShell extends StatelessWidget {
  const _DesktopChatShell();

  @override
  Widget build(BuildContext context) => Scaffold(
    backgroundColor: context.geemTokens.muted,
    body: Padding(
      padding: const EdgeInsets.all(10),
      child: Row(
        children: [
          Container(
            width: 270,
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.surface,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: context.geemTokens.border),
            ),
            clipBehavior: Clip.antiAlias,
            child: const ChatSidebar(),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Container(
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: context.geemTokens.border),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.035),
                    blurRadius: 20,
                    offset: const Offset(0, 8),
                  ),
                ],
              ),
              clipBehavior: Clip.antiAlias,
              child: const ChatView(),
            ),
          ),
        ],
      ),
    ),
  );
}

class _MobileChatShell extends StatelessWidget {
  const _MobileChatShell();

  @override
  Widget build(BuildContext context) {
    final controller = AppScope.of(context);
    final title = controller.activeConversation?.title?.trim();
    return Scaffold(
      appBar: AppBar(
        toolbarHeight: 60,
        scrolledUnderElevation: 0,
        titleSpacing: 4,
        title: Row(
          children: [
            const GeemAvatar(size: 32),
            const SizedBox(width: 9),
            Expanded(
              child: controller.activeConversation == null
                  ? const ExpertNavbarDropdown(compact: true)
                  : Text(
                      title?.isNotEmpty == true
                          ? title!
                          : context.strings.text('untitled'),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
            ),
          ],
        ),
        actions: [
          Padding(
            padding: const EdgeInsetsDirectional.only(end: 12),
            child: CircleAvatar(
              radius: 16,
              backgroundColor: Theme.of(
                context,
              ).colorScheme.primary.withValues(alpha: 0.11),
              foregroundColor: Theme.of(context).colorScheme.primary,
              child: Text(
                controller.userInitials,
                style: const TextStyle(
                  fontSize: 9.5,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ),
        ],
        shape: Border(bottom: BorderSide(color: context.geemTokens.border)),
      ),
      drawer: Drawer(
        width: 300,
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadiusDirectional.horizontal(
            end: Radius.circular(18),
          ),
        ),
        child: Builder(
          builder: (drawerContext) => ChatSidebar(
            onNavigate: () => Navigator.of(drawerContext).maybePop(),
          ),
        ),
      ),
      body: const SafeArea(top: false, child: ChatView()),
    );
  }
}
