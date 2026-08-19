import 'package:flutter/material.dart';

import '../../app_scope.dart';
import '../../controllers/app_controller.dart';
import '../../localization/app_strings.dart';
import '../../theme/geem_theme.dart';
import '../../widgets/geem_avatar.dart';
import '../../widgets/geem_gradient_button.dart';

class AuthScreen extends StatelessWidget {
  const AuthScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final controller = AppScope.of(context);
    final isDesktop = MediaQuery.sizeOf(context).width >= 1024;
    return Scaffold(
      body: DecoratedBox(
        decoration: BoxDecoration(
          color: Theme.of(context).scaffoldBackgroundColor,
          gradient: isDesktop
              ? null
              : RadialGradient(
                  center: const Alignment(-0.8, -0.9),
                  radius: 1.25,
                  colors: [
                    Theme.of(
                      context,
                    ).colorScheme.primary.withValues(alpha: 0.12),
                    Theme.of(context).scaffoldBackgroundColor,
                  ],
                ),
        ),
        child: SafeArea(
          child: Padding(
            padding: EdgeInsets.all(isDesktop ? 20 : 16),
            child: isDesktop
                ? _DesktopAuth(controller: controller)
                : _MobileAuth(controller: controller),
          ),
        ),
      ),
    );
  }
}

class _DesktopAuth extends StatelessWidget {
  const _DesktopAuth({required this.controller});

  final AppController controller;

  @override
  Widget build(BuildContext context) => Center(
    child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 1500),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(30),
        child: DecoratedBox(
          decoration: BoxDecoration(
            border: Border.all(color: context.geemTokens.border),
          ),
          child: Row(
            children: [
              const Expanded(flex: 10, child: _BrandPanel()),
              Expanded(
                flex: 11,
                child: ColoredBox(
                  color: Theme.of(context).colorScheme.surface,
                  child: _AuthFormArea(controller: controller),
                ),
              ),
            ],
          ),
        ),
      ),
    ),
  );
}

class _MobileAuth extends StatelessWidget {
  const _MobileAuth({required this.controller});

  final AppController controller;

  @override
  Widget build(BuildContext context) => Column(
    children: [
      Row(
        children: [
          const GeemAvatar(size: 38),
          const SizedBox(width: 10),
          Text(
            context.strings.text('appName'),
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const Spacer(),
          _LanguageButton(controller: controller),
        ],
      ),
      const SizedBox(height: 12),
      Expanded(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(vertical: 20),
            child: _AuthCard(controller: controller),
          ),
        ),
      ),
    ],
  );
}

class _AuthFormArea extends StatelessWidget {
  const _AuthFormArea({required this.controller});

  final AppController controller;

  @override
  Widget build(BuildContext context) => Stack(
    children: [
      Positioned.directional(
        textDirection: Directionality.of(context),
        top: 22,
        end: 24,
        child: _LanguageButton(controller: controller),
      ),
      Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 40, vertical: 64),
          child: _AuthCard(controller: controller),
        ),
      ),
    ],
  );
}

class _LanguageButton extends StatelessWidget {
  const _LanguageButton({required this.controller});

  final AppController controller;

  @override
  Widget build(BuildContext context) => TextButton.icon(
    onPressed: controller.toggleLocale,
    icon: const Icon(Icons.language_rounded, size: 18),
    label: Text(context.strings.text('language')),
  );
}

class _BrandPanel extends StatelessWidget {
  const _BrandPanel();

  @override
  Widget build(BuildContext context) {
    final strings = context.strings;
    return DecoratedBox(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF0A2739), GeemColors.brand2, Color(0xFF28627F)],
        ),
      ),
      child: Stack(
        fit: StackFit.expand,
        children: [
          const Positioned(top: -100, left: -80, child: _GlowOrb(size: 320)),
          const Positioned(
            bottom: -160,
            right: -100,
            child: _GlowOrb(size: 420),
          ),
          Padding(
            padding: const EdgeInsets.all(52),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const GeemAvatar(size: 48),
                    const SizedBox(width: 14),
                    Text(
                      strings.text('appName'),
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 22,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
                const Spacer(),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 500),
                  child: Text(
                    strings.isArabic
                        ? 'معرفتك، في محادثة واحدة.'
                        : 'Your knowledge, one conversation away.',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 42,
                      height: 1.25,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                const SizedBox(height: 18),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 470),
                  child: Text(
                    strings.isArabic
                        ? 'اسأل خبراء مساحة عملك واحصل على إجابات موثوقة من مصادر فريقك.'
                        : 'Ask your workspace experts and get grounded answers from your team’s sources.',
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.76),
                      fontSize: 18,
                      height: 1.65,
                    ),
                  ),
                ),
                const Spacer(),
                Text(
                  '© ${DateTime.now().year} Geem',
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.58),
                    fontSize: 12,
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

class _GlowOrb extends StatelessWidget {
  const _GlowOrb({required this.size});

  final double size;

  @override
  Widget build(BuildContext context) => Container(
    width: size,
    height: size,
    decoration: BoxDecoration(
      shape: BoxShape.circle,
      gradient: RadialGradient(
        colors: [Colors.white.withValues(alpha: 0.15), Colors.transparent],
      ),
    ),
  );
}

class _AuthCard extends StatelessWidget {
  const _AuthCard({required this.controller});

  final AppController controller;

  @override
  Widget build(BuildContext context) {
    final child = switch (controller.authPage) {
      AuthPage.login => const _LoginForm(key: ValueKey('login')),
      AuthPage.forgotPassword => const _ForgotPasswordForm(
        key: ValueKey('forgot'),
      ),
      AuthPage.checkEmail => const _CheckEmailForm(
        key: ValueKey('check-email'),
      ),
      AuthPage.verifyEmail => const _VerifyEmailForm(
        key: ValueKey('verify-email'),
      ),
      AuthPage.resetPassword => const _ResetPasswordForm(
        key: ValueKey('reset-password'),
      ),
    };
    return ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 460),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surface.withValues(alpha: 0.96),
          borderRadius: BorderRadius.circular(28),
          border: Border.all(color: context.geemTokens.border),
          boxShadow: [
            BoxShadow(
              color: GeemColors.brand.withValues(alpha: 0.11),
              blurRadius: 44,
              offset: const Offset(0, 20),
            ),
          ],
        ),
        child: Padding(
          padding: const EdgeInsets.all(30),
          child: AnimatedSwitcher(
            duration: const Duration(milliseconds: 220),
            child: child,
          ),
        ),
      ),
    );
  }
}

class _FormHeader extends StatelessWidget {
  const _FormHeader({
    required this.icon,
    required this.title,
    required this.subtitle,
  });

  final IconData icon;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Container(
        width: 56,
        height: 56,
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Icon(
          icon,
          color: Theme.of(context).colorScheme.primary,
          size: 26,
        ),
      ),
      const SizedBox(height: 22),
      Text(title, style: Theme.of(context).textTheme.headlineMedium),
      const SizedBox(height: 8),
      Text(
        subtitle,
        style: Theme.of(context).textTheme.bodyMedium?.copyWith(
          color: Theme.of(context).colorScheme.onSurfaceVariant,
        ),
      ),
    ],
  );
}

class _Feedback extends StatelessWidget {
  const _Feedback();

  @override
  Widget build(BuildContext context) {
    final controller = AppScope.of(context);
    if (controller.errorCode == null && controller.errorMessage == null) {
      return const SizedBox.shrink();
    }
    final scheme = Theme.of(context).colorScheme;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(13),
      decoration: BoxDecoration(
        color: scheme.errorContainer,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            Icons.error_outline_rounded,
            color: scheme.onErrorContainer,
            size: 19,
          ),
          const SizedBox(width: 9),
          Expanded(
            child: Text(
              context.strings.error(
                controller.errorCode,
                controller.errorMessage,
              ),
              style: TextStyle(color: scheme.onErrorContainer, fontSize: 13),
            ),
          ),
        ],
      ),
    );
  }
}

class _PasswordField extends StatefulWidget {
  const _PasswordField({
    required this.controller,
    required this.label,
    this.textInputAction,
    this.onSubmitted,
  });

  final TextEditingController controller;
  final String label;
  final TextInputAction? textInputAction;
  final VoidCallback? onSubmitted;

  @override
  State<_PasswordField> createState() => _PasswordFieldState();
}

class _PasswordFieldState extends State<_PasswordField> {
  bool hidden = true;

  @override
  Widget build(BuildContext context) => TextField(
    controller: widget.controller,
    obscureText: hidden,
    autofillHints: const [AutofillHints.password],
    textInputAction: widget.textInputAction,
    onSubmitted: (_) => widget.onSubmitted?.call(),
    decoration: InputDecoration(
      labelText: widget.label,
      prefixIcon: const Icon(Icons.lock_outline_rounded),
      suffixIcon: IconButton(
        onPressed: () => setState(() => hidden = !hidden),
        tooltip: context.strings.text(hidden ? 'showPassword' : 'hidePassword'),
        icon: Icon(
          hidden ? Icons.visibility_outlined : Icons.visibility_off_outlined,
        ),
      ),
    ),
  );
}

class _LoginForm extends StatefulWidget {
  const _LoginForm({super.key});

  @override
  State<_LoginForm> createState() => _LoginFormState();
}

class _LoginFormState extends State<_LoginForm> {
  final email = TextEditingController();
  final password = TextEditingController();
  String? localError;

  @override
  void dispose() {
    email.dispose();
    password.dispose();
    super.dispose();
  }

  void submit() {
    final strings = context.strings;
    if (email.text.trim().isEmpty || password.text.isEmpty) {
      setState(() => localError = strings.text('requiredFields'));
      return;
    }
    if (!_looksLikeEmail(email.text)) {
      setState(() => localError = strings.text('invalidEmail'));
      return;
    }
    setState(() => localError = null);
    AppScope.of(context, listen: false).login(email.text, password.text);
  }

  @override
  Widget build(BuildContext context) {
    final controller = AppScope.of(context);
    final strings = context.strings;
    return AutofillGroup(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          _FormHeader(
            icon: Icons.login_rounded,
            title: strings.text('loginTitle'),
            subtitle: strings.text('loginSubtitle'),
          ),
          const SizedBox(height: 26),
          const _Feedback(),
          if (controller.errorCode != null) const SizedBox(height: 14),
          if (localError != null) ...[
            Text(
              localError!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
            const SizedBox(height: 10),
          ],
          TextField(
            controller: email,
            textDirection: TextDirection.ltr,
            keyboardType: TextInputType.emailAddress,
            autofillHints: const [AutofillHints.email],
            textInputAction: TextInputAction.next,
            autocorrect: false,
            decoration: InputDecoration(
              labelText: strings.text('email'),
              hintText: strings.text('emailHint'),
              prefixIcon: const Icon(Icons.alternate_email_rounded),
            ),
          ),
          const SizedBox(height: 14),
          _PasswordField(
            controller: password,
            label: strings.text('password'),
            textInputAction: TextInputAction.done,
            onSubmitted: submit,
          ),
          Align(
            alignment: AlignmentDirectional.centerEnd,
            child: TextButton(
              onPressed: controller.authBusy
                  ? null
                  : controller.showForgotPassword,
              child: Text(strings.text('forgotPassword')),
            ),
          ),
          const SizedBox(height: 8),
          GeemGradientButton(
            label: strings.text(controller.authBusy ? 'signingIn' : 'signIn'),
            icon: Icons.arrow_forward_rounded,
            busy: controller.authBusy,
            onPressed: controller.authBusy ? null : submit,
          ),
        ],
      ),
    );
  }
}

class _ForgotPasswordForm extends StatefulWidget {
  const _ForgotPasswordForm({super.key});

  @override
  State<_ForgotPasswordForm> createState() => _ForgotPasswordFormState();
}

class _ForgotPasswordFormState extends State<_ForgotPasswordForm> {
  final email = TextEditingController();
  String? localError;

  @override
  void dispose() {
    email.dispose();
    super.dispose();
  }

  void submit() {
    if (!_looksLikeEmail(email.text)) {
      setState(() => localError = context.strings.text('invalidEmail'));
      return;
    }
    setState(() => localError = null);
    AppScope.of(context, listen: false).requestPasswordReset(email.text);
  }

  @override
  Widget build(BuildContext context) {
    final controller = AppScope.of(context);
    final strings = context.strings;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        _FormHeader(
          icon: Icons.key_rounded,
          title: strings.text(
            controller.forgotSubmitted ? 'forgotSuccessTitle' : 'forgotTitle',
          ),
          subtitle: strings.text(
            controller.forgotSubmitted ? 'forgotSuccessBody' : 'forgotSubtitle',
          ),
        ),
        const SizedBox(height: 26),
        const _Feedback(),
        if (controller.errorCode != null) const SizedBox(height: 14),
        if (!controller.forgotSubmitted) ...[
          if (localError != null) ...[
            Text(
              localError!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
            const SizedBox(height: 10),
          ],
          TextField(
            controller: email,
            textDirection: TextDirection.ltr,
            keyboardType: TextInputType.emailAddress,
            textInputAction: TextInputAction.done,
            onSubmitted: (_) => submit(),
            decoration: InputDecoration(
              labelText: strings.text('email'),
              prefixIcon: const Icon(Icons.alternate_email_rounded),
            ),
          ),
          const SizedBox(height: 18),
          GeemGradientButton(
            label: strings.text(
              controller.authBusy ? 'sending' : 'sendResetLink',
            ),
            icon: Icons.outgoing_mail,
            busy: controller.authBusy,
            onPressed: controller.authBusy ? null : submit,
          ),
        ] else
          OutlinedButton.icon(
            onPressed: () => controller.showResetPassword(),
            icon: const Icon(Icons.link_rounded),
            label: Text(strings.text('useResetLink')),
          ),
        const SizedBox(height: 12),
        TextButton(
          onPressed: controller.authBusy ? null : controller.showLogin,
          child: Text(strings.text('backToSignIn')),
        ),
      ],
    );
  }
}

class _CheckEmailForm extends StatefulWidget {
  const _CheckEmailForm({super.key});

  @override
  State<_CheckEmailForm> createState() => _CheckEmailFormState();
}

class _CheckEmailFormState extends State<_CheckEmailForm> {
  late final TextEditingController email;
  final verificationLink = TextEditingController();
  String? localError;

  @override
  void initState() {
    super.initState();
    email = TextEditingController(
      text: AppScope.of(context, listen: false).pendingVerificationEmail,
    );
  }

  @override
  void dispose() {
    email.dispose();
    verificationLink.dispose();
    super.dispose();
  }

  void resend() {
    if (!_looksLikeEmail(email.text)) {
      setState(() => localError = context.strings.text('invalidEmail'));
      return;
    }
    setState(() => localError = null);
    AppScope.of(context, listen: false).resendVerification(email.text);
  }

  @override
  Widget build(BuildContext context) {
    final controller = AppScope.of(context);
    final strings = context.strings;
    final known = controller.pendingVerificationEmail.isNotEmpty;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        _FormHeader(
          icon: Icons.mark_email_read_outlined,
          title: strings.text('checkEmailTitle'),
          subtitle: known
              ? '${strings.text('checkEmailKnown')} ${controller.pendingVerificationEmail}. '
                    '${strings.text('checkEmailSubtitle')}'
              : strings.text('checkEmailSubtitle'),
        ),
        const SizedBox(height: 24),
        if (controller.verificationResent) ...[
          _SuccessBanner(text: strings.text('verificationResent')),
          const SizedBox(height: 14),
        ],
        const _Feedback(),
        if (controller.errorCode != null) const SizedBox(height: 14),
        if (localError != null) ...[
          Text(
            localError!,
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
          const SizedBox(height: 10),
        ],
        TextField(
          controller: email,
          textDirection: TextDirection.ltr,
          keyboardType: TextInputType.emailAddress,
          onChanged: (_) => setState(() => localError = null),
          decoration: InputDecoration(
            labelText: strings.text('email'),
            prefixIcon: const Icon(Icons.alternate_email_rounded),
          ),
        ),
        const SizedBox(height: 14),
        OutlinedButton.icon(
          onPressed: controller.authBusy || !_looksLikeEmail(email.text)
              ? null
              : resend,
          icon: const Icon(Icons.refresh_rounded),
          label: Text(
            strings.text(
              controller.authBusy ? 'resending' : 'resendVerification',
            ),
          ),
        ),
        const Padding(
          padding: EdgeInsets.symmetric(vertical: 18),
          child: Divider(),
        ),
        TextField(
          controller: verificationLink,
          textDirection: TextDirection.ltr,
          autocorrect: false,
          textInputAction: TextInputAction.done,
          decoration: InputDecoration(
            labelText: strings.text('verificationLink'),
            prefixIcon: const Icon(Icons.link_rounded),
          ),
        ),
        const SizedBox(height: 14),
        GeemGradientButton(
          label: strings.text('verifyNow'),
          icon: Icons.verified_outlined,
          busy: controller.authBusy,
          onPressed: controller.authBusy
              ? null
              : () => controller.verifyEmailFromInput(verificationLink.text),
        ),
        const SizedBox(height: 10),
        TextButton(
          onPressed: controller.authBusy ? null : controller.showLogin,
          child: Text(strings.text('backToSignIn')),
        ),
      ],
    );
  }
}

class _VerifyEmailForm extends StatefulWidget {
  const _VerifyEmailForm({super.key});

  @override
  State<_VerifyEmailForm> createState() => _VerifyEmailFormState();
}

class _VerifyEmailFormState extends State<_VerifyEmailForm> {
  final link = TextEditingController();

  @override
  void dispose() {
    link.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = AppScope.of(context);
    final strings = context.strings;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        _FormHeader(
          icon: Icons.verified_rounded,
          title: strings.text('verifyTitle'),
          subtitle: strings.text('verifyWorking'),
        ),
        const SizedBox(height: 28),
        if (controller.authBusy)
          const Center(child: CircularProgressIndicator())
        else ...[
          const _Feedback(),
          const SizedBox(height: 16),
          TextField(
            controller: link,
            textDirection: TextDirection.ltr,
            decoration: InputDecoration(
              labelText: strings.text('verificationLink'),
              prefixIcon: const Icon(Icons.link_rounded),
            ),
          ),
          const SizedBox(height: 14),
          GeemGradientButton(
            label: strings.text('verifyNow'),
            onPressed: () => controller.verifyEmailFromInput(link.text),
          ),
          const SizedBox(height: 10),
          TextButton(
            onPressed: () => controller.showCheckEmail(),
            child: Text(strings.text('resendVerification')),
          ),
        ],
      ],
    );
  }
}

class _ResetPasswordForm extends StatefulWidget {
  const _ResetPasswordForm({super.key});

  @override
  State<_ResetPasswordForm> createState() => _ResetPasswordFormState();
}

class _ResetPasswordFormState extends State<_ResetPasswordForm> {
  final token = TextEditingController();
  final password = TextEditingController();
  final confirm = TextEditingController();
  String? localError;

  @override
  void dispose() {
    token.dispose();
    password.dispose();
    confirm.dispose();
    super.dispose();
  }

  void submit() {
    final strings = context.strings;
    final controller = AppScope.of(context, listen: false);
    final tokenInput = controller.resetToken.isNotEmpty
        ? controller.resetToken
        : token.text;
    if (tokenInput.trim().isEmpty || password.text.length < 8) {
      setState(() => localError = strings.text('requiredFields'));
      return;
    }
    if (password.text != confirm.text) {
      setState(() => localError = strings.text('passwordMismatch'));
      return;
    }
    setState(() => localError = null);
    controller.completePasswordReset(tokenInput, password.text);
  }

  @override
  Widget build(BuildContext context) {
    final controller = AppScope.of(context);
    final strings = context.strings;
    final hasDeepLinkToken = controller.resetToken.isNotEmpty;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        _FormHeader(
          icon: Icons.password_rounded,
          title: strings.text('resetTitle'),
          subtitle: strings.text('resetSubtitle'),
        ),
        const SizedBox(height: 24),
        const _Feedback(),
        if (controller.errorCode != null) const SizedBox(height: 14),
        if (localError != null) ...[
          Text(
            localError!,
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
          const SizedBox(height: 10),
        ],
        if (!hasDeepLinkToken) ...[
          TextField(
            controller: token,
            textDirection: TextDirection.ltr,
            autocorrect: false,
            decoration: InputDecoration(
              labelText: strings.text('resetLink'),
              prefixIcon: const Icon(Icons.link_rounded),
            ),
          ),
          const SizedBox(height: 14),
        ],
        _PasswordField(
          controller: password,
          label: strings.text('newPassword'),
        ),
        const SizedBox(height: 8),
        Text(
          strings.text('passwordHint'),
          style: Theme.of(context).textTheme.bodySmall?.copyWith(
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
        ),
        const SizedBox(height: 14),
        _PasswordField(
          controller: confirm,
          label: strings.text('confirmPassword'),
          textInputAction: TextInputAction.done,
          onSubmitted: submit,
        ),
        const SizedBox(height: 20),
        GeemGradientButton(
          label: strings.text(
            controller.authBusy ? 'resetting' : 'resetPassword',
          ),
          icon: Icons.check_rounded,
          busy: controller.authBusy,
          onPressed: controller.authBusy ? null : submit,
        ),
        const SizedBox(height: 10),
        TextButton(
          onPressed: controller.authBusy ? null : controller.showLogin,
          child: Text(strings.text('backToSignIn')),
        ),
      ],
    );
  }
}

class _SuccessBanner extends StatelessWidget {
  const _SuccessBanner({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(13),
    decoration: BoxDecoration(
      color: const Color(0xFF10B981).withValues(alpha: 0.1),
      borderRadius: BorderRadius.circular(12),
    ),
    child: Row(
      children: [
        const Icon(
          Icons.check_circle_outline_rounded,
          color: Color(0xFF059669),
          size: 19,
        ),
        const SizedBox(width: 9),
        Expanded(child: Text(text, style: const TextStyle(fontSize: 13))),
      ],
    ),
  );
}

bool _looksLikeEmail(String value) {
  final normalized = value.trim();
  return RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$').hasMatch(normalized);
}
