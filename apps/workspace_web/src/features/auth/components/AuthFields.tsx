import { useState, type ReactNode } from 'react';
import { Eye, EyeOff, Lock, Mail } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Input, InputWrapper } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

type AuthEmailFieldProps = {
  id: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  autoFocus?: boolean;
};

export function AuthFormHeader({
  title,
  subtitle,
}: {
  title: string;
  subtitle: string;
}) {
  return (
    <div className="space-y-2">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <p className="text-sm leading-relaxed text-muted-foreground">{subtitle}</p>
    </div>
  );
}

export function AuthEmailField({
  id,
  value,
  onChange,
  disabled,
  autoFocus,
}: AuthEmailFieldProps) {
  const { t } = useTranslation();

  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{t('auth.email')}</Label>
      <InputWrapper variant="lg">
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

type AuthPasswordFieldProps = {
  id: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  autoComplete: 'current-password' | 'new-password';
  minLength?: number;
  maxLength?: number;
  hint?: ReactNode;
  label?: string;
  placeholder?: string;
  autoFocus?: boolean;
  name?: string;
};

export function AuthPasswordField({
  id,
  value,
  onChange,
  disabled,
  autoComplete,
  minLength,
  maxLength,
  hint,
  label,
  placeholder,
  autoFocus,
  name = 'password',
}: AuthPasswordFieldProps) {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(false);

  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label ?? t('auth.password')}</Label>
      <InputWrapper variant="lg">
        <Lock aria-hidden />
        <Input
          id={id}
          name={name}
          type={visible ? 'text' : 'password'}
          autoComplete={autoComplete}
          required
          autoFocus={autoFocus}
          minLength={minLength}
          maxLength={maxLength}
          placeholder={placeholder ?? t('auth.passwordPlaceholder')}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
        />
        <button
          type="button"
          data-testid={`auth-password-toggle-${id}`}
          className="inline-flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:text-foreground disabled:pointer-events-none disabled:opacity-50"
          aria-label={visible ? t('auth.hidePassword') : t('auth.showPassword')}
          aria-pressed={visible}
          disabled={disabled}
          onClick={() => setVisible((prev) => !prev)}
        >
          {visible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
        </button>
      </InputWrapper>
      {hint}
    </div>
  );
}
