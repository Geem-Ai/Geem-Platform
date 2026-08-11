import { type FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Helmet } from 'react-helmet-async';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import { InstructionsEditor } from '../components/InstructionsEditor';
import { useCreateExpert } from '../hooks/useExpertMutations';

export function CreateExpertPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [instructions, setInstructions] = useState('');

  const mutation = useCreateExpert();

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    mutation.mutate(
      {
        name: name.trim(),
        description: description.trim() || null,
        system_instructions: instructions.trim() || null,
      },
      {
        onSuccess: (expert) => {
          toast.success(t('experts.created'));
          void navigate(`/experts/${expert.id}`);
        },
        onError: (err: unknown) => {
          if (err instanceof ApiError) {
            toast.error(t(errorMessageKey(err.code)));
          } else {
            toast.error(t('errors.generic'));
          }
        },
      },
    );
  };

  return (
    <div className="p-6 md:p-8 w-full max-w-xl space-y-6 ms-auto me-auto">
      <Helmet>
        <title>
          {t('experts.createTitle')} · {t('app.name')}
        </title>
      </Helmet>

      <div>
        <h1 className="text-xl font-semibold tracking-tight">{t('experts.createTitle')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('experts.createDescription')}</p>
      </div>

      <Card>
        <form onSubmit={onSubmit}>
          <CardHeader>
            <CardTitle>{t('experts.createTitle')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="expert-name">{t('experts.name')}</Label>
              <Input
                id="expert-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t('experts.namePlaceholder')}
                maxLength={200}
                required
                disabled={mutation.isPending}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="expert-description">{t('experts.descriptionField')}</Label>
              <Textarea
                id="expert-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={t('experts.descriptionPlaceholder')}
                maxLength={2000}
                disabled={mutation.isPending}
              />
            </div>
            <InstructionsEditor
              value={instructions}
              onChange={setInstructions}
              disabled={mutation.isPending}
            />
          </CardContent>
          <CardFooter className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => void navigate('/experts')}
              disabled={mutation.isPending}
            >
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={!name.trim() || mutation.isPending}>
              {mutation.isPending ? t('experts.saving') : t('experts.create')}
            </Button>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
