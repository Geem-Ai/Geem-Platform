import { useState, type FormEvent } from 'react';
import { LoaderCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { AuthAlert } from '@/features/auth/components/AuthAlert';
import { AuthPasswordField } from '@/features/auth/components/AuthFields';
import { useAuth } from '@/features/auth/AuthProvider';
import { changePassword } from '@/services/api';
import { ApiError, errorMessageKey } from '@/services/api/errors';

export function AccountPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (newPassword !== confirmPassword) {
      setErrorKey('errors.passwordMismatch');
      return;
    }
    setSubmitting(true);
    setErrorKey(null);
    try {
      await changePassword(currentPassword, newPassword);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      toast.success(t('account.passwordChanged'));
    } catch (err) {
      if (err instanceof ApiError) {
        setErrorKey(errorMessageKey(err.code));
      } else {
        setErrorKey('errors.generic');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="p-6 md:p-8 w-full max-w-xl space-y-6 ms-auto me-auto">
      <DocumentTitle title={t('account.title')} />
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{t('account.title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('account.description')}</p>
        {user?.email ? (
          <p className="text-sm text-muted-foreground mt-1" data-testid="account-email">
            {user.email}
          </p>
        ) : null}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t('account.changePasswordTitle')}</CardTitle>
          <CardDescription>{t('account.changePasswordDescription')}</CardDescription>
        </CardHeader>
        <form onSubmit={onSubmit} data-testid="change-password-form" aria-busy={submitting}>
          <CardContent className="space-y-4">
            {errorKey && <AuthAlert>{t(errorKey)}</AuthAlert>}
            <AuthPasswordField
              id="current-password"
              name="current-password"
              label={t('account.currentPassword')}
              value={currentPassword}
              onChange={setCurrentPassword}
              disabled={submitting}
              autoComplete="current-password"
              minLength={1}
              placeholder={t('account.currentPasswordPlaceholder')}
            />
            <AuthPasswordField
              id="new-password"
              name="new-password"
              label={t('account.newPassword')}
              value={newPassword}
              onChange={setNewPassword}
              disabled={submitting}
              autoComplete="new-password"
              minLength={8}
              maxLength={128}
              hint={<p className="text-xs text-muted-foreground">{t('auth.passwordHint')}</p>}
              placeholder={t('account.newPasswordPlaceholder')}
            />
            <AuthPasswordField
              id="confirm-new-password"
              name="confirm-new-password"
              label={t('auth.confirmPassword')}
              value={confirmPassword}
              onChange={setConfirmPassword}
              disabled={submitting}
              autoComplete="new-password"
              minLength={8}
              maxLength={128}
              placeholder={t('auth.confirmPasswordPlaceholder')}
            />
          </CardContent>
          <CardFooter>
            <Button type="submit" disabled={submitting}>
              {submitting ? (
                <LoaderCircle className="animate-spin" aria-hidden />
              ) : null}
              {submitting
                ? t('account.changingPassword')
                : t('account.changePasswordSubmit')}
            </Button>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
