import 'package:flutter/material.dart';

import '../../app_scope.dart';
import '../../localization/app_strings.dart';
import '../../theme/geem_theme.dart';

Future<void> openProfileScreen(BuildContext context) async {
  final navigator = Navigator.of(context);
  final scaffold = Scaffold.maybeOf(context);
  if (scaffold?.isDrawerOpen ?? false) {
    await navigator.maybePop();
  }
  if (!navigator.mounted) return;
  await navigator.push<void>(
    MaterialPageRoute(builder: (_) => const ProfileScreen()),
  );
}

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});

  static const screenKey = Key('profile-screen');
  static const logoutButtonKey = Key('profile-logout-button');
  static const logoutConfirmButtonKey = Key('profile-logout-confirm-button');

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  bool _loggingOut = false;

  Future<void> _showLogoutConfirmation() async {
    if (_loggingOut) return;

    final controller = AppScope.of(context, listen: false);
    final navigator = Navigator.of(context);
    final strings = context.strings;
    var dialogBusy = false;

    await showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) => StatefulBuilder(
        builder: (dialogContext, setDialogState) => PopScope(
          canPop: !dialogBusy,
          child: AlertDialog(
            title: Text(strings.text('logoutConfirmTitle')),
            content: Text(strings.text('logoutConfirmBody')),
            actions: [
              TextButton(
                onPressed: dialogBusy
                    ? null
                    : () => Navigator.of(dialogContext).pop(),
                child: Text(strings.text('cancel')),
              ),
              FilledButton(
                key: ProfileScreen.logoutConfirmButtonKey,
                style: FilledButton.styleFrom(
                  backgroundColor: Theme.of(context).colorScheme.error,
                  foregroundColor: Theme.of(context).colorScheme.onError,
                ),
                onPressed: dialogBusy
                    ? null
                    : () async {
                        setDialogState(() => dialogBusy = true);
                        if (mounted) setState(() => _loggingOut = true);

                        try {
                          await controller.logout();
                          if (navigator.mounted) {
                            navigator.popUntil((route) => route.isFirst);
                          }
                          if (mounted) setState(() => _loggingOut = false);
                        } catch (_) {
                          if (dialogContext.mounted) {
                            setDialogState(() => dialogBusy = false);
                          }
                          if (mounted) {
                            setState(() => _loggingOut = false);
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                content: Text(strings.text('errorGeneric')),
                              ),
                            );
                          }
                        }
                      },
                child: dialogBusy
                    ? Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          SizedBox.square(
                            dimension: 16,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Theme.of(context).colorScheme.onError,
                            ),
                          ),
                          const SizedBox(width: 9),
                          Text(strings.text('loggingOut')),
                        ],
                      )
                    : Text(strings.text('logout')),
              ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final controller = AppScope.of(context);
    final strings = context.strings;
    final workspace = controller.currentWorkspace;
    final theme = Theme.of(context);

    return Scaffold(
      key: ProfileScreen.screenKey,
      appBar: AppBar(
        title: Text(strings.text('profile')),
        scrolledUnderElevation: 0,
        shape: Border(bottom: BorderSide(color: context.geemTokens.border)),
      ),
      body: SafeArea(
        top: false,
        child: Align(
          alignment: Alignment.topCenter,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 640),
            child: ListView(
              padding: const EdgeInsets.fromLTRB(20, 28, 20, 32),
              children: [
                Center(
                  child: CircleAvatar(
                    radius: 44,
                    backgroundColor: theme.colorScheme.primary.withValues(
                      alpha: 0.12,
                    ),
                    foregroundColor: theme.colorScheme.primary,
                    child: Text(
                      controller.userInitials,
                      style: theme.textTheme.headlineMedium?.copyWith(
                        color: theme.colorScheme.primary,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 14),
                Text(
                  controller.user?.email ?? '',
                  textAlign: TextAlign.center,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.titleMedium,
                ),
                const SizedBox(height: 30),
                _SectionTitle(strings.text('account')),
                const SizedBox(height: 10),
                Card(
                  child: Column(
                    children: [
                      _ProfileField(
                        icon: Icons.alternate_email_rounded,
                        label: strings.text('email'),
                        value: controller.user?.email ?? '—',
                      ),
                      const Divider(),
                      _ProfileField(
                        icon: Icons.business_outlined,
                        label: strings.text('currentWorkspace'),
                        value: workspace?.name ?? '—',
                      ),
                      const Divider(),
                      _ProfileField(
                        icon: Icons.badge_outlined,
                        label: strings.text('role'),
                        value: workspace?.role.name ?? '—',
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 20),
                _SectionTitle(strings.text('preferences')),
                const SizedBox(height: 10),
                Card(
                  child: ListTile(
                    leading: const Icon(Icons.language_rounded),
                    title: Text(strings.text('languageSetting')),
                    trailing: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          strings.text('language'),
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(width: 6),
                        const Icon(Icons.chevron_right_rounded, size: 20),
                      ],
                    ),
                    onTap: _loggingOut ? null : controller.toggleLocale,
                  ),
                ),
                const SizedBox(height: 34),
                Divider(color: theme.colorScheme.error.withValues(alpha: 0.22)),
                const SizedBox(height: 18),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    key: ProfileScreen.logoutButtonKey,
                    style: FilledButton.styleFrom(
                      backgroundColor: theme.colorScheme.error,
                      foregroundColor: theme.colorScheme.onError,
                    ),
                    onPressed: _loggingOut ? null : _showLogoutConfirmation,
                    icon: _loggingOut
                        ? SizedBox.square(
                            dimension: 17,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: theme.colorScheme.onError,
                            ),
                          )
                        : const Icon(Icons.logout_rounded),
                    label: Text(
                      strings.text(_loggingOut ? 'loggingOut' : 'logout'),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.label);

  final String label;

  @override
  Widget build(BuildContext context) =>
      Text(label, style: Theme.of(context).textTheme.titleMedium);
}

class _ProfileField extends StatelessWidget {
  const _ProfileField({
    required this.icon,
    required this.label,
    required this.value,
  });

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
    child: Row(
      children: [
        Icon(
          icon,
          size: 21,
          color: Theme.of(context).colorScheme.onSurfaceVariant,
        ),
        const SizedBox(width: 13),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                label,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                value,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(
                  context,
                ).textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w500),
              ),
            ],
          ),
        ),
      ],
    ),
  );
}
