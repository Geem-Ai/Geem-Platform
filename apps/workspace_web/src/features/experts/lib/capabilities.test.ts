import { describe, expect, it } from 'vitest';
import {
  canAskExpert,
  canCreateExpert,
  canDeleteExpert,
  canEditExpert,
  canManageExpertKnowledge,
} from './capabilities';
import { WorkspacePermission } from '@/features/authz/permissions';

const allow =
  (...keys: string[]) =>
  (permission: string) =>
    keys.includes(permission);

describe('canCreateExpert', () => {
  it('requires experts.create', () => {
    expect(canCreateExpert(allow(WorkspacePermission.EXPERTS_CREATE))).toBe(true);
    expect(canCreateExpert(allow(WorkspacePermission.EXPERTS_VIEW))).toBe(false);
  });
});

describe('canDeleteExpert', () => {
  it('requires experts.delete and workspace ownership', () => {
    expect(canDeleteExpert(allow(WorkspacePermission.EXPERTS_DELETE), 'workspace')).toBe(
      true,
    );
    expect(canDeleteExpert(allow(WorkspacePermission.EXPERTS_DELETE), 'platform')).toBe(
      false,
    );
  });
});

describe('canEditExpert', () => {
  it('requires experts.update and workspace ownership', () => {
    expect(canEditExpert(allow(WorkspacePermission.EXPERTS_UPDATE), 'workspace')).toBe(
      true,
    );
    expect(canEditExpert(allow(WorkspacePermission.EXPERTS_VIEW), 'workspace')).toBe(
      false,
    );
  });
});

describe('canManageExpertKnowledge', () => {
  it('requires experts.manage_knowledge on workspace experts', () => {
    expect(
      canManageExpertKnowledge(
        allow(WorkspacePermission.EXPERTS_MANAGE_KNOWLEDGE),
        'workspace',
      ),
    ).toBe(true);
    expect(
      canManageExpertKnowledge(
        allow(WorkspacePermission.EXPERTS_MANAGE_KNOWLEDGE),
        'platform',
      ),
    ).toBe(false);
  });
});

describe('canAskExpert', () => {
  it('requires experts.use, chat.use, and ready status', () => {
    const ask = allow(WorkspacePermission.EXPERTS_USE, WorkspacePermission.CHAT_USE);
    expect(canAskExpert(ask, 'ready')).toBe(true);
    expect(canAskExpert(ask, 'draft')).toBe(false);
    expect(canAskExpert(allow(WorkspacePermission.EXPERTS_VIEW), 'ready')).toBe(false);
    expect(canAskExpert(allow(WorkspacePermission.EXPERTS_USE), 'ready')).toBe(false);
    expect(canAskExpert(allow(WorkspacePermission.CHAT_USE), 'ready')).toBe(false);
  });
});
