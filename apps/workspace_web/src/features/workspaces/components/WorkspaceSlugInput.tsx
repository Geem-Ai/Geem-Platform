import { Input, InputAddon, InputGroup } from '@/components/ui/input';
import { workspaceHostSuffix } from '@/features/workspaces/lib/hostname';
import { cn } from '@/lib/utils';

interface WorkspaceSlugInputProps {
  id: string;
  value: string;
  onChange?: (value: string) => void;
  disabled?: boolean;
  readOnly?: boolean;
  'data-testid'?: string;
}

export function WorkspaceSlugInput({
  id,
  value,
  onChange,
  disabled,
  readOnly,
  'data-testid': testId,
}: WorkspaceSlugInputProps) {
  const suffix = workspaceHostSuffix();
  const preview = `${value || 'workspace'}${suffix}`;

  return (
    <InputGroup dir="ltr" className="min-w-0" aria-label={preview}>
      <Input
        id={id}
        value={value}
        onChange={(e) => onChange?.(e.target.value.toLowerCase())}
        disabled={disabled}
        readOnly={readOnly}
        required={!readOnly}
        minLength={readOnly ? undefined : 3}
        maxLength={63}
        spellCheck={false}
        autoCapitalize="none"
        autoCorrect="off"
        dir="ltr"
        className="min-w-0 font-mono"
        data-testid={testId}
      />
      <InputAddon
        dir="ltr"
        className={cn(
          'font-mono text-muted-foreground whitespace-nowrap',
          (disabled || readOnly) && 'opacity-60',
        )}
        data-testid="workspace-slug-suffix"
      >
        {suffix}
      </InputAddon>
    </InputGroup>
  );
}
