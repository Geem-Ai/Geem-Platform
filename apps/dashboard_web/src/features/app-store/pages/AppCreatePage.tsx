import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { ArrowLeft } from 'lucide-react';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
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
import {
  createPlatformApp,
  fetchPlatformAppCategories,
  platformQueryKeys,
} from '@/services/api/platform';

export function AppCreatePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [slug, setSlug] = useState('');
  const [name, setName] = useState('');
  const [shortDescription, setShortDescription] = useState('');
  const [description, setDescription] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [billingType, setBillingType] = useState('free');
  const [iconUrl, setIconUrl] = useState('');
  const [connectorKey, setConnectorKey] = useState('');
  const [connectorKind, setConnectorKind] = useState('');
  const [isFeatured, setIsFeatured] = useState(false);
  const [sortOrder, setSortOrder] = useState('0');

  const categoriesQuery = useQuery({
    queryKey: platformQueryKeys.appCategories,
    queryFn: fetchPlatformAppCategories,
  });

  const mutation = useMutation({
    mutationFn: createPlatformApp,
    onSuccess: (app) => {
      toast.success(t('appStore.createSuccess'));
      navigate(`/app-store/${app.id}`);
    },
    onError: (error) => toast.error(getErrorMessage(error, t)),
  });

  const onSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!slug.trim() || !name.trim() || !shortDescription.trim() || !categoryId) return;
    mutation.mutate({
      slug: slug.trim().toLowerCase(),
      name: name.trim(),
      short_description: shortDescription.trim(),
      description: description.trim() || null,
      category_id: categoryId,
      billing_type: billingType,
      icon_url: iconUrl.trim() || null,
      connector_key: connectorKey.trim() || null,
      connector_kind: connectorKind.trim() || null,
      is_featured: isFeatured,
      sort_order: Number(sortOrder) || 0,
    });
  };

  return (
    <div className="mx-auto w-full max-w-3xl p-5 md:p-8" data-testid="app-create-page">
      <DocumentTitle title={t('appStore.createTitle')} />
      <Button variant="ghost" size="sm" asChild className="mb-4 -ms-2">
        <Link to="/app-store">
          <ArrowLeft className="size-4 rtl:rotate-180" aria-hidden />
          {t('appStore.backToList')}
        </Link>
      </Button>

      <form onSubmit={onSubmit}>
        <Card>
          <CardHeader>
            <CardTitle>{t('appStore.createTitle')}</CardTitle>
            <CardDescription>{t('appStore.createSubtitle')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="app-slug">{t('appStore.fields.slug')}</Label>
                <Input
                  id="app-slug"
                  value={slug}
                  onChange={(e) => setSlug(e.target.value)}
                  required
                  data-testid="app-create-slug"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="app-name">{t('appStore.fields.name')}</Label>
                <Input
                  id="app-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  data-testid="app-create-name"
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="app-short-description">{t('appStore.fields.shortDescription')}</Label>
              <Input
                id="app-short-description"
                value={shortDescription}
                onChange={(e) => setShortDescription(e.target.value)}
                required
                data-testid="app-create-short-description"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="app-description">{t('appStore.fields.description')}</Label>
              <Textarea
                id="app-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                data-testid="app-create-description"
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="app-category">{t('appStore.fields.category')}</Label>
                <select
                  id="app-category"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={categoryId}
                  onChange={(e) => setCategoryId(e.target.value)}
                  required
                  data-testid="app-create-category"
                >
                  <option value="">{t('appStore.selectCategory')}</option>
                  {(categoriesQuery.data?.items ?? [])
                    .filter((item) => item.is_active)
                    .map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.slug}
                      </option>
                    ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="app-billing-type">{t('appStore.fields.billingType')}</Label>
                <select
                  id="app-billing-type"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={billingType}
                  onChange={(e) => setBillingType(e.target.value)}
                  data-testid="app-create-billing-type"
                >
                  <option value="free">{t('appStore.billingType.free')}</option>
                  <option value="one_time">{t('appStore.billingType.one_time')}</option>
                  <option value="subscription">{t('appStore.billingType.subscription')}</option>
                </select>
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="app-icon">{t('appStore.fields.iconUrl')}</Label>
                <Input
                  id="app-icon"
                  value={iconUrl}
                  onChange={(e) => setIconUrl(e.target.value)}
                  placeholder="https://"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="app-sort-order">{t('appStore.fields.sortOrder')}</Label>
                <Input
                  id="app-sort-order"
                  type="number"
                  value={sortOrder}
                  onChange={(e) => setSortOrder(e.target.value)}
                />
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="app-connector-key">{t('appStore.fields.connectorKey')}</Label>
                <Input
                  id="app-connector-key"
                  value={connectorKey}
                  onChange={(e) => setConnectorKey(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="app-connector-kind">{t('appStore.fields.connectorKind')}</Label>
                <Input
                  id="app-connector-kind"
                  value={connectorKind}
                  onChange={(e) => setConnectorKind(e.target.value)}
                />
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={isFeatured}
                onChange={(e) => setIsFeatured(e.target.checked)}
              />
              {t('appStore.fields.featured')}
            </label>
          </CardContent>
          <CardFooter className="justify-end gap-2">
            <Button type="button" variant="outline" asChild>
              <Link to="/app-store">{t('common.cancel')}</Link>
            </Button>
            <Button
              type="submit"
              disabled={
                mutation.isPending ||
                !slug.trim() ||
                !name.trim() ||
                !shortDescription.trim() ||
                !categoryId
              }
              data-testid="app-create-submit"
            >
              {mutation.isPending ? t('common.working') : t('appStore.create')}
            </Button>
          </CardFooter>
        </Card>
      </form>
    </div>
  );
}
