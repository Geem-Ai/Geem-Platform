import { useState, type ReactNode } from 'react';
import { Eye, EyeOff, Lock, Mail, type LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Input, InputWrapper } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export function AuthFormHeader({
  title,
  subtitle,
  icon: Icon,
}: {
  title: string;
  subtitle: string;
  icon?: LucideIcon;
}) {
  return (
    <div className="text-center">
      {Icon ? (
        <div className="auth-form-icon mx-auto mb-5 flex size-14 items-center justify-center rounded-2xl border border-primary/10 bg-primary/10 text-primary">
          <Icon className="size-6" aria-hidden />
        </div>
      ) : null}
      <h1 className="text-[1.75rem] font-semibold leading-tight tracking-tight">{title}</h1>
      <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-muted-foreground">{subtitle}</p>
    </div>
  );
}

export function AuthEmailField({
  id,
  value,
  onChange,
  disabled,
  autoFocus,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  autoFocus?: boolean;
}) {
  const { t } = useTranslation();

  return (
    <div className="space-y-2.5">
      <Label htmlFor={id} className="text-sm font-medium">
        {t('auth.email')}
      </Label>
      <InputWrapper variant="lg" className="auth-input-wrapper h-12 rounded-xl px-3.5">
        <Mail aria-hidden />
        <Input
          id={id}
          name="email"
          type="email"
          inputMode="email"
          autoComplete="email"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          required
          autoFocus={autoFocus}
          placeholder={t('auth.emailPlaceholder')}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
        />
      </InputWrapper>
    </div>
  );
}

export function AuthPasswordField({
  id,
  value,
  onChange,
  disabled,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  hint?: ReactNode;
}) {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(false);

  return (
    <div className="space-y-2.5">
      <Label htmlFor={id} className="text-sm font-medium">
        {t('auth.password')}
      </Label>
      <InputWrapper variant="lg" className="auth-input-wrapper h-12 rounded-xl px-3.5">
        <Lock aria-hidden />
        <Input
          id={id}
          name="password"
          type={visible ? 'text' : 'password'}
          autoComplete="current-password"
          required
          minLength={1}
          placeholder={t('auth.passwordPlaceholder')}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
        />
        <button
          type="button"
          data-testid={`auth-password-toggle-${id}`}
          className="inline-flex size-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground"
          aria-label={visible ? t('auth.hidePassword') : t('auth.showPassword')}
          aria-pressed={visible}
          disabled={disabled}
          onClick={() => setVisible((prev) => !prev)}
        >
          {visible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
        </button>
      </InputWrapper>
    </div>
  );
}
