import { type FormEvent, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
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
import { RagConfigFields } from '../components/RagConfigFields';
import { useExpert } from '../hooks/useExpert';
import { useUpdateExpert } from '../hooks/useExpertMutations';
import { parseRagConfig, serializeRagConfig } from '../lib/rag-config';

export function EditExpertPage() {
  const { t } = useTranslation();
  const { expertId } = useParams<{ expertId: string }>();
  const navigate = useNavigate();

  const expertQuery = useExpert(expertId);
  const expert = expertQuery.data;
  const mutation = useUpdateExpert(expertId ?? '');

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [instructions, setInstructions] = useState('');
  const [ragConfig, setRagConfig] = useState(parseRagConfig(null));

  useEffect(() => {
    if (!expert) return;

    // Platform experts cannot be edited here
    if (expert.ownership === 'platform') {
      void navigate(`/experts`);
      return;
    }

    setName(expert.name);
    setDescription(expert.description ?? '');
    setInstructions(expert.system_instructions ?? '');
    setRagConfig(parseRagConfig(expert.rag_config));
  }, [expert, navigate]);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    mutation.mutate(
      {
        name: name.trim(),
        description: description.trim() || null,
        system_instructions: instructions.trim() || null,
        rag_config: serializeRagConfig(ragConfig),
      },
      {
        onSuccess: () => {
          toast.success(t('experts.saved'));
          void navigate(`/experts/${expertId}`);
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

  if (expertQuery.isLoading) {
    return (
      <div className="p-8">
        <p className="text-sm text-muted-foreground">{t('shell.loading')}</p>
      </div>
    );
  }

  if (expertQuery.isError || !expert) {
    return (
      <div className="p-8">
        <p className="text-sm text-destructive">{t('errors.expertNotFound')}</p>
      </div>
    );
  }

  return (
    <div className="p-6 md:p-8 w-full max-w-xl space-y-6 ms-auto me-auto">
      <Helmet>
        <title>
          {t('experts.editTitle')} · {expert.name} · {t('app.name')}
        </title>
      </Helmet>

      <div>
        <h1 className="text-xl font-semibold tracking-tight">{t('experts.editTitle')}</h1>
      </div>

      <Card>
        <form onSubmit={onSubmit}>
          <CardHeader>
            <CardTitle>{expert.name}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="edit-name">{t('experts.name')}</Label>
              <Input
                id="edit-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t('experts.namePlaceholder')}
                maxLength={200}
                required
                disabled={mutation.isPending}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-description">{t('experts.descriptionField')}</Label>
              <Textarea
                id="edit-description"
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
              id="edit-instructions"
            />
            <RagConfigFields
              value={ragConfig}
              onChange={setRagConfig}
              disabled={mutation.isPending}
            />
          </CardContent>
          <CardFooter className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => void navigate(`/experts/${expertId}`)}
              disabled={mutation.isPending}
            >
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={!name.trim() || mutation.isPending}>
              {mutation.isPending ? t('experts.saving') : t('common.save')}
            </Button>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
