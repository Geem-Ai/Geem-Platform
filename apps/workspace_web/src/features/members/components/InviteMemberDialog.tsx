import { useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { INVITE_ROLES } from '@/features/members/lib/role-matrix';
import { useCreateInvitation } from '@/features/members/hooks/useMembersQueries';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import type { InvitationRole } from '@/services/api/invitations';

type InviteMemberDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSent?: (email: string) => void;
};

function looksLikeEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

export function InviteMemberDialog({
  open,
  onOpenChange,
  onSent,
}: InviteMemberDialogProps) {
  const { t } = useTranslation();
  const create = useCreateInvitation();
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<InvitationRole>('member');
  const [errorKey, setErrorKey] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setEmail('');
    setRole('member');
    setErrorKey(null);
    create.reset();
    // Reset only when the dialog opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = email.trim().toLowerCase();
    if (!looksLikeEmail(trimmed)) {
      setErrorKey('members.errors.invalidEmail');
      return;
    }
    setErrorKey(null);
    try {
      await create.mutateAsync({ email: trimmed, role });
      onSent?.(trimmed);
      onOpenChange(false);
    } catch (err) {
      if (err instanceof ApiError) {
        setErrorKey(errorMessageKey(err.code));
      } else {
        setErrorKey('errors.generic');
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" data-testid="invite-dialog">
        <form onSubmit={onSubmit} className="space-y-5">
          <DialogHeader>
            <DialogTitle>{t('members.inviteTitle')}</DialogTitle>
            <DialogDescription>{t('members.inviteDescription')}</DialogDescription>
          </DialogHeader>

          {errorKey ? (
            <p className="text-sm text-destructive" role="alert" data-testid="invite-error">
              {t(errorKey)}
            </p>
          ) : null}

          <div className="space-y-2">
            <Label htmlFor="invite-email">{t('members.email')}</Label>
            <Input
              id="invite-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t('members.emailPlaceholder')}
              disabled={create.isPending}
              data-testid="invite-email"
            />
          </div>

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">{t('members.role')}</legend>
            <div className="grid gap-2">
              {INVITE_ROLES.map((option) => (
                <label
                  key={option}
                  className="flex cursor-pointer items-start gap-3 rounded-lg border border-border p-3 has-[:checked]:border-primary has-[:checked]:bg-primary/5"
                >
                  <input
                    type="radio"
                    name="invite-role"
                    value={option}
                    checked={role === option}
                    onChange={() => setRole(option)}
                    disabled={create.isPending}
                    className="mt-1"
                    data-testid={`invite-role-${option}`}
                  />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium">{t(`roles.${option}`)}</span>
                    <span className="mt-0.5 block text-xs text-muted-foreground leading-relaxed">
                      {t(`members.inviteRoleHint.${option}`)}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={create.isPending}
            >
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={create.isPending} data-testid="invite-submit">
              {create.isPending ? t('members.sending') : t('members.sendInvite')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
