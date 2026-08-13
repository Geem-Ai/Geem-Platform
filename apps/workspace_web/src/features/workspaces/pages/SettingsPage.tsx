import { useEffect, useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { toast } from 'sonner';
import { canManageWorkspace } from '@/features/workspaces/lib/roles';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { updateWorkspace } from '@/services/api';
import { ApiError, errorMessageKey } from '@/services/api/errors';

export function SettingsPage() {
  const { t } = useTranslation();
  const { currentWorkspace, currentMembership, refreshWorkspaces } = useWorkspace();
  const role = currentMembership?.role ?? currentWorkspace?.role;
  const canEdit = canManageWorkspace(role);
  const [name, setName] = useState(currentWorkspace?.name ?? '');

  useEffect(() => {
    setName(currentWorkspace?.name ?? '');
  }, [currentWorkspace?.id, currentWorkspace?.name]);

  const mutation = useMutation({
    mutationFn: () =>
      updateWorkspace(currentWorkspace!.id, { name: name.trim() }),
    onSuccess: async () => {
      await refreshWorkspaces();
      toast.success(t('settings.saved'));
    },
    onError: (err: unknown) => {
      if (err instanceof ApiError) {
        toast.error(t(errorMessageKey(err.code)));
      } else {
        toast.error(t('errors.generic'));
      }
    },
  });

  if (!currentWorkspace) {
    return null;
  }

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!canEdit) return;
    mutation.mutate();
  };

  return (
    <div className="p-6 md:p-8 w-full max-w-xl space-y-6 ms-auto me-auto">
      <DocumentTitle title={t('settings.title')} />
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{t('settings.title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('settings.description')}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t('settings.workspaceSection')}</CardTitle>
          <CardDescription>{t('settings.slugReadonly')}</CardDescription>
        </CardHeader>
        <form onSubmit={onSubmit}>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <label htmlFor="settings-name" className="text-sm font-medium">
                {t('onboarding.workspaceName')}
              </label>
              <Input
                id="settings-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={!canEdit || mutation.isPending}
                maxLength={200}
                required
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">{t('onboarding.workspaceSlug')}</label>
              <Input value={currentWorkspace.slug} disabled readOnly />
            </div>
          </CardContent>
          {canEdit && (
            <CardFooter>
              <Button type="submit" disabled={mutation.isPending || !name.trim()}>
                {mutation.isPending ? t('settings.saving') : t('settings.save')}
              </Button>
            </CardFooter>
          )}
        </form>
      </Card>
    </div>
  );
}
