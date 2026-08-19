import { Monitor, Moon, Sun } from 'lucide-react';
import { useTheme } from 'next-themes';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import type { AppLocale } from '@/lib/i18n';
import { cn } from '@/lib/utils';

type ThemeOption = 'light' | 'dark' | 'system';

const THEME_ORDER: ThemeOption[] = ['light', 'dark', 'system'];

function isThemeOption(value: string | undefined): value is ThemeOption {
  return value === 'light' || value === 'dark' || value === 'system';
}

function ThemeGlyph({ theme }: { theme: ThemeOption }) {
  if (theme === 'dark') return <Moon />;
  if (theme === 'system') return <Monitor />;
  return <Sun />;
}

function themeLabelKey(theme: ThemeOption): 'themeLight' | 'themeDark' | 'themeSystem' {
  if (theme === 'dark') return 'themeDark';
  if (theme === 'system') return 'themeSystem';
  return 'themeLight';
}

export function AuthChrome() {
  const { t, i18n } = useTranslation();
  const { theme, setTheme } = useTheme();
  const locale: AppLocale = i18n.language === 'en' ? 'en' : 'ar';
  const currentTheme: ThemeOption = isThemeOption(theme) ? theme : 'light';

  function cycleTheme() {
    const index = THEME_ORDER.indexOf(currentTheme);
    const next = THEME_ORDER[(index + 1) % THEME_ORDER.length];
    setTheme(next);
  }

  return (
    <div
      className="flex items-center justify-end gap-2"
      data-testid="auth-chrome"
    >
      <div
        role="group"
        aria-label={t('shell.language')}
        className="inline-flex rounded-md border border-input bg-background p-0.5 shadow-xs"
      >
        {(['ar', 'en'] as const).map((option) => (
          <button
            key={option}
            type="button"
            data-testid={`auth-language-${option}`}
            aria-pressed={locale === option}
            onClick={() => void i18n.changeLanguage(option)}
            className={cn(
              'h-7 rounded-[5px] px-2.5 text-xs font-medium transition-colors',
              locale === option
                ? 'bg-primary text-primary-foreground shadow-xs'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {t(option === 'ar' ? 'shell.languageAr' : 'shell.languageEn')}
          </button>
        ))}
      </div>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            variant="outline"
            mode="icon"
            size="sm"
            onClick={cycleTheme}
            aria-label={`${t('shell.theme')}: ${t(`shell.${themeLabelKey(currentTheme)}`)}`}
            data-testid="auth-theme-toggle"
          >
            <ThemeGlyph theme={currentTheme} />
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          {t(`shell.${themeLabelKey(currentTheme)}`)}
        </TooltipContent>
      </Tooltip>
    </div>
  );
}
