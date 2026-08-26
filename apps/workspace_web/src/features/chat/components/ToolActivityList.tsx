import { CircleAlert, CircleCheck, LoaderCircle, Wrench } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/badge';
import type { ChatToolActivity } from '@/services/api/types';

export function ToolActivityList({ activities }: { activities: ChatToolActivity[] }) {
  const { t } = useTranslation();
  if (activities.length === 0) return null;
  return (
    <ul className="space-y-2 mb-3" data-testid="tool-activity-list">
      {activities.map((activity) => {
        const pending = activity.status === 'calling' || activity.status === 'approval_required';
        const failed = activity.status === 'failed' || activity.status === 'outcome_unknown';
        const Icon = pending ? LoaderCircle : failed ? CircleAlert : CircleCheck;
        return (
          <li key={activity.id} className="rounded-lg border border-border bg-background/70 px-3 py-2 text-xs flex items-start gap-2" data-testid="tool-activity" data-status={activity.status}>
            <Icon className={`mt-0.5 size-3.5 shrink-0 ${pending ? 'animate-spin text-primary' : failed ? 'text-destructive' : 'text-green-600'}`} aria-hidden />
            <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-1.5"><Wrench className="size-3" aria-hidden /><span className="font-medium truncate" dir="auto">{activity.tool_name}</span><Badge variant={failed ? 'destructive' : pending ? 'info' : 'success'} appearance="light" size="xs">{t(`chat.tools.status.${activity.status}`, { defaultValue: activity.status })}</Badge></div>{activity.connection_name ? <p className="text-muted-foreground mt-0.5 truncate" dir="auto">{activity.connection_name}</p> : null}{activity.status === 'outcome_unknown' ? <p className="text-destructive mt-1">{t('chat.tools.outcomeUnknown')}</p> : null}</div>
          </li>
        );
      })}
    </ul>
  );
}
