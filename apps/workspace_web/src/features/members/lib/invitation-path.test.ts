import { describe, expect, it } from 'vitest';
import {
  invitationAcceptPath,
  isInvitationAcceptPath,
  readInvitationToken,
} from './invitation-path';
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

describe('invitation query keys and errors', () => {
  it('scopes invitation keys by workspace', () => {
    expect(queryKeys.invitations('ws-a')).toEqual(['workspace', 'ws-a', 'invitations']);
    expect(queryKeys.invitations('ws-a')[1]).not.toBe(queryKeys.invitations('ws-b')[1]);
    expect(queryKeys.roles('ws-a')).toEqual(['workspace', 'ws-a', 'roles']);
    expect(queryKeys.roles('ws-a')[1]).not.toBe(queryKeys.roles('ws-b')[1]);
    expect(queryKeys.assignableRoles('ws-a')[1]).toBe('ws-a');
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
