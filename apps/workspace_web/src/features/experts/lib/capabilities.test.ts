import { describe, expect, it } from 'vitest';
import {
  canAskExpert,
  canCreateExpert,
  canDeleteExpert,
  canEditExpert,
  canManageExpertKnowledge,
} from './capabilities';

describe('canCreateExpert', () => {
  it('allows owner and admin', () => {
    expect(canCreateExpert('owner')).toBe(true);
    expect(canCreateExpert('admin')).toBe(true);
  });
  it('denies member and undefined', () => {
    expect(canCreateExpert('member')).toBe(false);
    expect(canCreateExpert(null)).toBe(false);
    expect(canCreateExpert(undefined)).toBe(false);
  });
});

describe('canEditExpert', () => {
  it('allows owner/admin for workspace experts', () => {
    expect(canEditExpert('owner', 'workspace')).toBe(true);
    expect(canEditExpert('admin', 'workspace')).toBe(true);
  });
  it('denies platform experts regardless of role', () => {
    expect(canEditExpert('owner', 'platform')).toBe(false);
    expect(canEditExpert('admin', 'platform')).toBe(false);
  });
  it('denies member for workspace experts', () => {
    expect(canEditExpert('member', 'workspace')).toBe(false);
  });
});

describe('canDeleteExpert', () => {
  it('allows owner/admin for workspace experts', () => {
    expect(canDeleteExpert('owner', 'workspace')).toBe(true);
    expect(canDeleteExpert('admin', 'workspace')).toBe(true);
  });
  it('denies platform experts', () => {
    expect(canDeleteExpert('owner', 'platform')).toBe(false);
  });
});

describe('canManageExpertKnowledge', () => {
  it('allows owner/admin for workspace experts', () => {
    expect(canManageExpertKnowledge('owner', 'workspace')).toBe(true);
    expect(canManageExpertKnowledge('admin', 'workspace')).toBe(true);
  });
  it('denies member and platform', () => {
    expect(canManageExpertKnowledge('member', 'workspace')).toBe(false);
    expect(canManageExpertKnowledge('owner', 'platform')).toBe(false);
  });
});

describe('canAskExpert', () => {
  it('allows ready status', () => {
    expect(canAskExpert('ready')).toBe(true);
  });
  it('denies non-ready statuses', () => {
    expect(canAskExpert('draft')).toBe(false);
    expect(canAskExpert('processing')).toBe(false);
    expect(canAskExpert('failed')).toBe(false);
    expect(canAskExpert('disabled')).toBe(false);
  });
});
