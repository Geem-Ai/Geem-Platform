import { describe, expect, it } from 'vitest';
import {
  invitationAcceptPath,
  isInvitationAcceptPath,
  readInvitationToken,
} from './invitation-path';
import { ROLE_MATRIX_ROWS } from './role-matrix';
import { queryKeys } from '@/services/api/query-keys';
import { errorMessageKey } from '@/services/api/errors';
import en from '@/locales/en.json';
import ar from '@/locales/ar.json';

describe('invitation-path', () => {
  it('recognizes the accept route and rejects open redirects', () => {
    expect(isInvitationAcceptPath('/invitations/accept')).toBe(true);
    expect(isInvitationAcceptPath('/invitations/accept?token=abc')).toBe(true);
    expect(isInvitationAcceptPath('/login')).toBe(false);
    expect(invitationAcceptPath('abc+token')).toContain('/invitations/accept?');
    expect(invitationAcceptPath('abc+token')).toContain('token=');
  });

  it('reads a token from search without logging it', () => {
    expect(readInvitationToken('token=abc')).toBe('abc');
    expect(readInvitationToken('?token=xyz')).toBe('xyz');
    expect(readInvitationToken('')).toBeNull();
  });
});

describe('role matrix', () => {
  it('matches WorkspacePolicy: members cannot manage members or promote owners', () => {
    const manage = ROLE_MATRIX_ROWS.find((row) => row.id === 'manage_members');
    const promote = ROLE_MATRIX_ROWS.find((row) => row.id === 'promote_to_owner');
    const knowledge = ROLE_MATRIX_ROWS.find((row) => row.id === 'knowledge');
    expect(manage).toMatchObject({ owner: true, admin: true, member: false });
    expect(promote).toMatchObject({ owner: true, admin: false, member: false });
    expect(knowledge).toMatchObject({ owner: true, admin: true, member: true });
  });
});

describe('invitation query keys and errors', () => {
  it('scopes invitation keys by workspace', () => {
    expect(queryKeys.invitations('ws-a')).toEqual(['workspace', 'ws-a', 'invitations']);
    expect(queryKeys.invitations('ws-a')[1]).not.toBe(queryKeys.invitations('ws-b')[1]);
    expect(JSON.stringify(queryKeys.invitations('ws-a'))).not.toMatch(/token/i);
  });

  it('maps typed invitation error codes', () => {
    expect(errorMessageKey('already_workspace_member')).toBe('members.errors.alreadyMember');
    expect(errorMessageKey('invitation_already_exists')).toBe('members.errors.alreadyInvited');
    expect(errorMessageKey('invitation_email_mismatch')).toBe('invitations.emailMismatch');
    expect(errorMessageKey('invitation_expired')).toBe('invitations.expired');
    expect(errorMessageKey('invalid_invitation')).toBe('invitations.invalid');
  });

  it('keeps matching EN/AR members and invitations keys', () => {
    expect(Object.keys(en.members).sort()).toEqual(Object.keys(ar.members).sort());
    expect(Object.keys(en.invitations).sort()).toEqual(Object.keys(ar.invitations).sort());
    expect(en.members.invite).toBeTruthy();
    expect(ar.members.invite).toBeTruthy();
    expect(en.invitations.guestBody).toBeTruthy();
    expect(ar.invitations.guestBody).toBeTruthy();
  });
});
