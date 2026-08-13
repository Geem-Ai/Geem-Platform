/** Keep pagination placeholders; never reuse another Workspace's data. */
export function keepPreviousIfSameWorkspace<T>(
  workspaceId: string,
  previous: T | undefined,
  previousQuery: { queryKey: readonly unknown[] } | undefined,
): T | undefined {
  if (!previousQuery || previousQuery.queryKey[1] !== workspaceId) {
    return undefined;
  }
  return previous;
}
