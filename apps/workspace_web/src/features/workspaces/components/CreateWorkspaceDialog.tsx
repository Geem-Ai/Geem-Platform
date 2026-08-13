import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { suggestSlugFromName } from '@/features/workspaces/lib/hostname';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
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
import { WorkspaceSlugInput } from '@/features/workspaces/components/WorkspaceSlugInput';
import { ApiError, errorMessageKey } from '@/services/api/errors';

interface CreateWorkspaceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateWorkspaceDialog({
  open,
  onOpenChange,
}: CreateWorkspaceDialogProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { createWorkspace } = useWorkspace();
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [slugTouched, setSlugTouched] = useState(false);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setName('');
    setSlug('');
    setSlugTouched(false);
    setErrorKey(null);
    setSubmitting(false);
  }, [open]);

  useEffect(() => {
    if (!slugTouched) {
      setSlug(suggestSlugFromName(name));
    }
  }, [name, slugTouched]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setErrorKey(null);
    try {
      await createWorkspace({ name: name.trim(), slug: slug.trim() });
      onOpenChange(false);
      navigate('/', { replace: true });
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
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!submitting) onOpenChange(next);
      }}
    >
      <DialogContent data-testid="create-workspace-dialog">
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>{t('shell.createWorkspace')}</DialogTitle>
            <DialogDescription>{t('onboarding.description')}</DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {errorKey && (
              <p className="text-sm text-destructive" role="alert">
                {t(errorKey)}
              </p>
            )}
            <div className="space-y-2">
              <Label htmlFor="create-ws-name">{t('onboarding.workspaceName')}</Label>
              <Input
                id="create-ws-name"
                required
                maxLength={200}
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={submitting}
                autoFocus
                data-testid="create-workspace-name"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="create-ws-slug">{t('onboarding.workspaceSlug')}</Label>
              <WorkspaceSlugInput
                id="create-ws-slug"
                value={slug}
                onChange={(next) => {
                  setSlugTouched(true);
                  setSlug(next);
                }}
                disabled={submitting}
                data-testid="create-workspace-slug"
              />
              <p className="text-xs text-muted-foreground">{t('onboarding.slugHint')}</p>
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              disabled={submitting || !name.trim() || !slug.trim()}
              data-testid="create-workspace-submit"
            >
              {submitting ? t('onboarding.creating') : t('onboarding.create')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
