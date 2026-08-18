import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Search } from 'lucide-react';
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
import { Textarea } from '@/components/ui/textarea';
import {
  permissionDescriptionKey,
  permissionLabelKey,
} from '@/features/authz/permissions';
import { cn } from '@/lib/utils';
import type { PermissionCatalogItem, WorkspaceRoleDetail } from '@/services/api/roles';

type RoleEditorDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  catalog: PermissionCatalogItem[];
  role?: WorkspaceRoleDetail | null;
  pending?: boolean;
  onSave: (input: {
    name: string;
    description: string | null;
    permissions: string[];
  }) => void;
};

function groupCatalog(items: PermissionCatalogItem[]) {
  const groups = new Map<string, PermissionCatalogItem[]>();
  for (const item of items) {
    if (item.owner_only) continue;
    const list = groups.get(item.group) ?? [];
    list.push(item);
    groups.set(item.group, list);
  }
  return [...groups.entries()];
}

export function RoleEditorDialog({
  open,
  onOpenChange,
  catalog,
  role,
  pending,
  onSave,
}: RoleEditorDialogProps) {
  const { t } = useTranslation();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState('');
  const groups = useMemo(() => groupCatalog(catalog), [catalog]);
  const assignableCount = useMemo(
    () => groups.reduce((sum, [, items]) => sum + items.length, 0),
    [groups],
  );
  const selectedCount = useMemo(() => {
    const assignable = new Set(
      groups.flatMap(([, items]) => items.map((item) => item.key)),
    );
    let count = 0;
    for (const key of selected) {
      if (assignable.has(key)) count += 1;
    }
    return count;
  }, [groups, selected]);
  const readOnly = Boolean(role?.is_owner_role);
  const systemLocked = Boolean(role?.is_system);

  const filteredGroups = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return groups;
    return groups
      .map(([group, items]) => {
        const groupLabel = t(`permissions.groups.${group}`, { defaultValue: group });
        const matched = items.filter((item) => {
          const label = t(permissionLabelKey(item.key), {
            defaultValue: t(item.name_key, { defaultValue: item.key }),
          });
          const hint = t(permissionDescriptionKey(item.key), {
            defaultValue: t(item.description_key, { defaultValue: '' }),
          });
          return (
            groupLabel.toLowerCase().includes(q) ||
            label.toLowerCase().includes(q) ||
            hint.toLowerCase().includes(q)
          );
        });
        return [group, matched] as const;
      })
      .filter(([, items]) => items.length > 0);
  }, [groups, query, t]);

  useEffect(() => {
    if (!open) return;
    setName(role?.name ?? '');
    setDescription(role?.description ?? '');
    setSelected(new Set(role?.permissions ?? []));
    setQuery('');
  }, [open, role]);

  function toggle(key: string, on: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(key);
      else next.delete(key);
      return next;
    });
  }

  function setGroup(keys: string[], on: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      for (const key of keys) {
        if (on) next.add(key);
        else next.delete(key);
      }
      return next;
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-2xl max-h-[calc(100vh-80px)] overflow-hidden p-0 gap-0"
        data-testid="role-editor"
      >
        <form
          className="flex max-h-[calc(100vh-80px)] min-h-0 flex-col"
          onSubmit={(event) => {
            event.preventDefault();
            if (readOnly) return;
            onSave({
              name: name.trim(),
              description: description.trim() || null,
              permissions: [...selected],
            });
          }}
        >
          <div className="shrink-0 space-y-4 px-6 pt-6">
            <DialogHeader className="mb-0">
              <DialogTitle>
                {role ? t('members.roles.editTitle') : t('members.roles.createTitle')}
              </DialogTitle>
              <DialogDescription>
                {readOnly
                  ? t('members.roles.ownerLocked')
                  : t('members.roles.editorDescription')}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-2">
              <Label htmlFor="role-name">{t('members.roles.name')}</Label>
              <Input
                id="role-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={pending || readOnly || systemLocked}
                placeholder={t('members.roles.namePlaceholder')}
                data-testid="role-name"
              />
              {systemLocked && !readOnly ? (
                <p className="text-xs text-muted-foreground">{t('members.roles.systemNameLocked')}</p>
              ) : null}
            </div>
            {readOnly ? null : (
              <div className="space-y-2">
                <Label htmlFor="role-description">{t('members.roles.description')}</Label>
                <Textarea
                  id="role-description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  disabled={pending}
                  rows={2}
                  placeholder={t('members.roles.descriptionOptional')}
                  data-testid="role-description"
                />
              </div>
            )}
          </div>

          {readOnly ? (
            <p
              className="text-sm text-muted-foreground px-6 py-4"
              data-testid="owner-role-readonly"
            >
              {t('members.roles.ownerFullAccess')}
            </p>
          ) : (
            <div className="flex min-h-0 flex-1 flex-col pt-4" data-testid="permission-matrix">
              <div className="shrink-0 space-y-3 px-6 pb-3">
                <div className="flex items-baseline justify-between gap-3">
                  <h2 className="text-sm font-medium">{t('members.roles.permissionsHeading')}</h2>
                  <p className="text-xs text-muted-foreground" data-testid="permission-selected-count">
                    {t('members.roles.selectedCount', {
                      selected: selectedCount,
                      total: assignableCount,
                    })}
                  </p>
                </div>
                <div className="relative">
                  <Search className="pointer-events-none absolute start-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder={t('members.roles.search')}
                    className="ps-9"
                    disabled={pending}
                    data-testid="permission-search"
                    aria-label={t('members.roles.search')}
                  />
                </div>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-1">
                {filteredGroups.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-8 text-center">
                    {catalog.length === 0
                      ? t('members.roles.loadingPermissions')
                      : t('members.roles.emptyFilter')}
                  </p>
                ) : (
                  <div className="space-y-3 pb-3">
                    {filteredGroups.map(([group, items]) => {
                      const keys = items.map((item) => item.key);
                      const selectedInGroup = keys.filter((key) => selected.has(key)).length;
                      const allOn = selectedInGroup === keys.length && keys.length > 0;
                      const someOn = selectedInGroup > 0;
                      const groupLabel = t(`permissions.groups.${group}`, {
                        defaultValue: group,
                      });
                      return (
                        <section
                          key={group}
                          className="rounded-lg border border-border overflow-hidden"
                        >
                          <div className="flex items-center gap-3 bg-muted/40 px-3 py-2">
                            <input
                              type="checkbox"
                              className="size-4 shrink-0"
                              checked={allOn}
                              ref={(el) => {
                                if (el) el.indeterminate = someOn && !allOn;
                              }}
                              onChange={() => setGroup(keys, !allOn)}
                              disabled={pending}
                              aria-label={t('members.roles.toggleGroup', { group: groupLabel })}
                              data-testid={`permission-group-${group}`}
                            />
                            <div className="min-w-0 flex-1 flex items-center justify-between gap-2">
                              <h3 className="text-sm font-medium">{groupLabel}</h3>
                              <span className="text-xs text-muted-foreground tabular-nums">
                                {t('members.roles.groupCount', {
                                  selected: selectedInGroup,
                                  total: keys.length,
                                })}
                              </span>
                            </div>
                          </div>
                          <ul className="divide-y divide-border">
                            {items.map((item) => {
                              const label = t(permissionLabelKey(item.key), {
                                defaultValue: t(item.name_key, { defaultValue: item.key }),
                              });
                              const hint = t(permissionDescriptionKey(item.key), {
                                defaultValue: t(item.description_key, { defaultValue: '' }),
                              });
                              const on = selected.has(item.key);
                              return (
                                <li key={item.key}>
                                  <label
                                    className={cn(
                                      'flex cursor-pointer items-start gap-3 px-3 py-2.5 transition-colors',
                                      on ? 'bg-primary/5' : 'hover:bg-muted/50',
                                      pending && 'pointer-events-none opacity-60',
                                    )}
                                  >
                                    <input
                                      type="checkbox"
                                      className="mt-0.5 size-4 shrink-0"
                                      checked={on}
                                      onChange={(event) => toggle(item.key, event.target.checked)}
                                      disabled={pending}
                                      data-testid={`permission-${item.key}`}
                                    />
                                    <span className="min-w-0">
                                      <span className="block text-sm font-medium leading-5">
                                        {label}
                                      </span>
                                      {hint ? (
                                        <span className="mt-0.5 block text-xs text-muted-foreground leading-relaxed">
                                          {hint}
                                        </span>
                                      ) : null}
                                    </span>
                                  </label>
                                </li>
                              );
                            })}
                          </ul>
                        </section>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          )}

          <DialogFooter className="shrink-0 border-t border-border px-6 pb-6 mt-0">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t('common.cancel')}
            </Button>
            {readOnly ? null : (
              <Button type="submit" disabled={pending || !name.trim()} data-testid="role-save">
                {pending ? t('members.roles.saving') : t('common.save')}
              </Button>
            )}
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
