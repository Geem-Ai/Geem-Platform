import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { ArrowLeft } from 'lucide-react';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { RagConfigFields } from '@/features/experts/components/RagConfigFields';
import { RAG_CONFIG_DEFAULTS, serializeRagConfig } from '@/features/experts/lib/rag-config';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { getErrorMessage } from '@/services/api/errors';
import { createPlatformExpert } from '@/services/api/platform';

export function ExpertCreatePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [instructions, setInstructions] = useState('');
  const [iconUrl, setIconUrl] = useState('');
  const [ragConfig, setRagConfig] = useState(serializeRagConfig(RAG_CONFIG_DEFAULTS));

  const mutation = useMutation({
    mutationFn: createPlatformExpert,
    onSuccess: (expert) => {
      toast.success(t('experts.createSuccess'));
      navigate(`/experts/${expert.id}`);
    },
    onError: (error) => toast.error(getErrorMessage(error, t)),
  });

  const onSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return;
    mutation.mutate({
      name: name.trim(),
      description: description.trim() || null,
      system_instructions: instructions.trim() || null,
      icon_url: iconUrl.trim() || null,
      rag_config: ragConfig,
      visibility: 'platform_draft',
      availability_mode: 'selected_workspaces',
    });
  };

  return (
    <div className="mx-auto w-full max-w-3xl p-5 md:p-8" data-testid="expert-create-page">
      <DocumentTitle title={t('experts.createTitle')} />
      <Button variant="ghost" size="sm" asChild className="mb-4 -ms-2">
        <Link to="/experts">
          <ArrowLeft className="size-4 rtl:rotate-180" aria-hidden />
          {t('experts.backToList')}
        </Link>
      </Button>

      <form onSubmit={onSubmit}>
        <Card>
          <CardHeader>
            <CardTitle>{t('experts.createTitle')}</CardTitle>
            <CardDescription>{t('experts.createSubtitle')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="expert-name">{t('experts.fields.name')}</Label>
              <Input
                id="expert-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                data-testid="expert-create-name"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="expert-description">{t('experts.fields.description')}</Label>
              <Textarea
                id="expert-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                data-testid="expert-create-description"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="expert-icon">{t('experts.fields.iconUrl')}</Label>
              <Input
                id="expert-icon"
                value={iconUrl}
                onChange={(e) => setIconUrl(e.target.value)}
                placeholder="https://"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="expert-instructions">{t('experts.fields.instructions')}</Label>
              <Textarea
                id="expert-instructions"
                value={instructions}
                onChange={(e) => setInstructions(e.target.value)}
                className="min-h-40 font-mono text-xs"
                data-testid="expert-create-instructions"
              />
            </div>
            <div className="space-y-2">
              <Label>{t('experts.fields.ragConfig')}</Label>
              <RagConfigFields value={ragConfig} onChange={setRagConfig} />
            </div>
          </CardContent>
          <CardFooter className="justify-end gap-2">
            <Button type="button" variant="outline" asChild>
              <Link to="/experts">{t('common.cancel')}</Link>
            </Button>
            <Button type="submit" disabled={mutation.isPending || !name.trim()}>
              {mutation.isPending ? t('common.working') : t('experts.create')}
            </Button>
          </CardFooter>
        </Card>
      </form>
    </div>
  );
}
