import type { TFunction } from 'i18next';
import type { ConversationExpertSummary, Expert } from '@/services/api/types';

type ExpertLike = Pick<Expert, 'name' | 'description' | 'knowledge_mode' | 'ownership'> &
  Partial<Pick<ConversationExpertSummary, 'knowledge_mode' | 'ownership'>>;

export function isGeemGeneralExpert(expert: {
  knowledge_mode?: string | null;
  ownership?: string | null;
}): boolean {
  return expert.knowledge_mode === 'general' && expert.ownership === 'platform';
}

/** Localized name/description for display; API values for non-general Experts. */
export function localizeExpertDisplay(
  expert: ExpertLike,
  t: TFunction,
): { name: string; description: string | null } {
  if (isGeemGeneralExpert(expert)) {
    return {
      name: t('experts.geemGeneral.name'),
      description: t('experts.geemGeneral.description'),
    };
  }
  return {
    name: expert.name,
    description: expert.description ?? null,
  };
}
