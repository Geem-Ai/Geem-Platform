import 'package:flutter/material.dart';

import '../../app_scope.dart';
import '../../localization/app_strings.dart';
import '../../models/models.dart';
import '../../theme/geem_theme.dart';

class ExpertNavbarDropdown extends StatelessWidget {
  const ExpertNavbarDropdown({this.compact = false, super.key});

  static const navbarKey = ValueKey<String>('expert-navbar-dropdown');

  final bool compact;

  @override
  Widget build(BuildContext context) {
    final controller = AppScope.of(context);
    final conversation = controller.activeConversation;
    final height = compact ? 38.0 : 44.0;
    final iconSize = compact ? 16.0 : 18.0;
    final horizontalPadding = compact ? 9.0 : 12.0;

    return Container(
      key: navbarKey,
      height: height,
      constraints: BoxConstraints(
        minWidth: compact ? 140 : 190,
        maxWidth: compact ? 220 : 300,
      ),
      padding: EdgeInsetsDirectional.only(
        start: horizontalPadding,
        end: compact ? 4 : 6,
      ),
      decoration: BoxDecoration(
        color: context.geemTokens.muted,
        borderRadius: BorderRadius.circular(compact ? 10 : 12),
        border: Border.all(color: context.geemTokens.border),
      ),
      child: conversation == null
          ? _ReadyExpertDropdown(compact: compact, iconSize: iconSize)
          : _LockedConversationExpert(
              conversation: conversation,
              compact: compact,
              iconSize: iconSize,
            ),
    );
  }
}

class _ReadyExpertDropdown extends StatelessWidget {
  const _ReadyExpertDropdown({required this.compact, required this.iconSize});

  final bool compact;
  final double iconSize;

  @override
  Widget build(BuildContext context) {
    final controller = AppScope.of(context);
    final strings = context.strings;
    final readyExperts = controller.experts
        .where((expert) => expert.isAvailable)
        .toList(growable: false);
    final selectedId =
        readyExperts.any((expert) => expert.id == controller.selectedExpertId)
        ? controller.selectedExpertId
        : null;
    final disabled = controller.chatBusy || readyExperts.isEmpty;
    final hint = Text(
      strings.text('selectExpert'),
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      style: TextStyle(fontSize: compact ? 12.5 : 13.5),
    );

    return Row(
      children: [
        Icon(
          Icons.auto_awesome_rounded,
          size: iconSize,
          color: Theme.of(context).colorScheme.primary,
        ),
        SizedBox(width: compact ? 6 : 8),
        Expanded(
          child: DropdownButtonHideUnderline(
            child: DropdownButton<String>(
              isExpanded: true,
              value: selectedId,
              hint: hint,
              disabledHint: hint,
              borderRadius: BorderRadius.circular(14),
              menuMaxHeight: 360,
              icon: Icon(
                Icons.keyboard_arrow_down_rounded,
                size: compact ? 19 : 21,
              ),
              items: readyExperts
                  .map(
                    (expert) => DropdownMenuItem<String>(
                      value: expert.id,
                      child: Text(
                        expert.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: compact ? 12.5 : 13.5,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                  )
                  .toList(growable: false),
              onChanged: disabled
                  ? null
                  : (expertId) {
                      if (expertId != null) {
                        controller.selectExpert(expertId);
                      }
                    },
            ),
          ),
        ),
      ],
    );
  }
}

class _LockedConversationExpert extends StatelessWidget {
  const _LockedConversationExpert({
    required this.conversation,
    required this.compact,
    required this.iconSize,
  });

  final Conversation conversation;
  final bool compact;
  final double iconSize;

  @override
  Widget build(BuildContext context) {
    final controller = AppScope.of(context);
    final embeddedName = conversation.expert?.name.trim() ?? '';
    final matchingExpert = controller.experts.cast<Expert?>().firstWhere(
      (expert) => expert?.id == conversation.expertId,
      orElse: () => null,
    );
    final knownName = matchingExpert?.name.trim() ?? '';
    final name = embeddedName.isNotEmpty
        ? embeddedName
        : knownName.isNotEmpty
        ? knownName
        : conversation.expertId.isNotEmpty
        ? conversation.expertId
        : context.strings.text('selectExpert');

    return Tooltip(
      message: name,
      child: Row(
        children: [
          Icon(
            Icons.auto_awesome_rounded,
            size: iconSize,
            color: Theme.of(context).colorScheme.primary,
          ),
          SizedBox(width: compact ? 6 : 8),
          Expanded(
            child: Text(
              name,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: compact ? 12.5 : 13.5,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
          SizedBox(width: compact ? 5 : 7),
          Icon(
            Icons.lock_outline_rounded,
            size: compact ? 15 : 17,
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
          const SizedBox(width: 3),
        ],
      ),
    );
  }
}
