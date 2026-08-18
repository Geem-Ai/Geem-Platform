import { fireEvent, render, screen } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { beforeEach, describe, expect, it } from 'vitest';
import i18n from '@/lib/i18n';
import { RoleEditorDialog } from './RoleEditorDialog';
import type { PermissionCatalogItem, WorkspaceRoleDetail } from '@/services/api/roles';

const catalog: PermissionCatalogItem[] = [
  {
    key: 'workspace.view',
    group: 'workspace',
    name_key: 'permissions.workspace.view.name',
    description_key: 'permissions.workspace.view.description',
    owner_only: false,
  },
  {
    key: 'experts.manage_knowledge',
    group: 'experts',
    name_key: 'permissions.experts.manage_knowledge.name',
    description_key: 'permissions.experts.manage_knowledge.description',
    owner_only: false,
  },
];

function renderDialog() {
  return render(
    <I18nextProvider i18n={i18n}>
      <RoleEditorDialog open onOpenChange={() => undefined} catalog={catalog} onSave={() => undefined} />
    </I18nextProvider>,
  );
}

describe('RoleEditorDialog permission labels', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('shows translated labels instead of raw permission keys', () => {
    renderDialog();
    expect(screen.getByText('View workspace')).toBeInTheDocument();
    expect(screen.getByText('Manage knowledge')).toBeInTheDocument();
    expect(screen.queryByText('workspace.view')).not.toBeInTheDocument();
    expect(screen.queryByText('experts.manage_knowledge')).not.toBeInTheDocument();
  });

  it('shows Arabic labels', async () => {
    await i18n.changeLanguage('ar');
    renderDialog();
    expect(screen.getByText('عرض مساحة العمل')).toBeInTheDocument();
    expect(screen.getByText('إدارة المعرفة')).toBeInTheDocument();
  });

  it('filters permissions by the search field', () => {
    renderDialog();
    fireEvent.change(screen.getByTestId('permission-search'), {
      target: { value: 'knowledge' },
    });
    expect(screen.getByText('Manage knowledge')).toBeInTheDocument();
    expect(screen.queryByText('View workspace')).not.toBeInTheDocument();
  });

  it('shows how many permissions are selected', () => {
    const role: WorkspaceRoleDetail = {
      id: 'role-1',
      workspace_id: 'ws-a',
      name: 'Member',
      description: null,
      is_system: true,
      is_owner_role: false,
      system_key: 'member',
      permissions: ['workspace.view'],
      assigned_count: 1,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };
    render(
      <I18nextProvider i18n={i18n}>
        <RoleEditorDialog
          open
          onOpenChange={() => undefined}
          catalog={catalog}
          role={role}
          onSave={() => undefined}
        />
      </I18nextProvider>,
    );
    expect(screen.getByTestId('permission-selected-count')).toHaveTextContent(
      '1 of 2 selected',
    );
  });
});
