import type { ExpertKnowledgeItem } from '@/services/api/types';
import { isProcessingDocStatus, isProcessingExpertStatus } from './status';

export const POLL_INTERVAL_MS = 3000;

/** Returns true if any knowledge item is still processing/pending. */
export function shouldPollKnowledge(items: ExpertKnowledgeItem[]): boolean {
  return items.some((item) => isProcessingDocStatus(item.status));
}

/** Returns true if the expert status warrants continued polling. */
export function shouldPollExpert(status: string): boolean {
  return isProcessingExpertStatus(status);
}
