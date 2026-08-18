import { useTranslation } from 'react-i18next';
import { Check, Minus } from 'lucide-react';
import {
  ROLE_MATRIX_GROUPS,
  ROLE_MATRIX_ROWS,
  type MatrixRole,
} from '@/features/members/lib/role-matrix';

const COLUMNS: MatrixRole[] = ['owner', 'admin', 'member'];

function Cell({ allowed, label }: { allowed: boolean; label: string }) {
  return (
    <span className="inline-flex items-center justify-center" title={label}>
      {allowed ? (
        <Check className="size-4 text-primary" aria-label={label} />
      ) : (
        <Minus className="size-4 text-muted-foreground/70" aria-label={label} />
      )}
    </span>
  );
}

export function RoleMatrix() {
  const { t } = useTranslation();

  return (
    <div className="space-y-4" data-testid="role-matrix">
      <p className="text-sm text-muted-foreground leading-relaxed px-5 pt-1">
        {t('members.matrix.ownerNote')}
      </p>

      <div className="hidden md:block overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">{t('members.matrixTitle')}</caption>
          <thead>
            <tr className="border-b border-border text-start">
              <th className="px-5 py-2.5 font-medium text-muted-foreground">
                {t('members.matrix.capability')}
              </th>
              {COLUMNS.map((role) => (
                <th key={role} className="px-3 py-2.5 text-center font-medium">
                  {t(`roles.${role}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ROLE_MATRIX_GROUPS.map((group) => {
              const rows = ROLE_MATRIX_ROWS.filter((row) => row.groupKey === group);
              return rows.map((row, index) => (
                <tr key={row.id} className="border-b border-border last:border-0">
                  <th scope="row" className="px-5 py-2.5 text-start font-normal">
                    <span className="block text-[11px] uppercase tracking-wide text-muted-foreground">
                      {index === 0 ? t(`members.matrix.groups.${group}`) : '\u00a0'}
                    </span>
                    {t(row.labelKey)}
                  </th>
                  {COLUMNS.map((role) => (
                    <td key={role} className="px-3 py-2.5 text-center">
                      <Cell
                        allowed={row[role]}
                        label={
                          row[role]
                            ? t('members.matrix.allowed')
                            : t('members.matrix.notAllowed')
                        }
                      />
                    </td>
                  ))}
                </tr>
              ));
            })}
          </tbody>
        </table>
      </div>

      <div className="grid gap-3 px-5 pb-5 md:hidden">
        {COLUMNS.map((role) => (
          <div key={role} className="rounded-lg border border-border p-3 space-y-2">
            <p className="text-sm font-medium">{t(`roles.${role}`)}</p>
            <ul className="space-y-1.5">
              {ROLE_MATRIX_ROWS.filter((row) => row[role]).map((row) => (
                <li key={row.id} className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Check className="size-3.5 text-primary shrink-0" aria-hidden />
                  {t(row.labelKey)}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
