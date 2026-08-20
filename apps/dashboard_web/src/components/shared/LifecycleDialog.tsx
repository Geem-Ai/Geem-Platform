import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

type LifecycleDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  reasonRequired: boolean;
  confirmLabel: string;
  confirmVariant?: 'destructive' | 'primary';
  pending?: boolean;
  onConfirm: (reason: string) => void;
  testId: string;
};

export function LifecycleDialog({
  open,
  onOpenChange,
  title,
  description,
  reasonRequired,
  confirmLabel,
  confirmVariant = 'destructive',
  pending,
  onConfirm,
  testId,
}: LifecycleDialogProps) {
  const { t } = useTranslation();
  const [reason, setReason] = useState('');
  const trimmed = reason.trim();
  const canSubmit = !reasonRequired || trimmed.length > 0;

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setReason('');
        onOpenChange(next);
      }}
    >
      <AlertDialogContent data-testid={testId}>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <div className="space-y-2 py-1">
          <Label htmlFor={`${testId}-reason`}>
            {reasonRequired ? t('common.reasonRequired') : t('common.reasonOptional')}
          </Label>
          <Input
            id={`${testId}-reason`}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={500}
            data-testid={`${testId}-reason`}
            placeholder={t('common.reasonPlaceholder')}
          />
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={pending}>{t('common.cancel')}</AlertDialogCancel>
          <Button
            variant={confirmVariant}
            disabled={!canSubmit || pending}
            onClick={() => onConfirm(trimmed)}
            data-testid={`${testId}-confirm`}
          >
            {pending ? t('common.working') : confirmLabel}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
